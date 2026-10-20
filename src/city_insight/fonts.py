"""中文字体注册与解析：确保 matplotlib 在任意部署环境都能正确渲染中文。

背景（本模块要解决的问题）：
matplotlib 默认字体（DejaVu Sans）不含 CJK 字形。在没有安装中文字体的 Linux
服务器（Streamlit Community Cloud、`python:*-slim` 等镜像）上，图表标题 / 坐标轴 /
刻度 / 图例里的中文会渲染成「方框 + 字」的缺字占位（tofu）。

解决思路（按优先级依次尝试）：
1. 注册随代码一起部署的内置字体（`assets/fonts/*.otf|ttf|ttc`）——
   不依赖系统字体、不依赖运行时网络，Windows / macOS / Linux 表现一致；
2. 内置字体缺失时，回退到系统已安装的中文字体（`config.FONT_SANS` 中命中的第一个）；
3. 两者都没有时记录告警并交给 matplotlib 自行回退（页面仍可运行，仅中文可能缺字）。

模块内函数均为纯逻辑 + 幂等缓存，可被 pytest 直接导入测试。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import matplotlib
from matplotlib import font_manager

from .config import FONT_DIR, FONT_SANS

logger = logging.getLogger(__name__)

# matplotlib 可直接加载的字体文件扩展名
FONT_SUFFIXES: frozenset[str] = frozenset({".otf", ".ttf", ".ttc"})


def bundled_font_files(font_dir: Path | None = None) -> list[Path]:
    """返回内置字体目录下的字体文件（按文件名排序，保证跨平台结果确定）。

    Args:
        font_dir: 字体目录，默认 config.FONT_DIR；目录不存在 / 不可读时返回空列表
            （例如只部署了 src/ 的场景），由调用方回退到系统字体。
    """
    directory = Path(font_dir) if font_dir is not None else FONT_DIR
    try:
        entries = sorted(directory.iterdir(), key=lambda p: p.name)
    except OSError as exc:  # 目录缺失不应中断应用
        logger.debug("内置字体目录不可用（%s）：%s", directory, exc)
        return []
    return [p for p in entries if p.is_file() and p.suffix.lower() in FONT_SUFFIXES]


@lru_cache(maxsize=8)
def register_font_file(path: str) -> str | None:
    """把单个字体文件注册进 matplotlib，返回其字体族名；注册失败返回 None。

    注册（而非依赖 matplotlib 的字体缓存）可避免新装字体 / 缓存过期导致找不到字形，
    且对同一文件重复注册被 lru_cache 去重。
    """
    file_path = Path(path)
    try:
        font_manager.fontManager.addfont(str(file_path))
        return font_manager.FontProperties(fname=str(file_path)).get_name()
    except Exception as exc:  # noqa: BLE001 - 字体损坏 / 格式不支持时降级到系统字体
        logger.warning("内置字体注册失败（%s）：%s", file_path, exc)
        return None


@lru_cache(maxsize=1)
def bundled_families() -> tuple[str, ...]:
    """注册全部内置字体并返回其字体族名（结果缓存，避免每次 rerun 重复注册）。"""
    families: list[str] = []
    for path in bundled_font_files():
        name = register_font_file(str(path))
        if name and name not in families:
            families.append(name)
    if families:
        logger.info("已注册内置中文字体：%s（目录 %s）", "、".join(families), FONT_DIR)
    else:
        logger.debug("未在 %s 找到内置字体文件。", FONT_DIR)
    return tuple(families)


def available_families() -> set[str]:
    """matplotlib 当前可见的字体族名集合（含刚注册的内置字体）。"""
    return {entry.name for entry in font_manager.fontManager.ttflist}


@lru_cache(maxsize=1)
def resolve_cjk_font() -> str | None:
    """按优先级解析用于渲染中文的字体族名；无可用中文字体时返回 None。

    判定依据是 `config.FONT_SANS` 的顺序（内置字体 "Noto Sans SC" 排在首位），
    因此内置字体可用时优先使用内置字体，否则使用命中的系统中文字体。
    """
    registered = bundled_families()
    families = available_families()
    for family in FONT_SANS:
        if family in families:
            if registered and family not in registered:
                logger.info("未注册内置字体，改用系统中文字体：%s", family)
            return family
    logger.warning(
        "未找到任何可用的中文字体（候选：%s），图表中文可能显示为方框；"
        "请确认内置字体目录存在：%s（可用 python scripts/fetch_fonts.py 重新下载，"
        "或在服务器上安装中文字体包）。",
        "、".join(FONT_SANS),
        FONT_DIR,
    )
    return None


def cjk_font_stack(family: str | None = None) -> list[str]:
    """返回 `rcParams["font.sans-serif"]` 使用的候选字体列表（去重且保序）。

    Args:
        family: 已解析的字体族名；传 None 表示按需重新解析（resolve_cjk_font）。
    """
    resolved = resolve_cjk_font() if family is None else family
    stack: list[str] = []
    for name in ([resolved] if resolved else []) + list(FONT_SANS):
        if name and name not in stack:
            stack.append(name)
    return stack


def apply_cjk_font() -> str | None:
    """把解析到的中文字体写入 matplotlib 全局 rcParams，返回选中的字体族名。

    必须在 seaborn 的 `set_style` / `set_theme` 之后调用：它们会重置字体相关
    rcParams，先设置会被覆盖。
    """
    family = resolve_cjk_font()
    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = cjk_font_stack(family)
    matplotlib.rcParams["axes.unicode_minus"] = False
    return family


def font_report() -> dict[str, object]:
    """字体解析摘要（供启动日志 / 测试断言使用）。"""
    family = resolve_cjk_font()
    return {
        "family": family,
        "bundled": [p.name for p in bundled_font_files()],
        "stack": cjk_font_stack(family),
    }
