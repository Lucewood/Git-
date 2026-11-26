"""把 pyecharts 地图 HTML 的外部 CDN 脚本切换为应用自带静态资源。

背景：``notebooks/*.html`` 由 pyecharts 生成，默认引用
``https://assets.pyecharts.org/assets/...``。该 CDN 一旦网络不可达或证书失效，
地图 iframe 就会空白，浏览器控制台报 ``echarts is not defined``
（2026 年该域名证书已过期，本地与 Cloud 都会复现）。

修复：把 ``echarts.min.js`` 与 ``china.js`` 放入 ``src/static/pyecharts/v6/``，
通过 Streamlit 官方静态文件服务（``server.enableStaticServing = true``）以
**相对 URL** ``app/static/pyecharts/...`` 同源提供（Cloud 会自动解析到
``/~/+/app/static/...``），从而不依赖任何外部 CDN。
"""

from __future__ import annotations

from pathlib import Path

# 地图 HTML 中的外部脚本前缀（pyecharts v6 默认写法）
PYECHARTS_CDN_PREFIX = "https://assets.pyecharts.org/assets/"
# 启用 server.enableStaticServing 后的应用静态资源路径。必须使用**相对路径**：
# - 本地应用位于 /，解析为 /app/static/pyecharts/...
# - Streamlit Cloud 应用 iframe 位于 /~/+/，解析为 /~/+/app/static/pyecharts/...
#   根路径 /app/static/... 在 Cloud 会落到外壳 HTML，导致脚本 MIME 错误。
STATIC_URL_PREFIX = "app/static/pyecharts/"
# 应用静态目录：src/streamlit_app.py 所在目录下的 static/
STATIC_MAP_ROOT = Path(__file__).resolve().parent.parent / "static" / "pyecharts"
# 地图渲染实际需要的资源（与 notebooks/*.html 的引用路径保持一致）
REQUIRED_ASSETS: tuple[str, ...] = (
    "v6/echarts.min.js",
    "v6/maps/china.js",
)


def map_assets_available() -> bool:
    """本地地图脚本是否就位（文件存在且非空）。"""
    for relative in REQUIRED_ASSETS:
        path = STATIC_MAP_ROOT / relative
        try:
            if not path.is_file() or path.stat().st_size < 1024:
                return False
        except OSError:
            return False
    return True


def localize_map_assets(html: str, *, enabled: bool = True) -> str:
    """把地图 HTML 的 pyecharts CDN 脚本替换为应用静态资源 URL。

    Args:
        html: pyecharts 生成的完整 HTML。
        enabled: 是否启用本地化；静态服务未开启或资源缺失时应传 False，
            保留原 CDN 引用作为最后兜底（虽然 CDN 可能不可用）。
    """
    if not enabled or not map_assets_available():
        return html
    return html.replace(PYECHARTS_CDN_PREFIX, STATIC_URL_PREFIX)
