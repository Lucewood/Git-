"""Streamlit UI 组件封装：指标卡片、标题、滑块、表格格式化等。

将这些可复用组件抽离，便于统一视觉规范并降低入口脚本复杂度。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from .config import APP_VERSION, DATA_REF_YEAR

# 液态玻璃语义色（与 styles.CUSTOM_CSS 中的 .tone-* 一一对应）。
# 不传 tone 时由 CSS 按卡片所在列自动轮换配色，保证同一行玻璃色多元。
GLASS_TONES: frozenset[str] = frozenset(
    {"blue", "mint", "peach", "lilac", "rose", "sky", "amber"}
)

# 侧边栏章节导航配置：分组标题 → ((锚点 ID, 显示文本), ...)。
# 锚点必须与页面 section_title(anchor=...) / 章节容器的 id 一一对应，
# 由 tests/test_streamlit_app.py 断言「导航目标全部存在」，避免改名后失效。
SIDEBAR_NAV_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("总览", (("sec-overview", "📊 概览仪表盘"),)),
    (
        "分析视图",
        (
            ("sec-association", "📈 核心指标关联"),
            ("sec-city", "🔬 城市对比与画像"),
            ("sec-happiness", "😊 幸福度排名"),
            ("sec-affordability", "🏠 住房可负担性"),
            ("sec-top20", "🏆 TOP 20 详情"),
            ("sec-outliers", "🔍 异常值检测"),
        ),
    ),
    (
        "智能洞察",
        (
            ("sec-ai", "🤖 AI 生活成本顾问"),
            ("sec-forecast", "📉 房价趋势预测"),
            ("sec-career", "🧭 就业指导与产业"),
        ),
    ),
    (
        "地理与数据",
        (
            ("sec-province", "🗺️ 省份聚合分析"),
            ("sec-maps", "🌏 地理分布地图"),
            ("sec-data", "📋 数据浏览与质量"),
        ),
    ),
)


def _tone_class(tone: str | None) -> str:
    """返回玻璃色 CSS 类（未知 tone 静默忽略，避免拼写错误破坏样式）。"""
    return f" tone-{tone}" if tone in GLASS_TONES else ""


def metric_card(
    title: str, value: str, sub: str = "", tone: str | None = None
) -> None:
    """渲染顶部指标卡片。

    Args:
        tone: 可选的玻璃语义色（blue / mint / peach / lilac / rose / sky / amber）；
            缺省时由 CSS 按所在列自动轮换，保持多彩但不必逐个指定。
    """
    sub_html = f'<div class="sub">{sub}</div>' if sub else ""
    st.markdown(
        f'<div class="metric-card{_tone_class(tone)}">'
        f"<h3>{title}</h3><h1>{value}</h1>{sub_html}</div>",
        unsafe_allow_html=True,
    )


def section_title(text: str, anchor: str | None = None) -> None:
    """渲染章节标题。

    Args:
        anchor: 可选锚点 ID（与 ``SIDEBAR_NAV_GROUPS`` 中的链接一一对应）。

    说明：锚点必须是**独立的空 div**，不能直接写在 ``<h2>`` 上——Streamlit 渲染
    markdown 标题时会把标题的 id 重写成自动生成的哈希（实测 1.58），导致
    ``href="#sec-xxx"`` 找不到目标；而普通 div 的 id 会被保留。空 div 与标题
    写在同一次 markdown 调用里，因此不会额外产生一段垂直间距。
    """
    anchor_html = (
        f'<div id="{anchor}" class="section-anchor" aria-hidden="true"></div>'
        if anchor
        else ""
    )
    st.markdown(
        f'{anchor_html}<h2 class="section-title">{text}</h2>',
        unsafe_allow_html=True,
    )


def sidebar_nav_html(*, show_maps: bool = True) -> str:
    """构造侧边栏章节导航的链接 HTML（标题与折叠由 st.expander 提供）。

    Args:
        show_maps: 是否展示「地理分布地图」章节；关闭地图时一并隐藏该导航项，
            避免跳到不存在的章节。

    说明：链接使用页内锚点（``href="#sec-xxx"``），由浏览器原生滚动完成定位，
    不触发 Streamlit rerun，因此不会重置筛选条件或重新训练模型。
    """
    groups: list[str] = []
    for group_title, items in SIDEBAR_NAV_GROUPS:
        visible = [
            (anchor, label)
            for anchor, label in items
            if show_maps or anchor != "sec-maps"
        ]
        if not visible:
            continue
        links = "".join(
            f'<a class="nav-link" href="#{anchor}" title="{label}">'
            f"<span>{label}</span><span class=\"nav-arrow\" aria-hidden=\"true\">›</span></a>"
            for anchor, label in visible
        )
        groups.append(
            f'<div class="nav-group"><div class="nav-group-title">{group_title}</div>'
            f"{links}</div>"
        )

    return (
        '<div class="sidebar-nav-links">'
        + "".join(groups)
        + '<a class="nav-link nav-top" href="#sec-overview">↑ 回到顶部</a>'
        "</div>"
    )


def sidebar_nav_count(*, show_maps: bool = True) -> int:
    """导航包含的章节数（用于折叠面板标题，地图关闭时自动减一）。"""
    return sum(
        1
        for _group, items in SIDEBAR_NAV_GROUPS
        for anchor, _label in items
        if show_maps or anchor != "sec-maps"
    )


def sidebar_nav(*, show_maps: bool = True, expanded: bool = True) -> None:
    """在当前容器（通常是 st.sidebar）中渲染章节导航。

    外层用 st.expander 提供原生折叠：默认展开便于跳转，收起后把纵向空间
    让给下方的筛选控件（侧边栏导航与筛选共用一列，避免互相挤压）。
    """
    count = sidebar_nav_count(show_maps=show_maps)
    with st.expander(f"🧭 快速导航（{count} 个章节）", expanded=expanded):
        st.markdown(sidebar_nav_html(show_maps=show_maps), unsafe_allow_html=True)


# 光标跟随高光：把指针位置写成 CSS 变量（--glass-x / --glass-y），
# 由 styles.CUSTOM_CSS 中的玻璃背景层消费。脚本优先通过 st.html 内联注入主页
# （旧版 Streamlit 退回同源 iframe 的 components.html）；任何跨域 / 沙箱限制
# 都会被 try/catch 吞掉，退化为「固定在顶部的静态高光」，页面功能不受影响。
_POINTER_GLOW_SCRIPT = """
<script>
(function () {
  try {
    var host = window.parent;
    if (!host || host.__liquidGlassPointer) { return; }
    if (host.matchMedia && host.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      return;
    }
    if (host.matchMedia && !host.matchMedia('(hover: hover)').matches) { return; }
    var doc = host.document;
    var selector = [
      '.metric-card', '.insight-box', '.section-title', '.hero-glass',
      '[data-testid="stExpander"]', '[data-testid="stImageContainer"]',
      '[data-testid="stIFrame"]', '.footer'
    ].join(',');
    var frame = 0;
    var current = null;
    var pointerX = 0;
    var pointerY = 0;

    var paint = function () {
      frame = 0;
      var el = current;
      if (!el || !el.isConnected) { return; }
      var rect = el.getBoundingClientRect();
      if (rect.width < 1 || rect.height < 1) { return; }
      el.style.setProperty('--glass-x', (((pointerX - rect.left) / rect.width) * 100).toFixed(2) + '%');
      el.style.setProperty('--glass-y', (((pointerY - rect.top) / rect.height) * 100).toFixed(2) + '%');
    };

    doc.addEventListener('pointermove', function (event) {
      if (event.pointerType && event.pointerType !== 'mouse') { return; }
      var target = event.target;
      var el = target && target.closest ? target.closest(selector) : null;
      if (!el) { return; }
      current = el;
      pointerX = event.clientX;
      pointerY = event.clientY;
      if (!frame) { frame = host.requestAnimationFrame(paint); }
    }, { passive: true, capture: true });

    doc.addEventListener('pointerout', function (event) {
      var target = event.target;
      var el = target && target.closest ? target.closest(selector) : null;
      if (el && !el.contains(event.relatedTarget)) {
        el.style.removeProperty('--glass-x');
        el.style.removeProperty('--glass-y');
      }
    }, { passive: true, capture: true });

    host.__liquidGlassPointer = true;
  } catch (error) {
    /* 跨域 / 沙箱 / 旧浏览器：静默降级，不影响任何功能 */
  }
})();
</script>
"""


def pointer_glow() -> None:
    """启用玻璃面的光标跟随高光（渐进增强，失败时自动降级）。

    优先使用 ``st.html(..., unsafe_allow_javascript=True)``：内容不放进 iframe，
    不会在页面顶部留下额外的组件占位；Streamlit 版本较旧时不支持该参数，
    退回零高度 components.html。两种方式都在主页面只绑定一次监听器
    （以 ``window.__liquidGlassPointer`` 做幂等标记），Streamlit rerun 不会
    重复叠加；只更新当前悬停元素的 CSS 变量，并用 requestAnimationFrame
    合帧，避免逐事件重排。
    """
    try:
        st.html(_POINTER_GLOW_SCRIPT, unsafe_allow_javascript=True)
        return
    except TypeError:  # 旧版本 Streamlit 没有 unsafe_allow_javascript 参数
        pass
    except Exception:  # pragma: no cover - 注入失败只失去增强效果
        return
    try:
        components.html(_POINTER_GLOW_SCRIPT, height=0, scrolling=False)
    except Exception:  # pragma: no cover - 组件环境不可用时只失去增强效果
        pass


def insight_box(html: str, tone: str | None = None) -> None:
    """渲染洞察提示框（支持 HTML 片段）。

    Args:
        tone: 可选的玻璃语义色；缺省为蓝紫玻璃。
    """
    st.markdown(
        f'<div class="insight-box{_tone_class(tone)}">{html}</div>',
        unsafe_allow_html=True,
    )


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
            <p>🧭 就业推荐基于爬虫采集的城市支柱产业数据库，匹配度 = 技能 / 薪资 / 发展 / 规模 / 宜居 五维加权</p>
            <p>Made with ❤️ using Streamlit · Matplotlib · Seaborn · Pandas · v{APP_VERSION}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
