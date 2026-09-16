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
    # 横轴标签旋转 45°：比 30° 的水平投影更窄，可避免相邻中文标签（如
    # “房价(元/㎡)”与“常住人口(万)”）在宽列名场景下文字重叠
    ax.set_xticklabels(labels, rotation=45, ha="right")
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
    # 必须执行 tight_layout 并为 suptitle 预留顶部空间（rect），否则
    # 下方子图的标题会与上方子图的坐标轴标签 / 刻度标签发生文字重叠
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    return fig


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


# ---------------------------------------------------------------------------
# 房价趋势与机器学习预测
# ---------------------------------------------------------------------------
def house_trend_forecast_chart(
    hist: pd.DataFrame,
    fcst: pd.DataFrame,
    *,
    hist_color: str = "steelblue",
    forecast_color: str = REG_COLOR,
    conf: float = 0.8,
    title: str = "房价历史走势与机器学习预测",
    ylabel: str = "房价（元/㎡）",
    figsize: tuple[float, float] = (10, 5.4),
) -> plt.Figure:
    """历史走势（实线）+ 机器学习递归预测（虚线）与置信区间扇形图。

    Args:
        hist: 历史长表，需含 year / house_price。
        fcst: 预测表，需含 year / point / low / high。
        conf: 置信度（0-1），用于图例文案与区间标注。
    """
    from matplotlib.ticker import FuncFormatter

    fig, ax = plt.subplots(figsize=figsize)
    hist = hist.sort_values("year")
    fcst = fcst.sort_values("year")

    ax.plot(
        hist["year"], hist["house_price"], color=hist_color,
        marker="o", markersize=3.5, linewidth=1.8, label="历史均价",
    )
    if not fcst.empty:
        ax.plot(
            fcst["year"], fcst["point"], color=forecast_color,
            marker="o", markersize=3.5, linestyle="--", linewidth=2,
            label="机器学习预测（中位）",
        )
        ax.fill_between(
            fcst["year"], fcst["low"], fcst["high"],
            color=forecast_color, alpha=0.15, linewidth=0,
            label=f"预测区间（{conf * 100:.0f}% 置信）",
        )
    if not hist.empty and not fcst.empty:
        boundary = int(hist["year"].max()) + 0.5
        ax.axvline(boundary, color="#888", linestyle=":", linewidth=1.2, alpha=0.9)

    ax.set_xlabel("年份", fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f"{v:,.0f}"))
    ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
    ax.legend(fontsize=9, loc="upper left")
    return _finalize(fig)


def house_backtest_chart(
    hist: pd.DataFrame,
    backtest: pd.DataFrame,
    *,
    hist_color: str = "steelblue",
    actual_color: str = "#2e8b57",
    pred_color: str = REG_COLOR,
    conf: float = 0.8,
    title: str = "外样本回测：预测 vs 实际房价",
    ylabel: str = "房价（元/㎡）",
    figsize: tuple[float, float] = (9.6, 5.0),
) -> plt.Figure:
    """walk-forward 外样本回测图：真实历史 + 回测实际 + 模型逐点预测与区间。

    Args:
        hist: 历史长表（year / house_price），仅取近端年份用于对照背景。
        backtest: 回测表（year / point / low / high / actual）。
    """
    from matplotlib.ticker import FuncFormatter

    bt = backtest.sort_values("year").reset_index(drop=True)
    years = bt["year"].tolist()

    fig, ax = plt.subplots(figsize=figsize)
    if hist is not None and not hist.empty:
        win_start = max(int(years[0]) - 4, int(hist["year"].min()))
        win = hist[(hist["year"] >= win_start) & (hist["year"] <= int(years[-1]))]
        ax.plot(
            win["year"], win["house_price"], color=hist_color,
            linewidth=1.6, marker="o", markersize=3, label="历史实际均价",
        )
    ax.plot(
        years, bt["actual"], color=actual_color, marker="o", markersize=6,
        linewidth=2.0, label="回测期实际房价",
    )
    ax.plot(
        years, bt["point"], color=pred_color, marker="D", markersize=6,
        linestyle="--", linewidth=2.0, label="模型预测（外样本）",
    )
    if {"low", "high"}.issubset(bt.columns):
        ax.fill_between(
            years, bt["low"], bt["high"],
            color=pred_color, alpha=0.16, linewidth=0,
            label=f"预测区间（{conf * 100:.0f}%）",
        )
    ax.set_xlabel("年份", fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f"{v:,.0f}"))
    ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
    ax.legend(fontsize=9, loc="upper left")
    return _finalize(fig)



# ---------------------------------------------------------------------------
# 就业指导与支柱产业
# ---------------------------------------------------------------------------
# 匹配度构成图的内置维度配色（键 = 维度关键词，可用 color_map 覆盖）
CAREER_DIM_COLORS: dict[str, str] = {
    "skill": "#4e79a7",   # 技能匹配
    "salary": "#f28e2b",  # 薪资待遇
    "growth": "#59a14f",  # 发展空间
    "scale": "#8b5cf6",   # 岗位规模
    "life": "#e15759",    # 生活宜居
}
# 兜底配色：维度关键词识别失败时按序取色，保证任意命名下各段颜色互不相同
_FALLBACK_DIM_COLORS: tuple[str, ...] = (
    "#4e79a7", "#f28e2b", "#59a14f", "#b07aa1", "#e15759",
    "#76b7b2", "#edc948", "#9c755f",
)
# 列名 → 维度关键词的常见前后缀（w_skill_score / skill_score / weight_skill 等）
_DIM_KEY_PREFIXES: tuple[str, ...] = ("weight_", "w_")
_DIM_KEY_SUFFIXES: tuple[str, ...] = ("_weight", "_score", "_pct")
# 维度关键词别名（推荐引擎中「发展空间」的列名为 demand_score）
_DIM_KEY_ALIASES: dict[str, str] = {"demand": "growth", "life_quality": "life"}


def _first_unused_color(used: set[str], index: int) -> str:
    """从兜底配色中按位置轮转，返回第一个尚未被占用的颜色。"""
    total = len(_FALLBACK_DIM_COLORS)
    for offset in range(total):
        candidate = _FALLBACK_DIM_COLORS[(index + offset) % total]
        if candidate not in used:
            return candidate
    return "#999999"


def _dimension_key(text: object) -> str | None:
    """把列名 / 图例名归一化为维度关键词（如 ``w_skill_score`` → ``skill``）。

    归一化步骤：小写 → 去除 ``w_`` / ``weight_`` 前缀与 ``_score`` 等后缀 →
    查别名表 → 与内置维度关键词精确 / 包含匹配；无法识别时返回 None。
    """
    token = str(text).strip().lower()
    if not token:
        return None
    candidates = [token]
    stripped = token
    for prefix in _DIM_KEY_PREFIXES:
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix):]
            break
    for suffix in _DIM_KEY_SUFFIXES:
        if stripped.endswith(suffix):
            stripped = stripped[: -len(suffix)]
            break
    stripped = stripped.strip("_ ")
    if stripped:
        candidates.append(stripped)
    candidates.extend(_DIM_KEY_ALIASES.get(item, "") for item in tuple(candidates))
    for candidate in candidates:
        if candidate and candidate in CAREER_DIM_COLORS:
            return candidate
    # 中文图例名（技能匹配 / 生活宜居）或含关键词的自定义命名：宽松包含匹配
    for key in CAREER_DIM_COLORS:
        if any(key in candidate for candidate in candidates if candidate):
            return key
    return None


def _resolve_dim_colors(
    columns: tuple[str, ...],
    labels: tuple[str, ...],
    color_map: dict[str, str] | None = None,
) -> list[str]:
    """解析每个维度的条形配色，并保证同一张图内各维度颜色互不相同。

    解析优先级：color_map 精确键（列名 / 中文图例名）→ color_map 归一化维度键
    → 内置 CAREER_DIM_COLORS → 兜底配色；已占用的颜色自动跳过，
    因此即使维度命名（如 ``w_demand_score``）与配色键不一致，也不会退化为同色。
    """
    explicit = {str(key): str(value) for key, value in (color_map or {}).items()}
    palette = {**CAREER_DIM_COLORS, **explicit}
    colors: list[str] = []
    used: set[str] = set()
    for index, column in enumerate(columns):
        label = labels[index] if index < len(labels) else ""
        tokens = [token for token in (str(column).strip(), str(label).strip()) if token]
        color = ""
        # ① 显式覆盖：列名优先，其次中文图例名
        for token in tokens:
            if token in explicit:
                color = explicit[token]
                break
        # ② 归一化维度键（w_skill_score / demand_score / 技能匹配 …）
        if not color:
            for token in tokens:
                key = _dimension_key(token)
                if key and key in palette:
                    color = palette[key]
                    break
        # ③ 未命中或与已用颜色撞色 → 换用兜底配色中未被占用的颜色
        if not color or color in used:
            color = _first_unused_color(used, index)
        used.add(color)
        colors.append(color)
    return colors


def career_score_breakdown(
    data: pd.DataFrame,
    *,
    columns: tuple[str, ...],
    labels: tuple[str, ...],
    label_col: str = "city",
    color_map: dict[str, str] | None = None,
    title: str = "推荐匹配度构成（加权得分）",
    xlabel: str = "加权得分（0-100）",
    figsize: tuple[float, float] | None = None,
) -> plt.Figure:
    """推荐匹配度构成：各维度「加权贡献」的水平堆叠条形图。

    Args:
        data: 需含 label_col；columns 中缺失的维度列按 0 分处理，且数据应已按总分降序排列。
        columns: 维度列名（子得分 0-100，调用方需预先按权重折算为贡献值）。
        labels: 与 columns 等长的中文图例名。
        color_map: 维度 → 颜色。键可为列名（``w_skill_score``）、中文图例名
            （``技能匹配``）或维度关键词（``skill``）；未命中的维度按内置
            CAREER_DIM_COLORS / 兜底配色取色，且同一张图内颜色互不相同。
    """
    if data.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "无数据可展示", ha="center", va="center", fontsize=12)
        ax.axis("off")
        return _finalize(fig)

    order = [str(v) for v in data[label_col]]
    if figsize is None:
        figsize = (9, max(3.6, len(order) * 0.42 + 2))
    fig, ax = plt.subplots(figsize=figsize)

    left = np.zeros(len(data))
    y_pos = np.arange(len(data))
    # 每维度一种颜色（互不相同），确保图例与条形可区分
    colors = _resolve_dim_colors(columns, labels, color_map)
    for column, label, color in zip(columns, labels, colors):
        if column in data.columns:
            values = pd.to_numeric(data[column], errors="coerce").fillna(0.0).to_numpy()
        else:
            values = np.zeros(len(data))  # 字段缺失时该维度按 0 分计入
        ax.barh(
            y_pos, values, left=left, color=color,
            edgecolor="white", linewidth=0.6, label=label,
        )
        left += values

    ax.set_yticks(y_pos)
    ax.set_yticklabels(order)
    ax.invert_yaxis()  # 第一名显示在最上方
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.grid(axis="x", alpha=0.3, linestyle="--")
    ax.legend(
        fontsize=9, loc="lower right",
        ncol=min(3, max(1, len(columns))),
        framealpha=0.9,  # 半透明底避免遮挡条形，同时保证图例配色可辨
    )
    for idx, total in enumerate(left):
        ax.text(total + 0.6, idx, f"{total:.0f}", va="center", fontsize=9)
    return _finalize(fig)


def salary_demand_scatter(
    data: pd.DataFrame,
    *,
    x: str = "avg_salary",
    y: str = "demand_index",
    size_col: str | None = "share_pct",
    label_col: str = "category",
    color: str,
    highlight_col: str | None = None,
    highlight_color: str = DANGER_COLOR,
    xlabel: str = "平均月薪（元/月）",
    ylabel: str = "人才需求景气指数（0-100）",
    title: str = "支柱产业「薪资 × 需求」分布",
    figsize: tuple[float, float] = (8.4, 5.4),
) -> plt.Figure:
    """支柱产业散点图：横轴薪资、纵轴需求景气、点大小 = 就业占比。

    Args:
        highlight_col: 若提供，则该列非空（且非空串）的点用高亮色标出，
            用于标记推荐结果命中的产业。
    """
    fig, ax = plt.subplots(figsize=figsize)
    frame = data.dropna(subset=[x, y]).copy()
    if frame.empty:
        ax.text(0.5, 0.5, "无数据可展示", ha="center", va="center", fontsize=12)
        ax.axis("off")
        return _finalize(fig)

    if size_col and size_col in frame.columns:
        sizes = pd.to_numeric(frame[size_col], errors="coerce").fillna(1.0)
        span = max(float(sizes.max() - sizes.min()), 1e-9)
        sizes = 30.0 + (sizes - sizes.min()) / span * 260.0
    else:
        sizes = pd.Series(60.0, index=frame.index)

    if highlight_col and highlight_col in frame.columns:
        raw = frame[highlight_col]
        mask = raw.notna() & (raw.astype(str).str.strip() != "")
    else:
        mask = pd.Series(False, index=frame.index)

    for selected, point_color, label, edge, alpha in (
        (mask, highlight_color, "推荐命中", "black", 0.95),
        (~mask, color, "其他产业", "white", 0.6),
    ):
        sub = frame[selected]
        if sub.empty:
            continue
        ax.scatter(
            sub[x], sub[y], s=sizes.loc[sub.index], alpha=alpha,
            color=point_color, edgecolors=edge, linewidth=0.6, label=label,
        )

    # 标注各行业大类的代表点（每个大类取薪资最高的一个，最多 8 个）
    if label_col in frame.columns:
        representatives = (
            frame.sort_values(x, ascending=False)
            .drop_duplicates(subset=[label_col])
            .head(8)
        )
        for _, row in representatives.iterrows():
            ax.annotate(
                str(row[label_col]), (row[x], row[y]),
                textcoords="offset points", xytext=(5, 4), fontsize=8, alpha=0.85,
            )

    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.legend(fontsize=9, loc="lower right")
    return _finalize(fig)


def skill_demand_chart(
    data: pd.DataFrame,
    *,
    value_col: str = "demand_heat",
    label_col: str = "skill",
    color: str = "#667eea",
    highlight_label: str = "已具备",
    highlight_color: str = "#2e8b57",
    title: str = "技能需求热度榜",
    xlabel: str = "需求热度（出现产业数 × 平均景气指数 / 100）",
    fmt: str = "{:.1f}",
    figsize: tuple[float, float] | None = None,
) -> plt.Figure:
    """技能需求热度横向条形图；highlight 列（布尔）标记用户已具备的技能。"""
    if data.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "无数据可展示", ha="center", va="center", fontsize=12)
        ax.axis("off")
        return _finalize(fig)

    ordered = data.sort_values(value_col, ascending=True).reset_index(drop=True)
    if figsize is None:
        figsize = (8.4, max(3.6, len(ordered) * 0.34 + 2))
    fig, ax = plt.subplots(figsize=figsize)

    if "owned" in ordered.columns:
        owned = ordered["owned"].fillna(False).astype(bool)
    else:
        owned = pd.Series(False, index=ordered.index)

    bars = ax.barh(
        ordered[label_col].astype(str), ordered[value_col],
        color=[highlight_color if flag else color for flag in owned],
        edgecolor="white",
    )
    width_max = float(pd.to_numeric(ordered[value_col], errors="coerce").max() or 0.0)
    _add_bar_labels(
        ax, bars, ordered[value_col], fmt=fmt,
        offset=width_max * 0.02 if width_max > 0 else 0.1,
    )
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.grid(axis="x", alpha=0.3, linestyle="--")
    if bool(owned.any()):
        handles = [
            plt.Rectangle((0, 0), 1, 1, color=highlight_color),
            plt.Rectangle((0, 0), 1, 1, color=color),
        ]
        ax.legend(handles, [highlight_label, "建议补强"], fontsize=9, loc="lower right")
    return _finalize(fig)


