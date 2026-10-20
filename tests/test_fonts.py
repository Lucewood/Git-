"""中文字体注册与解析测试：确保「图表中文显示为方框」的问题不会回归。

回归场景：应用部署到未安装中文字体的 Linux 服务器（如 Streamlit Community
Cloud）后，matplotlib 回退到不含 CJK 字形的 DejaVu Sans，图表标题 / 坐标轴 /
刻度 / 图例里的中文被渲染成「方框 + 字」的缺字占位（tofu）。
"""

from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest
from matplotlib import font_manager
from matplotlib.ft2font import FT2Font

from city_insight import charts, fonts

# 覆盖图表中实际出现的文本类型：标题、轴标签、图例、刻度（城市 / 省份名）
CJK_SAMPLE = (
    "中国城市生活成本与幸福感分析可视化 · 房价（元/㎡）÷ 年收入 "
    "北京市 上海市 广州市 深圳市 成都市 杭州市 「匹配度」— 幸福度指数"
)


@pytest.fixture(autouse=True)
def _fresh_font_cache():
    """每个用例前后清空解析缓存：monkeypatch 场景下避免缓存互相污染。"""
    fonts.resolve_cjk_font.cache_clear()
    fonts.bundled_families.cache_clear()
    yield
    fonts.resolve_cjk_font.cache_clear()
    fonts.bundled_families.cache_clear()


def test_bundled_font_is_shipped():
    """仓库应内置中文字体文件（随代码部署，离线可用）。"""
    files = fonts.bundled_font_files()
    assert files, f"未在 {fonts.FONT_DIR} 找到内置字体文件"
    assert all(f.suffix.lower() in fonts.FONT_SUFFIXES for f in files)
    assert all(f.stat().st_size > 100_000 for f in files), "内置字体文件疑似损坏 / 被截断"


def test_register_bundled_font_family():
    """内置字体注册后应出现在 matplotlib 的字体列表中。"""
    families = fonts.bundled_families()
    assert families, "内置字体注册失败"
    assert set(families) <= fonts.available_families()


def test_resolve_prefers_bundled_font():
    """内置字体可用时应优先选中它（= config.FONT_SANS 首位）。"""
    bundled = fonts.bundled_families()
    family = fonts.resolve_cjk_font()
    assert family is not None, "应能解析出可用的中文字体"
    assert family in bundled
    assert fonts.cjk_font_stack(family)[0] == family


def test_cjk_font_stack_is_deduplicated():
    """候选字体栈去重且保持优先级顺序（首位 = 解析结果）。"""
    family = fonts.resolve_cjk_font()
    stack = fonts.cjk_font_stack(family)
    assert stack[0] == family
    assert len(stack) == len(set(stack))


def test_resolved_font_file_contains_cjk_glyphs():
    """matplotlib 按族名找到的字体文件必须真的包含中文字形。"""
    family = fonts.resolve_cjk_font()
    assert family is not None
    path = Path(font_manager.findfont(font_manager.FontProperties(family=family)))
    assert "DejaVu" not in path.name, f"解析结果回退到了无中文字形的 {path.name}"
    charmap = set(FT2Font(str(path)).get_charmap())
    assert all(ord(ch) in charmap for ch in "中国城市幸福度")


def test_resolve_falls_back_to_system_font(monkeypatch, tmp_path):
    """内置字体缺失（如只部署了 src/）时应回退到系统中文字体。"""
    monkeypatch.setattr(fonts, "FONT_DIR", tmp_path)
    monkeypatch.setattr(fonts, "FONT_SANS", ["DejaVu Sans"])
    fonts.resolve_cjk_font.cache_clear()
    fonts.bundled_families.cache_clear()
    assert fonts.bundled_families() == ()
    assert fonts.resolve_cjk_font() == "DejaVu Sans"


def test_resolve_returns_none_when_no_font_available(monkeypatch, tmp_path):
    """完全无可用字体时返回 None（由调用方降级），不得抛异常。"""
    monkeypatch.setattr(fonts, "FONT_DIR", tmp_path)
    monkeypatch.setattr(fonts, "FONT_SANS", ["No Such CJK Font XYZ"])
    fonts.resolve_cjk_font.cache_clear()
    fonts.bundled_families.cache_clear()
    assert fonts.resolve_cjk_font() is None
    assert fonts.cjk_font_stack(None) == ["No Such CJK Font XYZ"]


def test_apply_cjk_font_sets_rcparams():
    """setup_plot_style() 之后 rcParams 应以解析到的中文字体为首选。"""
    charts.setup_plot_style()
    # matplotlib 会把 font.family 规范化成列表
    assert list(matplotlib.rcParams["font.family"]) == ["sans-serif"]
    assert matplotlib.rcParams["font.sans-serif"][0] == fonts.resolve_cjk_font()
    assert matplotlib.rcParams["axes.unicode_minus"] is False


def test_cjk_text_renders_without_missing_glyph_warning():
    """只允许使用内置中文字体时，标题 / 轴标签 / 图例 / 刻度都不应缺字。"""
    family = fonts.resolve_cjk_font()
    assert family is not None
    with matplotlib.rc_context(
        {"font.family": "sans-serif", "font.sans-serif": [family]}
    ), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.plot([0, 1], [0, 1], label=CJK_SAMPLE)
        ax.set_title(CJK_SAMPLE)
        ax.set_xlabel(CJK_SAMPLE)
        ax.set_ylabel(CJK_SAMPLE)
        ax.set_xticks([0, 1], [CJK_SAMPLE, "上海市"])
        ax.legend()
        fig.canvas.draw()  # 缺字告警只在真实光栅化阶段出现
        plt.close(fig)

    missing = [str(w.message) for w in caught if "missing from font" in str(w.message)]
    assert missing == [], f"内置字体缺少字形（会显示为方框）：{missing}"


def test_font_report_shape():
    """字体解析摘要字段稳定（供日志 / 排查使用）。"""
    report = fonts.font_report()
    assert set(report) == {"family", "bundled", "stack"}
    assert report["bundled"], "摘要应列出内置字体文件"
