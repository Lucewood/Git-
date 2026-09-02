"""统一日志配置：控制台输出 + 滚动文件日志。"""

from __future__ import annotations

import logging
import logging.handlers
import sys

from .config import LOG_DIR, APP_VERSION

_CONFIGURED = False


def setup_logging(log_level: str = "INFO") -> None:
    """初始化全局日志。

    - 幂等：可安全重复调用（仅首次生效）；
    - 文件系统不可写时自动降级为仅控制台输出；
    - 抑制第三方库（matplotlib / streamlit）的噪音日志。
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    level = getattr(logging, str(log_level).upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_DIR / "app.log",
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError:
        logging.getLogger(__name__).warning("日志文件不可写，降级为仅控制台输出。")

    # 抑制第三方噪音日志
    logging.getLogger("matplotlib.font_manager").setLevel(logging.WARNING)
    logging.getLogger("streamlit").setLevel(logging.WARNING)

    logging.getLogger(__name__).info("日志系统初始化完成 (app_version=%s)", APP_VERSION)
