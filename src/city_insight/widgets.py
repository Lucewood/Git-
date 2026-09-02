"""Streamlit UI 组件封装：指标卡片、标题、滑块、表格格式化等。

将这些可复用组件抽离，便于统一视觉规范并降低入口脚本复杂度。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from .config import APP_VERSION, DATA_REF_YEAR


def metric_card(title: str, value: str, sub: str = "") -> None:
    """渲染顶部指标卡片。"""
    sub_html = f'<div class="sub">{sub}</div>' if sub else ""
    st.markdown(
        f'<div class="metric-card"><h3>{title}</h3><h1>{value}</h1>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def section_title(text: str) -> None:
    """渲染章节标题。"""
    st.markdown(f'<h2 class="section-title">{text}</h2>', unsafe_allow_html=True)


def insight_box(html: str) -> None:
    """渲染洞察提示框（支持 HTML 片段）。"""
    st.markdown(f'<div class="insight-box">{html}</div>', unsafe_allow_html=True)


def range_slider(
    label: str,
    series: pd.Series,
    step: float,
    key: str | None = None,
    to_int: bool = False,
):
    """创建数值范围滑块；自动处理 min==max / 非有限值等异常情况。"""
    lo, hi = float(series.min()), float(series.max())
    if not (np.isfinite(lo) and np.isfinite(hi)):
        lo, hi = 0.0, 1.0
    if to_int:
        lo, hi = int(np.floor(lo)), int(np.ceil(hi))
    if lo >= hi:
        hi = lo + step
    return st.slider(label, lo, hi, (lo, hi), step=step, key=key)


def top_n_slider(key: str, n_rows: int) -> int:
    """“显示城市数量”滑块；数据不足时自动收缩范围，避免 min>=max 报错。"""
    limit = min(50, n_rows)
    if limit <= 1:
        return max(1, limit)
    lo = min(10, limit)
    val = min(20, limit)
    if lo >= limit:
        return limit
    return st.slider("显示城市数量", lo, limit, val, key=key)


def fmt_table(
    df: pd.DataFrame,
    fmt_dict: dict,
    gradient_col: str | None = None,
    cmap: str | None = None,
):
    """统一格式化表格，可选添加渐变底色。"""
    style = df.style.format(fmt_dict)
    if gradient_col is not None and cmap is not None:
        style = style.background_gradient(subset=[gradient_col], cmap=cmap)
    return style


def render_footer() -> None:
    """渲染页脚。"""
    st.markdown("---")
    st.markdown(
        f"""
        <div class="footer">
            <p>📊 中国城市生活成本与幸福感分析可视化 | 覆盖全国 248 个城市 · 数据参考年份 {DATA_REF_YEAR}</p>
            <p>💡 可负担指数 = 年收入 ÷ 房价（元/㎡），数值越高代表住房压力越小；综合宜居分为加权标准化评分</p>
            <p>Made with ❤️ using Streamlit · Matplotlib · Seaborn · Pandas · v{APP_VERSION}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
