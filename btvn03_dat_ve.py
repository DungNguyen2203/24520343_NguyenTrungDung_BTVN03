# -*- coding: utf-8 -*-
"""SE373 · BTVN#3 · Dựng agent đặt vé bằng LangChain.

Một agent, một bộ tool, một lớp harness; đổi mẫu thiết kế và tình huống để
thấy hành vi khác nhau. Chạy lần lượt:

    python btvn03_dat_ve.py --mau react --tinh-huong chuan
        ReAct: mỗi lượt model chọn một bước, dừng khi đạt tiêu chí.

    python btvn03_dat_ve.py --mau plan --tinh-huong chuan
        Plan-then-Execute: sinh trọn kế hoạch một lần rồi thực thi.

    python btvn03_dat_ve.py --mau lai --tinh-huong lap
        Lai: lập kế hoạch ngắn, thực thi, lập lại theo quan sát → thoát lặp.

    python btvn03_dat_ve.py --tat-ca
        Chạy 12 tổ hợp (3 mẫu × 4 tình huống) và in bảng so sánh.

Bốn tình huống:
    chuan      có chuyến trong hạn mức tự quyết → đặt được bình thường
    duyet      chuyến không hoàn/vượt hạn mức → kiểm quyền chặn, bàn giao
    lap        tuyến không có dữ liệu → dễ lặp, LoopDetector phải bắt
    ngan-sach  không chuyến nào đạt trần giá → chạm ngân sách, bàn giao
"""
import argparse
import sys

from lib.ba_mau import TINH_HUONG, chay

MAU = ("react", "plan", "lai")
THU_TU_TINH_HUONG = ("chuan", "duyet", "lap", "ngan-sach")


def in_bang(ket_qua: list) -> None:
    rong = 70
    print("=" * rong)
    print("BẢNG SO SÁNH 3 MẪU × 4 TÌNH HUỐNG")
    print("=" * rong)
    print(f"{'Tình huống':<12}{'Mẫu':<7}{'Vòng':>5}{'Tool':>6}{'Token':>9} | "
          f"{'Lý do dừng':<30} | {'Đạt?':<6} | Bàn giao?")
    print("-" * rong)
    for kq in ket_qua:
        print(f"{kq.tinh_huong:<12}{kq.mau:<7}{kq.so_vong:>5}{kq.so_tool:>6}"
              f"{kq.token:>9} | {kq.ly_do_dung[:29]:<30} | "
              f"{('CÓ' if kq.dat_tieu_chi else 'không'):<6} | "
              f"{'có' if kq.co_ban_giao else 'không'}")
    print("-" * rong)


def main() -> int:
    p = argparse.ArgumentParser(description="BTVN#3 · agent đặt vé · 3 mẫu thiết kế")
    p.add_argument("--mau", default="react", choices=MAU)
    p.add_argument("--tinh-huong", default="chuan", choices=THU_TU_TINH_HUONG,
                   help="chuan | duyet | lap | ngan-sach")
    p.add_argument("--tat-ca", action="store_true",
                   help="chạy cả 12 tổ hợp và in bảng so sánh")
    args = p.parse_args()

    if args.tat_ca:
        ket_qua = [chay(m, t) for t in THU_TU_TINH_HUONG for m in MAU]
        in_bang(ket_qua)
        return 0

    chay(args.mau, args.tinh_huong, in_trace=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
