# -*- coding: utf-8 -*-
"""SE373 · BTVN#3 · Lớp harness viết tay cho agent đặt vé.

Framework không làm hộ bốn việc này (yêu cầu 01 của BTVN):

    RangBuoc        ràng buộc là dữ liệu, không nằm rải rác trong prompt
    kiem_tieu_chi   tiêu chí hoàn thành kiểm bằng code (vị từ khách quan)
    kiem_quyen      kiểm quyền trước khi thực thi hành động nhạy cảm
    ban_giao        dừng bất thường thì bàn giao đủ bốn trường

Cộng thêm hai bộ đếm mà mọi vòng lặp agent đều cần:

    LoopDetector    ba tín hiệu: trùng action · trùng observation · không tiến triển
    DemNganSach     trần vòng model và trần lần gọi tool

Toàn bộ là Python thường, không phụ thuộc LangChain, không gọi model.
"""
from __future__ import annotations

import ast
import json
import re
from collections import deque
from dataclasses import dataclass, field

from .tools_datve import CHUYEN_BAY

# ===================================================== 0 · RÀNG BUỘC LÀ DỮ LIỆU


@dataclass
class RangBuoc:
    """Ràng buộc của bài đặt vé, tách khỏi prompt và tách khỏi model.

    Model có thể quên; ràng buộc thì không, vì nó là dữ liệu được kiểm bằng code.
    """
    tu: str = "SGN"
    den: str = "DAD"
    ngay: str = "2026-10-08"
    buoi: str = "sang"                 # sang: gio < 12:00
    tran_gia: int = 2_000_000          # trần giá của yêu cầu
    han_muc_tu_quyet: int = 1_500_000  # trên mức này phải xin duyệt
    uu_tien_hoan_ve: bool = True

    def mo_ta(self) -> str:
        return (f"{self.tu} → {self.den}, ngày {self.ngay}, buổi {self.buoi}, "
                f"giá ≤ {self.tran_gia:,}đ, tự quyết ≤ {self.han_muc_tu_quyet:,}đ"
                .replace(",", "."))


# ============================================== 1 · ĐỌC QUAN SÁT TỪ MESSAGES


def doc_json(content) -> object:
    """ToolMessage.content có thể là dict, JSON, hoặc repr của dict."""
    if isinstance(content, (dict, list)):
        return content
    try:
        return json.loads(content)
    except Exception:
        pass
    try:
        return ast.literal_eval(content)
    except Exception:
        return content


def trich_trang_thai(messages) -> dict:
    """Gom mọi dữ kiện tool đã trả về thành một ảnh chụp trạng thái phẳng.

    Đây là nguồn duy nhất để kiểm tiêu chí; model không được tự khai.
    """
    tt: dict = {}
    for m in messages:
        if getattr(m, "type", "") != "tool":
            continue
        d = doc_json(getattr(m, "content", ""))
        if not isinstance(d, dict) or d.get("status") != "ok":
            continue
        if d.get("ma_dat_cho"):
            # Chỉ cập nhật trường có mặt: message sau không được xoá dữ liệu cũ.
            tt["ma_dat_cho"] = d["ma_dat_cho"]
            if "ma_chuyen" in d:
                tt["ma_chuyen"] = d["ma_chuyen"]
            if "trang_thai" in d:
                tt["trang_thai_dat_cho"] = d["trang_thai"]
            if "da_tra" in d:
                tt["da_tra"] = d["da_tra"]
            if "ghe" in d:
                tt["ghe"] = d["ghe"]
            if "gia" in d:
                tt["gia_dat_cho"] = d["gia"]
            if "hoan_ve" in d:
                tt["hoan_ve"] = d["hoan_ve"]
            if "ngay" in d:
                tt["ngay"] = d["ngay"]
            if "gio" in d:
                tt["gio"] = d["gio"]
        elif d.get("ma") and "ghe_trong" in d:
            tt["ma_check"] = d["ma"]
            if "gia" in d:
                tt["gia_check"] = d["gia"]
            if "ngay" in d:
                tt["ngay"] = d["ngay"]
            if "gio" in d:
                tt["gio"] = d["gio"]
    return tt


def dem_tien_do(rang_buoc: RangBuoc, tt: dict) -> int:
    """Đại lượng tiến triển của bài toán: số tiêu chí đang đạt được (0..5).

    Dùng cho tín hiệu thứ ba của LoopDetector (bế tắc: đổi tool liên tục
    nhưng con số này đứng yên qua N vòng).
    """
    return sum(1 for c in kiem_tieu_chi(rang_buoc, tt)["chi_tiet"] if c["dat"])


# ============================================ 2 · TIÊU CHÍ HOÀN THÀNH BẰNG CODE


def kiem_tieu_chi(rang_buoc: RangBuoc, tt: dict) -> dict:
    """Vị từ chạy bằng code, không tốn token, không phụ thuộc model tự khai.

    Tiêu chí của bài đặt vé:
        get_booking(code).status == "confirmed" and paid == True
        and price <= tran_gia and đúng ngày và đúng buổi
    """
    chua_dat = tt.get("trang_thai_dat_cho")
    chi_tiet = [
        {"ten": "có mã đặt chỗ", "dat": bool(tt.get("ma_dat_cho")),
         "mo_ta": f"mã: {tt.get('ma_dat_cho', 'chưa có')}"},
        {"ten": "đã thanh toán · confirmed",
         "dat": bool(tt.get("da_tra")) and chua_dat == "confirmed",
         "mo_ta": f"trạng thái: {chua_dat or 'chưa có'}, đã trả: {bool(tt.get('da_tra'))}"},
        {"ten": "trong trần giá",
         "dat": tt.get("gia_dat_cho") is not None and tt["gia_dat_cho"] <= rang_buoc.tran_gia,
         "mo_ta": f"giá: {tt.get('gia_dat_cho', '?')} / trần {rang_buoc.tran_gia}"},
        {"ten": "đúng ngày",
         "dat": tt.get("ngay") == rang_buoc.ngay,
         "mo_ta": f"ngày vé: {tt.get('ngay', '?')} / yêu cầu {rang_buoc.ngay}"},
        {"ten": "đúng buổi",
         "dat": tt.get("gio") is not None and (
             (rang_buoc.buoi == "sang" and tt["gio"] < "12:00")
             or (rang_buoc.buoi == "chieu" and tt["gio"] >= "12:00")),
         "mo_ta": f"giờ bay: {tt.get('gio', '?')} / buổi {rang_buoc.buoi}"},
    ]
    return {"dat": all(c["dat"] for c in chi_tiet), "chi_tiet": chi_tiet}


def kiem_chung_cheo(tt: dict) -> list[str]:
    """Đối chiếu chéo: giá trong đặt chỗ phải khớp giá đã thấy lúc kiểm ghế."""
    canh_bao = []
    if tt.get("gia_dat_cho") is not None and tt.get("gia_check") is not None:
        if tt["gia_dat_cho"] != tt["gia_check"]:
            canh_bao.append(f"Giá đặt chỗ {tt['gia_dat_cho']} khác giá đã kiểm "
                            f"{tt['gia_check']} — nghi dữ liệu bịa hoặc tool lệch")
    return canh_bao


# ================================================== 3 · KIỂM QUYỀN TRƯỚC KHI CHẠY


def kiem_quyen(ten_tool: str, args: dict, rang_buoc: RangBuoc) -> str | None:
    """Chạy trước khi thực thi tool. Trả lý do nếu cần người duyệt, None nếu tự quyết được.

    Quy tắc nghiệp vụ (ràng buộc là dữ liệu):
        book_seat vào chuyến vượt hạn mức tự quyết, hoặc vé không hoàn,
        thì phải dừng xin duyệt — không được tự đặt.
    """
    if ten_tool != "book_seat":
        return None
    ma = args.get("ma")
    chuyen = next((c for c in CHUYEN_BAY if c["ma"] == ma), None)
    if not chuyen:
        return None
    ly_do = []
    if chuyen["gia"] > rang_buoc.han_muc_tu_quyet:
        ly_do.append(f"giá {chuyen['gia']:,}đ vượt hạn mức tự quyết "
                     f"{rang_buoc.han_muc_tu_quyet:,}đ".replace(",", "."))
    if not chuyen["hoan_ve"]:
        ly_do.append("vé không hoàn được")
    if not ly_do:
        return None
    return "CAN_NGUOI · " + " và ".join(ly_do)


# ================================================== 4 · BÀN GIAO KHI DỪNG SAI


def ban_giao(ly_do: str, da_thu: list, trang_thai: dict, cau_hoi: str) -> dict:
    """Dừng bất thường thì bàn giao đủ bốn trường, không im lặng (slide phần 03)."""
    return {"stop_reason": ly_do,
            "da_thu": list(da_thu),
            "trang_thai": dict(trang_thai),
            "cau_hoi_cho_nguoi": cau_hoi}


def in_ban_giao(b: dict) -> str:
    return (
        "DỪNG BẤT THƯỜNG · " + b["stop_reason"] + "\n"
        "  Đã thử          : " + (" → ".join(b["da_thu"]) or "(chưa gọi tool nào)") + "\n"
        "  Trạng thái      : " + _tt_gon(b["trang_thai"]) + "\n"
        "  Hỏi người dùng  : " + b["cau_hoi_cho_nguoi"]
    )


def _tt_gon(tt: dict) -> str:
    phan = []
    if "so_vong" in tt:
        phan.append(f"{tt['so_vong']} vòng model")
    if "so_tool" in tt:
        phan.append(f"{tt['so_tool']} lần gọi tool")
    if "tien_do" in tt:
        phan.append(f"tiến độ {tt['tien_do']}")
    for k in ("ma_dat_cho", "trang_thai_dat_cho", "gia_dat_cho"):
        if tt.get(k) is not None:
            phan.append(f"{k}={tt[k]}")
    return " · ".join(phan) if phan else "trống"


# ========================================================= 5 · PHÁT HIỆN LẶP


class LoopDetector:
    """Ba tín hiệu theo đúng slide S48 (phần 03).

    1. trùng action      cùng (tool, args) lặp lại trong cửa sổ vài vòng
    2. trùng observation tham số khác nhau nhưng kết quả trả về giống hệt
    3. không tiến triển  đại lượng tiến triển đứng yên qua N vòng
    """

    def __init__(self, window=6, repeat_k=2, same_obs_k=4, stall_n=5):
        self.recent = deque(maxlen=window)
        self.obs = deque(maxlen=window)
        self.k, self.k_obs, self.n = repeat_k, same_obs_k, stall_n
        self.last_progress, self.stall = None, 0

    def check(self, tool: str, args: dict, observation=None, progress=None) -> str | None:
        fp = (tool, repr(sorted(args.items())))
        if self.recent.count(fp) + 1 >= self.k:
            return (f"LOOP · '{tool}' gọi {self.recent.count(fp) + 1} lần "
                    f"với cùng tham số trong {self.recent.maxlen} vòng gần nhất")
        self.recent.append(fp)

        if observation is not None:
            ofp = repr(observation)
            if self.obs.count(ofp) + 1 >= self.k_obs:
                return (f"LOOP · {self.obs.count(ofp) + 1} lời gọi khác tham số "
                        f"nhưng trả về cùng một kết quả")
            self.obs.append(ofp)

        if progress is not None:
            self.stall = self.stall + 1 if progress == self.last_progress else 0
            self.last_progress = progress
            if self.stall >= self.n:
                return (f"BE_TAC · tiến triển đứng yên ở {progress} tiêu chí "
                        f"qua {self.stall} vòng")
        return None


# ========================================================= 6 · NGÂN SÁCH VÒNG


class DemNganSach:
    """Trần cứng của harness: số vòng model và số lần gọi tool."""

    def __init__(self, tran_vong: int = 8, tran_tool: int = 12):
        self.tran_vong, self.tran_tool = tran_vong, tran_tool
        self.so_vong, self.so_tool = 0, 0

    def vuot_ngan_sach(self) -> str | None:
        if self.so_vong >= self.tran_vong:
            return f"NGAN_SACH · chạm trần {self.tran_vong} vòng model"
        if self.so_tool >= self.tran_tool:
            return f"NGAN_SACH · chạm trần {self.tran_tool} lần gọi tool"
        return None


def tinh_token(so_vong: int) -> int:
    """Ước lượng token theo đúng giả định của slide: 3.000 token nền,
    vòng thứ i cộng thêm 500·(i-1) vào ngữ cảnh, tổng chi phí là tổng cộng dồn."""
    return sum(3000 + 500 * (i - 1) for i in range(1, so_vong + 1))


# ==================================================== 7 · PHIÊN CHẠY & KẾT QUẢ


@dataclass
class KetQua:
    mau: str
    tinh_huong: str
    so_vong: int = 0
    so_tool: int = 0
    token: int = 0
    ly_do_dung: str = ""
    dat_tieu_chi: bool = False
    co_ban_giao: bool = False
    cau_tra_loi: str = ""
    chi_tiet_tieu_chi: list = field(default_factory=list)
    ban_giao: dict | None = None


class Phien:
    """Bối cảnh dùng chung cho cả ba mẫu: một chỗ giữ ngân sách, bộ phát hiện lặp,
    danh sách đã thử và các mốc dừng. Nhờ vậy ba mẫu so sánh được với nhau."""

    def __init__(self, rang_buoc: RangBuoc, mau: str, tinh_huong: str,
                 cau_hoi: str, cau_hoi_nguoi: str,
                 tran_vong: int = 8, tran_tool: int = 12):
        self.rang_buoc = rang_buoc
        self.mau = mau
        self.tinh_huong = tinh_huong
        self.cau_hoi = cau_hoi
        self.cau_hoi_nguoi = cau_hoi_nguoi
        self.messages: list = []
        self.da_thu: list[str] = []
        self.det = LoopDetector(window=6, repeat_k=2, same_obs_k=4, stall_n=5)
        self.ngan_sach = DemNganSach(tran_vong=tran_vong, tran_tool=tran_tool)
        self.ly_do_dung: str | None = None
        self.bao_cao: dict | None = None

    # -------------------------------------------------------------- tiện ích
    def ghi_vong(self) -> None:
        self.ngan_sach.so_vong += 1

    def kiem_truoc_khi_goi(self, ten: str, args: dict) -> str | None:
        """Kiểm quyền → phát hiện lặp → ngân sách, theo đúng checklist của slide.

        Chạy trước mỗi lần thực thi tool. Phát hiện lặp lấy tiến độ hiện tại
        làm tín hiệu thứ ba.
        """
        self.da_thu.append(f"{ten}({_args_gon(args)})")
        quyen = kiem_quyen(ten, args, self.rang_buoc)
        if quyen:
            return quyen
        tien_do = dem_tien_do(self.rang_buoc, trich_trang_thai(self.messages))
        lap = self.det.check(ten, args, progress=tien_do)
        if lap:
            return lap
        ns = self.ngan_sach.vuot_ngan_sach()
        if ns:
            return ns
        self.ngan_sach.so_tool += 1
        return None

    def anh_chup(self) -> dict:
        tt = trich_trang_thai(self.messages)
        kq = kiem_tieu_chi(self.rang_buoc, tt)
        return {"so_vong": self.ngan_sach.so_vong,
                "so_tool": self.ngan_sach.so_tool,
                "tien_do": f"{sum(1 for c in kq['chi_tiet'] if c['dat'])}/{len(kq['chi_tiet'])} tiêu chí",
                **{k: tt[k] for k in ("ma_dat_cho", "trang_thai_dat_cho", "gia_dat_cho")
                   if tt.get(k) is not None}}

    def dung_bat_thuong(self, ly_do: str) -> dict:
        """Tạo báo cáo bàn giao + message AI, dùng chung cho middleware và runner."""
        from langchain_core.messages import AIMessage
        self.ly_do_dung = ly_do
        self.bao_cao = ban_giao(ly_do=ly_do, da_thu=self.da_thu,
                                trang_thai=self.anh_chup(),
                                cau_hoi=self.cau_hoi_nguoi)
        return {"jump_to": "end", "messages": [AIMessage(content=in_ban_giao(self.bao_cao))]}

    # ---------------------------------------------------------------- chốt
    def chot(self, so_vong_thuc: int) -> KetQua:
        tt = trich_trang_thai(self.messages)
        kq = kiem_tieu_chi(self.rang_buoc, tt)
        if self.ly_do_dung is None:
            self.ly_do_dung = "DAT_MUC_TIEU" if kq["dat"] else "KET_THUC_KHONG_RO"
        ai_cuoi = [m for m in self.messages
                   if getattr(m, "type", "") == "ai" and getattr(m, "content", "")]
        return KetQua(mau=self.mau, tinh_huong=self.tinh_huong,
                      so_vong=so_vong_thuc,
                      so_tool=self.ngan_sach.so_tool,
                      token=tinh_token(so_vong_thuc),
                      ly_do_dung=self.ly_do_dung,
                      dat_tieu_chi=kq["dat"],
                      co_ban_giao=self.bao_cao is not None,
                      cau_tra_loi=str(ai_cuoi[-1].content) if ai_cuoi else "",
                      chi_tiet_tieu_chi=kq["chi_tiet"],
                      ban_giao=self.bao_cao)


def _args_gon(args: dict) -> str:
    return ", ".join(f"{k}={v!r}" for k, v in args.items())


# ================================================================ 8 · TỰ KIỂM


if __name__ == "__main__":
    rb = RangBuoc()
    print("── RangBuoc ──\n ", rb.mo_ta())

    print("\n── kiem_tieu_chi · vé đạt chuẩn ──")
    from langchain_core.messages import ToolMessage
    import json as _json
    msgs = [
        ToolMessage(content=_json.dumps({"status": "ok", "ma": "QH208", "ghe_trong": 6,
                                         "gia": 1_420_000, "hoan_ve": True,
                                         "ngay": "2026-10-08", "gio": "07:00"}),
                    tool_call_id="c1"),
        ToolMessage(content=_json.dumps({"status": "ok", "ma_dat_cho": "DX-QH208",
                                         "ma_chuyen": "QH208", "ghe": "A1",
                                         "trang_thai": "confirmed", "da_tra": True,
                                         "gia": 1_420_000, "hoan_ve": True,
                                         "ngay": "2026-10-08", "gio": "07:00"}),
                    tool_call_id="c2"),
    ]
    tt = trich_trang_thai(msgs)
    for c in kiem_tieu_chi(rb, tt)["chi_tiet"]:
        print(("   đạt    " if c["dat"] else "   CHƯA   ") + c["ten"] + " · " + c["mo_ta"])
    print("  kết luận:", "ĐẠT" if kiem_tieu_chi(rb, tt)["dat"] else "CHƯA ĐẠT")
    print("  kiểm chứng chéo:", kiem_chung_cheo(tt) or "không phát hiện lệch")

    print("\n── kiem_quyen · vé không hoàn và vượt hạn mức ──")
    print(" ", kiem_quyen("book_seat", {"ma": "VN122", "ghe": "12A"}, rb))
    print(" ", kiem_quyen("book_seat", {"ma": "QH208", "ghe": "A1"}, rb) or "được tự quyết")

    print("\n── LoopDetector · tái hiện chuỗi tên tuyến lặp ──")
    det = LoopDetector()
    for vong, ten in enumerate(["Hà Nội", "Ha Noi", "HAN", "Hà Nội"], 1):
        canh_bao = det.check("search_flights", {"tu": ten}, progress=0)
        print(f"  V{vong} search_flights(tu={ten!r}) → {canh_bao or 'bình thường'}")
        if canh_bao:
            break
