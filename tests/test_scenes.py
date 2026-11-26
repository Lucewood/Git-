"""滚动分幕背景：配色、对比度、CSS 变量与脚本拼装的回归测试。

这些测试不依赖浏览器：它们锁定「分幕顺序必须跟页面模块一致」「相邻幕的
背景基色必须有足够色差」「任意一幕上的深色正文都保持 AAA 对比度」以及
CSS / JS 两端确实消费同一份配色数据，避免后续改色时悄悄破坏可读性。
"""

from __future__ import annotations

import math
import re

import pytest

from city_insight import scenes


# 与页面模块顺序一一对应的分幕锚点（改动页面结构时需同步更新）。
EXPECTED_ANCHORS = (
    "sec-overview",
    "sec-insight",
    "sec-ranking",
    "sec-forecast",
    "sec-advice",
    "sec-geo",
    "sec-data",
)
# 正文主色（styles.CUSTOM_CSS 的 --ink-700），用于校验背景上的文字对比度。
TEXT_INK_700 = "#24314e"
# 说明文字颜色（stCaptionContainer / stImageCaption），需满足 WCAG AA。
CAPTION_INK = "#3d4b68"
# 相邻分幕基色的最小 CIE Lab 色差；低于该值人眼难以感知「换了一幕」。
MIN_ADJACENT_DELTA_E = 10.0
# WCAG AAA 正文对比度门槛 / AA 说明文字门槛。
MIN_TEXT_CONTRAST = 7.0
MIN_CAPTION_CONTRAST = 4.5


def _srgb_to_lab(hex_color: str) -> tuple[float, float, float]:
    """sRGB 十六进制颜色 → CIE Lab（D65）。"""
    value = hex_color.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]

    def linearize(channel: float) -> float:
        if channel <= 0.04045:
            return channel / 12.92
        return ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = (linearize(channel) for channel in channels)
    x = (red * 0.4124 + green * 0.3576 + blue * 0.1805) / 0.95047
    y = red * 0.2126 + green * 0.7152 + blue * 0.0722
    z = (red * 0.0193 + green * 0.1192 + blue * 0.9505) / 1.08883

    def pivot(t: float) -> float:
        if t > 0.008856:
            return t ** (1.0 / 3.0)
        return 7.787 * t + 16.0 / 116.0

    fx, fy, fz = pivot(x), pivot(y), pivot(z)
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def _delta_e(first: str, second: str) -> float:
    """两色的 CIE76 色差（近似人眼感知差异）。"""
    lab_a, lab_b = _srgb_to_lab(first), _srgb_to_lab(second)
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(lab_a, lab_b)))


def _relative_luminance(hex_color: str) -> float:
    """WCAG 相对亮度。"""
    value = hex_color.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]

    def linearize(channel: float) -> float:
        if channel <= 0.04045:
            return channel / 12.92
        return ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = (linearize(channel) for channel in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast_ratio(first: str, second: str) -> float:
    """WCAG 对比度（1–21）。"""
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def _parse_rgba(color: str) -> tuple[float, float, float, float]:
    """解析 ``rgba(r, g, b, a)`` 字符串。"""
    match = re.fullmatch(
        r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", color
    )
    assert match, f"无法解析光晕颜色：{color}"
    red, green, blue, alpha = match.groups()
    return float(red), float(green), float(blue), float(alpha)


def _composite(base: str, overlay: str, layer_opacity: float) -> str:
    """把半透明光晕按图层不透明度叠加到基色上，返回合成后的十六进制颜色。"""
    base_value = base.lstrip("#")
    base_rgb = [int(base_value[i : i + 2], 16) for i in (0, 2, 4)]
    red, green, blue, alpha = _parse_rgba(overlay)
    alpha *= layer_opacity
    mixed = [
        round(base_rgb[index] * (1 - alpha) + channel * alpha)
        for index, channel in enumerate((red, green, blue))
    ]
    return "#{:02x}{:02x}{:02x}".format(*mixed)


def test_scene_order_matches_page_modules() -> None:
    """分幕顺序与页面模块锚点一致，避免滚动时配色与内容错位。"""
    assert tuple(scene.anchor for scene in scenes.SCENE_PALETTES) == EXPECTED_ANCHORS
    assert len({scene.key for scene in scenes.SCENE_PALETTES}) == len(
        scenes.SCENE_PALETTES
    )


def test_adjacent_scenes_have_distinguishable_backgrounds() -> None:
    """相邻分幕的基色色差足够大，滚动到下一功能部分时能明显感知换色。"""
    pairs = zip(scenes.SCENE_PALETTES, scenes.SCENE_PALETTES[1:])
    for current, following in pairs:
        delta = _delta_e(current.base, following.base)
        assert delta >= MIN_ADJACENT_DELTA_E, (
            f"「{current.label}」→「{following.label}」基色过近：ΔE={delta:.1f}"
        )


@pytest.mark.parametrize("scene", scenes.SCENE_PALETTES, ids=lambda s: s.key)
def test_scene_background_keeps_text_readable(scene: scenes.ScenePalette) -> None:
    """每一幕的基色都保持深墨色正文 AAA 对比度（背景换色不牺牲可读性）。"""
    for background in (scene.base, scene.deep):
        ratio = _contrast_ratio(background, TEXT_INK_700)
        assert ratio >= MIN_TEXT_CONTRAST, (
            f"「{scene.label}」背景 {background} 与正文对比度仅 {ratio:.2f}:1"
        )


@pytest.mark.parametrize("scene", scenes.SCENE_PALETTES, ids=lambda s: s.key)
def test_glow_overlay_keeps_text_readable(scene: scenes.ScenePalette) -> None:
    """光晕中心（最坏情况）叠加后，正文与说明文字仍保持可读对比度。"""
    for glow in (scene.glow_a, scene.glow_b):
        surface = _composite(scene.base, glow, scenes.SCENE_GLOW_OPACITY)
        body_ratio = _contrast_ratio(surface, TEXT_INK_700)
        caption_ratio = _contrast_ratio(surface, CAPTION_INK)
        assert body_ratio >= MIN_TEXT_CONTRAST, (
            f"「{scene.label}」光晕 {glow} 上正文对比度仅 {body_ratio:.2f}:1"
        )
        assert caption_ratio >= MIN_CAPTION_CONTRAST, (
            f"「{scene.label}」光晕 {glow} 上说明文字对比度仅 {caption_ratio:.2f}:1"
        )


def test_scene_root_css_exposes_first_palette() -> None:
    """CSS 静态兜底与首个分幕共用同一份变量，避免首帧闪白 / 颜色漂移。"""
    css = scenes.scene_root_css()
    assert ":root" in css
    for name, value in scenes.SCENE_PALETTES[0].css_variables().items():
        assert f"{name}: {value};" in css
    assert f"--scene-glow-opacity: {scenes.SCENE_GLOW_OPACITY};" in css


def test_custom_css_consumes_scene_variables() -> None:
    """页面 CSS 必须真正使用分幕变量（背景、光晕、进度条）。"""
    from city_insight.styles import CUSTOM_CSS

    for token in (
        "var(--scene-base",
        "var(--scene-deep",
        "var(--scene-glow-a",
        "var(--scene-glow-b",
        "var(--scene-glow-opacity",
        "var(--scene-accent",
    ):
        assert token in CUSTOM_CSS
    assert CUSTOM_CSS.rstrip().endswith("</style>")


def test_scene_script_embeds_palettes_and_safeguards() -> None:
    """脚本内嵌全部锚点与配色，并保留幂等 / 减少动效等安全分支。"""
    script = scenes.scene_script()
    assert "__SCENE_PAYLOAD__" not in script
    for scene in scenes.SCENE_PALETTES:
        assert scene.anchor in script
        assert scene.base in script
    for token in (
        "prefers-reduced-motion",
        "__citySceneGradient",
        "__citySceneApply",
        '[data-testid="stMain"]',
        '[data-testid="stMainBlockContainer"]',
        "ResizeObserver",
        "--scene-base",
        "requestAnimationFrame",
    ):
        assert token in script
