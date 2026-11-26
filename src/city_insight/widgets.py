"""Streamlit UI 组件封装：指标卡片、标题、滑块、表格格式化等。

将这些可复用组件抽离，便于统一视觉规范并降低入口脚本复杂度。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from .config import APP_VERSION, DATA_REF_YEAR
from .scenes import scene_script

# 液态玻璃语义色（与 styles.CUSTOM_CSS 中的 .tone-* 一一对应）。
# 不传 tone 时由 CSS 按卡片所在列自动轮换配色，保证同一行玻璃色多元。
GLASS_TONES: frozenset[str] = frozenset(
    {"blue", "mint", "peach", "lilac", "rose", "sky", "amber"}
)


@dataclass(frozen=True)
class NavModule:
    """侧边栏一级导航模块（按钮 + 可选的细分章节）。

    Attributes:
        anchor: 模块锚点 ID，必须与页面 module_header() / 章节容器的 id 一致。
        icon: 导航按钮图标（emoji）。
        title: 模块名称（尽量短，保证侧边栏一行可读）。
        desc: 一句话说明，帮助用户判断该模块是否是自己要找的内容。
        subs: 细分章节 ((锚点 ID, 显示文本), ...)，收起在「细分章节」中。
    """

    anchor: str
    icon: str
    title: str
    desc: str
    subs: tuple[tuple[str, str], ...] = ()


# 侧边栏功能导航：6 个一级模块覆盖全部页面内容。
# 锚点必须与页面 module_header(anchor=...) / section_title(anchor=...) 的 id
# 一一对应，由 tests/test_streamlit_app.py 断言「导航目标全部存在」。
# 设计原则：一级入口只保留 6 个、文案直白；细分章节折叠，避免侧边栏过长。
SIDEBAR_NAV_MODULES: tuple[NavModule, ...] = (
    NavModule(
        "sec-overview", "📊", "概览", "筛选范围与核心指标",
    ),
    NavModule(
        "sec-insight", "📈", "城市洞察", "指标关联与城市画像",
        (
            ("sec-association", "📈 核心指标关联分析"),
            ("sec-city", "🔬 城市对比与画像"),
        ),
    ),
    NavModule(
        "sec-ranking", "🏆", "城市排行", "幸福度、可负担性与异常值",
        (
            ("sec-happiness", "😊 幸福度排名"),
            ("sec-affordability", "🏠 住房可负担性"),
            ("sec-top20", "🏆 TOP 20 明细"),
            ("sec-outliers", "🔍 异常值检测"),
        ),
    ),
    NavModule(
        "sec-forecast", "📉", "房价预测", "趋势外推与回测验证",
    ),
    NavModule(
        "sec-advice", "🧭", "决策建议", "AI 成本顾问与就业规划",
        (
            ("sec-ai", "🤖 AI 生活成本顾问"),
            ("sec-career", "🧭 就业指导与产业"),
        ),
    ),
    NavModule(
        "sec-geo", "🗺️", "地图与数据", "省份聚合、地图与数据下载",
        (
            ("sec-province", "🗺️ 省份聚合分析"),
            ("sec-maps", "🌏 地理分布地图"),
            ("sec-data", "📋 数据浏览与导出"),
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
    """渲染章节标题（模块内的二级标题）。

    Args:
        anchor: 可选锚点 ID（与 ``SIDEBAR_NAV_MODULES`` 中的细分章节对应）。

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


def module_header(step: str, title: str, desc: str, anchor: str) -> None:
    """渲染一级功能模块标题（编号 + 标题 + 一句话说明）。

    Args:
        step: 两位模块序号（如 ``"02"``），帮助用户建立页面顺序感。
        title: 模块标题（含 emoji）。
        desc: 一句话说明该模块能回答什么问题。
        anchor: 模块锚点 ID，与 ``SIDEBAR_NAV_MODULES`` 的一级入口对应。

    说明：锚点同样使用独立空 div（原因见 ``section_title``），保证侧边栏
    模块按钮点击后能准确定位，且标题不会被顶部工具栏遮住。
    """
    st.markdown(
        f'<div id="{anchor}" class="module-anchor" aria-hidden="true"></div>'
        f'<div class="module-header">'
        f'<span class="module-step" aria-hidden="true">{step}</span>'
        f'<div class="module-heading">'
        f'<h2 class="module-title">{title}</h2>'
        f'<p class="module-desc">{desc}</p>'
        f"</div></div>",
        unsafe_allow_html=True,
    )


def sidebar_nav_html(*, show_maps: bool = True) -> str:
    """构造侧边栏功能导航 HTML（6 个模块按钮 + 折叠的细分章节）。

    Args:
        show_maps: 是否展示「地理分布地图」章节；关闭地图时一并隐藏该细分子项，
            避免跳到不存在的章节。

    说明：链接使用页内锚点（``href="#sec-xxx"``），由浏览器原生滚动完成定位，
    不触发 Streamlit rerun，因此不会重置筛选条件或重新训练模型。
    """
    module_links: list[str] = []
    sub_groups: list[str] = []
    sub_count = 0
    for module in SIDEBAR_NAV_MODULES:
        module_links.append(
            f'<a class="nav-module" href="#{module.anchor}" '
            f'title="{module.title}：{module.desc}">'
            f'<span class="nav-module-icon" aria-hidden="true">{module.icon}</span>'
            f'<span class="nav-module-text">'
            f"<strong>{module.title}</strong><small>{module.desc}</small>"
            f"</span></a>"
        )
        visible = [
            (anchor, label)
            for anchor, label in module.subs
            if show_maps or anchor != "sec-maps"
        ]
        if not visible:
            continue
        sub_count += len(visible)
        links = "".join(
            f'<a class="nav-sublink" href="#{anchor}">{label}</a>'
            for anchor, label in visible
        )
        sub_groups.append(
            f'<div class="nav-subgroup">'
            f'<div class="nav-subtitle">{module.title}</div>'
            f'<div class="nav-sublinks">{links}</div></div>'
        )

    return (
        '<div class="sidebar-nav">'
        f'<div class="nav-module-grid">{"".join(module_links)}</div>'
        f'<details class="nav-more">'
        f"<summary>🔍 细分章节（{sub_count}）</summary>"
        f'<div class="nav-sub-groups">{"".join(sub_groups)}</div>'
        f"</details>"
        '<a class="nav-top-link" href="#sec-overview">↑ 回到顶部</a>'
        "</div>"
    )


def sidebar_nav_count(*, show_maps: bool = True) -> int:
    """一级导航模块数量（地图开关只影响细分章节，不改变模块数）。"""
    return len(SIDEBAR_NAV_MODULES)


def sidebar_nav(*, show_maps: bool = True) -> None:
    """在当前容器（通常是 st.sidebar）中渲染功能导航。

    导航常驻侧边栏顶部：6 个模块按钮直接可见，细分章节默认折叠，
    既不挤占筛选控件的空间，也避免用户在一长串小链接里寻找功能。
    """
    st.markdown(
        '<div class="nav-heading">🧭 功能导航</div>', unsafe_allow_html=True
    )
    st.markdown(sidebar_nav_html(show_maps=show_maps), unsafe_allow_html=True)


# 光标跟随高光：把指针位置写成 CSS 变量（--glass-x / --glass-y），
# 由 styles.CUSTOM_CSS 中的玻璃背景层消费。脚本优先定位包含 .stApp 的文档：
# 本地主文档 / Streamlit Cloud 的应用 iframe 都直接使用当前 document，
# 仅 components.html 兜底（脚本位于应用内子 iframe）才回退到同源父文档。
# 任何跨域 / 沙箱限制都会被 try/catch 吞掉，退化为「固定在顶部的静态高光」。
_POINTER_GLOW_SCRIPT = """
<script>
(function () {
  try {
    var host = window;
    var doc = document;
    var app = doc.querySelector('.stApp');
    var parentDoc = null;
    if (!app) {
      try {
        if (window.parent && window.parent !== window) {
          parentDoc = window.parent.document;
        }
      } catch (error) {
        parentDoc = null;
      }
    }
    if (!app && parentDoc) {
      var parentApp = parentDoc.querySelector('.stApp');
      if (parentApp) {
        host = window.parent;
        doc = parentDoc;
        app = parentApp;
      }
    }
    if (!app || host.__liquidGlassPointer) { return; }
    if (host.matchMedia && host.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      return;
    }
    if (host.matchMedia && !host.matchMedia('(hover: hover)').matches) { return; }
    var selector = [
      '.metric-card', '.insight-box', '.section-title', '.module-header',
      '.hero-glass', '[data-testid="stExpander"]', '[data-testid="stImageContainer"]',
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


def _inject_main_page_script(script: str) -> None:
    """把脚本注入 Streamlit 主文档（优先 st.html，旧版退回零高度组件）。

    ``st.html(..., unsafe_allow_javascript=True)`` 不会把内容放进 iframe，
    因此不会在页面顶部留下额外的组件占位；Streamlit 版本较旧不支持该参数时，
    退回 ``components.html``。脚本内部会优先定位包含 ``.stApp`` 的文档：
    本地主文档 / Streamlit Cloud 的应用 iframe 都直接生效，只有组件 iframe
    才回退到同源父文档，因此两种注入路径行为一致。跨域 / 沙箱 / 注入失败都
    只失去对应的增强效果，不影响页面功能。
    """
    try:
        st.html(script, unsafe_allow_javascript=True)
        return
    except TypeError:  # 旧版本 Streamlit 没有 unsafe_allow_javascript 参数
        pass
    except Exception:  # pragma: no cover - 注入失败只失去增强效果
        return
    try:
        components.html(script, height=0, scrolling=False)
    except Exception:  # pragma: no cover - 组件环境不可用时只失去增强效果
        pass


def pointer_glow() -> None:
    """启用玻璃面的光标跟随高光（渐进增强，失败时自动降级）。

    两种注入方式都在主页面只绑定一次监听器（以 ``window.__liquidGlassPointer``
    做幂等标记），Streamlit rerun 不会重复叠加；只更新当前悬停元素的 CSS 变量，
    并用 requestAnimationFrame 合帧，避免逐事件重排。
    """
    _inject_main_page_script(_POINTER_GLOW_SCRIPT)


def scroll_scene_gradient() -> None:
    """启用「分幕」滚动渐变背景（渐进增强，失败时保留 CSS 首屏配色）。

    脚本按真实章节锚点（scenes.SCENE_PALETTES）计算当前 / 下一分幕的位置，
    章节前半段保持本幕主色，后半段（最多约 0.8 屏）平滑过渡到下一幕：翻到
    下一功能部分时背景连续换色且有明显区分度。只读取 DOM 几何位置，不修改
    页面结构或业务数据；以 ``window.__citySceneGradient`` 保证重复注入幂等，
    并在系统开启「减少动态效果」时完全跳过。
    """
    _inject_main_page_script(scene_script())


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
