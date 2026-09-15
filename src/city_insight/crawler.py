"""通用网络爬虫框架（礼貌抓取 + 磁盘缓存 + HTML 表格解析）。

设计要点（工程化的「爬虫相关技术」要素）：
1. **合规抓取**：自定义 User-Agent 标识身份、robots.txt 准入检查（按主机缓存
   解析结果）、同域请求最小间隔限速（默认 1 秒）、请求失败指数退避重试；
2. **离线缓存**：响应按 URL 摘要落盘到 data/crawl_cache/，重复运行不再打网络，
   保证数据管道在无网络环境（CI）下同样可复现；
3. **协议无关**：同时支持 http(s):// 与 file:// —— 后者用于本地页面快照，
   便于「无网络也能跑通完整爬取 → 解析 → 落库流程」；
4. **依赖降级**：HTTP 客户端优先 requests、缺失时回退 urllib.request；
   HTML 解析优先 BeautifulSoup、缺失时回退 stdlib html.parser，均零外部依赖也能工作；
5. **解析与清洗分离**：parse_industry_page() 只负责 HTML → 记录，
   build_industry_frame() 负责类型转换与规范化，便于单元测试。

本模块不依赖 Streamlit，可被 scripts/ 与 pytest 直接调用。
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import urllib.robotparser
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlparse
from urllib.request import Request, url2pathname, urlopen

import pandas as pd

from .config import (
    CRAWL_CACHE_DIR,
    INDUSTRY_COLS,
    INDUSTRY_NUMERIC_COLS,
    SKILL_SEPARATOR,
)

logger = logging.getLogger(__name__)

# 可选依赖：HTTP 客户端与 HTML 解析器
try:
    import requests
except Exception:  # noqa: BLE001 - 缺失时回退到 urllib
    requests = None  # type: ignore[assignment]

try:
    from bs4 import BeautifulSoup
except Exception:  # noqa: BLE001 - 缺失时回退到 stdlib html.parser
    BeautifulSoup = None  # type: ignore[assignment]

DEFAULT_USER_AGENT = (
    "CityInsightCrawler/2.3 (+教学演示爬虫; 遵守 robots.txt; "
    "contact: city-insight@example.com)"
)
DEFAULT_CACHE_DIR = CRAWL_CACHE_DIR
# 目标表格的 CSS 类名（快照页面与真实统计网页的解析锚点，可在调用处覆盖）
INDUSTRY_TABLE_CLASS = "industry-table"

# 表头（中文，来自被爬取页面）→ 标准列名
HEADER_MAP: dict[str, str] = {
    "城市": "city",
    "支柱产业": "industry",
    "产业名称": "industry",
    "行业大类": "category",
    "就业占比(%)": "share_pct",
    "就业占比（%）": "share_pct",
    "平均月薪(元)": "avg_salary",
    "平均月薪（元）": "avg_salary",
    "需求景气指数": "demand_index",
    "岗位年增速(%)": "growth_pct",
    "岗位年增速（%）": "growth_pct",
    "学历门槛": "education",
    "核心技能": "skills",
}

REQUIRED_HEADERS: tuple[str, ...] = ("city", "industry", "category")


class FetchError(RuntimeError):
    """抓取失败（超时 / 重试耗尽 / robots 禁止 / 网络被禁用）。"""


@dataclass(frozen=True)
class CrawlSource:
    """待抓取的页面源（名称 + URL，URL 支持 http(s):// 与 file://）。"""

    name: str
    url: str
    note: str = ""


@dataclass(frozen=True)
class FetchPolicy:
    """抓取策略（礼貌爬虫参数，均可由环境变量 / CLI 覆盖）。"""

    user_agent: str = DEFAULT_USER_AGENT
    delay: float = 1.0            # 同域请求最小间隔（秒）
    timeout: float = 10.0         # 单次请求超时（秒）
    retries: int = 3              # 失败重试次数（指数退避）
    backoff: float = 1.5          # 退避倍数
    respect_robots: bool = True   # 是否检查 robots.txt（仅 http(s) 生效）
    use_cache: bool = True        # 是否启用磁盘缓存
    allow_network: bool = True    # 是否允许发起真实网络请求
    cache_dir: Path = DEFAULT_CACHE_DIR


@dataclass
class CrawlReport:
    """一次爬取任务的统计报告（用于日志与数据质量展示）。"""

    sources_total: int = 0
    sources_ok: int = 0
    sources_from_network: int = 0
    sources_from_cache: int = 0
    sources_from_snapshot: int = 0
    records: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sources_total": self.sources_total,
            "sources_ok": self.sources_ok,
            "sources_from_network": self.sources_from_network,
            "sources_from_cache": self.sources_from_cache,
            "sources_from_snapshot": self.sources_from_snapshot,
            "records": self.records,
            "errors": list(self.errors),
        }


# ---------------------------------------------------------------------------
# 抓取器
# ---------------------------------------------------------------------------
def http_get(url: str, *, user_agent: str, timeout: float) -> str:
    """统一 HTTP GET：优先 requests，缺失时回退 urllib.request。"""
    if requests is not None:
        response = requests.get(
            url, headers={"User-Agent": user_agent}, timeout=timeout
        )
        response.raise_for_status()
        # 显式指定编码，避免中文页面被误判为 latin-1 而乱码
        response.encoding = response.apparent_encoding or "utf-8"
        return response.text
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=timeout) as resp:  # noqa: S310 - 显式 URL（演示用）
        return resp.read().decode("utf-8", errors="replace")


def _soup_or_none(html: str):
    """构造 BeautifulSoup（优先 lxml，其次内置 html.parser）；不可用时返回 None。"""
    if BeautifulSoup is None:
        return None
    for parser in ("lxml", "html.parser"):
        try:
            return BeautifulSoup(html, parser)
        except Exception:  # noqa: BLE001 - 解析器不可用时换下一个
            continue
    return None


class _TableCollector(HTMLParser):
    """stdlib 回退实现：收集指定 class 表格的全部单元格文本。"""

    def __init__(self, table_class: str) -> None:
        super().__init__(convert_charrefs=True)
        self.table_class = table_class
        self.rows: list[list[str]] = []
        self._depth = 0          # 目标表格内嵌层数（0 = 未进入）
        self._in_row = False
        self._in_cell = False
        self._buf: list[str] = []
        self._row: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "table":
            classes = (attr.get("class") or "").split()
            if self._depth == 0 and self.table_class in classes:
                self._depth = 1
                return
            if self._depth:
                self._depth += 1
            return
        if not self._depth:
            return
        if tag == "tr":
            self._in_row, self._row = True, []
        elif tag in {"td", "th"}:
            self._in_cell, self._buf = True, []

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self._depth:
            self._depth -= 1
            return
        if not self._depth:
            return
        if tag in {"td", "th"} and self._in_cell:
            self._row.append("".join(self._buf).strip())
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if self._row:
                self.rows.append(self._row)
            self._in_row = False

    def handle_data(self, data: str) -> None:
        if self._depth and self._in_cell:
            self._buf.append(data)


def parse_html_table(html: str, table_class: str = INDUSTRY_TABLE_CLASS) -> list[list[str]]:
    """解析 HTML 中指定 class 的表格，返回「行 × 列」文本矩阵（含表头行）。

    优先使用 BeautifulSoup；不可用时回退 stdlib html.parser，行为一致。
    """
    soup = _soup_or_none(html)
    if soup is not None:
        table = soup.find("table", class_=table_class)
        if table is None:
            return []
        rows: list[list[str]] = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if cells:
                rows.append([cell.get_text(strip=True) for cell in cells])
        return rows

    collector = _TableCollector(table_class)
    collector.feed(html)
    return collector.rows

class Fetcher:
    """礼貌抓取器：robots 准入 + 同域限速 + 重试 + 磁盘缓存 + 本地快照回退。"""

    def __init__(self, policy: FetchPolicy | None = None) -> None:
        self.policy = policy or FetchPolicy()
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    # -- 对外入口 ---------------------------------------------------------
    def fetch(self, url: str) -> str:
        """抓取页面文本；失败抛出 FetchError。"""
        text, _origin = self.fetch_with_origin(url)
        return text

    def fetch_with_origin(self, url: str) -> tuple[str, str]:
        """抓取页面文本并返回来源标识：network / cache / snapshot。

        - file:// 协议直接读本地文件（来源标记 snapshot）；
        - http(s):// 先查磁盘缓存，命中则不发起网络请求（来源 cache）；
        - 未命中且允许联网时发起请求并写缓存（来源 network）。
        """
        scheme = urlparse(url).scheme.lower()
        if scheme in {"", "file"}:
            return self._read_local(url), "snapshot"

        cached = self._read_cache(url)
        if cached is not None:
            logger.debug("命中本地缓存：%s", url)
            return cached, "cache"

        if not self.policy.allow_network:
            raise FetchError(f"已禁用网络请求，且本地无缓存：{url}")

        text = self._fetch_remote(url)
        self._write_cache(url, text)
        return text, "network"

    # -- 缓存 -------------------------------------------------------------
    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        return Path(self.policy.cache_dir) / f"{digest}.html"

    def _read_cache(self, url: str) -> str | None:
        if not self.policy.use_cache:
            return None
        path = self._cache_path(url)
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
        return None

    def _write_cache(self, url: str, text: str) -> None:
        if not self.policy.use_cache:
            return
        path = self._cache_path(url)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except OSError as exc:  # 缓存不可写不应中断抓取
            logger.warning("写入爬取缓存失败（%s）：%s", path, exc)

    @staticmethod
    def _read_local(url: str) -> str:
        """读取 file:// 本地快照（url 亦可直接是文件路径）。"""
        parsed = urlparse(url)
        if parsed.scheme == "file":
            path = Path(url2pathname(parsed.path.lstrip("/")))
        elif parsed.scheme == "":
            path = Path(url)
        else:
            raise FetchError(f"不支持的 URL 协议：{url}")
        if not path.exists():
            raise FetchError(f"本地快照不存在：{path}")
        return path.read_text(encoding="utf-8", errors="replace")

    # -- 网络 -------------------------------------------------------------
    def _throttle(self, host: str) -> None:
        """同域限速：保证两次请求间隔不小于 policy.delay 秒。"""
        if self.policy.delay <= 0:
            return
        last = self._last_request.get(host)
        now = time.monotonic()
        if last is not None:
            wait = self.policy.delay - (now - last)
            if wait > 0:
                time.sleep(wait)
        self._last_request[host] = time.monotonic()

    def _allowed_by_robots(self, url: str) -> bool:
        """检查 robots.txt 是否允许抓取（无法获取 robots 时按允许处理）。"""
        if not self.policy.respect_robots:
            return True
        parsed = urlparse(url)
        host = f"{parsed.scheme}://{parsed.netloc}"
        if host not in self._robots:
            parser: urllib.robotparser.RobotFileParser | None = None
            try:
                text = http_get(
                    f"{host}/robots.txt",
                    user_agent=self.policy.user_agent,
                    timeout=min(self.policy.timeout, 5.0),
                )
                parser = urllib.robotparser.RobotFileParser()
                parser.parse(text.splitlines())
            except Exception as exc:  # noqa: BLE001 - robots 不可用时不阻断抓取
                logger.debug("robots.txt 获取失败（按允许处理）：%s", exc)
            self._robots[host] = parser
        parser = self._robots[host]
        if parser is None:
            return True
        allowed = parser.can_fetch(self.policy.user_agent, url)
        if not allowed:
            logger.warning("robots.txt 禁止抓取：%s", url)
        return allowed

    def _fetch_remote(self, url: str) -> str:
        """带限速、robots 检查与指数退避重试的网络抓取。"""
        if not self._allowed_by_robots(url):
            raise FetchError(f"robots.txt 不允许抓取：{url}")

        host = urlparse(url).netloc
        retries = max(1, self.policy.retries)
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            self._throttle(host)
            try:
                logger.info("抓取（第 %d/%d 次）：%s", attempt, retries, url)
                return http_get(
                    url,
                    user_agent=self.policy.user_agent,
                    timeout=self.policy.timeout,
                )
            except Exception as exc:  # noqa: BLE001 - 统一转为 FetchError
                last_error = exc
                if attempt >= retries:
                    break
                wait = self.policy.backoff ** attempt
                logger.warning("抓取失败（%s），%.1fs 后重试：%s", exc, wait, url)
                time.sleep(wait)
        raise FetchError(
            f"抓取失败（已重试 {retries} 次）：{url}：{last_error}"
        )


# ---------------------------------------------------------------------------
# 页面解析与清洗
# ---------------------------------------------------------------------------
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def clean_number(text: Any) -> float | None:
    """从单元格文本中提取数值：兼容千分位、「12.5%」、「1.2万」、「—」等写法。"""
    if text is None:
        return None
    raw = str(text).strip().replace(",", "").replace("，", "")
    if not raw or raw in {"-", "—", "--", "N/A", "无"}:
        return None
    match = _NUMBER_RE.search(raw)
    if match is None:
        return None
    value = float(match.group())
    if "万" in raw:
        value *= 10000.0
    return value


def split_skills(text: Any) -> tuple[str, ...]:
    """拆分技能单元格（支持 |、,、; 等分隔符），去空去重并保持顺序。

    注意：不把「/」当作分隔符，避免把「CAD/CAM」这类合成技能名拆散。
    """
    if text is None:
        return ()
    parts = re.split(r"[|、,，;；]+", str(text))
    seen: dict[str, None] = {}
    for part in parts:
        token = part.strip()
        if token:
            seen.setdefault(token, None)
    return tuple(seen)


def parse_industry_page(
    html: str, *, table_class: str = INDUSTRY_TABLE_CLASS
) -> list[dict[str, Any]]:
    """解析单个支柱产业页面 → 记录列表（字段名为 config.INDUSTRY_COLS 中的标准名）。

    解析规则：
    1. 取 class 为 table_class 的表格；表头行须含「城市 / 支柱产业 / 行业大类」
       三个必需列（其余列缺失时按 None 处理，便于兼容不同来源的列差异）；
    2. 数值列经 clean_number 归一化（支持千分位与百分号），技能列按分隔符拆分后
       重新以 config.SKILL_SEPARATOR 连接，保证落库格式统一；
    3. 缺少必需列或城市为空的脏数据行直接丢弃（返回结果条数可能少于表格行数）。
    """
    rows = parse_html_table(html, table_class)
    if len(rows) < 2:
        return []

    header = [HEADER_MAP.get(cell.strip()) for cell in rows[0]]
    if not {col for col in header if col} >= set(REQUIRED_HEADERS):
        logger.warning("页面表头缺少必需列，跳过：%s", rows[0])
        return []

    records: list[dict[str, Any]] = []
    for raw_row in rows[1:]:
        if not any(cell.strip() for cell in raw_row):
            continue  # 空行
        row: dict[str, Any] = {}
        for index, cell in enumerate(raw_row):
            if index >= len(header) or header[index] is None:
                continue
            row[header[index]] = cell

        city = str(row.get("city", "")).strip()
        industry = str(row.get("industry", "")).strip()
        category = str(row.get("category", "")).strip()
        if not (city and industry and category):
            continue

        records.append(
            {
                "city": city,
                "industry": industry,
                "category": category,
                "share_pct": clean_number(row.get("share_pct")),
                "avg_salary": clean_number(row.get("avg_salary")),
                "demand_index": clean_number(row.get("demand_index")),
                "growth_pct": clean_number(row.get("growth_pct")),
                "education": str(row.get("education", "")).strip(),
                "skills": SKILL_SEPARATOR.join(split_skills(row.get("skills"))),
            }
        )
    return records


def build_industry_frame(records: Iterable[dict[str, Any]]) -> pd.DataFrame:
    """记录列表 → 规范化的支柱产业长表（列顺序 / 数值类型 / 去重统一）。

    - 数值列强制转 float，非法值置 NaN 并在关键字段缺失时剔除该行；
    - 同一「城市 × 支柱产业」重复记录保留首次出现（可按需改为按占比取最大）；
    - 输出按城市、就业占比降序排列。
    """
    frame = pd.DataFrame(list(records))
    if frame.empty:
        return pd.DataFrame(columns=list(INDUSTRY_COLS))

    for col in INDUSTRY_COLS:
        if col not in frame.columns:
            frame[col] = None
    frame = frame[list(INDUSTRY_COLS)]

    for col in ("city", "industry", "category", "education", "skills"):
        frame[col] = frame[col].astype("string").fillna("").str.strip()
    for col in INDUSTRY_NUMERIC_COLS:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")

    frame = frame[
        (frame["city"] != "") & (frame["industry"] != "") & (frame["category"] != "")
    ]
    frame = frame.drop_duplicates(subset=["city", "industry"], keep="first")
    frame = frame.dropna(subset=["share_pct", "avg_salary"]).reset_index(drop=True)

    frame["share_pct"] = frame["share_pct"].round(1)
    frame["avg_salary"] = frame["avg_salary"].round().astype("Int64")
    frame["demand_index"] = frame["demand_index"].round(1)
    frame["growth_pct"] = frame["growth_pct"].round(1)
    return frame.sort_values(
        ["city", "share_pct"], ascending=[True, False]
    ).reset_index(drop=True)


def crawl_industry(
    sources: Sequence[CrawlSource],
    *,
    policy: FetchPolicy | None = None,
    fetcher: Fetcher | None = None,
    table_class: str = INDUSTRY_TABLE_CLASS,
) -> tuple[pd.DataFrame, CrawlReport]:
    """按源列表抓取并解析支柱产业数据。

    单个页面失败不影响整体流程：错误记入 CrawlReport.errors 并继续下一个源。

    Returns:
        (industry_df, report) —— DataFrame 为规范化长表；report 含抓取统计与错误。
    """
    fetcher = fetcher or Fetcher(policy)
    report = CrawlReport(sources_total=len(sources))
    records: list[dict[str, Any]] = []

    for source in sources:
        try:
            html, origin = fetcher.fetch_with_origin(source.url)
            page_records = parse_industry_page(html, table_class=table_class)
        except FetchError as exc:
            report.errors.append(f"{source.name}: {exc}")
            logger.warning("数据源抓取失败：%s（%s）", source.name, exc)
            continue

        report.sources_ok += 1
        if origin == "network":
            report.sources_from_network += 1
        elif origin == "cache":
            report.sources_from_cache += 1
        else:
            report.sources_from_snapshot += 1

        if not page_records:
            report.errors.append(f"{source.name}: 页面解析结果为空")
            logger.warning("数据源解析结果为空：%s", source.name)
        records.extend(page_records)
        logger.info("数据源 %s 解析出 %d 条记录（来源：%s）", source.name, len(page_records), origin)

    frame = build_industry_frame(records)
    report.records = int(len(frame))
    return frame, report

