"""纯 stdlib PNG 折线图渲染 + Aiyagari 4 张复现图（无 matplotlib 环境）。

图数据全部由 solve.py 的数值机器现算；PNG 编码用 zlib/struct 手写。
运行：uv run python checks/gen_figures_stdlib.py
"""
from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

import numpy as np

SRC = Path("workspace/challenges/local_c2643b50")
sys.path.insert(0, str(SRC))
import solve  # noqa: E402

SIGMA, RHO, MU = 0.2, 0.3, 1
N_A, A_MAX, SKEW = 200, 100.0, 2.0

# ---------- 最小 PNG 渲染器 ----------
W, H = 900, 560
MARGIN = 70

BLACK = (20, 20, 20)
GRAY = (190, 190, 190)
RED = (200, 40, 40)
BLUE = (40, 90, 200)
GREEN = (30, 140, 80)
ORANGE = (220, 130, 20)


class Canvas:
    def __init__(self, w: int = W, h: int = H):
        self.w, self.h = w, h
        self.px = bytearray([255] * (w * h * 3))

    def set(self, x: int, y: int, c: tuple[int, int, int]) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i:i + 3] = bytes(c)

    def line(self, x0, y0, x1, y1, c) -> None:
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            for ox in (0, 1):
                for oy in (0, 1):
                    self.set(x0 + ox, y0 + oy, c)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def save(self, path: Path) -> None:
        raw = b"".join(b"\x00" + bytes(self.px[y * self.w * 3:(y + 1) * self.w * 3])
                       for y in range(self.h))
        def chunk(tag: bytes, data: bytes) -> bytes:
            return (struct.pack(">I", len(data)) + tag + data
                    + struct.pack(">I", zlib.crc32(tag + data)))
        png = (b"\x89PNG\r\n\x1a\n"
               + chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(raw, 6))
               + chunk(b"IEND", b""))
        path.write_bytes(png)


def plot(series: list[tuple[np.ndarray, np.ndarray, tuple[int, int, int]]],
         path: Path, hline0: bool = False, vline: float | None = None) -> None:
    """series: [(x, y, color)]；自动坐标轴 + 网格。"""
    cv = Canvas()
    xs = np.concatenate([s[0] for s in series])
    ys = np.concatenate([s[1] for s in series])
    x0, x1 = float(xs.min()), float(xs.max())
    y0, y1 = float(ys.min()), float(ys.max())
    if vline is not None:
        x0 = min(x0, vline)
        x1 = max(x1, vline)
    if hline0:
        y0 = min(y0, 0.0)
        y1 = max(y1, 0.0)
    pad_y = (y1 - y0) * 0.06 or 1.0
    y0 -= pad_y
    y1 += pad_y

    def X(x):
        return MARGIN + (x - x0) / (x1 - x0) * (W - 2 * MARGIN)

    def Y(y):
        return H - MARGIN - (y - y0) / (y1 - y0) * (H - 2 * MARGIN)

    # 网格 + 轴
    for i in range(11):
        gx = MARGIN + i * (W - 2 * MARGIN) / 10
        gy = MARGIN + i * (H - 2 * MARGIN) / 10
        cv.line(gx, MARGIN, gx, H - MARGIN, GRAY)
        cv.line(MARGIN, gy, W - MARGIN, gy, GRAY)
    cv.line(MARGIN, H - MARGIN, W - MARGIN, H - MARGIN, BLACK)
    cv.line(MARGIN, MARGIN, MARGIN, H - MARGIN, BLACK)
    if hline0:
        cv.line(MARGIN, Y(0.0), W - MARGIN, Y(0.0), BLACK)
    if vline is not None:
        cv.line(X(vline), MARGIN, X(vline), H - MARGIN, RED)
    for x, y, c in series:
        order = np.argsort(x)
        x, y = x[order], y[order]
        for i in range(len(x) - 1):
            cv.line(X(x[i]), Y(y[i]), X(x[i + 1]), Y(y[i + 1]), c)
    cv.save(path)


# ---------- 计算 ----------

def main() -> None:
    ell, Pi = solve.efficiency_grid(RHO, SIGMA)
    a_grid = A_MAX * (np.linspace(0, 1, N_A) ** SKEW)
    r_star = 0.04043455  # 本 Run 实测（solve_run.log）
    w = solve.firm_w(r_star)

    # VFI 政策函数（与 solve.solve_household 同一数值过程）
    resources = w * ell[None, :] + (1.0 + r_star) * a_grid[:, None]
    c3 = resources[:, None, :] - a_grid[None, :, None]
    util = np.where(c3 >= solve.C_MIN, np.log(np.maximum(c3, solve.C_MIN)),
                    -np.inf)
    V = np.zeros((N_A, len(ell)))
    for _ in range(solve.VFI_MAXITER):
        Q = util + solve.BETA * (V @ Pi.T)[None, :, :]
        newV = Q.max(axis=1)
        policy = Q.argmax(axis=1)
        if np.abs(newV - V).max() < solve.VFI_TOL:
            V = newV
            break
        V = newV

    out = SRC / "figures"
    out.mkdir(exist_ok=True)

    # Fig 1: c(x) 与 a'(x)，最低/最高效率状态
    s1 = []
    for zi, col in [(0, BLUE), (len(ell) - 1, ORANGE)]:
        x = resources[:, zi]
        a_next = a_grid[policy[:, zi]]
        s1.append((x, x - a_next, col))       # c(x) 实线
        s1.append((x, a_next, GREEN))         # a'(x)
    plot(s1, out / "fig_1.png")
    print("fig_1 done", flush=True)

    # Fig 2: 单家庭 200 期总资源演化（真实马尔科夫抽样）
    rng = np.random.default_rng(20260918)
    T = 200
    z_idx = np.empty(T, dtype=int)
    z_idx[0] = len(ell) // 2
    for t in range(1, T):
        z_idx[t] = rng.choice(len(ell), p=Pi[z_idx[t - 1]])
    a_idx, xs = 0, []
    for t in range(T):
        i, z = a_idx, z_idx[t]
        xs.append(w * ell[z] + (1 + r_star) * a_grid[i])
        a_idx = int(policy[i, z])
    plot([(np.arange(T, dtype=float), np.array(xs), BLUE)],
         out / "fig_2.png")
    print("fig_2 done", flush=True)

    # Fig 3 + 4: A(r) vs K(r) 与超额需求
    r_grid = np.linspace(0.030, 0.041, 8)
    A_vals = []
    for r in r_grid:
        a_bar, info, _ = solve.solve_household(r, MU, ell, Pi, a_grid)
        A_vals.append(a_bar)
        print(f"A({r:.4f})={a_bar:.4f} ({info[0]} iters)", flush=True)
    A_arr = np.array(A_vals)
    K_arr = np.array([solve.firm_K(r) for r in r_grid])
    plot([(A_arr, r_grid * 100, BLUE), (K_arr, r_grid * 100, ORANGE)],
         out / "fig_3.png")
    plot([(r_grid * 100, A_arr - K_arr, BLUE)], out / "fig_4.png",
         hline0=True, vline=r_star * 100)
    print("fig_3/fig_4 done ->", out)


if __name__ == "__main__":
    main()
