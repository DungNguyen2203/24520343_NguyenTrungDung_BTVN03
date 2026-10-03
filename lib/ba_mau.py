# -*- coding: utf-8 -*-
"""SE373 · BTVN#3 · Cài đặt agent đặt vé với ba mẫu thiết kế (yêu cầu 02).

    ReAct              create_agent của LangChain: mỗi lượt model tự chọn MỘT
                       bước, harness kiểm quyền/lặp/ngân sách bằng middleware.
    Plan-then-Execute  graph LangGraph: model sinh trọn kế hoạch một lần,
                       harness thực thi từng bước, KHÔNG lập lại kế hoạch.
    Lai                graph LangGraph: mỗi lượt model sinh tối đa k bước,
                       thực thi xong thì lập lại kế hoạch theo quan sát mới.

Cả ba dùng chung: cùng tool mock, cùng lớp harness (RangBuoc, kiem_tieu_chi,
kiem_quyen, ban_giao, LoopDetector, DemNganSach). Khác biệt duy nhất nằm ở
cách tổ chức vòng lặp — đúng kiểu thí nghiệm có kiểm soát của slide phần 03.
"""
from __future__ import annotations

import json
from typing import TypedDict

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, hook_config
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, StateGraph

from .harness import KetQua, Phien, RangBuoc, kiem_tieu_chi, trich_trang_thai
from .model_gia import ModelGia
from .tools_datve import (book_seat, check_seat, get_booking, pay,
                          search_flights, tools_langchain, xoa_dat_cho)

# ------------------------------------------------------- bốn tình huống chạy
TINH_HUONG: dict[str, dict] = {
    "chuan": dict(
        nhan="Đủ điều kiện · tự đặt được",
        cau_hoi=("Tìm và đặt giúp tôi vé TP.HCM → Đà Nẵng sáng thứ Năm 08/10/2026, "
                 "dưới 2 triệu, ưu tiên vé hoàn được."),
        cau_hoi_nguoi="Xác nhận chuyến QH208 hay chọn chuyến khác?",
        rang_buoc=RangBuoc(tu="SGN", den="DAD", ngay="2026-10-08", buoi="sang",
                           tran_gia=2_000_000, han_muc_tu_quyet=1_500_000)),
    "duyet": dict(
        nhan="Chuyến vi phạm hạn mức · cần người duyệt",
        cau_hoi=("Đặt giúp tôi vé sáng thứ Năm 08/10/2026 từ TP.HCM đi Đà Nẵng, "
                 "chuyến nào cũng được."),
        cau_hoi_nguoi=("Duyệt đặt vé không hoàn 1.950.000đ vượt hạn mức 1.500.000đ, "
                       "hay chọn chuyến hoàn được rẻ hơn?"),
        rang_buoc=RangBuoc(tu="SGN", den="DAD", ngay="2026-10-08", buoi="sang",
                           tran_gia=2_000_000, han_muc_tu_quyet=1_500_000)),
    "lap": dict(
        nhan="Tuyến không có dữ liệu · dễ lặp",
        cau_hoi=("Đặt giúp tôi vé Hà Nội → Đà Nẵng sáng thứ Năm 08/10/2026."),
        cau_hoi_nguoi=("Tuyến Hà Nội → Đà Nẵng chưa có trong dữ liệu: đổi điểm đi "
                       "hay báo khách chưa hỗ trợ?"),
        rang_buoc=RangBuoc(tu="Hà Nội", den="Đà Nẵng", ngay="2026-10-08", buoi="sang",
                           tran_gia=2_000_000, han_muc_tu_quyet=1_500_000)),
    "ngan-sach": dict(
        nhan="Không chuyến nào đạt trần giá · cháy ngân sách",
        cau_hoi=("Tìm vé TP.HCM → Đà Nẵng sáng thứ Năm 08/10/2026 dưới 1,2 triệu."),
        cau_hoi_nguoi=("Không có chuyến dưới 1.200.000đ: nâng trần giá hay đổi "
                       "ngày/buổi bay?"),
        rang_buoc=RangBuoc(tu="SGN", den="DAD", ngay="2026-10-08", buoi="sang",
                           tran_gia=1_200_000, han_muc_tu_quyet=1_500_000)),
}

TOOL_MAP = {"search_flights": search_flights, "check_seat": check_seat,
            "book_seat": book_seat, "pay": pay, "get_booking": get_booking}


# ======================================================== 1 · HARNESS MIDDLEWARE
class HarnessMiddleware(AgentMiddleware):
    """Lớp harness cho mẫu ReAct: chạy sau mỗi lần model quyết định, trước khi
    tool thật sự được gọi.

    Thứ tự kiểm theo checklist của slide:
        model tự chốt  → kiểm tiêu chí hoàn thành (vị từ code)
        model gọi tool → kiểm quyền → phát hiện lặp → ngân sách
    """

    def __init__(self, phien: Phien):
        super().__init__()
        self.phien = phien

    @hook_config(can_jump_to=["end"])
    def after_model(self, state, runtime):
        self.phien.messages = state["messages"]
        self.phien.ghi_vong()
        cuoi = state["messages"][-1]
        calls = getattr(cuoi, "tool_calls", None)

        if not calls:
            tt = trich_trang_thai(state["messages"])
            if kiem_tieu_chi(self.phien.rang_buoc, tt)["dat"]:
                self.phien.ly_do_dung = "DAT_MUC_TIEU"
                return None
            return self.phien.dung_bat_thuong(
                "CHUA_DAT_TIEU_CHI · model chốt câu trả lời nhưng tiêu chí code chưa đạt")

        for c in calls:
            ly_do = self.phien.kiem_truoc_khi_goi(c["name"], c["args"])
            if ly_do:
                return self.phien.dung_bat_thuong(ly_do)
        return None


def chay_react(phien: Phien, model: ModelGia) -> None:
    mw = HarnessMiddleware(phien)
    agent = create_agent(model=model, tools=tools_langchain(), middleware=[mw])
    phien.messages = [HumanMessage(content=phien.cau_hoi)]
    try:
        kq = agent.invoke({"messages": [{"role": "user", "content": phien.cau_hoi}]},
                          {"recursion_limit": 36})
        phien.messages = kq["messages"]
    except Exception as e:                        # GraphRecursionError dự phòng
        phien.messages = phien.messages + phien.dung_bat_thuong(
            f"LOI_FRAMEWORK · {type(e).__name__}: {str(e).splitlines()[0]}")["messages"]


# ==================================================== 2 · GRAPH CHO PLAN & LAI
class TrangThai(TypedDict):
    messages: list
    dat: bool
    dung: bool


def _giai_ma(args: dict, tt: dict) -> dict:
    """Giải mẫu tham số dạng $ma_dat_cho trong kế hoạch đã lập trước."""
    ra = {}
    for k, v in args.items():
        if isinstance(v, str) and v.startswith("$"):
            ra[k] = tt.get(v[1:], v)
        else:
            ra[k] = v
    return ra


def _ket_ban_giao(phien: Phien, ly_do: str, msgs: list) -> dict:
    bao = phien.dung_bat_thuong(ly_do)
    msgs = msgs + bao["messages"]
    phien.messages = msgs
    return {"messages": msgs, "dat": False, "dung": True}


def _nut_lap_ke_hoach(state: TrangThai, model: ModelGia, phien: Phien) -> dict:
    msgs = list(state["messages"])
    ai = model.invoke(msgs)
    phien.ghi_vong()
    msgs = msgs + [ai]
    phien.messages = msgs
    return {"messages": msgs, "dat": False, "dung": False}


def _nut_thuc_thi(state: TrangThai, model: ModelGia, phien: Phien, mau: str) -> dict:
    msgs = list(state["messages"])
    ai = msgs[-1]
    calls = getattr(ai, "tool_calls", None)

    if not calls:
        # Model tự chốt mà không cần tool.
        tt = trich_trang_thai(msgs)
        if kiem_tieu_chi(phien.rang_buoc, tt)["dat"]:
            phien.ly_do_dung = "DAT_MUC_TIEU"
            return {"messages": msgs, "dat": True, "dung": False}
        return _ket_ban_giao(phien, "CHUA_DAT_TIEU_CHI · model chốt câu trả lời "
                                    "nhưng tiêu chí code chưa đạt", msgs)

    for c in calls:
        args = _giai_ma(c["args"], trich_trang_thai(msgs))
        ly_do = phien.kiem_truoc_khi_goi(c["name"], args)
        if ly_do:
            return _ket_ban_giao(phien, ly_do, msgs)
        obs = TOOL_MAP[c["name"]](**args)
        msgs = msgs + [ToolMessage(content=json.dumps(obs, ensure_ascii=False),
                                   tool_call_id=c["id"], name=c["name"])]
        phien.messages = msgs
        if kiem_tieu_chi(phien.rang_buoc, trich_trang_thai(msgs))["dat"]:
            phien.ly_do_dung = "DAT_MUC_TIEU"
            return {"messages": msgs, "dat": True, "dung": False}

    if mau == "plan":
        # Đặc trưng của plan-then-execute: hết kế hoạch mà chưa đạt thì dừng,
        # không có nhánh lập lại kế hoạch.
        return _ket_ban_giao(phien, "KE_HOACH_VO_HIEU · thực thi hết kế hoạch nhưng "
                                    "tiêu chí chưa đạt; mẫu này không lập lại kế hoạch", msgs)
    return {"messages": msgs, "dat": False, "dung": False}


def _nut_tra_loi(state: TrangThai, model: ModelGia, phien: Phien) -> dict:
    msgs = list(state["messages"])
    ai = model.invoke(msgs)
    phien.ghi_vong()
    msgs = msgs + [ai]
    phien.messages = msgs
    return {"messages": msgs, "dat": True, "dung": False}


def chay_do_thi(phien: Phien, model: ModelGia, mau: str) -> None:
    g = StateGraph(TrangThai)
    g.add_node("lap_ke_hoach", lambda s: _nut_lap_ke_hoach(s, model, phien))
    g.add_node("thuc_thi", lambda s: _nut_thuc_thi(s, model, phien, mau))
    g.add_node("tra_loi", lambda s: _nut_tra_loi(s, model, phien))
    g.add_edge(START, "lap_ke_hoach")
    g.add_edge("lap_ke_hoach", "thuc_thi")
    if mau == "plan":
        g.add_conditional_edges(
            "thuc_thi",
            lambda s: "tra_loi" if s["dat"] else END,
            {"tra_loi": "tra_loi", END: END})
    else:
        g.add_conditional_edges(
            "thuc_thi",
            lambda s: "tra_loi" if s["dat"] else (END if s["dung"] else "lap_ke_hoach"),
            {"tra_loi": "tra_loi", END: END, "lap_ke_hoach": "lap_ke_hoach"})
    g.add_edge("tra_loi", END)
    app = g.compile()
    kq = app.invoke({"messages": [HumanMessage(content=phien.cau_hoi)],
                     "dat": False, "dung": False})
    phien.messages = kq["messages"]


# ============================================================== 3 · ĐIỀU PHỐI
def chay(mau: str, tinh_huong: str, in_trace: bool = False) -> KetQua:
    """Chạy một lượt: dọn đặt chỗ cũ để kết quả tái lập được."""
    xoa_dat_cho()
    th = TINH_HUONG[tinh_huong]
    phien = Phien(rang_buoc=th["rang_buoc"], mau=mau, tinh_huong=tinh_huong,
                  cau_hoi=th["cau_hoi"], cau_hoi_nguoi=th["cau_hoi_nguoi"])
    model = ModelGia(tinh_huong=tinh_huong, mau=mau)
    if mau == "react":
        chay_react(phien, model)
    else:
        chay_do_thi(phien, model, mau)
    kq = phien.chot(model._luot)
    if in_trace:
        in_phien(phien, kq)
    return kq


# ================================================================ 4 · IN TRACE
def in_phien(phien: Phien, kq: KetQua) -> None:
    print("=" * 78)
    print(f"BTVN#3 · mẫu: {kq.mau} · tình huống: {kq.tinh_huong} · "
          f"{TINH_HUONG[kq.tinh_huong]['nhan']}")
    print("=" * 78)
    vong = 0
    for m in phien.messages:
        if getattr(m, "type", "") == "human":
            print(f'[V1] Human  "{m.content}"')
        elif getattr(m, "type", "") == "ai" and getattr(m, "tool_calls", None):
            vong += 1
            for c in m.tool_calls:
                args = ", ".join(f"{k}={v!r}" for k, v in c["args"].items())
                print(f"[V{vong}] AI     {c['name']}({args})")
        elif getattr(m, "type", "") == "tool":
            print(f"[V{vong}] Tool   {m.content}")
        elif getattr(m, "type", "") == "ai":
            for dong in str(m.content).splitlines():
                print(f"[V{vong}] AI     {dong}")
    print("-" * 78)
    print(f"Kết luận : {kq.ly_do_dung}")
    print(f"Tiêu chí : {'ĐẠT' if kq.dat_tieu_chi else 'CHƯA ĐẠT'} · "
          f"{sum(1 for c in kq.chi_tiet_tieu_chi if c['dat'])}/"
          f"{len(kq.chi_tiet_tieu_chi)} điều kiện")
    if kq.ban_giao:
        print(f"Bàn giao : có · {len(kq.ban_giao['da_thu'])} hành động đã thử")
    print(f"Chi phí  : {kq.so_vong} vòng model · {kq.so_tool} lần gọi tool · "
          f"~{kq.token:,} token (ước lượng theo slide)".replace(",", "."))
