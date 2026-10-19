"""图表光栅化测试：PNG 下发链路、dpi 控制与中文缺字告警。

回归场景：云端（Linux）图表区域空白或中文变方框时，需要能从日志 / 页面
自检直接定位问题；这里确保 PNG 渲染可用、宽度受控且中文字形完整。
"""

from __future__ import annotations

import logging
import struct
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import pytest
from matplotlib import font_manager
from PIL import Image

from city_insight import charts, fonts, rendering

CJK_TEXT = "中国城市生活成本与幸福感分析（房价元/㎡）"


def _ranking_figure(figsize: tuple[float, float] = (7, 4)):
    data = pd.DataFrame(
        {
            "city": ["北京", "上海", "广州", "深圳"],
            "happiness": [91.0, 88.0, 84.0, 82.0],
        }
    ).sort_values("happiness")
    return charts.barh_ranking(
        data,
        "happiness",
        color="#667eea",
        title=CJK_TEXT,
        xlabel="幸福度指数",
        fmt="{:.1f}",
        figsize=figsize,
    )


def test_display_dpi_is_bounded_and_scales_with_width():
    """宽图按目标宽度降低 dpi，窄图保持 200，且始终落在 [72, 200]。"""
    narrow = plt.figure(figsize=(6, 4))
    wide = plt.figure(figsize=(16, 4))
    try:
        narrow_dpi = rendering.display_dpi(narrow)
        wide_dpi = rendering.display_dpi(wide)
    finally:
        plt.close(narrow)
        plt.close(wide)

    assert narrow_dpi == rendering.DEFAULT_SAVE_DPI
    assert 72 <= wide_dpi < narrow_dpi
    # 目标像素宽度不超过 Streamlit 上限
    assert 16 * wide_dpi <= rendering.MAX_CONTENT_WIDTH


def test_figure_png_bytes_returns_valid_png():
    """Figure → PNG 字节应可被 Pillow 解码且有实际内容。"""
    charts.setup_plot_style()
    fig = _ranking_figure()
    try:
        png = rendering.figure_png_bytes(fig)
    finally:
        plt.close(fig)

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", png[16:24])
    assert 0 < width <= rendering.MAX_CONTENT_WIDTH + 80
    assert height > 0

    image = Image.open(BytesIO(png)).convert("RGB")
    assert image.size == (width, height)
    # 白底图上必须有非白像素（条形 / 文字 / 网格）
    assert image.convert("L").getextrema()[0] < 250


def test_cjk_labels_render_without_missing_glyph_warning(caplog):
    """中文字体就位时，渲染中文标题 / 刻度不应产生缺字告警。"""
    charts.setup_plot_style()
    assert fonts.resolve_cjk_font() is not None

    fig = _ranking_figure()
    try:
        with caplog.at_level(logging.WARNING, logger="city_insight.rendering"):
            rendering.figure_png_bytes(fig)
    finally:
        plt.close(fig)

    missing = [
        record.getMessage()
        for record in caplog.records
        if "缺字" in record.getMessage()
    ]
    assert missing == [], f"渲染出现缺字告警：{missing}"


def test_bundled_font_alone_covers_charts_without_system_fonts(monkeypatch, caplog):
    """模拟 Streamlit Cloud：只有内置字体（无系统中文字体）也能正常渲染中文。

    回归场景：Linux 容器没有微软雅黑 / 苹方 / Noto CJK 系统字体，只能依赖
    assets/fonts 里的内置字体。这里把 matplotlib 可见字体裁剪到「内置字体 +
    DejaVu Sans」，再渲染一张含中文的条形图并断言没有缺字告警。
    """
    bundled = {path.resolve() for path in fonts.bundled_font_files()}
    manager = font_manager.fontManager
    kept = [
        entry
        for entry in manager.ttflist
        if Path(entry.fname).resolve() in bundled or entry.name == "DejaVu Sans"
    ]
    monkeypatch.setattr(manager, "ttflist", kept)

    fonts.resolve_cjk_font.cache_clear()
    fonts.bundled_families.cache_clear()
    fonts.resolved_font_path.cache_clear()
    try:
        charts.setup_plot_style()
        assert fonts.resolve_cjk_font() == "Noto Sans SC"
        assert fonts.font_report()["ok"] is True

        fig = _ranking_figure()
        try:
            with caplog.at_level(logging.WARNING, logger="city_insight.rendering"):
                png = rendering.figure_png_bytes(fig)
        finally:
            plt.close(fig)
    finally:
        fonts.resolve_cjk_font.cache_clear()
        fonts.bundled_families.cache_clear()
        fonts.resolved_font_path.cache_clear()

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    missing = [
        record.getMessage()
        for record in caplog.records
        if "缺字" in record.getMessage()
    ]
    assert missing == [], f"只使用内置字体时出现缺字告警：{missing}"



def test_render_failure_is_not_swallowed_by_png_helper():
    """不是一个 Figure 时应抛出异常，供页面层显示真实原因。"""
    with pytest.raises(Exception):
        rendering.figure_png_bytes(object())  # type: ignore[arg-type]
