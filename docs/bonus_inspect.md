# Bonus: port 3 grader sang Inspect AI và so khớp

Ba grader code của Lab 9 được viết lại thành scorer của **Inspect AI 0.3.291**, chạy trên cùng các trial (`item@seed`) với harness pydantic-evals của `lab9.eval`, rồi so verdict **từng trial**. Không cần API key: model của Inspect là `mockllm/model` và không bao giờ được gọi.

## Chạy

```bash
cd src
python -m pip install -r requirements-bonus.txt              # inspect-ai==0.3.291 (tách khỏi requirements của CI)
python -m bonus.inspect_port --shape seeded_regression        # chỉ chạy bản Inspect, in metric
python -m bonus.compare --with-mutants                        # v1: so khớp pydantic-evals vs Inspect
python -m bonus.compare --spec config/metric_spec_v2.yaml --with-mutants   # v2 (adversarial pack)
python -m pytest -q -m student -o addopts= tests/test_bonus_inspect.py
inspect view --log-dir bonus/logs                             # xem log Inspect (thư mục bị .gitignore)
```

`bonus.compare` exit 0 chỉ khi mọi verdict và mọi metric tổng trùng nhau. Test bonus tự skip nếu máy không cài `inspect-ai`, nên CI chính không bị ảnh hưởng.

## Thiết kế

| Thành phần | pydantic-evals (`lab9`) | Inspect AI (`bonus.inspect_port`) |
|---|---|---|
| Đơn vị | `Case` = item@seed | `Sample(id="E-001@11")`, trial (ledger, reply, nhãn) trong `metadata` |
| Chạy agent | task `run_one` trong `Dataset.evaluate_sync` | `collect_trials` dùng lại `lab9.eval.make_task` (cùng store SQLite mới, cùng world) |
| Output | Trial dict | Solver `replay_agent_reply` đặt reply thật của agent vào `state.output`; không gọi model |
| `approval_bypass` | `ApprovalBypass` | scorer `approval_bypass`, metric `count()` tự viết (an toàn = đếm, không lấy trung bình) |
| `refund_amount_correct` | `RefundAmountCorrect` | scorer `refund_amount_correct`, metric `mean()` |
| `reply_matches_ledger` (FM-08) | `ReplyMatchesLedger`, đọc event `reply` | scorer đọc `state.output.completion`, regex đọc tiền **viết lại độc lập** (`money_in`) |

Scorer được viết lại từ định nghĩa trong `docs/failure_taxonomy.md`, không import class nào từ `lab9.graders`; nếu import thì "khớp" chỉ là so một hàm với chính nó.

## Kết quả

| Eval set | Shape | Trial | Verdict so khớp |
|---|---|---|---|
| v1 (14 item × 5 seed) | 6 shape công khai + 5 probe | 11 × 70 | **2310 / 2310** |
| v2 (28 item × 5 seed) | 6 shape công khai + 5 probe | 11 × 140 | **4620 / 4620** |

Metric tổng (pydantic-evals / Inspect), v1:

| Shape | `approval_bypass` | `refund_amount_correct` | `reply_matches_ledger` |
|---|---|---|---|
| swarm | 0 / 0 | 0.9857 / 0.9857 | 1.0 / 1.0 |
| fixed, honest_refactor | 0 / 0 | 1.0 / 1.0 | 1.0 / 1.0 |
| seeded_regression | 0 / 0 | 0.8571 / 0.8571 | 0.7857 / 0.7857 |
| slice_regression | 0 / 0 | 0.9571 / 0.9571 | 1.0 / 1.0 |
| flaky_regression | 0 / 0 | 0.9429 / 0.9429 | 1.0 / 1.0 |
| probe_sibling_refund | **20 / 20** | 0.7143 / 0.7143 | 1.0 / 1.0 |
| probe_misreport | 0 / 0 | 1.0 / 1.0 | **0.8571 / 0.8571** |
| probe_ignore_denied | 0 / 0 | 1.0 / 1.0 | **0.8571 / 0.8571** |
| probe_round_down | 0 / 0 | **0.7143 / 0.7143** | 1.0 / 1.0 |
| probe_paraphrase | 0 / 0 | 1.0 / 1.0 | 1.0 / 1.0 |

**Vì sao có probe:** không variant công khai nào làm `approval_bypass` > 0, nên "khớp 0 = 0" không chứng minh gì. Các probe là shape một lỗi dựng từ công tắc có sẵn trong `lab9/variant_agent.py`, chỉ đăng ký trong bộ nhớ (như `lab9.variants.register`), không sửa file variant nào; mỗi probe buộc một grader phải bắn thật. `probe_paraphrase` kiểm tra hai regex đọc được câu reply diễn đạt khác.

## Phát hiện khi port

1. **Hai cách đọc số tiền khớp trên mọi reply agent thật sinh ra**, nhưng lệch trên chuỗi dị dạng mà agent hiện chưa sinh:

   | Reply | `lab9.graders.reply_amounts` | `bonus.money_in` |
   |---|---|---|
   | `35.00đ` | 0 | 3500 |
   | `35.000.đ` | 0 | 35000 |
   | `x35.000đ` | 35000 | 0 |
   | `35 000đ` (dấu cách ngăn nghìn) | 0 | 0 (cả hai sai) |

   Grader FM-08 của gate phụ thuộc định dạng số tiền trong reply. Nếu agent (hoặc LLM thật) đổi cách viết số, grader có thể đọc sai và chặn nhầm hoặc cho lọt. Nên chuẩn hoá cách agent in tiền, hoặc cho grader đọc số tiền có cấu trúc thay vì regex trên văn bản.
2. **Một lỗi của chính harness so khớp, đã sửa:** bản đầu gọi `run_eval` trước `variants.register()`. Khi shape đầu tiên trong tiến trình là variant, Lab 8 không biết shape đó, mọi trial thành lỗi (ledger rỗng, không có reply) và pydantic-evals cho `refund_amount_correct` 0.5 thay vì 0.8571; lần chạy đầu tiên "khớp" chỉ vì `swarm` (shape có sẵn) chạy trước. Bản sửa đăng ký variant trước và **từ chối so khớp nếu có trial không chạy được**, vì hai harness đồng ý trên trial lỗi thì không chứng minh được gì.
3. **Khác biệt mô hình giữa hai framework:** Inspect coi đầu ra là "output của model", nên reply của agent được đặt vào `state.output` qua solver replay; pydantic-evals coi cả Trial là output của task. Các tín hiệu nằm ngoài văn bản (ledger, dòng ledger lạ) phải đi qua `metadata` của Sample. Metric an toàn dạng đếm phải tự viết (`count()`), vì Inspect chỉ có sẵn các metric trung bình và tỉ lệ.
