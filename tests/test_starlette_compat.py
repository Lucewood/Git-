"""Streamlit 1.58 与 starlette 版本兼容性回归测试。

背景：Streamlit 1.58.0 的 ``SelectiveGZipMiddleware`` 适配 starlette 1.3.x 的
GZipResponder 内部实现；starlette >= 1.4 时，gzip 中间件会吞掉
``http.response.start``，导致 ``/media/``（图表 PNG）等响应在 uvicorn 侧抛
``RuntimeError: Expected ASGI message 'http.response.start'`` 并返回 500，
页面表现为文字正常、所有图表空白。

requirements.txt 因此锁定 ``starlette==1.3.1``；本测试在 CI 中同时校验：
1. 安装版本仍低于 1.4；
2. 该版本下 gzip 中间件对 image/png 响应仍按「start → body」顺序下发。
"""

from __future__ import annotations

import asyncio
import importlib.metadata as metadata

from packaging.version import Version
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route
from streamlit.web.server.starlette.starlette_gzip_middleware import (
    SelectiveGZipMiddleware,
)


def test_starlette_version_is_compatible_with_streamlit():
    """starlette 必须保持在 Streamlit 1.58 适配的 1.3.x（<1.4）。"""
    installed = Version(metadata.version("starlette"))
    assert installed < Version("1.4"), (
        f"starlette {installed} 与 Streamlit 1.58 的 GZip 中间件不兼容："
        "图表的 /media 响应会丢 http.response.start 并返回 500。"
        "请保留 requirements.txt 中的 starlette==1.3.1。"
    )


def test_media_response_starts_before_body():
    """gzip 中间件包裹的 PNG 响应必须先发 response.start，再发 body。"""

    async def endpoint(_request):
        return Response(b"\x89PNG\r\n\x1a\n" + b"0" * 4096, media_type="image/png")

    app = SelectiveGZipMiddleware(
        Starlette(routes=[Route("/media/sample.png", endpoint)]),
        minimum_size=10,
        compresslevel=6,
    )

    async def run() -> list[dict]:
        sent: list[dict] = []

        async def send(message):
            sent.append(message)

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/media/sample.png",
            "raw_path": b"/media/sample.png",
            "query_string": b"",
            "root_path": "",
            "headers": [(b"accept-encoding", b"gzip")],
            "client": ("127.0.0.1", 12345),
            "server": ("localhost", 8501),
        }
        await app(scope, receive, send)
        return sent

    messages = asyncio.run(run())

    assert [message["type"] for message in messages] == [
        "http.response.start",
        "http.response.body",
    ]
    assert messages[0]["status"] == 200
    assert dict(messages[0]["headers"])[b"content-encoding"] == b"gzip"
