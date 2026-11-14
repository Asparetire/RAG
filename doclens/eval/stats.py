"""M5 统计检验（m5-runbook K7；Dror 协议 [L10] + bootstrap [L11]）。

不引 scipy/statsmodels——McNemar 用二项精确检验（纯 python），bootstrap 手写。
"""

from __future__ import annotations

import math
import random
from itertools import combinations


def mcnemar_exact(b: int, c: int) -> float:
    """McNemar 精确检验（双侧）：b/c=两配置不一致的双方格数。
    p = 2 * Σ_{i≤min(b,c)} C(b+c, i) / 2^(b+c)，截断到 1。"""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1))
    return min(1.0, tail * 2 / (2 ** n))


def bootstrap_ci_diff(values_a: list[float], values_b: list[float], *,
                      iters: int = 1000, seed: int = 42,
                      alpha: float = 0.05) -> dict:
    """配对 bootstrap：按题目重采样，返回均值差与 95% CI（value_a - value_b）。"""
    assert len(values_a) == len(values_b) and values_a, "配对数组长度需一致且非空"
    rng = random.Random(seed)
    n = len(values_a)
    diffs = []
    for _ in range(iters):
        idx = [rng.randrange(n) for _ in range(n)]
        da = sum(values_a[i] for i in idx) / n
        db = sum(values_b[i] for i in idx) / n
        diffs.append(da - db)
    diffs.sort()
    lo = diffs[int(iters * alpha / 2)]
    hi = diffs[min(iters - 1, int(iters * (1 - alpha / 2)))]
    mean_a = sum(values_a) / n
    mean_b = sum(values_b) / n
    return {"mean_diff": mean_a - mean_b, "ci_low": lo, "ci_high": hi,
            "significant": not (lo <= 0 <= hi)}


def rank_configs(config_scores: dict[str, list[float]], *, iters: int = 1000,
                 seed: int = 42) -> list[dict]:
    """多配置按均值排名 + 两两 bootstrap 显著性标记。"""
    order = sorted(config_scores.items(), key=lambda kv: -sum(kv[1]) / len(kv[1]))
    out = [{"config": name, "mean": sum(vals) / len(vals), "n": len(vals)}
           for name, vals in order]
    for i, a in enumerate(order):
        for b in order[i + 1:]:
            res = bootstrap_ci_diff(a["vals"], b["vals"], iters=iters, seed=seed)
            sig = f"{a['config']} > {b['config']}" if res["significant"] else "n.s."
            for row in out:
                if row["config"] == a["config"]:
                    row.setdefault("sig_vs", {})[b["config"]] = sig
    return out
