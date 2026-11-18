"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]

    # 1. Metric values must be real numbers: NaN compares False with every threshold.
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v} (not a finite number)")
        elif v is not None and not isinstance(v, (int, float)):
            problems.append(f"metric {k} is {v!r} (not a number)")

    # 2. Evaluator failures: a crashed grader is missing evidence, even on a green run.
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s), first: {pr['evaluator_failures'][0]}")

    # 3. Row coverage: full item x seed grid, no duplicates, same grid and manifest as the baseline.
    rows, brows = pr.get("rows") or [], base.get("rows") or []
    man, bman = pr.get("manifest") or {}, base.get("manifest") or {}
    want = (man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want:
        problems.append(f"{len(rows)} rows, manifest says {man.get('items')} items x {len(man.get('seeds') or [])} seeds = {want}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dups = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dups:
        problems.append(f"duplicated (item, seed) rows: {', '.join(f'{i}@{s}' for i, s in dups[:5])}")
    if len({k[0] for k in keys}) != man.get("items"):
        problems.append(f"{len({k[0] for k in keys})} distinct items in rows, manifest says {man.get('items')}")
    if sorted(map(str, man.get("seeds") or [])) != sorted({str(k[1]) for k in keys}):
        problems.append(f"manifest seeds {man.get('seeds')} differ from the seeds in rows")
    for field in ("items", "seeds"):
        if man.get(field) != bman.get(field):
            problems.append(f"manifest {field} {man.get(field)} differs from the baseline's {bman.get(field)}")
    pk, bk = set(keys), {(r.get("item_id"), r.get("seed")) for r in brows}
    if pk != bk:
        miss, extra = sorted(bk - pk, key=str), sorted(pk - bk, key=str)
        problems.append(f"(item, seed) set differs from the baseline: {len(miss)} missing "
                        f"{[f'{i}@{s}' for i, s in miss[:5]]}, {len(extra)} extra {[f'{i}@{s}' for i, s in extra[:5]]}")

    # 4. Every graded metric must be a real verdict on every row (None = crashed grader dropped from the mean).
    for m in graded:
        bad = [f"{r.get('item_id')}@{r.get('seed')}" for r in rows if not isinstance(r.get(m), bool)]
        if bad:
            problems.append(f"{len(bad)} row(s) without a {m} verdict (None/missing), first: {bad[:3]}")

    # 5. Reported metrics must be what the rows say (a hand-edited headline number fools the floors).
    problems += _metrics_match_rows(pr, graded, spec)

    # 6. Slice tags come from the eval set, not from the PR: relabelling hides a slice regression.
    btags = {r.get("item_id"): sorted(r.get("slices") or []) for r in brows}
    moved = sorted({r.get("item_id") for r in rows
                    if r.get("item_id") in btags and sorted(r.get("slices") or []) != btags[r.get("item_id")]}, key=str)
    if moved:
        problems.append(f"slice tags differ from the baseline's for {', '.join(moved[:5])}")

    # 7. Ratchet: the spec may only get stricter while the eval set stays the same.
    if base_spec is not None:
        problems += _ratchet(spec, base_spec)
    return problems


def _metrics_match_rows(pr: dict, graded: list[str], spec: dict) -> list[str]:
    rows = pr.get("rows") or []
    if not rows or any(not isinstance(r.get(m), bool) for r in rows for m in graded):
        return []                                  # already reported above; recomputing would mislead
    have_cost = all("cost" in r for r in rows)
    ids = [m for m in graded if m in rows[0]]
    redo = aggregate([r if have_cost else {**r, "cost": 0.0} for r in rows], ids,
                     k_values=spec.get("pass_k", []))
    out = []
    for k, v in (pr.get("metrics") or {}).items():
        if k not in redo or (k == "cost_per_success" and not have_cost):
            continue
        r = redo[k]
        if isinstance(v, (int, float)) and isinstance(r, (int, float)) and math.isfinite(v):
            if abs(v - r) > 1e-3:
                out.append(f"metric {k} = {v} but the rows give {r}")
        elif (v is None) != (r is None):
            out.append(f"metric {k} = {v} but the rows give {r}")
    return out


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    """Same eval set => thresholds may only tighten. A bumped version label on the same eval-set file
    is not a new eval set, so it does not reset the ratchet."""
    same = (spec.get("eval_set_version") == base_spec.get("eval_set_version")
            or (spec.get("eval_set") and spec.get("eval_set") == base_spec.get("eval_set")))
    if not same:
        return []
    out: list[str] = []

    def tighter(where: str, new: dict, old: dict) -> None:
        if old.get("blocking") and not new.get("blocking"):
            out.append(f"RATCHET {where}: blocking -> non-blocking")
        nt, ot = new.get("threshold", new), old.get("threshold", old)
        for key in ("min",):
            if key in ot and (key not in nt or nt[key] < ot[key]):
                out.append(f"RATCHET {where}: {key} {ot[key]} -> {nt.get(key)}")
        for key in ("max", "max_increase"):
            if key in ot and (key not in nt or nt[key] > ot[key]):
                out.append(f"RATCHET {where}: {key} {ot[key]} -> {nt.get(key)}")
        if ot.get("no_significant_drop") and not nt.get("no_significant_drop"):
            out.append(f"RATCHET {where}: no_significant_drop dropped")

    new_m = {m["id"]: m for m in spec.get("metrics", [])}
    for m in base_spec.get("metrics", []):
        if m["id"] not in new_m:
            out.append(f"RATCHET metric {m['id']} removed")
        else:
            tighter(f"metric {m['id']}", new_m[m["id"]], m)
    new_s = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for s in base_spec.get("slices") or []:
        key = (s["name"], s["metric"])
        if key not in new_s:
            out.append(f"RATCHET slice {key[0]}/{key[1]} removed")
        else:
            tighter(f"slice {key[0]}/{key[1]}", new_s[key], s)
    if sorted(spec.get("seeds") or []) != sorted(base_spec.get("seeds") or []):
        out.append(f"RATCHET seeds {base_spec.get('seeds')} -> {spec.get('seeds')}")
    nb, ob = spec.get("bootstrap") or {}, base_spec.get("bootstrap") or {}
    if nb.get("confidence", 0.95) > ob.get("confidence", 0.95):
        out.append(f"RATCHET bootstrap confidence {ob.get('confidence')} -> {nb.get('confidence')} (wider CI)")
    for key in ("rng", "n_resamples", "method"):
        if key in ob and nb.get(key) != ob.get(key):
            out.append(f"RATCHET bootstrap {key} {ob.get(key)} -> {nb.get(key)}")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            # An empty slice proves nothing; a slice that vanished from the PR is a gate bypass.
            verdict = "missing"
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in sl and val < sl["min"]:
                verdict = "fail"
            if sl.get("no_significant_drop"):
                keys = sorted(set(a) & set(b))
                if keys:
                    d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                       n_resamples=bs.get("n_resamples", 1000),
                                                       rng=bs.get("rng", 2027))
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                    if hi < 0:
                        verdict = "fail"
                else:
                    verdict, note = "missing", "no items shared with the baseline"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        th = {k: sl[k] for k in ("min", "no_significant_drop") if k in sl}
        lines.append(f"  {sid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}  (n={len(a)} items)")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
