"""从本 Run 实测的 Aiyagari 模型生成 4 张复现图（对应论文 Fig 1-4）。

全部曲线由 solve.py 的同一套数值机器现算，不复制论文原图。
运行：uv run --with matplotlib python checks/gen_figures.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

SRC = Path("workspace/challenges/local_c2643b50")
sys.path.insert(0, str(SRC))
import solve  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SIGMA, RHO, MU = 0.2, 0.3, 1  # 基线格点（实测 r*=4.0435%）
N_A, A_MAX, SKEW = 200, 100.0, 2.0


def baseline():
    ell, Pi = solve.efficiency_grid(RHO, SIGMA)
    a_grid = A_MAX * (np.linspace(0, 1, N_A) ** SKEW)
    return ell, Pi, a_grid


def vfi_policy(r, mu, ell, Pi, a_grid):
    """与 solve.solve_household 同一 VFI，额外返回政策函数索引。"""
    w = solve.firm_w(r)
    resources = w * ell[None, :] + (1.0 + r) * a_grid[:, None]
    c = resources[:, None, :] - a_grid[None, :, None]
    if mu == 1:
        util = np.where(c >= solve.C_MIN, np.log(np.maximum(c, solve.C_MIN)),
                        -np.inf)
    else:
        util = np.where(c >= solve.C_MIN,
                        c ** (1.0 - mu) / (1.0 - mu), -np.inf)
    V = np.zeros((len(a_grid), len(ell)))
    for _ in range(solve.VFI_MAXITER):
        EV = V @ Pi.T
        Q = util + solve.BETA * EV[None, :, :]
        newV = Q.max(axis=1)
        policy = Q.argmax(axis=1)
        if np.abs(newV - V).max() < solve.VFI_TOL:
            V = newV
            break
        V = newV
    return policy, resources


def main() -> None:
    ell, Pi, a_grid = baseline()
    r_star = 0.04043455  # 本 Run 实测（solve_run.log）
    w = solve.firm_w(r_star)
    policy, resources = vfi_policy(r_star, MU, ell, Pi, a_grid)
    out = SRC / "figures"
    out.mkdir(exist_ok=True)

    # Fig 1: Consumption and Assets as Functions of Total Resources
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for zi, label in [(0, f"lowest efficiency (ℓ={ell[0]:.2f})"),
                      (len(ell) - 1, f"highest efficiency (ℓ={ell[-1]:.2f})")]:
        x = resources[:, zi]
        a_next = a_grid[policy[:, zi]]
        c = x - a_next
        order = np.argsort(x)
        ax.plot(x[order], c[order], label=f"c(x), {label}")
        ax.plot(x[order], a_next[order], "--", label=f"a'(x), {label}")
    ax.set_xlabel("Total resources x = w·ℓ + (1+r)·a")
    ax.set_ylabel("Consumption / next-period assets")
    ax.set_title("Fig 1 (repro): Consumption and assets vs total resources\n"
                 f"σ={SIGMA}, ρ={RHO}, μ={MU}, r*={r_star*100:.4f}% (computed)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "fig_1.png", dpi=130)
    plt.close(fig)

    # Fig 2: Evolution of Total Resources（单个家庭 200 期模拟，真实马尔科夫链抽样）
    rng = np.random.default_rng(20260918)
    T = 200
    z_idx = np.empty(T, dtype=int)
    z_idx[0] = len(ell) // 2
    for t in range(1, T):
        z_idx[t] = rng.choice(len(ell), p=Pi[z_idx[t - 1]])
    a_idx = 0
    xs = []
    for t in range(T):
        i, z = a_idx, z_idx[t]
        xs.append(w * ell[z] + (1 + r_star) * a_grid[i])
        a_idx = int(policy[i, z])
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(range(T), xs, lw=1)
    ax.set_xlabel("Period t")
    ax.set_ylabel("Total resources x_t")
    ax.set_title("Fig 2 (repro): Evolution of total resources, single household\n"
                 f"σ={SIGMA}, ρ={RHO}, μ={MU}, r*={r_star*100:.4f}% (computed)")
    fig.tight_layout()
    fig.savefig(out / "fig_2.png", dpi=130)
    plt.close(fig)

    # Fig 3: Interest Rate versus Per Capita Assets（家计供给 A(r) 与厂商需求 K(r)）
    r_grid = np.linspace(0.030, 0.041, 8)
    A_vals = []
    for r in r_grid:
        a_bar, info, _ = solve.solve_household(r, MU, ell, Pi, a_grid)
        A_vals.append(a_bar)
        print(f"A({r:.4f}) = {a_bar:.4f}  (vfi {info[0]} iters)", flush=True)
    K_vals = [solve.firm_K(r) for r in r_grid]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(np.array(A_vals), r_grid * 100, "o-", label="A(r) household asset supply")
    ax.plot(np.array(K_vals), r_grid * 100, "s--", label="K(r) firm capital demand")
    a_eq, _, _ = solve.solve_household(r_star, MU, ell, Pi, a_grid)
    ax.axvline(a_eq, color="gray", lw=0.8, alpha=0.6)
    ax.annotate(f"equilibrium r*={r_star*100:.4f}%", (a_eq, r_star * 100),
                textcoords="offset points", xytext=(8, -14), fontsize=8)
    ax.set_xlabel("Per capita assets")
    ax.set_ylabel("Net interest rate r (%)")
    ax.set_title("Fig 3 (repro): Interest rate vs per capita assets (computed)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "fig_3.png", dpi=130)
    plt.close(fig)

    # Fig 4: Steady-State Determination（超额需求 A(r)-K(r) 过零）
    excess = np.array(A_vals) - np.array(K_vals)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(r_grid * 100, excess, "o-")
    ax.axhline(0, color="gray", lw=0.8)
    ax.axvline(r_star * 100, color="red", lw=0.8, ls="--",
               label=f"computed r* = {r_star*100:.4f}%")
    ax.set_xlabel("Net interest rate r (%)")
    ax.set_ylabel("Excess asset demand A(r) − K(r)")
    ax.set_title("Fig 4 (repro): Steady-state determination (computed)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "fig_4.png", dpi=130)
    plt.close(fig)
    print("figures written to", out)


if __name__ == "__main__":
    main()
