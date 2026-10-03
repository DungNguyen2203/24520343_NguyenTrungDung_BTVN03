# -*- coding: utf-8 -*-
"""SE373 · BTVN#3 · Bộ tool đặt vé máy bay (mock).

Dữ liệu tĩnh, không gọi mạng: mọi lần chạy đều ra cùng một kết quả, để ba
mẫu thiết kế (ReAct · Plan-then-Execute · Lai) được so sánh trên đúng một
tập dữ liệu và một câu hỏi.

    search_flights(tu, den, ngay, buoi)  -> danh sách chuyến khớp tuyến/ngày/buổi
    check_seat(ma)                       -> ghế trống, giá, điều kiện hoàn vé
    book_seat(ma, ghe)                   -> giữ chỗ, sinh mã đặt chỗ
    pay(ma_dat_cho, phuong_thuc)         -> thanh toán
    get_booking(ma_dat_cho)              -> trạng thái cuối của đặt chỗ

Mọi observation đều có cấu trúc rõ: status + dữ liệu + hint khi thất bại.
Không có chuỗi rỗng hay "not found" trần trụi — đúng bài học phần 04 của
slide: tool phải trả kết quả rõ để agent biết đường đi tiếp.
"""
from __future__ import annotations

# ---------------------------------------------------------------- dữ liệu
# Tuần 08/10/2026 (thứ Năm). Giá đã gồm thuế, phí.
CHUYEN_BAY = [
    dict(ma="VN122", hang="Vietnam Airlines", tu="SGN", den="DAD",
         ngay="2026-10-08", gio="08:00", gia=1_950_000,
         hoan_ve=False, hang_ghe="Tiết kiệm", ghe_trong=4),
    dict(ma="VJ604", hang="VietJet Air", tu="SGN", den="DAD",
         ngay="2026-10-08", gio="06:30", gia=1_750_000,
         hoan_ve=True, hang_ghe="Eco", ghe_trong=2),
    dict(ma="QH208", hang="Bamboo Airways", tu="SGN", den="DAD",
         ngay="2026-10-08", gio="07:00", gia=1_420_000,
         hoan_ve=True, hang_ghe="Eco", ghe_trong=6),
    dict(ma="VN134", hang="Vietnam Airlines", tu="SGN", den="DAD",
         ngay="2026-10-08", gio="11:30", gia=1_350_000,
         hoan_ve=False, hang_ghe="Tiết kiệm", ghe_trong=3),
    dict(ma="QH118", hang="Bamboo Airways", tu="SGN", den="DAD",
         ngay="2026-10-08", gio="09:15", gia=2_450_000,
         hoan_ve=True, hang_ghe="Flex", ghe_trong=8),
    dict(ma="VJ612", hang="VietJet Air", tu="SGN", den="DAD",
         ngay="2026-10-08", gio="14:00", gia=1_650_000,
         hoan_ve=True, hang_ghe="Eco", ghe_trong=5),
    dict(ma="VN126", hang="Vietnam Airlines", tu="SGN", den="DAD",
         ngay="2026-10-09", gio="07:30", gia=1_500_000,
         hoan_ve=True, hang_ghe="Eco", ghe_trong=7),
    dict(ma="VN128", hang="Vietnam Airlines", tu="SGN", den="DAD",
         ngay="2026-10-08", gio="10:45", gia=1_880_000,
         hoan_ve=True, hang_ghe="Eco", ghe_trong=9),
    dict(ma="VJ614", hang="VietJet Air", tu="SGN", den="DAD",
         ngay="2026-10-08", gio="05:50", gia=1_610_000,
         hoan_ve=False, hang_ghe="Eco", ghe_trong=1),
    dict(ma="QH210", hang="Bamboo Airways", tu="SGN", den="DAD",
         ngay="2026-10-08", gio="10:20", gia=2_100_000,
         hoan_ve=False, hang_ghe="Eco", ghe_trong=2),
]

# Đặt chỗ do book_seat sinh ra trong phiên chạy. Xoá trước mỗi lượt chạy.
DAT_CHO: dict[str, dict] = {}

MA_SAN_BAY = {
    "sgn": "SGN", "tp.hcm": "SGN", "tp hcm": "SGN", "tphcm": "SGN",
    "hồ chí minh": "SGN", "ho chi minh": "SGN", "sài gòn": "SGN", "sai gon": "SGN",
    "dad": "DAD", "đà nẵng": "DAD", "da nang": "DAD",
    "han": "HAN", "hà nội": "HAN", "ha noi": "HAN",
}


def xoa_dat_cho() -> None:
    """Xoá sạch đặt chỗ — gọi trước mỗi lượt chạy để kết quả tái lập được."""
    DAT_CHO.clear()


def _chuan(s: object) -> str:
    return " ".join(str(s).lower().split())


def _san_bay(x: str) -> str | None:
    return MA_SAN_BAY.get(_chuan(x))


def _tim_chuyen(ma: str) -> dict | None:
    for c in CHUYEN_BAY:
        if _chuan(c["ma"]) == _chuan(ma):
            return c
    return None


def _tom_tat(c: dict) -> dict:
    return {"ma": c["ma"], "hang": c["hang"], "gio": c["gio"],
            "gia": c["gia"], "hoan_ve": c["hoan_ve"]}


# ---------------------------------------------------------------- tool 1
def search_flights(tu: str, den: str, ngay: str, buoi: str | None = None) -> dict:
    """Tìm chuyến bay theo tuyến, ngày và buổi.

    tu/den nhận mã sân bay (SGN, DAD) hoặc tên thành phố tiếng Việt.
    ngay theo định dạng YYYY-MM-DD. buoi: "sang" (trước 12:00) hoặc "chieu".
    Trả về danh sách chuyến kèm mã, hãng, giờ, giá, điều kiện hoàn vé.
    """
    s_tu, s_den = _san_bay(tu), _san_bay(den)
    if not s_tu or not s_den:
        return {"status": "invalid_param",
                "param": "tu/den",
                "queried": {"tu": tu, "den": den},
                "hint": "Dữ liệu demo chỉ hỗ trợ SGN (TP.HCM), DAD (Đà Nẵng), HAN (Hà Nội)",
                "supported": sorted(set(MA_SAN_BAY.values()))}
    if buoi not in (None, "sang", "chieu"):
        return {"status": "invalid_param", "param": "buoi",
                "allowed": ["sang", "chieu"],
                "hint": "Bỏ trống buoi nếu muốn xem cả ngày"}

    hits = [c for c in CHUYEN_BAY
            if c["tu"] == s_tu and c["den"] == s_den and c["ngay"] == ngay]
    if buoi == "sang":
        hits = [c for c in hits if c["gio"] < "12:00"]
    elif buoi == "chieu":
        hits = [c for c in hits if c["gio"] >= "12:00"]
    hits.sort(key=lambda c: c["gio"])

    if not hits:
        return {"status": "ok", "matched": 0, "chuyen": [],
                "hint": "Không có chuyến khớp tuyến/ngày/buổi này. "
                        "Thử bỏ bộ lọc buổi hoặc đổi ngày."}
    return {"status": "ok", "matched": len(hits),
            "tuyen": f"{s_tu}->{s_den}", "ngay": ngay, "buoi": buoi,
            "chuyen": [_tom_tat(c) for c in hits]}


# ---------------------------------------------------------------- tool 2
def check_seat(ma: str) -> dict:
    """Kiểm tra ghế trống và giá của một chuyến. Mã chuyến phải lấy từ search_flights."""
    c = _tim_chuyen(ma)
    if not c:
        return {"status": "not_found", "param": "ma", "queried": ma,
                "hint": "Gọi search_flights để lấy danh sách mã chuyến hợp lệ",
                "valid_examples": [x["ma"] for x in CHUYEN_BAY[:3]]}
    return {"status": "ok", "ma": c["ma"], "hang": c["hang"], "ghe_trong": c["ghe_trong"],
            "hang_ghe": c["hang_ghe"], "gia": c["gia"], "hoan_ve": c["hoan_ve"],
            "ngay": c["ngay"], "gio": c["gio"]}


# ---------------------------------------------------------------- tool 3
def book_seat(ma: str, ghe: str) -> dict:
    """Giữ một ghế trên chuyến bay. Trả về mã đặt chỗ để dùng cho pay/get_booking."""
    c = _tim_chuyen(ma)
    if not c:
        return {"status": "not_found", "param": "ma", "queried": ma,
                "hint": "Gọi check_seat để xác nhận chuyến trước khi đặt",
                "valid_examples": [x["ma"] for x in CHUYEN_BAY[:3]]}
    if c["ghe_trong"] <= 0:
        return {"status": "no_seat", "ma": c["ma"],
                "hint": "Chuyến đã hết ghế, chọn chuyến khác"}
    ma_dat_cho = f"DX-{c['ma']}"
    if ma_dat_cho in DAT_CHO:
        return {"status": "ok", "ma_dat_cho": ma_dat_cho, "ma_chuyen": c["ma"],
                "ghe": DAT_CHO[ma_dat_cho]["ghe"], "trang_thai": DAT_CHO[ma_dat_cho]["trang_thai"],
                "gia": c["gia"], "hoan_ve": c["hoan_ve"],
                "hint": "Đặt chỗ này đã tồn tại, dùng lại mã cũ"}
    DAT_CHO[ma_dat_cho] = dict(ma_chuyen=c["ma"], ghe=ghe, gia=c["gia"],
                               hoan_ve=c["hoan_ve"], ngay=c["ngay"], gio=c["gio"],
                               trang_thai="held", da_tra=False)
    return {"status": "ok", "ma_dat_cho": ma_dat_cho, "ma_chuyen": c["ma"], "ghe": ghe,
            "trang_thai": "held", "gia": c["gia"], "hoan_ve": c["hoan_ve"]}


# ---------------------------------------------------------------- tool 4
def pay(ma_dat_cho: str, phuong_thuc: str = "corp_card") -> dict:
    """Thanh toán một đặt chỗ đang giữ. Sau khi trả tiền, get_booking sẽ báo confirmed."""
    dc = DAT_CHO.get(ma_dat_cho)
    if not dc:
        return {"status": "not_found", "param": "ma_dat_cho", "queried": ma_dat_cho,
                "hint": "Chưa có đặt chỗ này, gọi book_seat trước"}
    if dc["da_tra"]:
        return {"status": "ok", "ma_dat_cho": ma_dat_cho, "trang_thai": "paid",
                "da_tra": True, "so_tien": dc["gia"], "phuong_thuc": phuong_thuc,
                "hint": "Đã thanh toán trước đó, không thu thêm"}
    dc["da_tra"] = True
    dc["trang_thai"] = "paid"
    return {"status": "ok", "ma_dat_cho": ma_dat_cho, "trang_thai": "paid",
            "da_tra": True, "so_tien": dc["gia"], "phuong_thuc": phuong_thuc}


# ---------------------------------------------------------------- tool 5
def get_booking(ma_dat_cho: str) -> dict:
    """Đọc trạng thái cuối cùng của một đặt chỗ: held/paid/confirmed và số tiền."""
    dc = DAT_CHO.get(ma_dat_cho)
    if not dc:
        return {"status": "not_found", "param": "ma_dat_cho", "queried": ma_dat_cho,
                "hint": "Gọi book_seat để tạo đặt chỗ mới"}
    trang_thai = "confirmed" if dc["da_tra"] else "held"
    return {"status": "ok", "ma_dat_cho": ma_dat_cho, "ma_chuyen": dc["ma_chuyen"],
            "ghe": dc["ghe"], "trang_thai": trang_thai, "da_tra": dc["da_tra"],
            "gia": dc["gia"], "hoan_ve": dc["hoan_ve"],
            "ngay": dc["ngay"], "gio": dc["gio"]}


# ------------------------------------------------- đóng gói cho LangChain
def tools_langchain():
    """Trả danh sách tool LangChain cho create_agent."""
    from langchain_core.tools import tool
    return [tool(search_flights), tool(check_seat), tool(book_seat),
            tool(pay), tool(get_booking)]


if __name__ == "__main__":
    import json
    xoa_dat_cho()
    print(json.dumps(search_flights("TP.HCM", "Đà Nẵng", "2026-10-08", "sang"),
                     ensure_ascii=False, indent=2))
    print(json.dumps(book_seat("QH208", "A1"), ensure_ascii=False))
    print(json.dumps(pay("DX-QH208"), ensure_ascii=False))
    print(json.dumps(get_booking("DX-QH208"), ensure_ascii=False))
    print(json.dumps(search_flights("Hà Nội", "Đà Nẵng", "2026-10-08"),
                     ensure_ascii=False))
