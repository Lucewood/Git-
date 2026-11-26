"""页面自定义 CSS 样式（由 streamlit_app 以 unsafe_allow_html 注入）。

视觉语言：Apple 式「液态玻璃（Liquid Glass）」。
- 背景用低饱和极光渐变，为玻璃提供可折射的色彩；
- 玻璃面板半透明 + 彩色晕染，层级、圆角、描边统一；
- 每个玻璃面只保留极弱内高光（1px 顶缘亮线 + 大面积柔光 + 底缘冷色回光），
  模拟曲面反光而不产生刺眼白边；
- 所有正文统一深墨色，浅玻璃上的对比度 ≥ 7:1，保证可读性优先。
"""

from __future__ import annotations

from .scenes import scene_root_css

CUSTOM_CSS = """
<style>
    /* =====================================================================
       1. 设计令牌
       ===================================================================== */
    :root {
        --ink-900: #0b1428;
        --ink-800: #131f3a;
        --ink-700: #24314e;
        --ink-600: #3a4866;
        --ink-500: #53607c;
        --glass-line: rgba(255, 255, 255, 0.72);
        --glass-blur: blur(22px) saturate(180%);
        --shadow-soft: 0 24px 60px -34px rgba(20, 33, 78, 0.45);
        --shadow-contact: 0 2px 8px -4px rgba(20, 33, 78, 0.25);
        /* 极弱内高光：顶部亮线 + 上缘柔光 + 底缘冷色回光（模拟玻璃曲面） */
        --inner-light:
            inset 0 1px 0 rgba(255, 255, 255, 0.92),
            inset 0 20px 34px -30px rgba(255, 255, 255, 1),
            inset 0 -22px 38px -34px rgba(82, 104, 158, 0.35);
        --radius-xl: 30px;
        --radius-lg: 22px;
        --radius-md: 16px;
        --radius-sm: 12px;
        /* 动效曲线；--glass-x / --glass-y 由 widgets.pointer_glow() 的脚本更新，
           未启用脚本时回退到「顶部中央」的静态高光 */
        --ease-glide: cubic-bezier(0.22, 1, 0.36, 1);
        --ease-soft: cubic-bezier(0.4, 0, 0.2, 1);
    }

    /* =====================================================================
       2. 画布与极光背景
       ===================================================================== */
    html, body, .stApp {
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display",
            "SF Pro Text", "Segoe UI", "PingFang SC", "Microsoft YaHei",
            "Noto Sans SC", sans-serif;
    }
    html, body { background-color: #eef2fa; }
    /* 基底：静态极光渐变；动态柔光交给 ::before（只用 transform，避免整页重绘） */
    .stApp {
        isolation: isolate;
        color: var(--ink-700);
        /* 分幕背景：--scene-* 由 scenes.scene_script() 随滚动逐帧插值；
           无脚本 / 减少动态效果时使用 :root 的首屏静态配色（见文件末尾）。 */
        background-color: var(--scene-base, #e2ebfd);
        background-image: linear-gradient(
            162deg,
            var(--scene-base, #e2ebfd) 0%,
            var(--scene-deep, #f2f6ff) 52%,
            var(--scene-base, #e2ebfd) 100%
        );
        background-attachment: fixed;
    }
    .stApp::before {
        content: "";
        position: fixed;
        inset: -28%;
        z-index: -1;
        pointer-events: none;
        background:
            radial-gradient(38% 38% at 24% 26%, var(--scene-glow-a, rgba(74, 124, 255, 0.54)), transparent 68%),
            radial-gradient(34% 34% at 76% 20%, var(--scene-glow-b, rgba(126, 108, 255, 0.40)), transparent 70%),
            radial-gradient(36% 36% at 22% 78%, var(--scene-glow-b, rgba(126, 108, 255, 0.40)), transparent 70%),
            radial-gradient(38% 38% at 80% 82%, var(--scene-glow-a, rgba(74, 124, 255, 0.54)), transparent 70%);
        opacity: var(--scene-glow-opacity, 0.6);
        animation: auroraFloat 34s ease-in-out infinite alternate;
        will-change: transform;
    }
    /* 极淡的玻璃颗粒：让大面积渐变不显“塑料”，几乎不可见但能增加质感 */
    .stApp::after {
        content: "";
        position: fixed;
        inset: 0;
        z-index: -1;
        pointer-events: none;
        opacity: 0.022;
        mix-blend-mode: soft-light;
        background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.55'/%3E%3C/svg%3E");
    }
    @keyframes auroraFloat {
        0% { transform: translate3d(-2%, -1%, 0) scale(1) rotate(0deg); }
        50% { transform: translate3d(2.5%, 2%, 0) scale(1.07) rotate(3deg); }
        100% { transform: translate3d(-1.5%, 2.5%, 0) scale(1.04) rotate(-2deg); }
    }
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stToolbar"] {
        background: transparent !important;
    }
    /* 为滚动进度条命名 stMain 的滚动时间线 */
    [data-testid="stMain"] {
        scroll-timeline-name: --main-scroll;
        scroll-timeline-axis: block;
    }
    /* 顶栏只保留一层极淡的磨砂，避免滚动时文字与背景互相干扰 */
    [data-testid="stHeader"] {
        background: linear-gradient(
            180deg,
            rgba(255, 255, 255, 0.86) 0%,
            rgba(255, 255, 255, 0.42) 58%,
            rgba(255, 255, 255, 0) 100%
        ) !important;
        backdrop-filter: blur(8px);
    }
    [data-testid="stMainBlockContainer"] {
        max-width: 1500px !important;
        padding-top: 2.2rem;
        padding-bottom: 4rem;
    }

    /* =====================================================================
       3. 基础排版（深墨色，先声明，组件样式随后覆盖）
       ===================================================================== */
    [data-testid="stMarkdownContainer"] h1,
    [data-testid="stMarkdownContainer"] h2,
    [data-testid="stMarkdownContainer"] h3,
    [data-testid="stMarkdownContainer"] h4,
    [data-testid="stMarkdownContainer"] h5,
    [data-testid="stMarkdownContainer"] h6 {
        color: var(--ink-900);
        letter-spacing: -0.01em;
    }
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li,
    [data-testid="stMarkdownContainer"] dd {
        color: var(--ink-700);
    }
    [data-testid="stMarkdownContainer"] strong { color: #101c38; }
    [data-testid="stMarkdownContainer"] a {
        color: #2f4fb8;
        text-decoration-color: rgba(47, 79, 184, 0.35);
        text-underline-offset: 2px;
    }
    [data-testid="stWidgetLabel"] p,
    [data-testid="stWidgetLabel"] label {
        color: #2a3856 !important;
        font-weight: 600;
        letter-spacing: 0.01em;
    }
    /* 小节标题下的一小段流动渐变线：给长页面建立节奏 */
    [data-testid="stMain"] [data-testid="stMarkdownContainer"] h3 {
        position: relative;
        padding-bottom: 0.35rem;
    }
    [data-testid="stMain"] [data-testid="stMarkdownContainer"] h3::after {
        content: "";
        position: absolute;
        left: 0;
        bottom: 0;
        width: 2.1rem;
        height: 2px;
        border-radius: 99px;
        background: linear-gradient(90deg, #6ea8ff, #8b7cf6 45%, #3fd0bd 75%, #6ea8ff);
        background-size: 220% 100%;
        opacity: 0.85;
        animation: underlineFlow 9s linear infinite;
    }
    @keyframes underlineFlow {
        from { background-position: 0% 50%; }
        to { background-position: 220% 50%; }
    }
    /* 指标卡标题不需要下划线 */
    [data-testid="stMain"] .metric-card h3 { padding-bottom: 0; }
    [data-testid="stMain"] .metric-card h3::after { content: none; }

    /* =====================================================================
       4. Hero（标题区玻璃面板）
       ===================================================================== */
    .hero-glass {
        position: relative;
        overflow: hidden;
        margin: 0.2rem 0 1.5rem;
        padding: 2.3rem 2rem 1.9rem;
        border-radius: var(--radius-xl);
        border: 1px solid var(--glass-line);
        background:
            radial-gradient(460px 300px at var(--glass-x, 50%) var(--glass-y, -18%), rgba(255, 255, 255, 0.36), rgba(255, 255, 255, 0) 72%),
            radial-gradient(120% 150% at 8% -10%, rgba(112, 154, 255, 0.30), transparent 58%),
            radial-gradient(110% 140% at 92% 0%, rgba(255, 166, 200, 0.28), transparent 60%),
            radial-gradient(120% 140% at 50% 120%, rgba(126, 226, 208, 0.22), transparent 62%),
            linear-gradient(155deg, rgba(255, 255, 255, 0.84), rgba(255, 255, 255, 0.52));
        box-shadow: var(--shadow-soft), var(--inner-light);
        backdrop-filter: var(--glass-blur);
        transition: border-color 0.35s var(--ease-soft), box-shadow 0.35s var(--ease-soft);
        animation: heroIn 0.78s var(--ease-glide) both;
    }
    @keyframes heroIn {
        from { opacity: 0; translate: 0 -10px; }
        to { opacity: 1; translate: 0 0; }
    }
    /* 上缘大面积柔光：只做 36% 高度，模拟玻璃曲面的一次反射 */
    .hero-glass::before {
        content: "";
        position: absolute;
        inset: 0;
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.55), rgba(255, 255, 255, 0) 36%);
        opacity: 0.6;
        pointer-events: none;
    }
    /* 顶缘 1px 高光：极缓慢地缩放呼吸，模拟玻璃边缘的曲面反光 */
    .hero-glass::after {
        content: "";
        position: absolute;
        left: 8%;
        right: 8%;
        top: 0;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.98), transparent);
        opacity: 0.9;
        pointer-events: none;
        animation: hairlineBreathe 7.5s ease-in-out infinite;
    }
    @keyframes hairlineBreathe {
        0%, 100% { opacity: 0.5; transform: scaleX(0.88); }
        50% { opacity: 1; transform: scaleX(1); }
    }
    .hero-eyebrow {
        position: relative;
        z-index: 1;
        text-align: center;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.34em;
        text-indent: 0.34em;
        color: #42568a;
        text-transform: uppercase;
    }
    .main-header {
        position: relative;
        z-index: 1;
        margin: 0.35rem 0 0;
        padding: 0;
        font-size: clamp(1.9rem, 3vw, 2.7rem);
        font-weight: 800;
        line-height: 1.22;
        letter-spacing: -0.02em;
        text-align: center;
        background: linear-gradient(112deg, #20337a 0%, #3f56b8 38%, #6d4bb5 68%, #1e6f86 100%);
        -webkit-background-clip: text;
        background-clip: text;
        -webkit-text-fill-color: transparent;
        filter: drop-shadow(0 1px 0 rgba(255, 255, 255, 0.6));
    }
    /* 保留 emoji 原色（避免被文字渐变裁剪成剪影） */
    .hero-emoji {
        -webkit-text-fill-color: initial;
        background: none;
        filter: drop-shadow(0 4px 10px rgba(60, 90, 160, 0.18));
    }
    .hero-sub {
        position: relative;
        z-index: 1;
        max-width: 920px;
        margin: 0.55rem auto 0;
        text-align: center;
        font-size: 1.02rem;
        line-height: 1.75;
        color: #38476b;
    }
    /* Hero 内部的漂浮光球与扫光：只在 Hero 内运动，不干扰正文 */
    .hero-aurora {
        position: absolute;
        inset: 0;
        z-index: 0;
        overflow: hidden;
        border-radius: inherit;
        pointer-events: none;
    }
    /* 慢速旋转的棱镜光晕：只用 transform 合成，不会逐帧重绘 Hero 内容 */
    .hero-aurora::before {
        content: "";
        position: absolute;
        inset: -46%;
        border-radius: inherit;
        background: conic-gradient(
            from 0deg,
            rgba(110, 150, 255, 0.34),
            rgba(255, 158, 196, 0.22),
            rgba(86, 222, 200, 0.28),
            rgba(164, 140, 255, 0.34),
            rgba(110, 150, 255, 0.34)
        );
        filter: blur(54px);
        opacity: 0.34;
        animation: prismSpin 52s linear infinite;
        will-change: transform;
    }
    /* 极淡的星尘：只有 transform + opacity 动画，成本极低 */
    .hero-aurora::after {
        content: "";
        position: absolute;
        inset: -4%;
        opacity: 0.45;
        background-image:
            radial-gradient(circle at 10% 26%, rgba(255, 255, 255, 0.95) 0 1.4px, transparent 2.2px),
            radial-gradient(circle at 23% 68%, rgba(255, 255, 255, 0.85) 0 1.2px, transparent 2px),
            radial-gradient(circle at 38% 18%, rgba(255, 255, 255, 0.8) 0 1.6px, transparent 2.4px),
            radial-gradient(circle at 52% 82%, rgba(255, 255, 255, 0.9) 0 1.3px, transparent 2.1px),
            radial-gradient(circle at 66% 32%, rgba(255, 255, 255, 0.8) 0 1.5px, transparent 2.3px),
            radial-gradient(circle at 78% 74%, rgba(255, 255, 255, 0.92) 0 1.2px, transparent 2px),
            radial-gradient(circle at 88% 22%, rgba(255, 255, 255, 0.85) 0 1.6px, transparent 2.4px),
            radial-gradient(circle at 44% 48%, rgba(255, 255, 255, 0.7) 0 1px, transparent 1.8px);
        background-repeat: no-repeat;
        animation: dustDrift 16s ease-in-out infinite alternate;
        will-change: transform, opacity;
    }
    @keyframes prismSpin { to { transform: rotate(360deg); } }
    @keyframes dustDrift {
        from { transform: translate3d(0, 0, 0); opacity: 0.22; }
        to { transform: translate3d(0, -12px, 0); opacity: 0.58; }
    }
    .hero-orb {
        position: absolute;
        display: block;
        border-radius: 50%;
        filter: blur(22px);
        opacity: 0.55;
        animation: heroOrb 18s ease-in-out infinite alternate;
        will-change: transform;
    }
    .hero-orb-blue {
        width: 320px;
        height: 320px;
        left: -90px;
        top: -130px;
        background: radial-gradient(circle at 35% 35%, rgba(96, 146, 255, 0.62), rgba(96, 146, 255, 0) 67%);
        animation-delay: -2s;
    }
    .hero-orb-pink {
        width: 300px;
        height: 300px;
        right: -70px;
        bottom: -140px;
        background: radial-gradient(circle at 50% 50%, rgba(255, 138, 184, 0.52), rgba(255, 138, 184, 0) 68%);
        animation-delay: -8s;
    }
    .hero-orb-teal {
        width: 230px;
        height: 230px;
        right: 24%;
        top: 6%;
        opacity: 0.34;
        background: radial-gradient(circle at 50% 50%, rgba(74, 220, 198, 0.5), rgba(74, 220, 198, 0) 68%);
        animation-delay: -14s;
    }
    .hero-orb-violet {
        width: 250px;
        height: 250px;
        left: 18%;
        bottom: -150px;
        opacity: 0.32;
        background: radial-gradient(circle at 50% 50%, rgba(168, 132, 255, 0.55), rgba(168, 132, 255, 0) 68%);
        animation-delay: -6s;
    }
    .hero-sheen {
        position: absolute;
        top: -70%;
        left: 0;
        width: 40%;
        height: 240%;
        opacity: 0;
        transform: translate3d(-160%, 0, 0) rotate(14deg);
        background: linear-gradient(100deg, transparent, rgba(255, 255, 255, 0.55), transparent);
        animation: heroSheen 12s ease-in-out infinite;
        pointer-events: none;
    }
    .hero-chips {
        position: relative;
        z-index: 1;
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 0.5rem;
        margin-top: 1.15rem;
    }
    .hero-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.32rem;
        padding: 0.4rem 0.82rem;
        border-radius: 999px;
        border: 1px solid rgba(255, 255, 255, 0.78);
        background: linear-gradient(150deg, rgba(255, 255, 255, 0.74), rgba(255, 255, 255, 0.42));
        color: #2e3f66;
        font-size: 0.76rem;
        font-weight: 600;
        white-space: nowrap;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.92),
            0 8px 20px -16px rgba(20, 35, 80, 0.45);
        backdrop-filter: blur(10px) saturate(150%);
        transition: transform 0.2s ease, background 0.2s ease, border-color 0.2s ease;
    }
    .hero-chip:hover {
        transform: translateY(-2px);
        border-color: rgba(255, 255, 255, 0.98);
        background: linear-gradient(150deg, rgba(255, 255, 255, 0.92), rgba(255, 255, 255, 0.56));
    }
    /* 胶囊入场：只动 translate / opacity，避免覆盖 hover 的 transform */
    .hero-chip { animation: chipIn 0.62s var(--ease-glide) both; }
    .hero-chip:nth-child(2) { animation-delay: 0.05s; }
    .hero-chip:nth-child(3) { animation-delay: 0.1s; }
    .hero-chip:nth-child(4) { animation-delay: 0.15s; }
    @keyframes chipIn {
        from { opacity: 0; translate: 0 10px; }
        to { opacity: 1; translate: 0 0; }
    }
    .hero-eyebrow { animation: none; }
    .hero-sub { animation: none; }
    .main-header {
        background-size: 200% 100%;
        animation: titleFlow 16s ease-in-out infinite;
    }
    @keyframes titleFlow {
        0%, 100% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
    }
    @keyframes heroOrb {
        0% { transform: translate3d(0, 0, 0) scale(1); }
        50% { transform: translate3d(20px, -14px, 0) scale(1.08); }
        100% { transform: translate3d(-14px, 12px, 0) scale(1.03); }
    }
    @keyframes heroSheen {
        0%, 68% { transform: translate3d(-160%, 0, 0) rotate(14deg); opacity: 0; }
        76% { opacity: 0.55; }
        100% { transform: translate3d(360%, 0, 0) rotate(14deg); opacity: 0; }
    }
    /* =====================================================================
       5. 章节标题（二级）
       ===================================================================== */
    /* 一级模块标题：编号圆牌 + 标题 + 一句话说明，给长页面建立清晰的段落感 */
    .module-header {
        position: relative;
        display: flex;
        align-items: center;
        gap: 1rem;
        margin: 2.2rem 0 0.55rem;
        padding: 1.1rem 1.35rem;
        border-radius: var(--radius-lg);
        border: 1px solid var(--glass-line);
        background:
            radial-gradient(320px 180px at var(--glass-x, 50%) var(--glass-y, -10%), rgba(255, 255, 255, 0.4), rgba(255, 255, 255, 0) 72%),
            radial-gradient(120% 160% at 0% 0%, rgba(110, 152, 255, 0.20), transparent 58%),
            radial-gradient(120% 160% at 100% 100%, rgba(63, 208, 189, 0.13), transparent 60%),
            linear-gradient(150deg, rgba(255, 255, 255, 0.82), rgba(255, 255, 255, 0.48));
        box-shadow: var(--shadow-soft),
            inset 0 1px 0 rgba(255, 255, 255, 0.94),
            inset 0 20px 36px -34px rgba(255, 255, 255, 1);
        overflow: hidden;
        backdrop-filter: blur(18px) saturate(160%);
        transition: border-color 0.3s var(--ease-soft), box-shadow 0.3s var(--ease-soft);
        animation: glassRise 0.52s var(--ease-glide) both;
    }
    .module-header::after {
        content: "";
        position: absolute;
        left: 8%;
        right: 8%;
        top: 0;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.98), transparent);
        opacity: 0.85;
        pointer-events: none;
        animation: hairlineBreathe 8s ease-in-out infinite;
    }
    .module-header:hover {
        border-color: rgba(255, 255, 255, 0.98);
        box-shadow: 0 30px 66px -38px rgba(20, 33, 78, 0.52),
            inset 0 1px 0 rgba(255, 255, 255, 1),
            inset 0 20px 36px -34px rgba(255, 255, 255, 1);
    }
    .module-step {
        flex: 0 0 auto;
        display: grid;
        place-items: center;
        width: 2.5rem;
        height: 2.5rem;
        border-radius: 50%;
        font-size: 0.8rem;
        font-weight: 800;
        letter-spacing: 0.04em;
        color: #ffffff;
        background: linear-gradient(135deg, #33489f 0%, #4b3a9e 55%, #2c6b86 100%);
        box-shadow: 0 12px 26px -14px rgba(43, 52, 140, 0.75),
            inset 0 1px 0 rgba(255, 255, 255, 0.35);
    }
    .module-heading { min-width: 0; }
    .module-header .module-title {
        margin: 0;
        font-size: clamp(1.3rem, 0.55vw + 1.1rem, 1.6rem);
        font-weight: 800;
        line-height: 1.3;
        letter-spacing: -0.015em;
        color: var(--ink-900);
    }
    .module-header .module-desc {
        margin: 0.18rem 0 0;
        font-size: 0.82rem;
        line-height: 1.55;
        color: #4a5877;
    }

    /* 二级章节标题：比模块标题小一级，保持「模块 → 小节」的层级 */
    .section-title {
        position: relative;
        display: flex;
        align-items: center;
        gap: 0.65rem;
        margin: 1.6rem 0 0.85rem;
        padding: 0.78rem 1.05rem 0.78rem 1rem;
        font-size: 1.3rem;
        font-weight: 700;
        letter-spacing: -0.01em;
        color: var(--ink-900);
        border-radius: var(--radius-lg);
        border: 1px solid var(--glass-line);
        background:
            radial-gradient(280px 160px at var(--glass-x, 50%) var(--glass-y, -10%), rgba(255, 255, 255, 0.38), rgba(255, 255, 255, 0) 72%),
            radial-gradient(120% 160% at 0% 0%, rgba(110, 152, 255, 0.16), transparent 58%),
            radial-gradient(120% 160% at 100% 100%, rgba(167, 139, 250, 0.13), transparent 60%),
            linear-gradient(150deg, rgba(255, 255, 255, 0.78), rgba(255, 255, 255, 0.46));
        box-shadow: var(--shadow-soft),
            inset 0 1px 0 rgba(255, 255, 255, 0.92),
            inset 0 18px 34px -32px rgba(255, 255, 255, 1);
        overflow: hidden;
        transition: box-shadow 0.3s var(--ease-soft), border-color 0.3s var(--ease-soft);
    }
    .section-title:hover {
        border-color: rgba(255, 255, 255, 0.98);
        box-shadow: 0 30px 66px -38px rgba(20, 33, 78, 0.52),
            inset 0 1px 0 rgba(255, 255, 255, 1),
            inset 0 18px 34px -32px rgba(255, 255, 255, 1);
    }
    /* 蓝色光条改为 flex 占位元素：与图标/文字自然排版，永不重叠 */
    .section-title::before {
        content: "";
        flex: 0 0 4px;
        align-self: center;
        width: 4px;
        height: 1.35em;
        border-radius: 99px;
        background: linear-gradient(180deg, #6ea8ff, #8b7cf6 38%, #3fd0bd 70%, #6ea8ff 100%);
        background-size: 100% 260%;
        box-shadow: 0 0 14px rgba(110, 150, 255, 0.45);
        animation: accentFlow 7s linear infinite, accentPulse 6.5s ease-in-out infinite;
    }
    @keyframes accentFlow {
        from { background-position: 50% 0%; }
        to { background-position: 50% 260%; }
    }
    @keyframes accentPulse {
        0%, 100% { opacity: 0.82; }
        50% { opacity: 1; }
    }
    /* 悬停时一道柔光扫过玻璃标题：替代原先重复的静态顶线（顶线由 inset 内高光提供） */
    .section-title::after {
        content: "";
        position: absolute;
        top: -60%;
        bottom: -60%;
        left: -32%;
        width: 24%;
        border-radius: inherit;
        background: linear-gradient(100deg, transparent, rgba(255, 255, 255, 0.55), transparent);
        opacity: 0;
        transform: translate3d(-140%, 0, 0) rotate(10deg);
        pointer-events: none;
    }
    .section-title:hover::after { animation: panelSheen 1.15s var(--ease-soft); }
    @keyframes panelSheen {
        0% { opacity: 0; transform: translate3d(-140%, 0, 0) rotate(10deg); }
        22% { opacity: 0.6; }
        100% { opacity: 0; transform: translate3d(520%, 0, 0) rotate(10deg); }
    }

    /* 顶部滚动进度条（滚动驱动动画；不支持的浏览器保持不可见） */
    .scroll-progress {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        z-index: 2147483000;
        transform: scaleX(0);
        transform-origin: 0 50%;
        background: linear-gradient(
            90deg,
            var(--scene-accent, #6ea8ff),
            var(--scene-glow-b, #8b7cf6) 55%,
            var(--scene-accent, #3fd0bd)
        );
        box-shadow: 0 0 14px var(--scene-glow-a, rgba(110, 150, 255, 0.55));
        pointer-events: none;
    }
    @supports (animation-timeline: scroll()) {
        .scroll-progress {
            animation: scrollProgress linear both;
            animation-timeline: --main-scroll;
        }
    }
    @keyframes scrollProgress {
        from { transform: scaleX(0); }
        to { transform: scaleX(1); }
    }

    @keyframes statusPulse {
        0%, 100% { transform: scale(1); opacity: 0.82; box-shadow: 0 0 6px rgba(80, 200, 220, 0.45); }
        50% { transform: scale(1.35); opacity: 1; box-shadow: 0 0 14px rgba(80, 200, 220, 0.9); }
    }

    /* =====================================================================
       6. 指标卡片：多彩浅玻璃（文字始终为深墨色）
       ===================================================================== */
    .metric-card {
        position: relative;
        isolation: isolate;
        overflow: hidden;
        height: 100%;
        min-height: 118px;
        padding: 1.1rem 1.15rem 1.05rem;
        border-radius: var(--radius-lg);
        border: 1px solid var(--glass-line);
        color: var(--ink-900);
        text-align: left;
        background:
            radial-gradient(190px 190px at var(--glass-x, 50%) var(--glass-y, -12%), rgba(255, 255, 255, 0.42), rgba(255, 255, 255, 0) 72%),
            radial-gradient(130% 130% at 6% 0%, var(--tint-1, rgba(96, 146, 255, 0.22)), transparent 62%),
            radial-gradient(120% 120% at 100% 100%, var(--tint-2, rgba(150, 130, 255, 0.14)), transparent 60%),
            linear-gradient(150deg, rgba(255, 255, 255, 0.86), rgba(255, 255, 255, 0.54));
        box-shadow: var(--shadow-soft), var(--shadow-contact), var(--inner-light);
        backdrop-filter: var(--glass-blur);
        transition: transform 0.28s var(--ease-glide), box-shadow 0.28s var(--ease-soft),
            border-color 0.28s var(--ease-soft);
        animation: glassRise 0.52s var(--ease-glide) both;
    }
    .metric-card:hover {
        transform: translateY(-3px);
        border-color: rgba(255, 255, 255, 0.96);
        box-shadow:
            0 30px 66px -34px rgba(20, 33, 78, 0.5),
            var(--shadow-contact), var(--inner-light);
    }
    @keyframes glassRise {
        from { opacity: 0.35; translate: 0 12px; }
        to { opacity: 1; translate: 0 0; }
    }
    /* 悬停时一道极淡的高光扫过玻璃表面 */
    .metric-card::before {
        content: "";
        position: absolute;
        top: -70%;
        left: 0;
        width: 55%;
        height: 240%;
        z-index: 0;
        opacity: 0;
        transform: translate3d(-180%, 0, 0) rotate(14deg);
        background: linear-gradient(100deg, transparent, rgba(255, 255, 255, 0.52), transparent);
        pointer-events: none;
    }
    .metric-card:hover::before { animation: cardSheen 0.95s ease; }
    @keyframes cardSheen {
        0% { transform: translate3d(-180%, 0, 0) rotate(14deg); opacity: 0; }
        25% { opacity: 0.52; }
        100% { transform: translate3d(280%, 0, 0) rotate(14deg); opacity: 0; }
    }
    .metric-card h3,
    .metric-card h1,
    .metric-card .sub {
        position: relative;
        z-index: 1;
    }
    /* 顶缘极细高光：只在卡片上缘中段出现，模拟曲面反射 */
    .metric-card::after {
        content: "";
        position: absolute;
        left: 12%;
        right: 12%;
        top: 0;
        height: 1px;
        z-index: 2;
        background: linear-gradient(90deg, transparent, var(--accent, rgba(255, 255, 255, 0.95)), transparent);
        opacity: 0.7;
        pointer-events: none;
        animation: hairlineBreathe 9s ease-in-out infinite;
    }
    .metric-card h3 {
        margin: 0 0 0.45rem;
        font-size: 0.84rem;
        font-weight: 600;
        letter-spacing: 0.03em;
        color: #33415f;
        opacity: 1;
        overflow-wrap: anywhere;
    }
    .metric-card h1 {
        margin: 0;
        /* 6 列指标卡在 1440px 左右容易挤出卡片：按视口宽度平滑收缩 */
        font-size: clamp(1.35rem, 0.95vw + 0.85rem, 1.9rem);
        line-height: 1.15;
        font-weight: 700;
        letter-spacing: -0.02em;
        color: #0a1327;
        font-variant-numeric: tabular-nums;
        overflow-wrap: anywhere;
    }
    .metric-card .sub {
        margin-top: 0.35rem;
        font-size: 0.76rem;
        line-height: 1.45;
        color: #4a5877;
        opacity: 1;
    }

    /* 语义色（可在 widgets.metric_card(..., tone="mint") 显式指定） */
    .metric-card.tone-blue  { --tint-1: rgba(96, 146, 255, 0.26); --tint-2: rgba(122, 112, 255, 0.14); --accent: rgba(126, 164, 255, 0.9); }
    .metric-card.tone-mint  { --tint-1: rgba(50, 202, 168, 0.24); --tint-2: rgba(120, 232, 206, 0.14); --accent: rgba(96, 222, 190, 0.9); }
    .metric-card.tone-peach { --tint-1: rgba(255, 150, 104, 0.24); --tint-2: rgba(255, 200, 130, 0.14); --accent: rgba(255, 176, 128, 0.9); }
    .metric-card.tone-lilac { --tint-1: rgba(164, 136, 250, 0.25); --tint-2: rgba(120, 112, 255, 0.14); --accent: rgba(178, 152, 255, 0.9); }
    .metric-card.tone-rose  { --tint-1: rgba(255, 122, 164, 0.23); --tint-2: rgba(255, 176, 204, 0.14); --accent: rgba(255, 152, 184, 0.9); }
    .metric-card.tone-sky   { --tint-1: rgba(72, 186, 238, 0.23); --tint-2: rgba(120, 220, 242, 0.14); --accent: rgba(112, 206, 246, 0.9); }
    .metric-card.tone-amber { --tint-1: rgba(246, 190, 92, 0.25); --tint-2: rgba(255, 224, 150, 0.14); --accent: rgba(248, 206, 120, 0.9); }

    /* 自动轮换：同一行卡片呈现不同玻璃色（:where 降低优先级，显式 tone 仍可覆盖） */
    :where([data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(6n+1)) .metric-card {
        --tint-1: rgba(96, 146, 255, 0.25); --tint-2: rgba(122, 112, 255, 0.13);
        --accent: rgba(126, 164, 255, 0.9);
    }
    :where([data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(6n+2)) .metric-card {
        --tint-1: rgba(50, 202, 168, 0.23); --tint-2: rgba(120, 232, 206, 0.13);
        --accent: rgba(96, 222, 190, 0.9);
    }
    :where([data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(6n+3)) .metric-card {
        --tint-1: rgba(255, 150, 104, 0.23); --tint-2: rgba(255, 200, 130, 0.13);
        --accent: rgba(255, 176, 128, 0.9);
    }
    :where([data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(6n+4)) .metric-card {
        --tint-1: rgba(164, 136, 250, 0.24); --tint-2: rgba(120, 112, 255, 0.13);
        --accent: rgba(178, 152, 255, 0.9);
    }
    :where([data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(6n+5)) .metric-card {
        --tint-1: rgba(255, 122, 164, 0.22); --tint-2: rgba(255, 176, 204, 0.13);
        --accent: rgba(255, 152, 184, 0.9);
    }
    :where([data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(6n+6)) .metric-card {
        --tint-1: rgba(72, 186, 238, 0.22); --tint-2: rgba(120, 220, 242, 0.13);
        --accent: rgba(112, 206, 246, 0.9);
    }

    /* =====================================================================
       7. 洞察框（浅玻璃 + 左侧彩色光条）
       ===================================================================== */
    .insight-box {
        position: relative;
        overflow: hidden;
        margin: 1rem 0;
        padding: 1.05rem 1.15rem 1.05rem 1.35rem;
        border-radius: var(--radius-md);
        border: 1px solid var(--glass-line);
        color: #1e2a47;
        background:
            radial-gradient(240px 200px at var(--glass-x, 50%) var(--glass-y, -10%), rgba(255, 255, 255, 0.4), rgba(255, 255, 255, 0) 72%),
            radial-gradient(120% 130% at 0% 0%, var(--tint-1, rgba(110, 150, 255, 0.20)), transparent 58%),
            radial-gradient(120% 130% at 100% 100%, var(--tint-2, rgba(167, 139, 250, 0.15)), transparent 60%),
            linear-gradient(150deg, rgba(255, 255, 255, 0.84), rgba(255, 255, 255, 0.54));
        box-shadow: 0 16px 40px -30px rgba(20, 35, 80, 0.45),
            inset 0 1px 0 rgba(255, 255, 255, 0.95),
            inset 0 18px 30px -28px rgba(255, 255, 255, 1);
        backdrop-filter: blur(16px) saturate(160%);
        transition: transform 0.3s var(--ease-glide), box-shadow 0.3s var(--ease-soft);
        animation: glassRise 0.5s var(--ease-glide) both;
    }
    .insight-box:hover {
        transform: translateY(-3px);
        box-shadow: 0 24px 54px -32px rgba(20, 35, 80, 0.5),
            inset 0 1px 0 rgba(255, 255, 255, 1),
            inset 0 18px 30px -28px rgba(255, 255, 255, 1);
    }
    /* 悬停扫光：与章节标题同一套 keyframes，保持动效语言一致 */
    .insight-box::after {
        content: "";
        position: absolute;
        top: -80%;
        bottom: -80%;
        left: -30%;
        width: 22%;
        background: linear-gradient(100deg, transparent, rgba(255, 255, 255, 0.45), transparent);
        opacity: 0;
        transform: translate3d(-160%, 0, 0) rotate(10deg);
        pointer-events: none;
    }
    .insight-box:hover::after { animation: panelSheen 1.2s var(--ease-soft); }
    .insight-box::before {
        content: "";
        position: absolute;
        left: 0;
        top: 14%;
        bottom: 14%;
        width: 4px;
        border-radius: 99px;
        background: linear-gradient(180deg, var(--accent-a, #6ea8ff), var(--accent-b, #8b7cf6), var(--accent-a, #6ea8ff));
        background-size: 100% 220%;
        opacity: 0.9;
        animation: accentFlow 8s linear infinite, accentPulse 7s ease-in-out infinite;
    }
    .insight-box strong { color: #1b2c5e; }
    .insight-box p { color: #1e2a47; }

    .insight-box.tone-blue  { --tint-1: rgba(110, 150, 255, 0.20); --tint-2: rgba(167, 139, 250, 0.15); --accent-a: #6ea8ff; --accent-b: #8b7cf6; }
    .insight-box.tone-mint  { --tint-1: rgba(50, 202, 168, 0.20); --tint-2: rgba(110, 226, 214, 0.14); --accent-a: #2fc9a0; --accent-b: #7ee7d5; }
    .insight-box.tone-peach { --tint-1: rgba(255, 150, 104, 0.20); --tint-2: rgba(255, 206, 138, 0.14); --accent-a: #ff9f6e; --accent-b: #ffc978; }
    .insight-box.tone-lilac { --tint-1: rgba(164, 136, 250, 0.20); --tint-2: rgba(110, 132, 255, 0.14); --accent-a: #a78bfa; --accent-b: #7c8cff; }
    .insight-box.tone-rose  { --tint-1: rgba(255, 122, 164, 0.19); --tint-2: rgba(255, 182, 208, 0.14); --accent-a: #ff7fa8; --accent-b: #ffb0c8; }
    .insight-box.tone-amber { --tint-1: rgba(246, 190, 92, 0.21); --tint-2: rgba(255, 222, 148, 0.14); --accent-a: #f2be5c; --accent-b: #ffd98a; }

    .info-badge {
        display: inline-block;
        padding: 0.25rem 0.9rem;
        border-radius: 999px;
        border: 1px solid rgba(255, 255, 255, 0.75);
        background: linear-gradient(135deg, rgba(96, 132, 255, 0.16), rgba(150, 130, 255, 0.13));
        color: #2b3c74;
        font-size: 0.8rem;
        margin-right: 0.5rem;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85);
    }

    /* =====================================================================
       8. 侧边栏：整块磨砂玻璃
       ===================================================================== */
    [data-testid="stSidebar"] {
        position: relative;
        background-color: rgba(255, 255, 255, 0.62) !important;
        background-image:
            radial-gradient(120% 55% at 0% 0%, rgba(120, 158, 255, 0.26), transparent 60%),
            radial-gradient(120% 55% at 100% 100%, rgba(167, 143, 255, 0.22), transparent 62%),
            linear-gradient(180deg, rgba(255, 255, 255, 0.74), rgba(243, 246, 255, 0.58)) !important;
        background-repeat: no-repeat;
        background-size: 180% 70%, 180% 70%, 100% 100%;
        background-position: 0% 0%, 100% 100%, 0 0;
        border-right: 1px solid rgba(255, 255, 255, 0.68);
        box-shadow: 18px 0 50px -40px rgba(20, 32, 80, 0.55),
            inset -1px 0 0 rgba(255, 255, 255, 0.5);
        backdrop-filter: blur(28px) saturate(170%);
        animation: sidebarAurora 28s ease-in-out infinite alternate;
    }
    @keyframes sidebarAurora {
        0% { background-position: 0% 0%, 100% 100%, 0 0; }
        50% { background-position: 12% 8%, 88% 92%, 0 0; }
        100% { background-position: 4% 14%, 96% 86%, 0 0; }
    }
    /* 侧边栏右缘的「光带」：极慢地自上而下流动，强化玻璃边缘的折射感 */
    [data-testid="stSidebar"]::after {
        content: "";
        position: absolute;
        top: 0;
        right: 0;
        width: 1px;
        height: 45%;
        background: linear-gradient(180deg, transparent, rgba(255, 255, 255, 0.95), transparent);
        opacity: 0;
        pointer-events: none;
        z-index: 3;
        animation: sidebarEdge 13s ease-in-out infinite;
        will-change: transform, opacity;
    }
    @keyframes sidebarEdge {
        0% { transform: translateY(-30%); opacity: 0; }
        30% { opacity: 0.85; }
        70% { opacity: 0.45; }
        100% { transform: translateY(130%); opacity: 0; }
    }
    [data-testid="stSidebar"] h2::before {
        content: "";
        display: inline-block;
        width: 7px;
        height: 7px;
        margin-right: 0.5rem;
        border-radius: 50%;
        background: linear-gradient(135deg, #3fd0bd, #6ea8ff);
        box-shadow: 0 0 10px rgba(80, 200, 220, 0.7);
        vertical-align: middle;
        animation: statusPulse 2.8s ease-in-out infinite;
    }
    [data-testid="stSidebarContent"],
    [data-testid="stSidebarHeader"] {
        background: transparent !important;
    }
    [data-testid="stSidebarUserContent"] { padding-top: 1.1rem; }
    [data-testid="stSidebar"] h2 {
        font-size: 1.08rem;
        font-weight: 700;
        letter-spacing: 0.01em;
        color: #12203c;
    }
    [data-testid="stSidebar"] h3 {
        font-size: 0.92rem;
        font-weight: 700;
        color: #1c2a4a;
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
        color: #43506e !important;
    }
    [data-testid="stSidebar"] hr,
    [data-testid="stMain"] hr {
        border: none;
        border-top: 1px solid rgba(120, 140, 185, 0.22);
        margin: 1rem 0;
    }
    /* 侧边栏分隔线做一点玻璃反光 */
    [data-testid="stSidebar"] hr {
        border-top-color: rgba(255, 255, 255, 0.6);
        box-shadow: 0 1px 0 rgba(120, 140, 185, 0.12);
    }
    [data-testid="stExpandSidebarButton"],
    [data-testid="stSidebarCollapseButton"] button {
        border-radius: 12px !important;
        border: 1px solid rgba(255, 255, 255, 0.7) !important;
        background: rgba(255, 255, 255, 0.58) !important;
        color: #2c3c62 !important;
        backdrop-filter: blur(12px);
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85);
    }

    /* =====================================================================
       8.1 侧边栏功能导航（6 个模块按钮 + 折叠细分章节，页内锚点不触发 rerun）
       ===================================================================== */
    .nav-heading {
        margin: 0.15rem 0 0.5rem;
        padding-left: 0.1rem;
        font-size: 0.82rem;
        font-weight: 800;
        letter-spacing: 0.02em;
        color: #1c2a4a;
    }
    .sidebar-nav {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
        margin: 0 0 0.9rem;
    }
    .nav-module-grid {
        display: flex;
        flex-direction: column;
        gap: 0.34rem;
    }
    .nav-module {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        padding: 0.5rem 0.6rem;
        border-radius: 13px;
        border: 1px solid rgba(255, 255, 255, 0.72);
        background: linear-gradient(150deg, rgba(255, 255, 255, 0.78), rgba(255, 255, 255, 0.44));
        color: #1f2d4f !important;
        text-decoration: none !important;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.92),
            0 10px 22px -20px rgba(20, 35, 80, 0.5);
        transition: transform 0.18s var(--ease-glide), background 0.18s ease,
            border-color 0.18s ease, box-shadow 0.18s ease;
    }
    .nav-module:hover {
        transform: translateX(2px);
        background: rgba(255, 255, 255, 0.94);
        border-color: rgba(255, 255, 255, 0.98);
        box-shadow: 0 12px 26px -18px rgba(20, 35, 80, 0.55),
            inset 0 1px 0 rgba(255, 255, 255, 1);
    }
    .nav-module:focus-visible {
        outline: 2px solid rgba(79, 110, 247, 0.5);
        outline-offset: 2px;
    }
    .nav-module-icon {
        flex: 0 0 auto;
        display: grid;
        place-items: center;
        width: 1.85rem;
        height: 1.85rem;
        border-radius: 10px;
        font-size: 0.95rem;
        background: linear-gradient(135deg, rgba(96, 132, 255, 0.18), rgba(167, 139, 250, 0.16));
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85);
    }
    .nav-module-text {
        display: flex;
        flex-direction: column;
        min-width: 0;
        line-height: 1.25;
    }
    .nav-module-text strong {
        font-size: 0.82rem;
        font-weight: 700;
        color: #1a2747;
        white-space: nowrap;
    }
    .nav-module-text small {
        overflow: hidden;
        font-size: 0.68rem;
        font-weight: 500;
        color: #667493;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .nav-more {
        padding-top: 0.28rem;
        border-top: 1px dashed rgba(120, 140, 185, 0.28);
    }
    .nav-more summary {
        padding: 0.32rem 0.4rem;
        border-radius: 9px;
        color: #56658a;
        font-size: 0.7rem;
        font-weight: 700;
        cursor: pointer;
        list-style: none;
        transition: background 0.18s ease, color 0.18s ease;
    }
    .nav-more summary::-webkit-details-marker { display: none; }
    .nav-more summary::marker { content: ""; }
    .nav-more summary::before {
        content: "▸";
        display: inline-block;
        margin-right: 0.34rem;
        transition: transform 0.18s ease;
    }
    .nav-more[open] summary::before { transform: rotate(90deg); }
    .nav-more summary:hover { background: rgba(255, 255, 255, 0.6); color: #2b3a5c; }
    .nav-sub-groups {
        display: flex;
        flex-direction: column;
        gap: 0.32rem;
        padding: 0.3rem 0.05rem 0.15rem;
    }
    .nav-subgroup { padding-left: 0.2rem; }
    .nav-subtitle {
        padding: 0.12rem 0.3rem;
        color: #7a86a5;
        font-size: 0.6rem;
        font-weight: 700;
        letter-spacing: 0.12em;
    }
    .nav-sublinks { display: flex; flex-direction: column; gap: 0.05rem; }
    .nav-sublink {
        display: block;
        padding: 0.28rem 0.5rem;
        border-radius: 8px;
        border: 1px solid transparent;
        color: #2b3a5c !important;
        font-size: 0.74rem;
        font-weight: 600;
        text-decoration: none !important;
        transition: background 0.18s ease, border-color 0.18s ease, transform 0.18s ease;
    }
    .nav-sublink:hover {
        background: rgba(255, 255, 255, 0.72);
        border-color: rgba(255, 255, 255, 0.92);
        transform: translateX(2px);
    }
    .nav-sublink:focus-visible {
        outline: 2px solid rgba(79, 110, 247, 0.5);
        outline-offset: 2px;
    }
    .nav-top-link {
        display: flex;
        justify-content: center;
        padding: 0.34rem 0.5rem;
        border-radius: 9px;
        border: 1px solid rgba(255, 255, 255, 0.7);
        background: rgba(255, 255, 255, 0.5);
        color: #3a4a70 !important;
        font-size: 0.72rem;
        font-weight: 600;
        text-decoration: none !important;
        transition: background 0.18s ease, border-color 0.18s ease;
    }
    .nav-top-link:hover {
        background: rgba(255, 255, 255, 0.82);
        border-color: rgba(255, 255, 255, 0.98);
    }

    /* =====================================================================
       9. 输入控件：半透明玻璃内胆
       ===================================================================== */
    [data-baseweb="input"],
    [data-baseweb="base-input"],
    [data-baseweb="textarea"],
    [data-baseweb="select"] > div {
        background: rgba(255, 255, 255, 0.78) !important;
        border: 1px solid rgba(146, 164, 205, 0.38) !important;
        border-radius: var(--radius-sm) !important;
        color: #14203a !important;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9),
            0 4px 14px -12px rgba(20, 35, 80, 0.4) !important;
        transition: border-color 0.18s ease, box-shadow 0.18s ease;
    }
    [data-baseweb="input"] input,
    [data-baseweb="select"] input,
    [data-baseweb="textarea"] textarea {
        color: #14203a !important;
        background: transparent !important;
        caret-color: #3b5bd9;
    }
    [data-baseweb="select"] svg {
        fill: #40506f !important;
        color: #40506f !important;
    }
    ::placeholder { color: #64718a !important; opacity: 1; }
    [data-baseweb="input"]:focus-within,
    [data-baseweb="textarea"]:focus-within,
    [data-baseweb="select"] > div:focus-within {
        border-color: rgba(79, 110, 247, 0.62) !important;
        box-shadow: 0 0 0 4px rgba(79, 110, 247, 0.15),
            inset 0 1px 0 rgba(255, 255, 255, 0.9) !important;
    }
    /* 多选标签：浅蓝玻璃胶囊 */
    [data-baseweb="tag"] {
        background: linear-gradient(135deg, rgba(96, 132, 255, 0.17), rgba(150, 130, 255, 0.15)) !important;
        border: 1px solid rgba(255, 255, 255, 0.7) !important;
        border-radius: 9px !important;
        color: #26386e !important;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
    }
    [data-baseweb="tag"] span { color: #26386e !important; }
    [data-baseweb="tag"] svg { fill: #4a5a86 !important; color: #4a5a86 !important; }
    /* 下拉浮层 */
    [data-baseweb="popover"] [role="listbox"],
    [data-baseweb="popover"] [data-baseweb="menu"] {
        background: rgba(255, 255, 255, 0.96) !important;
        border-radius: var(--radius-sm) !important;
        border: 1px solid rgba(255, 255, 255, 0.8) !important;
        box-shadow: 0 24px 54px -30px rgba(20, 33, 78, 0.5),
            inset 0 1px 0 rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(18px) saturate(160%);
    }
    [data-baseweb="popover"] li { color: #1d2a46 !important; }
    [data-baseweb="popover"] li:hover { background: rgba(96, 140, 255, 0.12) !important; }
    /* 滑块：白色玻璃圆珠 + 柔和光晕 */
    [data-testid="stSlider"] [role="slider"] {
        background: #ffffff !important;
        border: 1px solid rgba(120, 143, 200, 0.6) !important;
        box-shadow: 0 3px 10px rgba(35, 55, 120, 0.28),
            inset 0 1px 0 rgba(255, 255, 255, 1) !important;
    }
    [data-testid="stSlider"] [data-testid="stSliderThumbValue"] {
        color: #2b3b63 !important;
        background: rgba(255, 255, 255, 0.76);
        border-radius: 6px;
    }
    [data-testid="stRadio"] label,
    [data-testid="stCheckbox"] label,
    [data-testid="stRadio"] p,
    [data-testid="stCheckbox"] p {
        color: #26334f !important;
    }

    /* =====================================================================
       10. 按钮：普通按钮为玻璃，主按钮为深色渐变（白字对比度 ≥ 7:1）
       ===================================================================== */
    .stButton > button,
    .stDownloadButton > button,
    .stLinkButton > a,
    [data-testid="stFormSubmitButton"] > button {
        position: relative;
        isolation: isolate;
        overflow: hidden;
        border-radius: var(--radius-sm) !important;
        border: 1px solid rgba(255, 255, 255, 0.82) !important;
        background: linear-gradient(155deg, rgba(255, 255, 255, 0.9), rgba(255, 255, 255, 0.56)) !important;
        color: #1c2a4a !important;
        font-weight: 600 !important;
        letter-spacing: 0.01em;
        box-shadow: 0 8px 22px -14px rgba(23, 37, 84, 0.45),
            inset 0 1px 0 rgba(255, 255, 255, 0.92) !important;
        transition: transform 0.18s ease, box-shadow 0.18s ease,
            background 0.18s ease, border-color 0.18s ease;
    }
    .stButton > button:hover,
    .stDownloadButton > button:hover,
    .stLinkButton > a:hover,
    [data-testid="stFormSubmitButton"] > button:hover {
        transform: translateY(-1px);
        border-color: rgba(255, 255, 255, 0.98) !important;
        box-shadow: 0 14px 30px -16px rgba(23, 37, 84, 0.5),
            inset 0 1px 0 rgba(255, 255, 255, 1) !important;
    }
    .stButton > button:active,
    .stDownloadButton > button:active,
    [data-testid="stFormSubmitButton"] > button:active {
        transform: translateY(0);
    }
    /* 按钮悬停扫光（普通按钮与深色主按钮都适用） */
    .stButton > button::before,
    .stDownloadButton > button::before,
    [data-testid="stFormSubmitButton"] > button::before {
        content: "";
        position: absolute;
        top: -50%;
        left: 0;
        width: 45%;
        height: 200%;
        z-index: 0;
        opacity: 0;
        transform: translate3d(-160%, 0, 0) rotate(12deg);
        background: linear-gradient(100deg, transparent, rgba(255, 255, 255, 0.55), transparent);
        pointer-events: none;
    }
    .stButton > button:hover::before,
    .stDownloadButton > button:hover::before,
    [data-testid="stFormSubmitButton"] > button:hover::before {
        animation: buttonSheen 0.8s ease;
    }
    .stButton > button > *,
    .stDownloadButton > button > *,
    [data-testid="stFormSubmitButton"] > button > * {
        position: relative;
        z-index: 1;
    }
    @keyframes buttonSheen {
        0% { transform: translate3d(-160%, 0, 0) rotate(12deg); opacity: 0; }
        20% { opacity: 0.55; }
        100% { transform: translate3d(260%, 0, 0) rotate(12deg); opacity: 0; }
    }
    /* 主按钮 / 表单提交：深靛蓝 → 深紫 → 深青，白字清晰 */
    [data-testid="stBaseButton-primary"],
    [data-testid="stBaseButton-primaryFormSubmit"],
    [data-testid="stFormSubmitButton"] > button[kind="primary"],
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #33489f 0%, #4b3a9e 55%, #2c6b86 100%) !important;
        border-color: rgba(255, 255, 255, 0.34) !important;
        color: #ffffff !important;
        text-shadow: 0 1px 1px rgba(0, 0, 0, 0.18);
        box-shadow: 0 14px 34px -18px rgba(43, 52, 140, 0.75),
            inset 0 1px 0 rgba(255, 255, 255, 0.32),
            inset 0 -10px 18px -16px rgba(0, 0, 0, 0.5) !important;
        background-size: 200% 100% !important;
        animation: primaryFlow 11s ease-in-out infinite;
    }
    @keyframes primaryFlow {
        0%, 100% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
    }
    [data-testid="stBaseButton-primary"]:hover,
    [data-testid="stBaseButton-primaryFormSubmit"]:hover,
    [data-testid="stFormSubmitButton"] > button[kind="primary"]:hover,
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #3b51b4 0%, #5644b2 55%, #33809f 100%) !important;
        box-shadow: 0 18px 40px -18px rgba(43, 52, 140, 0.8),
            inset 0 1px 0 rgba(255, 255, 255, 0.4) !important;
    }
    .stButton > button:focus-visible,
    .stDownloadButton > button:focus-visible,
    [data-baseweb="input"]:focus-within,
    [data-testid="stExpander"] summary:focus-visible {
        outline: 2px solid rgba(79, 110, 247, 0.5);
        outline-offset: 2px;
    }

    /* =====================================================================
       11. 标签页：玻璃胶囊 + 白色选中态
       ===================================================================== */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        gap: 0.35rem;
        padding: 0.35rem;
        border-radius: var(--radius-md);
        border: 1px solid rgba(255, 255, 255, 0.72);
        background: rgba(255, 255, 255, 0.52);
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9),
            0 10px 28px -22px rgba(20, 35, 80, 0.5);
        backdrop-filter: blur(14px) saturate(150%);
    }
    [data-baseweb="tab"] {
        border-radius: 11px !important;
        padding: 0.45rem 0.95rem !important;
        color: #33415f !important;
        font-weight: 600 !important;
        transition: background 0.18s ease, color 0.18s ease,
            box-shadow 0.18s ease, transform 0.18s ease;
    }
    [data-baseweb="tab"]:hover {
        background: rgba(255, 255, 255, 0.45);
        transform: translateY(-1px);
    }
    [aria-selected="true"][data-baseweb="tab"] {
        background-color: rgba(255, 255, 255, 0.92) !important;
        background-image: linear-gradient(120deg, rgba(255, 255, 255, 0.98), rgba(238, 243, 255, 0.9) 55%, rgba(248, 240, 255, 0.95)) !important;
        background-size: 200% 100% !important;
        background-position: 0% 50%;
        color: #1b2a56 !important;
        box-shadow: 0 6px 16px -10px rgba(28, 48, 110, 0.5),
            inset 0 1px 0 #ffffff;
        animation: tabFlow 10s ease-in-out infinite, tabPop 0.42s var(--ease-glide);
    }
    @keyframes tabFlow {
        0%, 100% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
    }
    @keyframes tabPop {
        from { scale: 0.965; }
        to { scale: 1; }
    }
    [data-baseweb="tab-highlight"],
    [data-baseweb="tab-border"] { display: none !important; }

    /* =====================================================================
       12. 内容容器：折叠面板 / 表单 / 表格
       ===================================================================== */
    [data-testid="stExpander"] {
        position: relative;
        border-radius: var(--radius-md) !important;
        border: 1px solid rgba(255, 255, 255, 0.68) !important;
        background:
            radial-gradient(220px 160px at var(--glass-x, 50%) var(--glass-y, -10%), rgba(255, 255, 255, 0.36), rgba(255, 255, 255, 0) 72%),
            radial-gradient(120% 160% at 0% 0%, rgba(110, 152, 255, 0.12), transparent 58%),
            linear-gradient(155deg, rgba(255, 255, 255, 0.68), rgba(255, 255, 255, 0.42));
        box-shadow: 0 20px 48px -36px rgba(20, 32, 80, 0.45),
            inset 0 1px 0 rgba(255, 255, 255, 0.92),
            inset 0 18px 32px -30px rgba(255, 255, 255, 1);
        overflow: hidden;
        transition: border-color 0.3s var(--ease-soft), box-shadow 0.3s var(--ease-soft);
    }
    [data-testid="stExpander"]:hover {
        border-color: rgba(255, 255, 255, 0.95) !important;
        box-shadow: 0 26px 56px -38px rgba(20, 32, 80, 0.5),
            inset 0 1px 0 rgba(255, 255, 255, 1),
            inset 0 18px 32px -30px rgba(255, 255, 255, 1);
    }
    [data-testid="stExpander"]::before {
        content: "";
        position: absolute;
        left: 8%;
        right: 8%;
        top: 0;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.95), transparent);
        opacity: 0.7;
        pointer-events: none;
        animation: hairlineBreathe 8s ease-in-out infinite;
    }
    [data-testid="stExpander"] summary {
        padding: 0.85rem 1.05rem;
        color: #1e2c4c;
        font-weight: 600;
        border-radius: var(--radius-md);
    }
    [data-testid="stExpander"] summary:hover { background: rgba(255, 255, 255, 0.4); }
    [data-testid="stExpanderDetails"] {
        border-top: 1px solid rgba(120, 140, 185, 0.16);
        padding-top: 0.6rem;
    }
    [data-testid="stExpander"] [data-testid="stMarkdownContainer"] p { color: #24314e; }

    [data-testid="stForm"] {
        padding: 1.2rem 1.2rem 0.9rem;
        border-radius: var(--radius-lg) !important;
        border: 1px solid rgba(255, 255, 255, 0.72) !important;
        background:
            radial-gradient(120% 130% at 0% 0%, rgba(110, 152, 255, 0.14), transparent 58%),
            radial-gradient(120% 130% at 100% 100%, rgba(167, 139, 250, 0.12), transparent 60%),
            linear-gradient(155deg, rgba(255, 255, 255, 0.74), rgba(255, 255, 255, 0.46));
        box-shadow: 0 24px 60px -40px rgba(20, 32, 80, 0.45),
            inset 0 1px 0 rgba(255, 255, 255, 0.92),
            inset 0 20px 38px -34px rgba(255, 255, 255, 1);
        backdrop-filter: blur(18px) saturate(160%);
    }

    /* 表格：外框玻璃，内部保持高对比白底（可读性优先） */
    [data-testid="stDataFrame"] {
        border-radius: var(--radius-md);
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.72);
        background: rgba(255, 255, 255, 0.66);
        box-shadow: 0 18px 44px -30px rgba(20, 35, 80, 0.45),
            inset 0 1px 0 rgba(255, 255, 255, 0.9);
        transition: box-shadow 0.3s ease, border-color 0.3s ease;
    }
    [data-testid="stDataFrame"] > div { border-radius: inherit; }
    [data-testid="stTable"] {
        border-radius: var(--radius-md);
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.72);
        box-shadow: 0 18px 44px -30px rgba(20, 35, 80, 0.45);
        background: rgba(255, 255, 255, 0.8);
    }

    /* =====================================================================
       13. 图表 / 地图 / 原生指标 / 提示
       ===================================================================== */
    /* matplotlib 图表：画布已透明，这里给它一层"玻璃衬板"（不叠加模糊，
       避免几十张图同时模糊造成 GPU 压力） */
    [data-testid="stImageContainer"],
    [data-testid="stImages"] {
        position: relative;
        padding: 0.8rem 0.9rem 0.55rem;
        border-radius: var(--radius-lg);
        border: 1px solid rgba(255, 255, 255, 0.7);
        background:
            radial-gradient(280px 200px at var(--glass-x, 50%) var(--glass-y, -10%), rgba(255, 255, 255, 0.34), rgba(255, 255, 255, 0) 72%),
            radial-gradient(120% 110% at 0% 0%, rgba(120, 160, 255, 0.13), transparent 58%),
            radial-gradient(120% 110% at 100% 100%, rgba(167, 139, 250, 0.09), transparent 60%),
            linear-gradient(150deg, rgba(255, 255, 255, 0.80), rgba(255, 255, 255, 0.56));
        box-shadow: 0 22px 50px -34px rgba(20, 35, 80, 0.45),
            inset 0 1px 0 rgba(255, 255, 255, 0.95),
            inset 0 24px 44px -40px rgba(255, 255, 255, 1);
        overflow: hidden;
        transition: transform 0.32s var(--ease-glide), box-shadow 0.32s var(--ease-soft),
            border-color 0.32s var(--ease-soft);
    }
    [data-testid="stImageContainer"]::before,
    [data-testid="stImages"]::before {
        content: "";
        position: absolute;
        left: 10%;
        right: 10%;
        top: 0;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.95), transparent);
        opacity: 0.75;
        pointer-events: none;
        animation: edgeBreathe 8s ease-in-out infinite;
    }
    @keyframes edgeBreathe {
        0%, 100% { opacity: 0.45; }
        50% { opacity: 0.9; }
    }
    /* 图表卡片悬停扫光：鼠标掠过时一道柔光扫过画布衬板 */
    [data-testid="stImageContainer"]::after,
    [data-testid="stImages"]::after {
        content: "";
        position: absolute;
        top: -70%;
        bottom: -70%;
        left: -35%;
        width: 26%;
        background: linear-gradient(100deg, transparent, rgba(255, 255, 255, 0.34), transparent);
        opacity: 0;
        transform: translate3d(-160%, 0, 0) rotate(10deg);
        pointer-events: none;
    }
    [data-testid="stImageContainer"]:hover::after,
    [data-testid="stImages"]:hover::after {
        animation: panelSheen 1.3s var(--ease-soft);
    }
    [data-testid="stImageContainer"] img,
    [data-testid="stImages"] img { border-radius: var(--radius-sm); }
    [data-testid="stImageCaption"] { color: #3d4b68 !important; }

    /* HTML 地图（pyecharts iframe） */
    [data-testid="stIFrame"] {
        border-radius: var(--radius-lg);
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.72);
        background: rgba(255, 255, 255, 0.74);
        box-shadow: 0 24px 60px -40px rgba(20, 32, 80, 0.5),
            inset 0 1px 0 rgba(255, 255, 255, 0.95);
        transition: transform 0.32s var(--ease-glide), box-shadow 0.32s var(--ease-soft),
            border-color 0.32s var(--ease-soft);
    }
    [data-testid="stIFrame"] iframe {
        border-radius: calc(var(--radius-lg) - 1px);
        background: #ffffff;
    }
    [data-testid="stImageContainer"]:hover,
    [data-testid="stImages"]:hover,
    [data-testid="stIFrame"]:hover {
        transform: translateY(-3px);
        border-color: rgba(255, 255, 255, 0.95);
        box-shadow: 0 30px 66px -38px rgba(20, 35, 80, 0.5),
            inset 0 1px 0 rgba(255, 255, 255, 1),
            inset 0 24px 44px -40px rgba(255, 255, 255, 1);
    }
    [data-testid="stDataFrame"]:hover {
        border-color: rgba(255, 255, 255, 0.95);
        box-shadow: 0 24px 56px -34px rgba(20, 35, 80, 0.5),
            inset 0 1px 0 rgba(255, 255, 255, 1);
    }

    /* 原生 st.metric：小号玻璃卡 */
    [data-testid="stMetric"] {
        padding: 0.85rem 1rem;
        border-radius: var(--radius-md);
        border: 1px solid rgba(255, 255, 255, 0.72);
        background: linear-gradient(150deg, rgba(255, 255, 255, 0.8), rgba(255, 255, 255, 0.52));
        box-shadow: 0 14px 32px -26px rgba(20, 35, 80, 0.45),
            inset 0 1px 0 rgba(255, 255, 255, 0.92);
    }
    [data-testid="stMetricLabel"] p { color: #3c4a68 !important; font-weight: 600; }
    [data-testid="stMetricValue"] { color: #0f1a33 !important; }

    /* 提示框：保留语义色，仅加玻璃描边与阴影 */
    [data-testid="stAlert"] {
        border-radius: var(--radius-md) !important;
        border: 1px solid rgba(255, 255, 255, 0.72) !important;
        box-shadow: 0 14px 34px -26px rgba(20, 35, 80, 0.42),
            inset 0 1px 0 rgba(255, 255, 255, 0.85);
        backdrop-filter: blur(14px);
    }
    [data-testid="stAlert"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stAlert"] [data-testid="stMarkdownContainer"] li {
        color: #1f2b47 !important;
    }

    [data-testid="stCaptionContainer"] p,
    [data-testid="stCaptionContainer"] {
        color: #3d4b68 !important;
    }
    [data-testid="stMarkdownContainer"] code {
        padding: 0.1rem 0.36rem;
        border-radius: 6px;
        border: 1px solid rgba(255, 255, 255, 0.68);
        background: rgba(255, 255, 255, 0.66);
        color: #1c2b52;
        font-size: 0.86em;
    }
    [data-testid="stMarkdownContainer"] pre {
        padding: 0.9rem 1rem;
        border-radius: var(--radius-sm);
        border: 1px solid rgba(255, 255, 255, 0.7);
        background: rgba(255, 255, 255, 0.64) !important;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
        overflow: auto;
    }
    [data-testid="stMarkdownContainer"] table {
        border-collapse: separate;
        border-spacing: 0;
        border: 1px solid rgba(255, 255, 255, 0.72);
        border-radius: var(--radius-sm);
        overflow: hidden;
        background: rgba(255, 255, 255, 0.62);
    }
    [data-testid="stMarkdownContainer"] th {
        background: rgba(238, 243, 255, 0.85);
        color: #1b2a4c;
        font-weight: 600;
    }
    [data-testid="stMarkdownContainer"] th,
    [data-testid="stMarkdownContainer"] td {
        border-color: rgba(146, 164, 205, 0.28) !important;
        color: #24314e;
    }

    /* =====================================================================
       14. 页脚
       ===================================================================== */
    .footer {
        position: relative;
        overflow: hidden;
        margin-top: 2.6rem;
        padding: 1.9rem 1.6rem;
        border-radius: var(--radius-xl);
        border: 1px solid rgba(255, 255, 255, 0.7);
        background:
            radial-gradient(320px 220px at var(--glass-x, 50%) var(--glass-y, -10%), rgba(255, 255, 255, 0.32), rgba(255, 255, 255, 0) 72%),
            radial-gradient(120% 150% at 0% 0%, rgba(110, 152, 255, 0.14), transparent 58%),
            radial-gradient(120% 150% at 100% 100%, rgba(167, 139, 250, 0.12), transparent 60%),
            linear-gradient(155deg, rgba(255, 255, 255, 0.74), rgba(255, 255, 255, 0.48));
        box-shadow: 0 22px 54px -38px rgba(20, 32, 80, 0.5),
            inset 0 1px 0 rgba(255, 255, 255, 0.92),
            inset 0 20px 38px -34px rgba(255, 255, 255, 1);
        text-align: center;
        color: #3f4c6b;
        font-size: 0.86rem;
        backdrop-filter: blur(18px) saturate(160%);
    }
    .footer::before {
        content: "";
        position: absolute;
        left: 10%;
        right: 10%;
        top: 0;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.95), transparent);
        opacity: 0.8;
        pointer-events: none;
        animation: hairlineBreathe 8.5s ease-in-out infinite;
    }
    .footer p { margin: 0.28rem 0; color: #3f4c6b; line-height: 1.65; }
    [data-testid="stSidebar"] .sidebar-version {
        padding-top: 1rem;
        font-size: 0.75rem;
        color: #5b6885;
        text-align: center;
    }

    /* =====================================================================
       15. 滚动条 / 选中 / 焦点 / 响应式
       ===================================================================== */
    ::selection { background: rgba(120, 150, 255, 0.28); color: #111c33; }
    ::-webkit-scrollbar { width: 10px; height: 10px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb {
        background: rgba(110, 130, 175, 0.34);
        border: 2px solid transparent;
        border-radius: 99px;
        background-clip: content-box;
    }
    ::-webkit-scrollbar-thumb:hover { background: rgba(90, 112, 165, 0.48); background-clip: content-box; }
    :focus-visible { outline: 2px solid rgba(79, 110, 247, 0.5); outline-offset: 2px; }

    /* Safari 旧版本：仅在浏览器不支持无前缀 backdrop-filter 时补 -webkit- 前缀，
       避免覆盖各玻璃面在 Chrome / Edge 中的差异化模糊值 */
    @supports not (backdrop-filter: blur(1px)) {
        .hero-glass, .metric-card, .insight-box, .footer,
        [data-testid="stSidebar"], [data-testid="stForm"] {
            -webkit-backdrop-filter: blur(18px) saturate(170%);
        }
    }

    @media (max-width: 1400px) {
        .metric-card {
            min-height: 110px;
            padding: 0.88rem 0.82rem 0.82rem;
        }
        .metric-card h3 {
            font-size: 0.76rem;
            letter-spacing: 0;
        }
        .metric-card h1 { font-size: 1.62rem; }
        .metric-card .sub { font-size: 0.72rem; }
    }

    @media (max-width: 900px) {
        .hero-glass { padding: 1.7rem 1.1rem 1.5rem; border-radius: 24px; }
        .hero-sub { font-size: 0.95rem; }
        .hero-eyebrow { letter-spacing: 0.24em; text-indent: 0.24em; }
        .hero-orb-teal, .hero-sheen { display: none; }
        .stApp::before { animation-duration: 60s; }
        .module-header {
            margin-top: 1.6rem;
            padding: 0.9rem 1rem;
            gap: 0.75rem;
        }
        .module-step { width: 2.15rem; height: 2.15rem; font-size: 0.72rem; }
        .module-header .module-title { font-size: 1.2rem; }
        .module-header .module-desc { font-size: 0.76rem; }
        .section-title {
            font-size: 1.16rem;
            padding: 0.7rem 0.9rem 0.7rem 1.05rem;
            margin-top: 1.3rem;
        }
        .metric-card {
            min-height: 104px;
            padding: 0.95rem 1rem;
            backdrop-filter: blur(14px) saturate(160%);
        }
        .metric-card h1 { font-size: 1.65rem; }
        [data-testid="stMainBlockContainer"] { padding-top: 1.2rem; }
    }

    @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after {
            transition: none !important;
            animation: none !important;
        }
        .metric-card:hover,
        .insight-box:hover,
        [data-testid="stImageContainer"]:hover,
        [data-testid="stImages"]:hover,
        [data-testid="stIFrame"]:hover { transform: none; }
    }

    /* =====================================================================
       16. 排版对齐 / 防重叠（列宽、卡片、图表、标签页、锚点）
       ===================================================================== */
    /* 列内元素不得撑破列宽：否则窄列里的图片 / 表格会溢出到相邻列，造成重叠 */
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { min-width: 0; }
    [data-testid="stImageContainer"],
    [data-testid="stImageContainer"] img,
    [data-testid="stIFrame"] { max-width: 100%; }
    [data-testid="stImageContainer"] img { display: block; height: auto; }

    /* 同一行指标卡等高：副标题换行时卡片底缘仍然对齐（不支持 :has 时退回 min-height） */
    [data-testid="stColumn"]:has(.metric-card) > [data-testid="stVerticalBlock"],
    [data-testid="stColumn"]:has(.metric-card) [data-testid="stMarkdown"],
    [data-testid="stColumn"]:has(.metric-card) [data-testid="stMarkdownContainer"] {
        height: 100%;
    }
    .metric-card { min-width: 0; }

    /* 标签页较多时横向滚动，避免标签互相挤压或被裁切 */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        overflow-x: auto;
        flex-wrap: nowrap;
        scrollbar-width: thin;
    }
    [data-baseweb="tab"] { white-space: nowrap; }

    /* 锚点跳转的顶部留白：章节标题不会被顶部工具栏遮住。
       锚点是标题前一个零高度 div（见 widgets.section_title / module_header），
       标题自身的 margin-top 会与它一起计入滚动位置，因此留白取一个适中的值。 */
    .section-anchor,
    .module-anchor {
        height: 0;
        overflow: hidden;
        scroll-margin-top: 5rem;
    }
    .hero-glass[id] { scroll-margin-top: 2.2rem; }
    .stApp,
    [data-testid="stMain"] { scroll-behavior: smooth; }
    @media (prefers-reduced-motion: reduce) {
        .stApp,
        [data-testid="stMain"] { scroll-behavior: auto; }
    }

    /* =====================================================================
       17. 动效编排：入场节奏 / 滚动显现 / 移动端降级
       ===================================================================== */
    /* 指标卡按列错峰入场：同一行从左到右依次浮现，避免整屏同时动画 */
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(1) .metric-card { animation-delay: 0.02s; }
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2) .metric-card { animation-delay: 0.07s; }
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(3) .metric-card { animation-delay: 0.12s; }
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(4) .metric-card { animation-delay: 0.17s; }
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(5) .metric-card { animation-delay: 0.22s; }
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(6) .metric-card { animation-delay: 0.27s; }

    /* 滚动驱动显现：章节标题进入视口时轻轻上浮。
       仅 Chrome / Edge 等支持 animation-timeline: view() 的浏览器生效；
       其余浏览器退化为一次性的时间动画（同样是 translate + opacity）。 */
    @media (prefers-reduced-motion: no-preference) {
        @supports (animation-timeline: view()) {
            .section-title {
                animation: sectionReveal linear both;
                animation-timeline: view();
                animation-range: entry 2% entry 55%;
            }
        }
        @supports not (animation-timeline: view()) {
            .section-title { animation: glassRise 0.55s var(--ease-glide) both; }
        }
    }
    @keyframes sectionReveal {
        from { opacity: 0.4; translate: 0 18px; }
        to { opacity: 1; translate: 0 0; }
    }

    /* 移动端：关闭最耗 GPU 的装饰层，只保留柔光与玻璃质感 */
    @media (max-width: 900px) {
        .hero-aurora::before,
        .hero-aurora::after,
        .hero-orb-violet { display: none; }
        [data-testid="stSidebar"]::after { display: none; }
    }

    /* 降低动效偏好：显式关闭本页新增的装饰性动画（内容与布局不受影响） */
    @media (prefers-reduced-motion: reduce) {
        .metric-card,
        .insight-box,
        .section-title,
        .module-header,
        .hero-glass,
        .hero-chip { animation: none !important; }
        .metric-card::after,
        .hero-glass::after,
        [data-testid="stExpander"]::before,
        .footer::before,
        .hero-aurora::before,
        .hero-aurora::after { animation: none !important; }
    }

    /* ===================================================================== */
</style>
"""

# 在 </style> 前注入由 scenes.SCENE_PALETTES 生成的首屏 `--scene-*` 变量：
# CSS 静态兜底与滚动脚本共用同一份配色数据源，避免两处手写颜色漂移。
CUSTOM_CSS = CUSTOM_CSS.replace("</style>", scene_root_css() + "</style>")
