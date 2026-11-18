# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case: `seeded_regression C-008@11` (FM-08 misreport)

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-008 --seed 11
python -m lab9.trace_case --shape fixed --claim C-008 --seed 11
```

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-008@11` (item E-008), run ID `E-seeded_regression-20261118-a05d`, eval set `a05d3255ecd1`; baseline `E-swarm-20261118-a05d` |
| Triệu chứng | `reply_matches_ledger` = False ("reply says 35000 but ledger holds 20000"). Reply nói **"Dạ, LogiX đã hoàn 35.000đ cho đơn O-808."**, ledger ghi `refund_vnd=20000`. Grader Lab 8 (`pass_rate`) **PASS** và `refund_amount_correct` cũng đúng (20.000 = nhãn), nên nếu chỉ có các grader cũ thì trial này "xanh" |
| Bước sai đầu tiên | Event 5 `reply` `{"text": "Dạ, LogiX đã hoàn 35.000đ cho đơn O-808."}` |
| Vì sao là bước *đầu tiên* | Event 2 `investigator` đọc đơn O-808 đúng (trễ 4 ngày, phí ship 35.000). Event 3 `quote {"amount_vnd": 35000, "reason": "entitled", "clause_ids": ["SHIP-LATE-03"]}` đúng chính sách. Event 4 `refund_history {"refund_count": 0, "refunded_vnd": 0}` chỉ là lệnh đọc; không có event `proposal`, tức agent không tự trừ và gửi đúng quote 35.000 cho host. Host ghi `min(quote, approved_vnd)` = 20.000 vì approval A-008 chỉ duyệt 20.000: ledger đúng nhãn. Sai đầu tiên là reply báo số agent đề xuất thay vì số host đã ghi |
| Failure mode | **FM-08** misreport (reply nói số tiền khác ledger), xem `docs/failure_taxonomy.md` |
| Đối chứng | `fixed C-008@11`: event 1–3 giống hệt; event 4 là `reply` **"Dạ, LogiX đã hoàn 20.000đ cho đơn O-808."**, đúng số host ghi. Không có event `refund_history` |
| Regression test | `tests/test_lab9_trace_case.py`: `test_lab9_trace_case_c008_misreport_is_caught` (assert reply chứa 35.000đ, ledger 20.000, Lab 8 PASS, `ReplyMatchesLedger` = False) và `test_lab9_trace_case_c008_fixed_reports_the_ledger` (`fixed` → `ReplyMatchesLedger` = True). Cả hai chạy trong CI (`-m student -k lab9`), đã thấy fail đúng trên variant lỗi và pass trên `fixed`. Ở mức eval set: item E-008 có `failure_modes` chứa FM-08 và `provenance.from_trace = "seeded_regression C-008@11"`; metric `reply_matches_ledger` (min 1.0, blocking) đưa nó vào gate |
| Chưa chắc chắn | Trace không cho biết *vì sao* reply lấy số đề xuất: trong `seeded_regression` công tắc `pre_deducted` vừa trừ trước vừa đổi số báo lại, nên trên claim không có lần hoàn trước (C-008) chỉ còn lộ triệu chứng ở reply. Grader trích số tiền bằng regex (`35.000đ`, `35000 VND` …); reply viết số bằng chữ ("ba mươi lăm nghìn") sẽ bị đọc thành 0. Trace của `swarm` không có event `reply` nên metric này không kiểm được reply của baseline |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
