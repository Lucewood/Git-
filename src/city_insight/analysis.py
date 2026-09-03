"""核心分析逻辑（纯函数，无 UI / 无 Streamlit 依赖，便于单元测试）。"""

from __future__ import annotations

import numpy as np
import pandas as pd


def safe_corr(a: pd.Series, b: pd.Series) -> float:
    """安全计算相关系数；样本不足或零方差时返回 NaN。"""
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    if len(a) < 2 or a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(a.corr(b))


def corr_summary_text(
    corr: float, threshold: float, strong_msg: str, weak_msg: str
) -> str:
    """将相关系数转换为人类可读的洞察文本；数据不足时给出友好提示。"""
    if not np.isfinite(corr):
        return "数据量不足，无法计算有效相关性。"
    desc = strong_msg if abs(corr) > threshold else weak_msg
    return f"相关系数为 {corr:.3f}，{desc}。"


def detect_outliers(series: pd.Series, k: float = 1.5) -> pd.Series:
    """基于 IQR（四分位距）规则检测异常值，返回与输入等长的布尔掩码。

    Args:
        series: 数值序列。
        k: 离群系数（默认 1.5，即 Tukey's fence 标准）。
    """
    s = pd.to_numeric(series, errors="coerce")
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    lower, upper = q1 - k * iqr, q3 + k * iqr
    return (s < lower) | (s > upper)


def aggregate_by_province(df: pd.DataFrame) -> pd.DataFrame:
    """按省份聚合各指标均值与城市数量，按平均幸福度降序返回。"""
    agg = (
        df.groupby("province", as_index=False)
        .agg(
            happiness=("happiness", "mean"),
            income=("income", "mean"),
            house_price=("house_price", "mean"),
            population=("population", "sum"),
            value_index=("value_index", "mean"),
            composite_score=("composite_score", "mean"),
            city_count=("city", "count"),
        )
    )
    agg.columns = [
        "省份", "平均幸福度", "平均收入", "平均房价",
        "常住人口", "平均可负担指数", "平均综合宜居分", "城市数量",
    ]
    return agg.sort_values("平均幸福度", ascending=False).reset_index(drop=True)


def top_n(df: pd.DataFrame, column: str, n: int, ascending: bool = False) -> pd.DataFrame:
    """返回指定指标排名前（默认）或后 n 条记录。"""
    n = max(1, min(int(n), len(df)))
    return df.nlargest(n, column) if not ascending else df.nsmallest(n, column)


def percentile_rank(series: pd.Series) -> pd.Series:
    """计算每个值在序列中的百分位排名（0-1，值越大排名越靠前）。"""
    return series.rank(pct=True)


def describe_series(series: pd.Series) -> dict[str, float]:
    """输出序列的核心描述统计（对 NaN / 空序列安全）。"""
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return {
            "count": 0.0, "mean": float("nan"), "std": float("nan"),
            "min": float("nan"), "median": float("nan"), "max": float("nan"),
        }
    return {
        "count": float(len(s)),
        "mean": float(s.mean()),
        "std": float(s.std()),
        "min": float(s.min()),
        "median": float(s.median()),
        "max": float(s.max()),
    }
