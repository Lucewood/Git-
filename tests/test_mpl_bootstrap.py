"""matplotlib 配置目录引导测试（只读 HOME / 只读容器场景）。"""

from __future__ import annotations

import os
from pathlib import Path

from city_insight.mpl_bootstrap import ensure_mpl_config_dir


def test_uses_existing_writable_config_dir(monkeypatch, tmp_path):
    """已显式配置且可写的 MPLCONFIGDIR 应被沿用。"""
    target = tmp_path / "matplotlib"
    monkeypatch.setenv("MPLCONFIGDIR", str(target))

    result = ensure_mpl_config_dir()

    assert result == target
    assert target.is_dir()
    assert Path(os.environ["MPLCONFIGDIR"]) == target


def test_replaces_unwritable_config_dir(monkeypatch, tmp_path):
    """配置目录不可写时自动改用其它可写目录，避免字体缓存写入失败。"""
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory", encoding="utf-8")
    broken = blocker / "matplotlib"
    monkeypatch.setenv("MPLCONFIGDIR", str(broken))

    result = ensure_mpl_config_dir()

    assert result is not None
    assert result != broken
    assert result.is_dir()
    assert Path(os.environ["MPLCONFIGDIR"]) == result
