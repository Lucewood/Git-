"""
下载 / 校验仓库内置中文字体（assets/fonts/）。

仓库已内置 Noto Sans SC Regular（SIL OFL 1.1，见 assets/fonts/LICENSE-OFL.txt），
正常克隆后无需执行本脚本；仅在字体文件丢失（手工拷贝源码、误删等）或需要更新
字体时用它重新拉取，避免 Linux 服务器（Streamlit Community Cloud 等）上
matplotlib 缺字、图表中文显示成「方框」。

运行方式（在项目根目录）：
    python scripts/fetch_fonts.py                 # 缺失时下载（已存在则跳过）
    python scripts/fetch_fonts.py --force         # 强制重新下载
    python scripts/fetch_fonts.py --check         # 只校验现有字体（不联网）
    python scripts/fetch_fonts.py --url <字体URL> --name Custom.otf

下载源为 jsDelivr 的多个镜像（含 fastly / gcore 别名，规避单一 CDN 不可达），
逐镜像重试；HTTP 客户端优先 requests、缺失时回退 urllib.request（与 crawler 一致）。
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from city_insight import fonts  # noqa: E402
from city_insight.config import FONT_DIR  # noqa: E402

# Noto Sans SC Regular 在 notofonts/noto-cjk 仓库中的路径；各镜像前缀不同
FONT_REPO_PATH = "gh/notofonts/noto-cjk@main/Sans/SubsetOTF/SC/NotoSansSC-Regular.otf"
DEFAULT_MIRRORS: tuple[str, ...] = (
    f"https://fastly.jsdelivr.net/{FONT_REPO_PATH}",
    f"https://gcore.jsdelivr.net/{FONT_REPO_PATH}",
    f"https://cdn.jsdelivr.net/{FONT_REPO_PATH}",
    "https://raw.githubusercontent.com/notofonts/noto-cjk/main"
    "/Sans/SubsetOTF/SC/NotoSansSC-Regular.otf",
)
DEFAULT_NAME = "NotoSansSC-Regular.otf"
# 完整 CJK 字体至少 1 MB；明显偏小说明下载被截断或返回了错误页
MIN_BYTES = 1_000_000
TIMEOUT = 120.0
ATTEMPTS = 3  # 单镜像重试次数
BACKOFF = 1.5  # 指数退避倍数（秒）
# 明确的 UA：便于 CDN 侧识别来源，不伪装成浏览器
USER_AGENT = "city-insight-fetch-fonts/1.0"

try:  # 可选依赖：优先 requests（与 city_insight.crawler 的降级策略一致）
    import requests
except Exception:  # noqa: BLE001 - 缺失时回退 urllib
    requests = None  # type: ignore[assignment]


def fetch_once(url: str) -> bytes:
    """单次抓取，返回响应体；失败抛出异常（由调用方决定是否重试）。"""
    if requests is not None:
        response = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
        )
        response.raise_for_status()
        return response.content
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 - 固定 https 源
        return response.read()


def fetch_with_retry(url: str) -> bytes:
    """按指数退避重试抓取；全部失败时抛出最后一次异常。"""
    last_error: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return fetch_once(url)
        except Exception as exc:  # noqa: BLE001 - 网络抖动 / TLS 重置均重试
            last_error = exc
            print(f"  第 {attempt}/{ATTEMPTS} 次失败：{exc}")
            if attempt < ATTEMPTS:
                time.sleep(BACKOFF ** attempt)
    raise last_error if last_error else RuntimeError(f"下载失败：{url}")


def save_font(urls: tuple[str, ...], target: Path) -> int:
    """依次尝试各镜像下载字体并原子落盘，返回字节数。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f"{target.name}.part")
    errors: list[str] = []
    try:
        for url in urls:
            print(f"下载：{url}")
            try:
                data = fetch_with_retry(url)
            except Exception as exc:  # noqa: BLE001 - 该镜像不可用，换下一个
                errors.append(f"{url} -> {exc}")
                continue
            if len(data) < MIN_BYTES:
                errors.append(f"{url} -> 仅 {len(data)} 字节，疑似被截断 / 非字体文件")
                continue
            partial.write_bytes(data)
            partial.replace(target)  # 原子替换，避免半截文件被应用读到
            return len(data)
        raise RuntimeError("所有下载源均失败：\n  " + "\n  ".join(errors))
    finally:
        partial.unlink(missing_ok=True)


def describe(path: Path) -> None:
    """打印字体文件摘要：大小 / SHA-256 / matplotlib 识别到的字体族名。"""
    data = path.read_bytes()
    family = fonts.register_font_file(str(path))
    print(f"  文件：{path}")
    print(f"  大小：{len(data):,} 字节")
    print(f"  SHA-256：{hashlib.sha256(data).hexdigest()}")
    print(f"  字体族名：{family or '无法识别（文件可能损坏）'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="下载 / 校验仓库内置中文字体")
    parser.add_argument(
        "--url", action="append", default=None,
        help="自定义下载地址（可重复传入；默认使用内置 jsDelivr 镜像列表）",
    )
    parser.add_argument("--name", default=DEFAULT_NAME, help="保存的文件名")
    parser.add_argument("--force", action="store_true", help="即使已存在也重新下载")
    parser.add_argument("--check", action="store_true", help="只校验现有字体，不联网")
    args = parser.parse_args()

    target = Path(FONT_DIR) / args.name
    print(f"字体目录：{FONT_DIR}")

    if args.check:
        files = fonts.bundled_font_files()
        if not files:
            print("未找到内置字体文件，请运行：python scripts/fetch_fonts.py")
            return 1
        for path in files:
            describe(path)
        print(f"matplotlib 将使用：{fonts.resolve_cjk_font() or '（无可用中文字体）'}")
        return 0

    if target.exists() and not args.force:
        print(f"已存在，跳过下载（--force 可强制更新）：{target.name}")
        describe(target)
        return 0

    try:
        size = save_font(tuple(args.url or DEFAULT_MIRRORS), target)
    except Exception as exc:  # noqa: BLE001 - 网络不可用时只提示，不影响仓库其余内容
        print(f"下载失败：{exc}")
        print(
            "可手动处理：用浏览器打开上述任一 URL，把字体文件保存为\n"
            f"  {target}\n"
            "（需 7~10 MB 的完整字体文件），再运行 --check 校验。"
        )
        return 1
    print(f"已写入 {size:,} 字节")
    describe(target)
    print(f"matplotlib 将使用：{fonts.resolve_cjk_font() or '（无可用中文字体）'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
