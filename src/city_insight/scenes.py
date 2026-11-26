"""页面「分幕」背景配色与滚动渐变换色脚本。

设计目标
--------
长页面滚动时，整页背景（基色 + 极光光晕）会随所在功能模块平滑换色：

- 每个一级功能模块对应一幕（概览 / 洞察 / 排行 / 预测 / 建议 / 地图 / 数据），
  配色在浅色系内刻意拉开色相，看背景就能感知「已经翻到下一个功能部分」；
- 相邻两幕之间不是硬切，而是按真实章节锚点的位置连续插值（见
  ``scene_script``）：章节前半段保持本幕主色，后半段平滑过渡到下一幕
  （过渡窗口最多约 0.8 屏），既保证区分度，也避免长时间阅读时背景一直在变；
- 无脚本 / 开启「减少动态效果」时，CSS 使用首屏静态配色（颜色仍然可读），
  不会影响任何内容与交互。

配色全部为浅色高亮调：每幕**基色**与深墨色正文的对比度 ≥ 7:1（WCAG AAA）；
极光光晕以低不透明度叠加（见 ``SCENE_GLOW_OPACITY``），最坏情况下正文仍 ≥ 7:1、
说明文字 ≥ 4.5:1（WCAG AA），因此背景换色不会牺牲可读性。
"""

from __future__ import annotations

from dataclasses import dataclass
import json


@dataclass(frozen=True)
class ScenePalette:
    """一个背景分幕的配色（全部可在 CSS 渐变中直接使用）。

    Attributes:
        key: 稳定标识，同时写入 ``.stApp[data-scene]``，便于样式 / 测试定位。
        label: 中文名称（侧边栏说明与可读性检查使用）。
        anchor: 该幕起始位置对应的页面锚点 ID（与 widgets 导航锚点一致）。
        base: 整页基色（不透明，决定背景主色调）。
        deep: 渐变过渡用的深一档基色（不透明，增加层次）。
        glow_a: 主要极光光晕（半透明彩色）。
        glow_b: 次要极光光晕（半透明彩色）。
        accent: 该幕的强调色（用于进度指示等需要实色的位置）。
    """

    key: str
    label: str
    anchor: str
    base: str
    deep: str
    glow_a: str
    glow_b: str
    accent: str

    def css_variables(self) -> dict[str, str]:
        """该幕对应的 CSS 自定义属性（变量名与 styles.CUSTOM_CSS 一致）。"""
        return {
            "--scene-base": self.base,
            "--scene-deep": self.deep,
            "--scene-glow-a": self.glow_a,
            "--scene-glow-b": self.glow_b,
            "--scene-accent": self.accent,
        }

    def payload(self) -> dict[str, str]:
        """供前端脚本消费的最小字段（键名转换为 JS 风格）。"""
        return {
            "key": self.key,
            "anchor": self.anchor,
            "base": self.base,
            "deep": self.deep,
            "glowA": self.glow_a,
            "glowB": self.glow_b,
            "accent": self.accent,
        }


# 分幕顺序必须与页面模块顺序一致（概览 → 城市洞察 → 城市排行 → 房价预测
# → 决策建议 → 地图与数据 → 数据浏览）。相邻幕的基色刻意拉开色相：
# 晨雾蓝 → 薄荷绿 → 暖琥珀 → 紫罗兰 → 玫瑰粉 → 湖水青 → 暮色砂。
SCENE_PALETTES: tuple[ScenePalette, ...] = (
    ScenePalette(
        key="overview",
        label="概览 · 晨雾蓝",
        anchor="sec-overview",
        base="#e2ebfd",
        deep="#f2f6ff",
        glow_a="rgba(74, 124, 255, 0.54)",
        glow_b="rgba(126, 108, 255, 0.40)",
        accent="#3f6ae0",
    ),
    ScenePalette(
        key="insight",
        label="城市洞察 · 薄荷绿",
        anchor="sec-insight",
        base="#d9f2e7",
        deep="#eefaf4",
        glow_a="rgba(23, 184, 146, 0.52)",
        glow_b="rgba(64, 206, 190, 0.38)",
        accent="#0f9f7f",
    ),
    ScenePalette(
        key="ranking",
        label="城市排行 · 暖琥珀",
        anchor="sec-ranking",
        base="#fce9d6",
        deep="#fdf5e8",
        glow_a="rgba(240, 152, 48, 0.50)",
        glow_b="rgba(255, 126, 94, 0.36)",
        accent="#d97a12",
    ),
    ScenePalette(
        key="forecast",
        label="房价预测 · 紫罗兰",
        anchor="sec-forecast",
        base="#e8e0fb",
        deep="#f4effd",
        glow_a="rgba(128, 90, 240, 0.52)",
        glow_b="rgba(84, 126, 255, 0.38)",
        accent="#6f4bd8",
    ),
    ScenePalette(
        key="advice",
        label="决策建议 · 玫瑰粉",
        anchor="sec-advice",
        base="#fbdbe8",
        deep="#fdf0f5",
        glow_a="rgba(238, 90, 136, 0.48)",
        glow_b="rgba(255, 152, 182, 0.38)",
        accent="#d8396f",
    ),
    ScenePalette(
        key="geo",
        label="地图与数据 · 湖水青",
        anchor="sec-geo",
        base="#d7eefb",
        deep="#ecf8fe",
        glow_a="rgba(24, 152, 214, 0.50)",
        glow_b="rgba(46, 198, 182, 0.36)",
        accent="#0a86b8",
    ),
    ScenePalette(
        key="data",
        label="数据浏览 · 暮色砂",
        anchor="sec-data",
        base="#e9e4da",
        deep="#f5f2ec",
        glow_a="rgba(120, 102, 74, 0.40)",
        glow_b="rgba(86, 124, 164, 0.30)",
        accent="#6b5a3e",
    ),
)

# 极光光晕层的整体不透明度：光晕只负责氛围，基础色负责分幕区分度。
# 该值同时注入 CSS（--scene-glow-opacity）并参与 tests/test_scenes.py 的
# 最坏情况对比度校验（正文 ≥ 7:1、说明文字 ≥ 4.5:1），调色时请勿绕过测试。
SCENE_GLOW_OPACITY = 0.6


def scene_root_css() -> str:
    """生成首屏 / 无脚本时的 CSS 兜底变量（首个分幕的静态配色）。

    返回的片段会由 styles 在 ``</style>`` 前插入。脚本接管后会在 ``.stApp``
    上写入同名的内联变量，按滚动位置逐帧插值，因此这里只负责「首帧不闪白」。
    """
    variables = "\n".join(
        f"        {name}: {value};"
        for name, value in SCENE_PALETTES[0].css_variables().items()
    )
    return (
        "\n    /* =====================================================================\n"
        "       滚动分幕背景：首屏 / 无脚本静态配色（脚本接管后逐帧插值 --scene-*）\n"
        "       ===================================================================== */\n"
        "    :root {\n"
        f"{variables}\n"
        f"        --scene-glow-opacity: {SCENE_GLOW_OPACITY};\n"
        "    }\n"
    )


# 说明：st.html 的脚本运行在「应用自己的 document」里；Streamlit Community
# Cloud 会把整个应用放进同源 iframe，因此 window.parent 反而是没有 .stApp 的
# Cloud 外壳。脚本优先使用包含 .stApp 的当前文档，仅在 components.html 兜底
# （脚本位于应用内的子 iframe）时才回退到同源父文档。脚本只读页面已有锚点、
# 写入 5 个 CSS 变量，不触碰业务数据或 DOM 结构，失败时静默退回首屏静态配色。
_SCENE_SCRIPT = r"""
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
    if (!app) { return; }
    if (host.matchMedia &&
        host.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      return;
    }
    // Streamlit rerun 会重新注入脚本：保留已绑定的事件，但强制重刷一次配色，
    // 防止根节点内联变量被重渲染清空。
    if (host.__citySceneGradient) {
      if (host.__citySceneApply) { host.__citySceneApply(); }
      return;
    }

    var scenes = __SCENE_PAYLOAD__;
    var frame = 0;
    var anchors = [];
    var scroller = null;
    var viewport = 800;
    var lastSignature = '';
    var lastKey = '';

    var parseColor = function (value) {
      var text = String(value).trim();
      var match;
      if (text.charAt(0) === '#') {
        var hex = text.slice(1);
        if (hex.length === 3) {
          hex = hex.charAt(0) + hex.charAt(0) + hex.charAt(1) + hex.charAt(1) +
            hex.charAt(2) + hex.charAt(2);
        }
        if (hex.length === 6 || hex.length === 8) {
          var number = parseInt(hex.slice(0, 6), 16);
          var alpha = hex.length === 8
            ? parseInt(hex.slice(6, 8), 16) / 255
            : 1;
          return [(number >> 16) & 255, (number >> 8) & 255, number & 255, alpha];
        }
        return [255, 255, 255, 1];
      }
      match = text.match(/rgba?\(([^)]+)\)/i);
      if (match) {
        var parts = match[1].split(',').map(function (part) {
          return parseFloat(part);
        });
        return [
          parts[0] || 0,
          parts[1] || 0,
          parts[2] || 0,
          parts.length > 3 ? parts[3] : 1
        ];
      }
      return [255, 255, 255, 1];
    };

    var parsed = scenes.map(function (scene) {
      return {
        key: scene.key,
        anchor: scene.anchor,
        base: parseColor(scene.base),
        deep: parseColor(scene.deep),
        glowA: parseColor(scene.glowA),
        glowB: parseColor(scene.glowB),
        accent: parseColor(scene.accent)
      };
    });

    var channel = function (from, to, progress) {
      return Math.round(from + (to - from) * progress);
    };

    var mix = function (from, to, progress) {
      var alpha = from[3] + (to[3] - from[3]) * progress;
      return 'rgba(' +
        channel(from[0], to[0], progress) + ',' +
        channel(from[1], to[1], progress) + ',' +
        channel(from[2], to[2], progress) + ',' +
        alpha.toFixed(3) + ')';
    };

    var currentScroller = function () {
      var main = doc.querySelector('[data-testid="stMain"]');
      if (main && main.scrollHeight > main.clientHeight + 8) { return main; }
      return null;
    };

    var scrollTop = function () {
      if (scroller) { return scroller.scrollTop; }
      return host.pageYOffset || doc.documentElement.scrollTop || 0;
    };

    // 以「章节标题到达视口约 32% 高度」作为换幕基准，读到标题时配色已经就位。
    var measure = function () {
      scroller = currentScroller();
      viewport = scroller ? scroller.clientHeight : (host.innerHeight || 800);
      var line = viewport * 0.32;
      var top = scrollTop();
      var found = [];
      for (var index = 0; index < parsed.length; index += 1) {
        var node = doc.getElementById(parsed[index].anchor);
        if (!node) { continue; }
        var rect = node.getBoundingClientRect();
        found.push({ index: index, at: top + rect.top - line });
      }
      found.sort(function (a, b) { return a.at - b.at; });
      anchors = found;
    };

    var write = function (from, to, progress) {
      if (!app || !app.isConnected) {
        app = doc.querySelector('.stApp');
        lastSignature = '';
        lastKey = '';
        if (!app) { return; }
      }
      var base = mix(from.base, to.base, progress);
      var deep = mix(from.deep, to.deep, progress);
      var glowA = mix(from.glowA, to.glowA, progress);
      var glowB = mix(from.glowB, to.glowB, progress);
      var accent = mix(from.accent, to.accent, progress);
      var signature = base + '|' + deep + '|' + glowA + '|' + glowB + '|' + accent;
      // 签名相同且变量仍在：无需重复写入；若变量被重渲染清空，则强制补回。
      if (signature === lastSignature &&
          app.style.getPropertyValue('--scene-base') === base) { return; }
      lastSignature = signature;
      app.style.setProperty('--scene-base', base);
      app.style.setProperty('--scene-deep', deep);
      app.style.setProperty('--scene-glow-a', glowA);
      app.style.setProperty('--scene-glow-b', glowB);
      app.style.setProperty('--scene-accent', accent);
      var key = progress < 0.5 ? from.key : to.key;
      if (key !== lastKey) {
        lastKey = key;
        app.setAttribute('data-scene', key);
      }
    };

    var smooth = function (value) {
      return value * value * (3 - 2 * value);
    };

    var update = function (force) {
      frame = 0;
      if (force) {
        lastSignature = '';
        lastKey = '';
      }
      measure();
      if (!anchors.length) { return; }
      var top = scrollTop();
      var first = anchors[0];
      var last = anchors[anchors.length - 1];
      if (top <= first.at) {
        write(parsed[first.index], parsed[first.index], 0);
        return;
      }
      if (top >= last.at) {
        write(parsed[last.index], parsed[last.index], 1);
        return;
      }
      for (var index = 0; index < anchors.length - 1; index += 1) {
        var current = anchors[index];
        var upcoming = anchors[index + 1];
        if (top < current.at || top >= upcoming.at) { continue; }
        var span = upcoming.at - current.at;
        // 过渡窗口最多占本章节的一半、最多 0.8 屏：章节被读到前一半时保持本幕
        // 主色，后半段才渐变到下一幕，短章节（如首屏概览）也不会一进页就变色。
        var fade = Math.min(viewport * 0.8, span * 0.5);
        fade = Math.max(fade, Math.min(span * 0.35, viewport * 0.3));
        var start = upcoming.at - fade;
        var progress = 0;
        if (top > start && fade > 0) {
          progress = smooth(Math.min(1, (top - start) / fade));
          // 量化到约 64 级：视觉上仍是连续渐变，但显著减少整页样式重算次数。
          progress = Math.round(progress * 64) / 64;
        }
        write(parsed[current.index], parsed[upcoming.index], progress);
        return;
      }
    };

    var schedule = function () {
      if (!frame) {
        frame = host.requestAnimationFrame(function () { update(false); });
      }
    };

    // 首帧立即应用首幕配色，避免等待第一个滚动事件时出现色差。
    // html.scene-js 标记「脚本已接管背景」，便于样式降级判断与线上排查。
    doc.documentElement.classList.add('scene-js');
    measure();
    update(true);
    host.setTimeout(schedule, 350);
    host.setTimeout(schedule, 1500);
    // 图表 / 字体 / 图片在首屏之后陆续撑开布局，再多补几次延迟测量，
    // 保证用户未滚动时首屏也能落到正确分幕。
    host.setTimeout(schedule, 4000);
    host.setTimeout(schedule, 9000);

    doc.addEventListener('scroll', schedule, { passive: true, capture: true });
    host.addEventListener('resize', schedule, { passive: true });

    var main = doc.querySelector('[data-testid="stMain"]');
    if (main) {
      main.addEventListener('scroll', schedule, { passive: true });
      if (host.MutationObserver) {
        var observer = new host.MutationObserver(schedule);
        // 展开折叠面板 / 切换 Tab 会改变章节位置，观察内容变化后重新测量。
        observer.observe(main, { childList: true, subtree: true });
        host.__citySceneObserver = observer;
      }
    }
    // 图表 / 图片加载会改变内容高度但不一定触发 DOM 变动，用 ResizeObserver
    // 监听主内容区尺寸变化，布局稳定后自动重算分幕位置。
    if (host.ResizeObserver) {
      var resizeObserver = new host.ResizeObserver(schedule);
      var content = doc.querySelector('[data-testid="stMainBlockContainer"]');
      if (content) { resizeObserver.observe(content); }
      if (main) { resizeObserver.observe(main); }
      host.__citySceneResizeObserver = resizeObserver;
    }
    if (doc.fonts && doc.fonts.ready && doc.fonts.ready.then) {
      doc.fonts.ready.then(schedule);
    }
    // 暴露一个「强制重刷」入口，供 Streamlit rerun 后的重复注入调用。
    host.__citySceneApply = function () { update(true); };
    host.__citySceneGradient = true;
  } catch (error) {
    /* 跨域 / 沙箱 / 旧浏览器：静默降级为 CSS 首屏静态配色 */
  }
})();
</script>
"""


def scene_script() -> str:
    """生成滚动换色脚本（把配色数据内嵌为 JSON，避免前后端颜色漂移）。"""
    payload = json.dumps(
        [scene.payload() for scene in SCENE_PALETTES],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return _SCENE_SCRIPT.replace("__SCENE_PAYLOAD__", payload)

