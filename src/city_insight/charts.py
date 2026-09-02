"""图表工厂：所有绘图函数返回 matplotlib Figure 对象（纯渲染，无 UI 依赖）。

约定：
- 返回的 figure 已执行 tight_layout（除非显式关闭），可直接 st.pyplot(fig)；
- 调用方负责 plt.close(fig) 释放内存；
- 中文字体 / 风格在 setup_plot_style() 中统一配置。
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # 必须在导入 pyplot 之前设置，规避 GUI 后端

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from .config import (
    FONT_SANS,
    ACCENT_COLOR,
    DANGER_COLOR,
    REG_COLOR,
    COLUMN_LABELS,
    METRIC_UNITS,
)


def setup_plot_style() -> None:
    """设置全局绘图风格与中文字体。

    注意：必须先调用 sns.set_style（它会重置 font.sans-serif 等 rcParams），
    再设置中文字体，否则字体配置会被 seaborn 覆盖。
    """
    sns.set_style("whitegrid", {"axes.grid": True, "grid.linestyle": "--", "grid.alpha": 0.3})
    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = FONT_SANS
    matplotlib.rcParams["axes.unicode_minus"] = False


def _finalize(fig: plt.Figure, tight: bool = True) -> plt.Figure:
    if tight:
        fig.tight_layout()
    return fig


def _add_bar_labels(ax, bars, values, fmt: str = "{:.2f}", offset: float = 0.05, fontsize: int = 9) -> None:
    """在条形右侧标注数值。"""
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_width() + offset,
            bar.get_y() + bar.get_height() / 2,
            fmt.format(val),
            va="center",
            fontsize=fontsize,
        )


# ---------------------------------------------------------------------------
# 关联分析
# ---------------------------------------------------------------------------
def scatter_with_regression(
    df: pd.DataFrame,
    x: str,
    y: str,
    *,
    color: str,
    xlabel: str,
    ylabel: str,
    title: str,
    n_boot: int = 100,
    figsize: tuple[float, float] = (6, 4.5),
) -> plt.Figure:
    """散点图 + 回归线；样本过少时自动跳过回归线。"""
    fig, ax = plt.subplots(figsize=figsize)
    sns.scatterplot(
        data=df, x=x, y=y, alpha=0.6, s=60, color=color,
        edgecolors="white", linewidth=0.5, ax=ax,
    )
    if len(df) >= 2:
        sns.regplot(
            data=df, x=x, y=y, scatter=False, color=REG_COLOR, n_boot=n_boot,
            line_kws={"linewidth": 2, "linestyle": "--"}, ax=ax,
        )
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_title(title, fontsize=13, fontweight="bold")
    return _finalize(fig)


def correlation_heatmap(
    df: pd.DataFrame,
    cols: tuple[str, ...],
    *,
    cmap: str = "coolwarm",
    figsize: tuple[float, float] = (7, 5.2),
    annot_fmt: str = ".3f",
) -> plt.Figure:
    """指标相关性矩阵热力图（轴标签自动映射为中文）。"""
    sub = df[list(cols)].dropna()
    if len(sub) < 2:
        fig, ax = plt.subplots(figsize=figsize)
        ax.text(0.5, 0.5, "数据量不足，无法绘制相关性热力图",
                ha="center", va="center", fontsize=12)
        ax.axis("off")
        return _finalize(fig)
    corr = sub.corr()
    fig, ax = plt.subplots(figsize=figsize)
    sns.heatmap(
        corr, annot=True, fmt=annot_fmt, cmap=cmap, center=0,
        annot_kws={"size": 9}, ax=ax, cbar_kws={"shrink": 0.8},
    )
    labels = [COLUMN_LABELS.get(c, c) for c in cols]
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_yticklabels(labels, rotation=0)
    ax.set_title("指标相关性热力图", fontsize=13, fontweight="bold")
    return _finalize(fig)


# ---------------------------------------------------------------------------
# 排名条形图
# ---------------------------------------------------------------------------
def barh_ranking(
    data: pd.DataFrame,
    column: str,
    *,
    label_col: str = "city",
    color: str,
    title: str,
    xlabel: str,
    fmt: str = "{:.2f}",
    figsize: tuple[float, float] | None = None,
) -> plt.Figure:
    """横向条形图；data 需按 column 升序排列（第一名显示在最上方）。

    Args:
        data: 已按 column 升序排列的数据。
        label_col: 条形标签列名（默认 "city"）。
    """
    n = len(data)
    if n == 0:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "无数据可展示", ha="center", va="center", fontsize=12)
        ax.axis("off")
        return _finalize(fig)
    if figsize is None:
        figsize = (8, max(4, n * 0.25 + 2))
    fig, ax = plt.subplots(figsize=figsize)
    bars = ax.barh(data[label_col], data[column], color=color, edgecolor="white")
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.grid(axis="x", alpha=0.3, linestyle="--")

    width_max = data[column].max()
    offset = width_max * 0.02 if width_max > 0 else 0.1
    _add_bar_labels(ax, bars, data[column], fmt=fmt, offset=offset)
    return _finalize(fig)


def affordability_overview(
    df: pd.DataFrame,
    *,
    color: str,
    figsize: tuple[float, float] = (7, 5),
) -> plt.Figure:
    """全量城市可负担指数柱状图（带阈值参考线）。"""
    sorted_df = df.sort_values("value_index", ascending=False).reset_index(drop=True)
    fig, ax = plt.subplots(figsize=figsize)
    ax.bar(
        range(len(sorted_df)), sorted_df["value_index"],
        color=color, alpha=0.8, width=1.0,
    )
    thresholds = [
        (10, "高可负担线 (10)", "red"),
        (5, "中等可负担线 (5)", "orange"),
    ]
    for val, label, c in thresholds:
        ax.axhline(y=val, color=c, linestyle="--", alpha=0.7, label=label)
    ax.set_xlabel("城市排名", fontsize=11)
    ax.set_ylabel("可负担指数", fontsize=11)
    ax.set_title("全国城市住房可负担性全貌", fontsize=13, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    return _finalize(fig)



# ---------------------------------------------------------------------------
# 分布
# ---------------------------------------------------------------------------
def distribution_hist(
    series: pd.Series,
    *,
    color: str,
    title: str,
    xlabel: str,
    kde: bool = True,
    figsize: tuple[float, float] = (7, 4.5),
) -> plt.Figure:
    """数值分布直方图（可选核密度曲线）。"""
    s = pd.to_numeric(series, errors="coerce").dropna()
    fig, ax = plt.subplots(figsize=figsize)
    if kde and len(s) > 1 and s.nunique() > 1:
        sns.histplot(s, kde=True, color=color, alpha=0.7, ax=ax)
    else:
        ax.hist(s, bins="auto", color=color, alpha=0.7, edgecolor="white")
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel("城市数量", fontsize=11)
    ax.set_title(title, fontsize=13, fontweight="bold")
    return _finalize(fig)


# ---------------------------------------------------------------------------
# 城市对比
# ---------------------------------------------------------------------------
def city_comparison(
    df: pd.DataFrame,
    cities: list[str],
    metrics: tuple[str, ...],
    *,
    color: str,
    figsize: tuple[float, float] = (14, 8),
) -> plt.Figure:
    """多指标城市对比：每个指标一个子图，横向条形图。"""
    n_metrics = len(metrics)
    cols = 2
    rows = int(np.ceil(n_metrics / cols))
    fig, axes = plt.subplots(rows, cols, figsize=figsize, squeeze=False)
    data = df[df["city"].isin(cities)].set_index("city")

    for i, metric in enumerate(metrics):
        ax = axes[i // cols][i % cols]
        if metric not in data.columns:
            ax.axis("off")
            continue
        sub = data[metric].dropna().sort_values()
        if sub.empty:
            ax.axis("off")
            continue
        bars = ax.barh(sub.index, sub.values, color=color, edgecolor="white")
        ax.set_title(COLUMN_LABELS.get(metric, metric), fontsize=12, fontweight="bold")
        ax.set_xlabel(METRIC_UNITS.get(metric, metric), fontsize=9)
        for bar, val in zip(bars, sub.values):
            ax.text(
                bar.get_width() * 1.01,
                bar.get_y() + bar.get_height() / 2,
                f"{val:,.1f}",
                va="center",
                fontsize=8,
            )
        ax.grid(axis="x", alpha=0.3, linestyle="--")

    for i in range(n_metrics, rows * cols):
        axes[i // cols][i % cols].axis("off")

    fig.suptitle("多城市多指标对比", fontsize=14, fontweight="bold")
    return _finalize(fig, tight=False)


def city_profile_chart(
    profile: pd.Series,
    *,
    color: str,
    figsize: tuple[float, float] = (7, 5),
) -> plt.Figure:
    """城市画像：各指标在筛选范围内的百分位排名（0-100）条形图。

    Args:
        profile: 以指标名为索引、值为百分位（0-100）的 Series。
    """
    sub = profile.dropna().sort_values()
    if sub.empty:
        return plt.figure(figsize=figsize)  # 空占位图
    fig, ax = plt.subplots(figsize=figsize)
    labels = [COLUMN_LABELS.get(m, m) for m in sub.index]
    bars = ax.barh(range(len(sub)), sub.values, color=color, edgecolor="white")
    ax.set_yticks(range(len(sub)))
    ax.set_yticklabels(labels)
    ax.set_xlim(0, 100)
    ax.set_xlabel("百分位排名（0-100）", fontsize=11)
    ax.set_title("该城市在筛选范围内的百分位画像", fontsize=13, fontweight="bold")
    for bar, val in zip(bars, sub.values):
        ax.text(val + 1, bar.get_y() + bar.get_height() / 2, f"{val:.0f}",
                va="center", fontsize=9)
    return _finalize(fig)


# ---------------------------------------------------------------------------
# 异常值
# ---------------------------------------------------------------------------
def outlier_scatter(
    df: pd.DataFrame,
    x: str,
    y: str,
    outlier_mask: pd.Series,
    *,
    color: str,
    outlier_color: str = DANGER_COLOR,
    xlabel: str,
    ylabel: str,
    title: str,
    figsize: tuple[float, float] = (7, 5),
) -> plt.Figure:
    """散点图，异常值用红色高亮。"""
    fig, ax = plt.subplots(figsize=figsize)
    normal = df[~outlier_mask]
    outs = df[outlier_mask]
    ax.scatter(
        normal[x], normal[y], alpha=0.5, s=45, color=color,
        edgecolors="white", linewidth=0.4, label="正常值",
    )
    if not outs.empty:
        ax.scatter(
            outs[x], outs[y], alpha=0.9, s=70, color=outlier_color,
            edgecolors="black", linewidth=0.6, label="异常值",
        )
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, linestyle="--")
    return _finalize(fig)
