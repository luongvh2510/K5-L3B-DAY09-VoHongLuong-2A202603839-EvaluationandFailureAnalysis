"""Bonus: compare the pydantic-evals graders (lab9.eval) with their Inspect AI ports, trial by trial.

    python -m bonus.compare                                   # v1 spec, all public shapes
    python -m bonus.compare --spec config/metric_spec_v2.yaml # v2 (adversarial pack)

Both harnesses run the same shape on the same item@seed grid (MockLLM is deterministic per seed),
so every trial must get the same verdict from both. Exit 0 = every verdict and every aggregate agrees.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from bonus.inspect_port import SCORERS, collect_trials, run_inspect
from lab9 import variants
from lab9.eval import SPEC, load_spec, run_eval

SHAPES = ["swarm", "fixed", "honest_refactor", "seeded_regression", "slice_regression", "flaky_regression"]
# The public variants never trip approval_bypass, so agreement on it would be trivially 0 == 0.
# These single-bug shapes (switches already in lab9.variant_agent, registered in memory only, the
# same way lab9.variants.register does) make each ported grader fire for real.
MUTANTS = {
    "probe_sibling_refund": {"no_override", "sibling_refund"},   # FM-07 -> approval_bypass (foreign rows)
    "probe_misreport": {"no_override", "misreport"},             # FM-08 -> reply_matches_ledger
    "probe_ignore_denied": {"no_override", "ignore_denied"},     # FM-02 -> reply says money, ledger 0
    "probe_round_down": {"no_override", "round_down"},           # FM-04 -> refund_amount_correct
    "probe_paraphrase": {"no_override", "paraphrase"},           # different reply wording, same money
}


def register_mutants() -> list[str]:
    from lab8.shapes import SHAPES as REGISTRY
    from lab9.variant_agent import make_shape

    for name, bugs in MUTANTS.items():
        REGISTRY.setdefault(name, make_shape(name, frozenset(bugs)))
    return list(MUTANTS)


def agg(metric: str, vals: list[bool]) -> float:
    return float(sum(vals)) if metric == "approval_bypass" else round(sum(vals) / len(vals), 4)


def compare(shape: str, spec: dict) -> tuple[int, int, list[str], dict[str, tuple[float, float]]]:
    variants.register()       # variants live in lab8.shapes.SHAPES only after this (lab9.eval.main does it too)
    rep = run_eval(shape, spec)                                   # pydantic-evals harness
    pyd = {f"{r['item_id']}@{r['seed']}": r for r in rep["rows"]}
    trials = collect_trials(shape, spec)
    # Two harnesses "agreeing" on crashed trials (empty ledger, no reply) proves nothing: refuse.
    errors = [f"{t['item_id']}@{t['seed']}: {t['error']}" for t in trials if t.get("error")]
    if errors:
        raise RuntimeError(f"{shape}: {len(errors)} trial(s) did not run, first: {errors[0]}")
    ins = run_inspect(shape, trials)                              # Inspect AI harness
    diffs, n = [], 0
    if set(pyd) != set(ins):
        diffs.append(f"sample sets differ: {sorted(set(pyd) ^ set(ins))[:5]}")
    for key in sorted(set(pyd) & set(ins)):
        for m in SCORERS:
            n += 1
            if bool(pyd[key][m]) != ins[key][m]:
                diffs.append(f"{key} {m}: pydantic-evals={pyd[key][m]} inspect={ins[key][m]}")
    aggs = {m: (agg(m, [bool(r[m]) for r in pyd.values()]), agg(m, [r[m] for r in ins.values()]))
            for m in SCORERS}
    return n, len(pyd), diffs, aggs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bonus.compare")
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--shapes", default=",".join(SHAPES))
    ap.add_argument("--with-mutants", action="store_true", help="also compare on single-bug probe shapes")
    a = ap.parse_args(argv)
    spec = load_spec(Path(a.spec))
    shapes = a.shapes.split(",") + (register_mutants() if a.with_mutants else [])
    print(f"spec {a.spec} · eval set {spec['eval_set_version']} · seeds {spec['seeds']}")
    print(f"{'shape':<18} {'trials':>6} {'verdicts':>8} {'agree':>6}  "
          + "  ".join(f"{m} (pydantic / inspect)" for m in SCORERS))
    total, bad = 0, 0
    for shape in shapes:
        n, trials, diffs, aggs = compare(shape, spec)
        total, bad = total + n, bad + len(diffs)
        cells = "  ".join(f"{aggs[m][0]:>8} / {aggs[m][1]:<8}{'' if aggs[m][0] == aggs[m][1] else ' !'}" for m in SCORERS)
        print(f"{shape:<18} {trials:>6} {n:>8} {n - len(diffs):>6}  {cells}")
        for d in diffs[:10]:
            print(f"    DIFF {d}")
    print(f"{total - bad}/{total} verdicts agree" + ("" if bad else " — the Inspect AI port matches the pydantic-evals graders"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
