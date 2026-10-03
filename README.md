# BÁO CÁO BTVN#3 · Dựng agent đặt vé bằng LangChain

**Môn:** SE373 · Agentic AI Engineering · Buổi 03
**Họ tên · MSSV:** Nguyễn Trung Dũng · 24520343
**Nội dung:** Tìm hiểu LangChain, LangGraph → tạo tool mockup → viết lớp harness → cài đặt 3 mẫu thiết kế (ReAct, Plan-then-Execute, Lai) → đánh giá hiệu quả.

---

## 1. Tóm tắt yêu cầu và cách đáp ứng

| Yêu cầu của BTVN | Cách đáp ứng | Nơi xem |
|---|---|---|
| 01 · Đủ các lớp harness | Ràng buộc là dữ liệu (`RangBuoc`), tiêu chí hoàn thành kiểm bằng code (`kiem_tieu_chi`), kiểm quyền (`kiem_quyen`), bàn giao (`ban_giao`) | `lib/harness.py` |
| 01 · Tool mockup | 5 tool đặt vé, observation có cấu trúc rõ (status + dữ liệu + hint) | `lib/tools_datve.py` |
| 02 · Ba mẫu thiết kế | ReAct dùng `create_agent` + middleware; Plan và Lai dùng `StateGraph` của LangGraph | `lib/ba_mau.py` |
| 03 · Đánh giá hiệu quả | Chạy 3 mẫu × 4 tình huống, đo vòng/tool/token/lý do dừng; sinh bảng tự động | `danh_gia.py`, `ket_qua_danh_gia.md` |

## 2. Kiến trúc project

```
24520343_NguyenTrungDung_BTVN03/
├── btvn03_dat_ve.py        # chạy 1 lượt (--mau · --tinh-huong) hoặc --tat-ca
├── danh_gia.py             # chạy 12 tổ hợp, in bảng, ghi ket_qua_danh_gia.md
├── lib/
│   ├── tools_datve.py      # tool mockup: search/check/book/pay/get_booking
│   ├── harness.py          # RangBuoc, kiem_tieu_chi, kiem_quyen, ban_giao,
│   │                       # LoopDetector, DemNganSach, Phien, KetQua
│   ├── model_gia.py        # model giả lập: 3 mẫu × 4 tình huống, không cần API key
│   └── ba_mau.py           # HarnessMiddleware (ReAct), graph Plan, graph Lai
├── ket_qua_danh_gia.md     # bảng kết quả do danh_gia.py sinh ra
├── BAO_CAO.md              # báo cáo này
└── requirements.txt
```

Vòng lặp chạy chung cho cả ba mẫu (đúng sơ đồ trục của slide):

```
Human → MODEL (đề xuất bước) → HARNESS kiểm quyền → thực thi tool
      → HARNESS kiểm tiêu chí / lặp / ngân sách → lặp tiếp hoặc dừng + bàn giao
```

Chỉ bước "model đề xuất" là của model; bốn bước còn lại là harness viết tay.

## 3. Lớp harness (yêu cầu 01)

### 3.1 Ràng buộc là dữ liệu

```python
RangBuoc(tu="SGN", den="DAD", ngay="2026-10-08", buoi="sang",
         tran_gia=2_000_000, han_muc_tu_quyet=1_500_000)
```

Yêu cầu khách hàng được biến thành dataclass, không nhét vào prompt. Model có
thể quên; ràng buộc thì không, vì mọi phép kiểm đều đọc từ đối tượng này.

### 3.2 Tiêu chí hoàn thành kiểm bằng code

`kiem_tieu_chi()` là vị từ chạy trong mili giây, không tốn token:

```
get_booking(code).trang_thai == "confirmed" and da_tra == True
and gia <= tran_gia and ngay == yêu cầu and gio thuộc buổi yêu cầu
```

Model không được tự tuyên bố "đã xong": middleware/graph chỉ công nhận
`DAT_MUC_TIEU` khi vị từ này trả về `ĐẠT` (5/5 điều kiện). Nếu model chốt câu
trả lời mà tiêu chí chưa đạt, harness chuyển thành dừng bất thường + bàn giao.

### 3.3 Kiểm quyền trước khi thực thi

`kiem_quyen()` chặn `book_seat` khi chuyến vượt hạn mức tự quyết hoặc vé
không hoàn — đúng ví dụ V3 của slide:

> `CAN_NGUOI · giá 1.950.000đ vượt hạn mức tự quyết 1.500.000đ và vé không hoàn được`

Đây là phép kiểm duy nhất chạy **trước** khi thực thi; bốn phép kiểm còn lại
chạy sau khi có observation, đúng checklist của slide.

### 3.4 Bàn giao

Khi dừng bất thường, `ban_giao()` trả đủ 4 trường: `stop_reason`, `da_thu`,
`trang_thai`, `cau_hoi_cho_nguoi` — người nhận trả lời được trong 30 giây.

### 3.5 Hai bộ đếm

* `LoopDetector` — ba tín hiệu của slide: trùng action `(tool, args)`, trùng
  observation, không tiến triển. Đại lượng tiến triển ở đây là **số tiêu chí
  đang đạt (0..5)**, tính từ kết quả tool chứ không từ lời model.
* `DemNganSach` — trần 8 vòng model và 12 lần gọi tool. Ngân sách kiểm sau
  cùng trong chuỗi kiểm, để lỗi nghiệp vụ không bị che thành "hết ngân sách".

### 3.6 Ánh xạ 5 kiểu dừng của slide vào code

| Kiểu dừng | Ai phát hiện | Cài đặt |
|---|---|---|
| 1 · Đạt mục tiêu | Model chốt + harness kiểm | `kiem_tieu_chi` trong middleware/graph |
| 2 · Hết ngân sách | Harness đếm | `DemNganSach` (8 vòng · 12 tool) |
| 3 · Phát hiện lặp | Harness so sánh | `LoopDetector` dấu vân tay `(tool, args)` |
| 4 · Bế tắc | Harness đo tiến triển | `LoopDetector` tín hiệu 3 (`progress`) |
| 5 · Cần con người | Harness kiểm quyền | `kiem_quyen` + `ban_giao` |

## 4. Ba mẫu thiết kế (yêu cầu 02)

### 4.1 ReAct — `create_agent` + `HarnessMiddleware`

Mỗi lượt model đề xuất **một** hành động dựa trên quan sát mới. Harness cài
bằng middleware `after_model`: kiểm quyền → lặp → ngân sách trước khi tool
chạy; khi model thôi gọi tool thì kiểm tiêu chí trước khi tin.

### 4.2 Plan-then-Execute — graph LangGraph 3 nút

Model sinh **trọn kế hoạch** trong một lượt (nhiều `tool_calls` trong một
AIMessage), harness thực thi tuần tự từng bước, tham số phụ thuộc
(`$ma_dat_cho`) được harness giải mã từ trạng thái. Chạy hết kế hoạch mà chưa
đạt tiêu chí thì dừng, **không lập lại kế hoạch** — đúng đặc trưng cứng nhắc
của mẫu này.

### 4.3 Lai — graph LangGraph có nhánh quay về

Mỗi lượt model sinh tối đa `k = 2` bước, thực thi xong thì graph quay về nút
lập kế hoạch để **lập lại theo quan sát mới**. Đây chính là sơ đồ "ReAct +
Plan" của slide (LangChain gợi ý TodoListMiddleware; ở đây cài tay bằng
StateGraph để thấy rõ luồng).

## 5. Kết quả đánh giá (yêu cầu 03)

Bảng dưới sinh tự động bởi `python danh_gia.py` (file `ket_qua_danh_gia.md`):

| Tình huống | Mẫu | Vòng model | Lần gọi tool | Token ước lượng | Lý do dừng | Đạt tiêu chí | Bàn giao |
|---|---|---:|---:|---:|---|---|---|
| chuan | react | 6 | 5 | 25.500 | DAT_MUC_TIEU | CÓ | không |
| chuan | plan | 2 | 5 | 6.500 | DAT_MUC_TIEU | CÓ | không |
| chuan | lai | 4 | 5 | 15.000 | DAT_MUC_TIEU | CÓ | không |
| duyet | react | 3 | 2 | 10.500 | CAN_NGUOI (vượt hạn mức + không hoàn) | không | có |
| duyet | plan | 1 | 2 | 3.000 | CAN_NGUOI | không | có |
| duyet | lai | 2 | 2 | 6.500 | CAN_NGUOI | không | có |
| lap | react | 4 | 3 | 15.000 | LOOP · search_flights lặp ở V4 | không | có |
| lap | plan | 1 | 2 | 3.000 | KE_HOACH_VO_HIEU · không lập lại kế hoạch | không | có |
| lap | lai | 2 | 1 | 6.500 | CHUA_DAT_TIEU_CHI · model chốt sau khi tự đổi chiến lược | không | có |
| ngan-sach | react | 8 | 7 | 38.000 | NGAN_SACH · chạm trần 8 vòng model | không | có |
| ngan-sach | plan | 1 | 11 | 3.000 | KE_HOACH_VO_HIEU · kế hoạch dò hết vẫn không đạt | không | có |
| ngan-sach | lai | 7 | 11 | 31.500 | CHUA_DAT_TIEU_CHI · kiểm hết chuyến mới kết luận | không | có |

Tổng hợp theo mẫu:

| Mẫu | Tổng vòng | Tổng tool | Tổng token | Lượt đạt tiêu chí | Lượt có bàn giao |
|---|---:|---:|---:|---:|---:|
| react | 21 | 17 | 89.000 | 1/4 | 3/4 |
| plan | 5 | 20 | 15.500 | 1/4 | 3/4 |
| lai | 15 | 19 | 59.500 | 1/4 | 3/4 |

### 5.1 Phân tích

**Tình huống `chuan` (đủ điều kiện):** cả ba mẫu đều đạt 5/5 tiêu chí.
Plan rẻ nhất (2 vòng · 6.500 token) vì kế hoạch đúng ngay lần đầu; ReAct đắt
nhất (6 vòng · 25.500 token) vì mỗi bước một lần gọi model; Lai ở giữa
(4 vòng) nhờ gộp 2 bước mỗi lượt.

**Tình huống `duyet` (vượt thẩm quyền):** cả ba mẫu đều bị chặn **trước khi**
đặt vé và bàn giao đủ 4 trường với cùng một lý do. Vì phép kiểm quyền nằm ở
harness dùng chung, đổi mẫu không làm thay đổi hành vi an toàn — đúng tinh
thần "harness là lớp bảo vệ độc lập với model".

**Tình huống `lap` (tuyến không có dữ liệu):** đây là nơi ba mẫu khác nhau rõ
nhất.
* ReAct: đổi cách viết `Hà Nội → Ha Noi → HAN → Hà Nội`, lặp lại đúng hành
  động cũ ở V4 → `LoopDetector` bắt và bàn giao (4 vòng).
* Plan: kế hoạch sinh một lần không có nhánh dự phòng → chạy hết kế hoạch,
  tiêu chí không đạt → `KE_HOACH_VO_HIEU` (1 vòng, rẻ nhưng không tự cứu).
* Lai: sau khi thấy `matched = 0` ở lượt đầu, lượt sau **đổi chiến lược** —
  không thử thêm cách viết tên nào, kết luận cần người quyết định (2 vòng,
  1 tool). Không phải dùng tới bộ đếm lặp.

**Tình huống `ngan-sach` (không chuyến nào dưới trần):** ReAct dò từng chuyến
đến khi chạm trần 8 vòng (38.000 token — đắt nhất toàn bảng); Plan dò 11
chuyến chỉ trong 1 vòng model (3.000 token); Lai dò theo cặp, tự kết luận sau
7 vòng. Cả ba đều bàn giao, không mẫu nào tự ý đặt chuyến vượt trần.

### 5.2 Kết luận chọn mẫu

| Tiêu chí | ReAct | Plan-then-Execute | Lai |
|---|---|---|---|
| Chi phí khi bài toán ổn định | Cao | **Thấp nhất** | Trung bình |
| Khả năng thích nghi khi quan sát đổi | Cao | **Kém** (kế hoạch đóng băng) | **Cao** |
| Chi phí khi bài toán xấu | **Cao nhất** (chạm trần) | Thấp | Trung bình |
| Nhu cầu harness bổ trợ | Rất cần loop + budget | Cần kiểm tiêu chí cuối | Cần ít nhất |

Với bài đặt vé này, **Lai là lựa chọn cân bằng nhất**: chỉ đắt hơn Plan khi
tình huống xấu đi, nhưng thoát khỏi bẫy lặp mà không cần LoopDetector phải
cứu. ReAct phù hợp khi không đoán được số bước nhưng bắt buộc phải có trần
ngân sách và phát hiện lặp. Plan phù hợp khi cần người duyệt trước hoặc bài
toán ổn định, chấp nhận rủi ro kế hoạch lỗi thời.

Điểm chung quan trọng nhất: **dừng bất thường ở cả 12 lượt chạy đều kèm bàn
giao** — không lượt nào "im lặng thất bại".

## 6. Cách chạy

```bash
pip install -r requirements.txt

python btvn03_dat_ve.py --mau react --tinh-huong chuan   # xem trace 1 lượt
python btvn03_dat_ve.py --mau plan --tinh-huong duyet
python btvn03_dat_ve.py --mau lai  --tinh-huong lap
python btvn03_dat_ve.py --tat-ca                          # bảng 12 tổ hợp
python danh_gia.py                                        # sinh ket_qua_danh_gia.md
```

Mặc định chạy **model giả lập** (`lib/model_gia.py`) nên không cần API key và
kết quả tái lập được. Muốn dùng model thật: đặt biến `SE373_MODEL` và thay
`ModelGia(...)` bằng `model_that()` trong `lib/ba_mau.py`.

## 7. Hạn chế và hướng phát triển

* Model giả lập kịch bản hóa theo từng mẫu nên kết quả mang tính **minh họa
  kiến trúc**, không phải đo năng lực LLM thật; muốn so công bằng hơn cần
  chạy cùng một prompt thật trên cả ba mẫu.
* Token là ước lượng theo công thức của slide (3.000 nền + 500/vòng), chưa
  tính token của phần observation tool trả về.
* Chưa có test tự động dạng pytest; các lớp harness hiện tự kiểm bằng
  `python -m lib.harness` và bảng đánh giá.
* Hướng mở rộng: thêm người duyệt thật (human-in-the-loop qua interrupt của
  LangGraph), thêm tool `cancel_booking` để minh họa kiểm quyền cho hành động
  có tác dụng phụ, và lưu trace để so sánh giữa các lần chạy.
