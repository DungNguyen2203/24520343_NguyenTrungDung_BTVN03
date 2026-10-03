# Kết quả đánh giá tự động · BTVN#3

Sinh bởi `python danh_gia.py`. Mỗi dòng là một lượt chạy thật, chỉ số lấy từ lớp harness.

| Tình huống | Mẫu | Vòng model | Lần gọi tool | Token ước lượng | Lý do dừng | Đạt tiêu chí | Bàn giao |
|---|---|---:|---:|---:|---|---|---|
| chuan | react | 6 | 5 | 25.500 | DAT_MUC_TIEU | CÓ | không |
| chuan | plan | 2 | 5 | 6.500 | DAT_MUC_TIEU | CÓ | không |
| chuan | lai | 4 | 5 | 15.000 | DAT_MUC_TIEU | CÓ | không |
| duyet | react | 3 | 2 | 10.500 | CAN_NGUOI · giá 1.950.000đ vượt hạn mức tự quyết 1.500.000đ và vé không hoàn được | không | có |
| duyet | plan | 1 | 2 | 3.000 | CAN_NGUOI · giá 1.950.000đ vượt hạn mức tự quyết 1.500.000đ và vé không hoàn được | không | có |
| duyet | lai | 2 | 2 | 6.500 | CAN_NGUOI · giá 1.950.000đ vượt hạn mức tự quyết 1.500.000đ và vé không hoàn được | không | có |
| lap | react | 4 | 3 | 15.000 | LOOP · 'search_flights' gọi 2 lần với cùng tham số trong 6 vòng gần nhất | không | có |
| lap | plan | 1 | 2 | 3.000 | KE_HOACH_VO_HIEU · thực thi hết kế hoạch nhưng tiêu chí chưa đạt; mẫu này không lập lại kế hoạch | không | có |
| lap | lai | 2 | 1 | 6.500 | CHUA_DAT_TIEU_CHI · model chốt câu trả lời nhưng tiêu chí code chưa đạt | không | có |
| ngan-sach | react | 8 | 7 | 38.000 | NGAN_SACH · chạm trần 8 vòng model | không | có |
| ngan-sach | plan | 1 | 11 | 3.000 | KE_HOACH_VO_HIEU · thực thi hết kế hoạch nhưng tiêu chí chưa đạt; mẫu này không lập lại kế hoạch | không | có |
| ngan-sach | lai | 7 | 11 | 31.500 | CHUA_DAT_TIEU_CHI · model chốt câu trả lời nhưng tiêu chí code chưa đạt | không | có |

## Tổng hợp theo mẫu

| Mẫu | Tổng vòng | Tổng tool | Tổng token | Lượt đạt tiêu chí | Lượt có bàn giao |
|---|---:|---:|---:|---:|---:|
| react | 21 | 17 | 89.000 | 1/4 | 3/4 |
| plan | 5 | 20 | 15.500 | 1/4 | 3/4 |
| lai | 15 | 19 | 59.500 | 1/4 | 3/4 |
