# -*- coding: utf-8 -*-
"""SE373 · BTVN#3 · Model giả lập, tương thích LangChain.

Đây KHÔNG phải LLM. Nó là một BaseChatModel trả tool_calls theo kịch bản,
để so sánh ba mẫu thiết kế trên giảng đường khi không có API key và để mỗi
lần chạy ra đúng một kết quả.

Ba mẫu (yêu cầu 02 của BTVN):

    "react"  mỗi lượt model đề xuất đúng một hành động, dựa trên quan sát
    "plan"   lượt đầu sinh trọn kế hoạch nhiều bước, các lượt sau chỉ chốt
    "lai"    mỗi lượt sinh tối đa k bước, lập lại kế hoạch sau mỗi batch

Bốn tình huống (yêu cầu 03 của BTVN — đánh giá hiệu quả):

    "chuan"      có chuyến hợp lệ nằm trong hạn mức tự quyết → đặt được
    "duyet"      chuyến bị chọn vượt hạn mức / không hoàn → phải xin duyệt
    "lap"        tuyến Hà Nội → Đà Nẵng không có dữ liệu → dễ rơi vào lặp
    "ngan-sach"  không chuyến nào dưới 1,2 triệu → dò mãi không ra

Đổi model thật: xem hàm `model_that()` ở cuối file.
"""
from __future__ import annotations

import os
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from .harness import trich_trang_thai

# Năm cách viết tên kiểu Trace A của slide, rút còn ba biến thể rồi quay lại
# biến thể đầu — vòng lặp bắt đầu từ lần gọi thứ tư.
BIEN_THE_HA_NOI = ["Hà Nội", "Ha Noi", "HAN"]

# Thứ tự dò chuyến khi tình huống "ngan-sach": mọi chuyến đều trên trần giá.
DS_KIEM = ["VN134", "VJ604", "VN122", "QH208", "QH118",
           "VJ612", "VN126", "VN128", "VJ614", "QH210"]


def _tien(x: int) -> str:
    return f"{x:,}đ".replace(",", ".")


class ModelGia(BaseChatModel):
    """Model giả lập sinh tool_calls theo kịch bản cố định.

    Tham số:
        tinh_huong  "chuan" · "duyet" · "lap" · "ngan-sach"
        mau         "react" · "plan" · "lai"
        k           số bước tối đa mỗi lần lập kế hoạch (mẫu "lai")
    """

    tinh_huong: str = "chuan"
    mau: str = "react"
    k: int = 2
    _luot: int = 0

    @property
    def _llm_type(self) -> str:
        return "se373-model-gia-dat-ve"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ModelGia":
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._luot += 1
        ai = self._quyet_dinh(messages)
        return ChatResult(generations=[ChatGeneration(message=ai)])

    # ------------------------------------------------------------ điều phối
    def _quyet_dinh(self, messages: list[BaseMessage]) -> AIMessage:
        if self.mau == "plan":
            return self._plan(messages)
        if self.mau == "lai":
            return self._lai(messages)
        return self._react(messages)

    # ------------------------------------------------------------- mẫu ReAct
    def _react(self, messages: list[BaseMessage]) -> AIMessage:
        return {
            "chuan": self._react_chuan,
            "duyet": self._react_duyet,
            "lap": self._react_lap,
            "ngan-sach": self._react_ngan_sach,
        }[self.tinh_huong](messages)

    def _react_chuan(self, messages) -> AIMessage:
        tt = trich_trang_thai(messages)
        if not self._da_search(messages):
            return self._goi("search_flights", self._args_tuyen(messages))
        if "QH208" not in self._da_kiem(messages):
            return self._goi("check_seat", {"ma": "QH208"})
        if not tt.get("ma_dat_cho"):
            return self._goi("book_seat", {"ma": "QH208", "ghe": "A1"})
        if not tt.get("da_tra"):
            return self._goi("pay", {"ma_dat_cho": tt["ma_dat_cho"],
                                     "phuong_thuc": "corp_card"})
        if tt.get("trang_thai_dat_cho") != "confirmed":
            return self._goi("get_booking", {"ma_dat_cho": tt["ma_dat_cho"]})
        return AIMessage(content=tra_loi_thanh_cong(tt))

    def _react_duyet(self, messages) -> AIMessage:
        # Chọn chuyến đầu tiên tìm thấy là VN122 — vé không hoàn, trên hạn mức.
        tt = trich_trang_thai(messages)
        if not self._da_search(messages):
            return self._goi("search_flights", self._args_tuyen(messages))
        if "VN122" not in self._da_kiem(messages):
            return self._goi("check_seat", {"ma": "VN122"})
        if not tt.get("ma_dat_cho"):
            return self._goi("book_seat", {"ma": "VN122", "ghe": "12A"})
        if not tt.get("da_tra"):
            return self._goi("pay", {"ma_dat_cho": tt["ma_dat_cho"],
                                     "phuong_thuc": "corp_card"})
        return AIMessage(content="Đã xử lý xong theo kịch bản dự phòng.")

    def _react_lap(self, messages) -> AIMessage:
        # Đổi cách viết tên rồi quay lại cách cũ — không có hướng đi mới.
        i = self._dem_goi(messages, "search_flights") % len(BIEN_THE_HA_NOI)
        return self._goi("search_flights", {"tu": BIEN_THE_HA_NOI[i],
                                            "den": "Đà Nẵng",
                                            "ngay": "2026-10-08", "buoi": "sang"})

    def _react_ngan_sach(self, messages) -> AIMessage:
        # Dò lần lượt từng chuyến, mỗi vòng một chuyến khác — không lặp,
        # không tiến triển, chạy tới khi chạm trần ngân sách.
        if not self._da_search(messages):
            return self._goi("search_flights", self._args_tuyen(messages))
        da_kiem = self._da_kiem(messages)
        for ma in DS_KIEM:
            if ma not in da_kiem:
                return self._goi("check_seat", {"ma": ma})
        return AIMessage(content="Đã dò hết danh sách chuyến nhưng không có chuyến nào "
                                 "dưới 1.200.000đ.")

    # -------------------------------------------------- mẫu Plan-then-Execute
    def _plan(self, messages) -> AIMessage:
        if self._luot == 1:
            return self._nhieu(self._ke_hoach_day_du())
        # Lượt chốt cuối: chỉ đọc quan sát rồi trả lời, không lập lại kế hoạch.
        return AIMessage(content=self._chot_loi(trich_trang_thai(messages)))

    def _ke_hoach_day_du(self) -> list[tuple[str, dict]]:
        """Kế hoạch sinh một lần, không có nhánh dự phòng."""
        a = self._args_tuyen(messages=None)
        return {
            "chuan": [
                ("search_flights", a),
                ("check_seat", {"ma": "QH208"}),
                ("book_seat", {"ma": "QH208", "ghe": "A1"}),
                ("pay", {"ma_dat_cho": "$ma_dat_cho", "phuong_thuc": "corp_card"}),
                ("get_booking", {"ma_dat_cho": "$ma_dat_cho"}),
            ],
            "duyet": [
                ("search_flights", a),
                ("check_seat", {"ma": "VN122"}),
                ("book_seat", {"ma": "VN122", "ghe": "12A"}),
                ("pay", {"ma_dat_cho": "$ma_dat_cho", "phuong_thuc": "corp_card"}),
            ],
            "lap": [
                ("search_flights", {"tu": "Hà Nội", "den": "Đà Nẵng",
                                    "ngay": "2026-10-08", "buoi": "sang"}),
                ("check_seat", {"ma": "VN122"}),
            ],
            "ngan-sach": [
                ("search_flights", a),
                *[("check_seat", {"ma": m}) for m in DS_KIEM],
            ],
        }[self.tinh_huong]

    # ------------------------------------------------------------- mẫu Lai
    def _lai(self, messages) -> AIMessage:
        tt = trich_trang_thai(messages)
        if self.tinh_huong == "chuan":
            if not self._da_search(messages):
                return self._nhieu([("search_flights", self._args_tuyen(messages))])
            if not tt.get("ma_dat_cho"):
                return self._nhieu([("check_seat", {"ma": "QH208"}),
                                    ("book_seat", {"ma": "QH208", "ghe": "A1"})])
            if not tt.get("da_tra"):
                return self._nhieu([("pay", {"ma_dat_cho": tt["ma_dat_cho"],
                                             "phuong_thuc": "corp_card"}),
                                    ("get_booking", {"ma_dat_cho": tt["ma_dat_cho"]})])
            return AIMessage(content=tra_loi_thanh_cong(tt))

        if self.tinh_huong == "duyet":
            if not self._da_search(messages):
                return self._nhieu([("search_flights", self._args_tuyen(messages))])
            if "VN122" not in self._da_kiem(messages):
                return self._nhieu([("check_seat", {"ma": "VN122"}),
                                    ("book_seat", {"ma": "VN122", "ghe": "12A"})])
            return AIMessage(content=self._chot_loi(tt))

        if self.tinh_huong == "lap":
            if not self._da_search(messages):
                return self._nhieu([("search_flights", {"tu": "Hà Nội", "den": "Đà Nẵng",
                                                        "ngay": "2026-10-08",
                                                        "buoi": "sang"})])
            # Đọc observation thấy matched = 0 → đổi chiến lược thay vì đổi cách viết.
            return AIMessage(content="Tuyến Hà Nội → Đà Nẵng chưa có trong dữ liệu của "
                                     "demo (search trả về matched = 0). Không thể tự "
                                     "quyết định thay khách: cần người chọn đổi điểm "
                                     "đi hoặc báo chưa hỗ trợ.")

        # ngan-sach: mỗi lượt dò hai chuyến chưa kiểm, đủ dữ kiện thì tự chốt.
        if not self._da_search(messages):
            return self._nhieu([("search_flights", self._args_tuyen(messages))])
        da_kiem = self._da_kiem(messages)
        con_lai = [m for m in DS_KIEM if m not in da_kiem]
        if con_lai:
            return self._nhieu([("check_seat", {"ma": m}) for m in con_lai[:self.k]])
        return AIMessage(content="Đã kiểm toàn bộ chuyến sáng thứ Năm: không chuyến nào "
                                 "dưới 1.200.000đ. Đề xuất nâng trần giá hoặc đổi giờ bay.")

    # ------------------------------------------------------------ tiện ích
    @staticmethod
    def _args_tuyen(messages) -> dict:
        return {"tu": "SGN", "den": "DAD", "ngay": "2026-10-08", "buoi": "sang"}

    def _chot_loi(self, tt: dict) -> str:
        if tt.get("trang_thai_dat_cho") == "confirmed" and tt.get("da_tra"):
            return tra_loi_thanh_cong(tt)
        return ("Kế hoạch đã thực thi xong nhưng tiêu chí hoàn thành chưa đạt; "
                "cần người quyết định bước tiếp theo.")

    def _goi(self, ten: str, args: dict) -> AIMessage:
        return self._nhieu([(ten, args)])

    def _nhieu(self, calls: list[tuple[str, dict]]) -> AIMessage:
        return AIMessage(content="", tool_calls=[
            {"name": ten, "args": args, "id": f"call_{self._luot}_{i}",
             "type": "tool_call"}
            for i, (ten, args) in enumerate(calls, 1)])

    @staticmethod
    def _dem_goi(messages, ten: str) -> int:
        return sum(1 for m in messages
                   for c in (getattr(m, "tool_calls", None) or [])
                   if c["name"] == ten)

    def _da_search(self, messages) -> bool:
        return self._dem_goi(messages, "search_flights") > 0

    def _da_kiem(self, messages) -> set:
        ra = set()
        for m in messages:
            if getattr(m, "type", "") != "tool":
                continue
            d = _doc(m.content)
            if isinstance(d, dict) and d.get("status") == "ok" and "ghe_trong" in d:
                ra.add(d.get("ma"))
        return ra


def tra_loi_thanh_cong(tt: dict) -> str:
    return (f"Đã đặt vé {tt.get('ma_chuyen')} (ghế {tt.get('ghe')}), khởi hành "
            f"{tt.get('gio')} ngày {tt.get('ngay')}, giá {_tien(tt.get('gia_dat_cho', 0))}, "
            f"đã thanh toán và xác nhận. Mã đặt chỗ {tt.get('ma_dat_cho')}.")


def _doc(content: Any) -> Any:
    from .harness import doc_json
    return doc_json(content)


def model_that():
    """Model thật, đọc SE373_MODEL trong .env. Chỉ dùng khi có API key.

    Ví dụ SE373_MODEL: "openai:gpt-4.1-mini" · "anthropic:claude-sonnet-4-5"
    """
    from langchain.chat_models import init_chat_model

    ten = os.environ.get("SE373_MODEL")
    if not ten:
        raise SystemExit(
            "Chưa đặt SE373_MODEL. Copy .env.example thành .env, điền model và khoá API,\n"
            "rồi chạy:  set -a && source .env && set +a"
        )
    return init_chat_model(ten)
