"""图表光栅化：把 matplotlib Figure 转成 PNG 字节（UI 无关，便于单测）。

为什么不让 Streamlit 直接下发 Figure（``st.pyplot``）：

1. 先自行 ``savefig`` 可以显式控制 dpi / 背景色 / 边距，并在同一处捕获
   ``Glyph ... missing from font`` 等字体告警——云端日志能直接看出是不是缺字；
2. ``st.image`` 接收 PNG 字节的链路更短，不依赖 Streamlit 内部对 Figure 的
   二次 ``savefig`` 与图片缩放，避免不同版本 / 不同部署环境下的差异；
3. 保存失败能拿到明确异常，页面可以据此降级提示，而不是整块图表空白。

本模块只做光栅化，不调用任何 ``st.*`` 接口。
"""

from __future__ import annotations

import logging
import math
import warnings
from io import BytesIO
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - 仅类型检查
    from matplotlib.figure import Figure

logger = logging.getLogger(__name__)

# st.pyplot 内部重绘使用的 dpi（streamlit/elements/pyplot.py），作为上限
DEFAULT_SAVE_DPI = 200

# Streamlit 下发图片时允许的最大宽度（streamlit.elements.lib.image_utils
# .MAXIMUM_CONTENT_WIDTH，1.58 版为 2 × 730 = 1460 px）；取不到时用同一数值兜底。
try:  # pragma: no cover - 仅随 Streamlit 版本变化
    from streamlit.elements.lib.image_utils import (
        MAXIMUM_CONTENT_WIDTH as _MAX_CONTENT_WIDTH,
    )

    MAX_CONTENT_WIDTH = int(_MAX_CONTENT_WIDTH)
except Exception:  # noqa: BLE001 - 取不到时退化为固定值，渲染逻辑不受影响
    MAX_CONTENT_WIDTH = 1460

# 已经写进日志的缺字告警（避免每张图重复刷屏）
_LOGGED_GLYPHS: set[str] = set()


def display_dpi(
    fig: "Figure",
    *,
    width_limit: int = MAX_CONTENT_WIDTH,
    save_dpi: int = DEFAULT_SAVE_DPI,
) -> int:
    """按 Streamlit 实际下发的宽度反推渲染 dpi，避免「高 dpi 渲染后再缩放」。

    窄图在 200 dpi 下本就不超限，返回 200 保持原状；tight bbox 可能略宽于
    画布，因此留 2% 余量，宁可少一点像素也不要触发缩放。
    """
    try:
        width_in = float(fig.get_figwidth())
    except Exception:  # noqa: BLE001 - 取不到画布尺寸时退回默认 dpi
        return save_dpi
    if not math.isfinite(width_in) or width_in <= 0:
        return save_dpi
    dpi = int(width_limit * 0.98 / width_in)
    return max(72, min(save_dpi, dpi))


def figure_png_bytes(
    fig: "Figure",
    *,
    dpi: int | None = None,
    facecolor: str = "white",
) -> bytes:
    """把 Figure 渲染为 PNG 字节；同时把缺字告警写入日志。

    Args:
        fig: 已布局完成的 matplotlib Figure。
        dpi: 渲染 dpi；None 表示按 ``display_dpi`` 自动推算。
        facecolor: 画布背景色，显式给白色避免深色模式下出现透明底。
    """
    target_dpi = display_dpi(fig) if dpi is None else max(72, int(dpi))
    buffer = BytesIO()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fig.savefig(
            buffer,
            format="png",
            dpi=target_dpi,
            bbox_inches="tight",
            facecolor=facecolor,
        )
    _log_missing_glyphs(caught)
    return buffer.getvalue()


def _log_missing_glyphs(caught: list[warnings.WarningMessage]) -> None:
    """记录 matplotlib 的缺字告警（同一类告警只写一次）。"""
    messages = [
        str(item.message) for item in caught if "missing from font" in str(item.message)
    ]
    fresh = [message for message in dict.fromkeys(messages) if message not in _LOGGED_GLYPHS]
    if not fresh:
        return
    _LOGGED_GLYPHS.update(fresh)
    logger.warning(
        "图表文字缺字（中文会显示为方框），共 %d 类，例如：%s；"
        "请检查 assets/fonts 是否随代码部署，或运行 python scripts/fetch_fonts.py --check。",
        len(messages),
        fresh[:3],
    )
