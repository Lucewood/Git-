"""地图静态资源本地化：ECharts / china.js 随应用部署，摆脱外部 CDN。

回归背景：线上 Cloud 的地图 iframe 依赖 `assets.pyecharts.org`，其证书在
2026-11 已过期；浏览器报 `ERR_CERT_DATE_INVALID` / `echarts is not defined`，
导致地图空白，而本地有时因缓存仍能显示。
"""

from __future__ import annotations

import re
from pathlib import Path

from city_insight import map_assets

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOKS_DIR = ROOT / "notebooks"
CONFIG_PATH = ROOT / ".streamlit" / "config.toml"
CDN_PREFIX = "https://assets.pyecharts.org/assets/"


def test_required_assets_are_present_and_non_empty() -> None:
    """ECharts 与 china.js 必须随仓库部署，且体积合理。"""
    for relative in map_assets.REQUIRED_ASSETS:
        path = map_assets.STATIC_MAP_ROOT / relative
        assert path.is_file(), f"缺少地图静态资源：{path}"
        assert path.stat().st_size > 1024, f"地图静态资源异常小：{path}"
    assert map_assets.map_assets_available() is True


def test_localize_map_assets_rewrites_all_pyecharts_cdn_urls() -> None:
    """地图 HTML 中所有 pyecharts CDN 脚本都应改写为应用静态路径。"""
    html = (
        "<html><head>"
        f'<script src="{CDN_PREFIX}v6/echarts.min.js"></script>'
        f'<script src="{CDN_PREFIX}v6/maps/china.js"></script>'
        "</head><body><div id=\"chart\"></div></body></html>"
    )
    localized = map_assets.localize_map_assets(html)
    assert CDN_PREFIX not in localized
    assert "https://assets.pyecharts.org" not in localized
    # 必须是相对路径：Cloud 的应用 iframe 在 /~/+/ 下，相对路径才能正确解析
    assert "app/static/pyecharts/v6/echarts.min.js" in localized
    assert "app/static/pyecharts/v6/maps/china.js" in localized
    assert 'src="/app/static/pyecharts/' not in localized
    # 其余 HTML 内容保持不变
    assert '<div id="chart"></div>' in localized


def test_localize_can_be_disabled_for_fallback() -> None:
    """静态服务不可关闭用启用时，应保留原 CDN 作为兜底。"""
    html = f'<script src="{CDN_PREFIX}v6/echarts.min.js"></script>'
    assert map_assets.localize_map_assets(html, enabled=False) == html


def test_notebooks_still_use_pyecharts_cdn_as_source() -> None:
    """notebooks 是生成物，仍以 CDN 写法为源；本地化在读取时完成。"""
    map_files = sorted(NOTEBOOKS_DIR.glob("*.html"))
    assert map_files, "notebooks/ 下应有 pyecharts 地图 HTML"
    for path in map_files:
        assert CDN_PREFIX in path.read_text(encoding="utf-8")


def test_static_serving_is_enabled_in_config() -> None:
    """Streamlit 静态文件服务必须在配置中开启（Cloud 同样读取该配置）。"""
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    assert re.search(
        r"(?m)^\s*enableStaticServing\s*=\s*true\s*$", config_text
    ), ".streamlit/config.toml 未启用 server.enableStaticServing"
