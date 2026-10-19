"""在导入 matplotlib 之前准备可写的配置 / 字体缓存目录。

背景：Streamlit Community Cloud、只读根文件系统的 Docker 容器等环境中，
``HOME`` 可能不可写。matplotlib 首次导入时会在 ``MPLCONFIGDIR``（默认
``~/.config/matplotlib``）构建字体缓存；目录不可写时会反复打印
"Matplotlib is building the font cache" 甚至导致字体解析异常。

本模块只依赖标准库，必须在 ``import matplotlib`` 之前调用：

    from city_insight.mpl_bootstrap import ensure_mpl_config_dir
    ensure_mpl_config_dir()
    import matplotlib
    matplotlib.use("Agg")
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_PROBE_NAME = ".city_insight_write_probe"


def _usable(directory: Path) -> bool:
    """目录是否可创建且可写（用一个临时探针文件验证，而非只看权限位）。"""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / _PROBE_NAME
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def ensure_mpl_config_dir() -> Path | None:
    """确保 matplotlib 的配置目录可写，返回最终使用的目录（失败时返回 None）。

    优先级：
    1. 环境变量 ``MPLCONFIGDIR``（可写则沿用）；
    2. ``~/.config/matplotlib``（常规位置）；
    3. 系统临时目录下的 ``city_insight_matplotlib``（只读 HOME 的兜底）。

    该函数是幂等的，重复调用不会改变已经可写的目录。
    """
    configured = os.environ.get("MPLCONFIGDIR", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if _usable(path):
            return path
        logger.warning(
            "MPLCONFIGDIR=%s 不可写，改用临时目录存放 matplotlib 字体缓存。",
            configured,
        )

    candidates: list[Path] = []
    try:
        candidates.append(Path.home() / ".config" / "matplotlib")
    except (RuntimeError, OSError):  # 极端环境（无 HOME）下 Path.home() 会抛异常
        logger.debug("无法解析用户主目录，直接使用临时目录。", exc_info=True)
    candidates.append(Path(tempfile.gettempdir()) / "city_insight_matplotlib")

    for path in candidates:
        if _usable(path):
            os.environ["MPLCONFIGDIR"] = str(path)
            return path

    logger.warning("未找到可写的 matplotlib 配置目录，字体缓存可能无法保存。")
    return None
