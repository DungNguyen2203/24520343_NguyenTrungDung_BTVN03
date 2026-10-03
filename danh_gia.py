# -*- coding: utf-8 -*-
"""SE373 · BTVN#3 · Đánh giá hiệu quả của agent với 3 mẫu thiết kế (yêu cầu 03).

Chạy 3 mẫu × 4 tình huống, in bảng so sánh và ghi ket_qua_danh_gia.md.

    python danh_gia.py

Chỉ số thu được từ harness, không phải cảm nhận:
    so_vong, so_tool      đếm thật trong phiên chạy
    token                 ước lượng theo công thức slide (3.000 nền, mỗi vòng +500)
    ly_do_dung            DAT_MUC_TIEU · CAN_NGUOI · PHAT_HIEN_LAP · BE_TAC ·
                          NGAN_SACH · KE_HOACH_VO_HIEU · CHUA_DAT_TIEU_CHI
    dat_tieu_chi          vị từ code trong harness.kiem_tieu_chi
    co_ban_giao           dừng bất thường có kèm báo cáo bàn giao 4 trường
"""
from __future__ import annotations

import sys

from lib.ba_mau import TINH_HUONG, chay

MAU = ("react", "plan", "lai")
THU_TU = ("chuan", "duyet", "lap", "ngan-sach")


def in_bang(ket_qua: list) -> None:
    print(f"{'Tình huống':<12}{'Mẫu':<7}{'Vòng':>5}{'Tool':>6}{'Token':>9} | "
          f"{'Lý do dừng':<32} | {'Đạt?':<6} | Bàn giao?")
    print("-" * 92)
    for kq in ket_qua:
        print(f"{kq.tinh_huong:<12}{kq.mau:<7}{kq.so_vong:>5}{kq.so_tool:>6}"
              f"{kq.token:>9} | {kq.ly_do_dung[:31]:<32} | "
              f"{('CÓ' if kq.dat_tieu_chi else 'không'):<6} | "
              f"{'có' if kq.co_ban_giao else 'không'}")


def ghi_markdown(ket_qua: list, duong_dan: str) -> None:
    d = {m: [kq for kq in ket_qua if kq.mau == m] for m in MAU}
    dong = []
    dong.append("# Kết quả đánh giá tự động · BTVN#3\n")
    dong.append("Sinh bởi `python danh_gia.py`. Mỗi dòng là một lượt chạy thật, "
                "chỉ số lấy từ lớp harness.\n")
    dong.append("| Tình huống | Mẫu | Vòng model | Lần gọi tool | Token ước lượng "
                "| Lý do dừng | Đạt tiêu chí | Bàn giao |")
    dong.append("|---|---|---:|---:|---:|---|---|---|")
    for kq in ket_qua:
        dong.append(f"| {kq.tinh_huong} | {kq.mau} | {kq.so_vong} | {kq.so_tool} | "
                    f"{kq.token:,} | {kq.ly_do_dung} | "
                    f"{'CÓ' if kq.dat_tieu_chi else 'không'} | "
                    f"{'có' if kq.co_ban_giao else 'không'} |".replace(",", "."))
    dong.append("\n## Tổng hợp theo mẫu\n")
    dong.append("| Mẫu | Tổng vòng | Tổng tool | Tổng token | Lượt đạt tiêu chí "
                "| Lượt có bàn giao |")
    dong.append("|---|---:|---:|---:|---:|---:|")
    for m in MAU:
        rows = d[m]
        dong.append(f"| {m} | {sum(r.so_vong for r in rows)} | "
                    f"{sum(r.so_tool for r in rows)} | "
                    f"{sum(r.token for r in rows):,} | "
                    f"{sum(1 for r in rows if r.dat_tieu_chi)}/{len(rows)} | "
                    f"{sum(1 for r in rows if r.co_ban_giao)}/{len(rows)} |"
                    .replace(",", "."))
    with open(duong_dan, "w", encoding="utf-8") as f:
        f.write("\n".join(dong) + "\n")


def main() -> int:
    ket_qua = [chay(m, t) for t in THU_TU for m in MAU]
    print("=" * 84)
    print("ĐÁNH GIÁ 3 MẪU THIẾT KẾ TRÊN 4 TÌNH HUỐNG")
    print("=" * 84)
    in_bang(ket_qua)
    ghi_markdown(ket_qua, "ket_qua_danh_gia.md")
    print("\nĐã ghi ket_qua_danh_gia.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
