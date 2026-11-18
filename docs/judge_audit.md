# Judge audit

Chạy (trong `src/`, judge REPLAY, không cần key):

```bash
python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 10      # exit 0, PASS floors
python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 21   # exit 1, FAIL floors
```

Lớp dương = `FAIL` (việc của judge là **tìm** lỗi). Specificity = tn / (tn + fp).

| Tiêu chí | n | κ | Precision | Recall | Confusion (tp/fp/fn/tn) | Fail rate quan sát → Rogan-Gladen | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | 24 / 4 / 6 / 66 (spec 0.943) | 0.28 → 0.30 | **Đạt** | **dùng** (không blocking, xem kết luận) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | 9 / 0 / 21 / 70 (spec 1.000) | 0.09 → 0.30 | **Không đạt** (κ, R) | **loại**, không dùng làm gate |

Tỉ lệ lỗi thật theo nhãn người là 30/100 ở cả hai tập. Rogan-Gladen kéo tỉ lệ quan sát về đúng 0.30, nhưng với helpful thì chỉ đúng ở mức **tổng thể**: judge vẫn không biết **reply nào** sai, nên không dùng được để chặn từng PR.

## ≥5 case audit thủ công

### tone_ok (10/10 bất đồng)
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người | Xưng "em" + "nha" quá suồng sã với khách khiếu nại. Rubric thêm: *xưng hô phải là "LogiX" / "anh/chị"; "em", "bạn", "nha", "nhé" ⇒ FAIL*. |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ … rồi nha." | PASS | FAIL | Người | Cùng lỗi xưng hô ("bạn ơi"). Judge coi thân mật là thân thiện. Cùng mục rubric #1, thêm 1 ví dụ FAIL. |
| 3 | H-029 "Dạ, vui lòng chờ. … không cần nhắn thêm." | PASS | FAIL | Người | Giọng ra lệnh; judge chỉ bắt từ khoá lịch sự "Dạ, vui lòng". Rubric: *chấm cả câu, từ khoá lịch sự không bù cho câu ra lệnh / gạt khách*. |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì "thiếu xin lỗi". Rubric: *xin lỗi không bắt buộc khi kết quả đã rõ; ngắn mà đủ ý ⇒ PASS*. Tránh thiên vị độ dài. |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ …" | FAIL | PASS | Người | CS LogiX cho phép từ "refund". Rubric: *danh sách từ tiếng Anh được phép: refund, ship, voucher*. |
| 6 | H-063 "… đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | Người | Hứa "sẽ hoàn thêm" ngoài kết quả hệ thống. Đây là lỗi **nội dung**, không phải giọng: chuyển sang grader code (so reply với ledger, FM-08) thay vì nhồi vào rubric tone. |
| 7 | H-070 "… đã hoàn 90.000đ cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | Emoji cười trong ngữ cảnh khiếu nại. Rubric: *không dùng emoji*; có thể bắt bằng regex trước khi gọi judge. |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | **Judge** | Ghi chú gốc: nhãn người sai (đọc nhầm ticket). Hành động: **sửa nhãn người → FAIL** trong lần gán nhãn tới (không sửa file replay công khai vì test tham chiếu dùng nó), và cho 2 người gán nhãn độc lập case này. |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ …" | FAIL | PASS | Người (tạm) | Lặp "Dạ" do lỗi gõ. Rubric: *lỗi gõ nhỏ không đổi nghĩa ⇒ PASS*; nếu CS muốn chặt hơn thì ghi rõ thành quy tắc, đừng để mỗi bên tự hiểu. |
| 10 | H-094 "Da, LogiX da hoan 40.000đ … xin loi vi su bat tien." | PASS | FAIL | Người | Mất dấu tiếng Việt (dịch máy). Rubric: *reply tiếng Việt phải có dấu*; bắt được bằng code (tỉ lệ ký tự có dấu). |

### helpful (21/21 bất đồng đều là judge PASS, người FAIL; audit đại diện)
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 11 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (ledger 40.000đ) | PASS | FAIL | Người | Judge **không nhìn thấy ledger**, nên không thể biết số tiền sai. 18/21 lỗi bị bỏ sót là "sai tiền". Không sửa được bằng rubric: chấm bằng code (FM-08). |
| 12 | HL-016 reply dài, xin lỗi 2 lần, "đã hoàn 55.000đ cho đơn O-404" (ledger 35.000đ) | PASS | FAIL | Người | Ngoài sai tiền còn thấy **thiên vị độ dài / xin lỗi**: 13/18 reply sai tiền bị bỏ sót là reply dài nhiều câu xin lỗi. Rubric: *xin lỗi và độ dài không cộng điểm helpful*. |
| 13 | HL-043 reply dài, "đã hoàn 35.000đ cho đơn O-202" (ledger 20.000đ) | PASS | FAIL | Người | Như #12. Liên hệ trace thật: `seeded_regression C-014@11` reply "120.000đ" khi ledger 90.000. Đây chính là FM-08. |
| 14 | HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | Sai xưng hô và không nói kết quả cụ thể (bao nhiêu tiền). Rubric: *helpful = nói rõ kết quả (hoàn bao nhiêu / vì sao từ chối / cần thông tin gì)*. Cũng gặp ở HL-091, HL-097. |
| 15 | HL-087 "Dạ, LogiX đã hoàn 60.000đ cho đơn O-202 ạ." (ledger 90.000đ) | PASS | FAIL | Người | Sai tiền theo chiều **ít hơn** ledger: vẫn sai, khách sẽ khiếu nại lại. Chỉ grader code so với ledger bắt được. |

Các loại lỗi helpful mà judge **bắt được** (tp = 9): giọng cụt (4), không hỏi lại mã đơn (3), trả lời lạc đề (2). Đều là lỗi nhìn thấy được trong chữ. Các loại judge **bỏ sót** (fn = 21): sai tiền (18), sai xưng hô (3).

## Kết luận

- **helpful bị loại.** Recall 0.30 < 0.70 và κ 0.375 < 0.60: judge bỏ sót 21/30 reply hỏng (fn = 21). Precision 1.0 vô nghĩa ở đây: judge chỉ báo FAIL khi lỗi hiển nhiên trong chữ. 18/21 lỗi bị bỏ sót là **sai số tiền so với ledger**, thứ judge không có dữ liệu để biết. Dùng judge này làm gate thì PR làm agent nói sai tiền vẫn xanh. Thay bằng **grader code so số tiền trong reply với ledger** (metric FM-08, M3). Quy tắc: tiền và approval luôn chấm bằng code.
- **tone_ok dùng được** (κ 0.757, P 0.857, R 0.80 đều qua FLOORS), nhưng chỉ cho tiêu chí giọng văn, và chỉ là metric theo dõi/cảnh báo, không chặn release một mình: 6/30 reply sai giọng vẫn lọt (fn = 6), chủ yếu do xưng hô suồng sã. Áp dụng sửa rubric ở #1–#10 rồi calibrate lại trên tập nhãn mới.
- **Rogan-Gladen** chỉ dùng để báo cáo tỉ lệ lỗi tổng (tone: 0.28 → 0.30), không thay cho việc chấm từng trial.
- **Rủi ro còn lại:** judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng mỗi tiêu chí, cùng phân phối với rubric hiện tại); sau khi sửa rubric cần nhãn người mới làm held-out thật. Có ít nhất 1 nhãn người sai (H-081), nên cần 2 người gán nhãn độc lập và đo κ giữa người với người trước khi tin κ người–judge.
