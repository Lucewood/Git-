"""
爬取城市支柱产业数据并生成 data/industry.csv（就业指导推荐功能的数据基础）。

两阶段流程（可分别执行）：
  1. snapshot 阶段：依据 city_insight.industry_seed 的种子口径渲染 8 个区域
     「支柱产业与人才需求统计快报」HTML 页面（data/raw/industry/），
     模拟公开统计网页结构（含导航 / 脚注等噪音节点，数据表 class=industry-table）；
  2. crawl 阶段：用 city_insight.crawler 的礼貌抓取器（UA 标识、robots 准入、
     同域限速、失败指数退避重试、响应磁盘缓存）抓取上述页面 → 解析表格 →
     清洗规范化 → 写出 data/industry.csv。

用法（在项目根目录）：
    python scripts/crawl_industry.py                  # 生成快照 + 爬取（离线，推荐）
    python scripts/crawl_industry.py --mode snapshot  # 仅重新生成离线页面快照
    python scripts/crawl_industry.py --mode crawl     # 仅爬取（要求快照已存在）
    python scripts/crawl_industry.py --mode crawl --no-network   # 强制只用本地快照
    python scripts/crawl_industry.py --mode crawl \
        --url https://example.com/pillar-industry.html           # 追加真实公开页面

> ⚠️ 合规提示：抓取真实站点前请确认其 robots.txt 与使用条款；本脚本默认只抓取
> 仓库内置的离线快照（file://），不产生任何对外网络请求。

依赖：requests / beautifulsoup4 为可选增强（缺失时自动回退 urllib + stdlib 解析）。
"""

from __future__ import annotations

import argparse
import sys
from html import escape
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from city_insight.config import (
    DATA_DIR,
    DATA_REF_YEAR,
    INDUSTRY_FILE,
    INDUSTRY_SNAPSHOT_DIR,
    get_settings,
)
from city_insight.crawler import CrawlSource, FetchPolicy, crawl_industry
from city_insight.data_loader import load_and_merge
from city_insight.industry_seed import records_by_region, seed_records
from city_insight.logging_setup import setup_logging

OUT_PATH = DATA_DIR / INDUSTRY_FILE
SNAPSHOT_SUFFIX = "支柱产业与人才需求统计快报.html"

# 页面表头（与 crawler.HEADER_MAP 对应，保持真实站点的中文列名习惯）
TABLE_HEADERS: tuple[str, ...] = (
    "城市", "支柱产业", "行业大类", "就业占比(%)", "平均月薪(元)",
    "需求景气指数", "岗位年增速(%)", "学历门槛", "核心技能",
)

# 静态样式单独存放，避免与 f-string 的花括号语法冲突
_PAGE_STYLE = """
    <style>
      body { font-family: "Microsoft YaHei", sans-serif; margin: 24px; color: #222; }
      .site-nav a { margin-right: 12px; color: #06c; }
      .industry-table { border-collapse: collapse; width: 100%; margin-top: 12px; }
      .industry-table th, .industry-table td {
        border: 1px solid #ccc; padding: 4px 8px; font-size: 13px;
      }
      .industry-table thead th { background: #eef2ff; }
      .site-footer { margin-top: 24px; color: #888; font-size: 12px; }
    </style>
"""


def render_snapshot_page(
    region: str,
    records: list[dict],
    city_count: int,
) -> str:
    """把一个区域的产业记录渲染为统计快报 HTML 页面（模拟真实站点结构）。"""
    rows: list[str] = []
    for record in records:
        rows.append(
            "        <tr>"
            f"<td>{escape(str(record['city']))}</td>"
            f"<td>{escape(str(record['industry']))}</td>"
            f"<td>{escape(str(record['category']))}</td>"
            f"<td>{float(record['share_pct']):.1f}%</td>"
            f"<td>{int(record['avg_salary']):,}</td>"
            f"<td>{float(record['demand_index']):.1f}</td>"
            f"<td>{float(record['growth_pct']):+.1f}%</td>"
            f"<td>{escape(str(record['education']))}</td>"
            f"<td>{escape(str(record['skills']).replace('|', '、'))}</td>"
            "</tr>"
        )
    header_html = "".join(f"<th>{escape(h)}</th>" for h in TABLE_HEADERS)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{escape(region)}地区支柱产业与人才需求统计快报（演示）</title>
{_PAGE_STYLE}
</head>
<body>
<nav class="site-nav">
  <a href="/index.html">首页</a><a href="/stats.html">统计快报</a><a href="/about.html">关于我们</a>
</nav>
<h1>{escape(region)}地区支柱产业与人才需求统计快报</h1>
<p class="meta">区域：{escape(region)} · 覆盖城市：{city_count} 个 · 数据参考年份：{DATA_REF_YEAR} ·
口径：结构化演示数据（非官方统计）</p>
<table class="industry-table">
  <caption>支柱产业就业占比、平均月薪与人才需求景气指数</caption>
  <thead>
    <tr>{header_html}</tr>
  </thead>
  <tbody>
{chr(10).join(rows)}
  </tbody>
</table>
<footer class="site-footer">
  <p>本页由 scripts/crawl_industry.py 生成，仅用于演示爬虫抓取与解析流程。</p>
</footer>
</body>
</html>
"""


def write_snapshots(buckets: dict[str, list[dict]]) -> list[Path]:
    """把各区域记录写成 HTML 页面快照，返回生成的文件路径列表。"""
    INDUSTRY_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for region, records in buckets.items():
        if not records:
            continue
        city_count = len({str(r["city"]) for r in records})
        path = INDUSTRY_SNAPSHOT_DIR / f"{region}{SNAPSHOT_SUFFIX}"
        path.write_text(
            render_snapshot_page(region, records, city_count), encoding="utf-8"
        )
        paths.append(path)
        print(f"  已生成快照：{path.name}（{city_count} 城 / {len(records)} 条记录）")
    return paths


def build_sources(extra_urls: list[str]) -> list[CrawlSource]:
    """构造爬取源：本地快照（file://）+ 命令行追加的真实 URL。"""
    sources: list[CrawlSource] = [
        CrawlSource(
            name=path.stem,
            url=path.resolve().as_uri(),
            note="本地页面快照（离线可复现）",
        )
        for path in sorted(INDUSTRY_SNAPSHOT_DIR.glob("*.html"))
    ]
    sources.extend(
        CrawlSource(name=f"remote-{idx + 1}", url=url, note="命令行指定页面")
        for idx, url in enumerate(extra_urls)
    )
    return sources


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    parser = argparse.ArgumentParser(
        description="爬取城市支柱产业数据并生成 data/industry.csv",
    )
    parser.add_argument(
        "--mode", choices=("all", "snapshot", "crawl"), default="all",
        help="all=生成快照并爬取（默认）；snapshot=仅生成离线快照；crawl=仅爬取",
    )
    parser.add_argument(
        "--url", action="append", default=[],
        help="追加的页面 URL（http(s):// 或 file://），可重复指定",
    )
    parser.add_argument("--out", default=str(OUT_PATH), help="输出 CSV 路径")
    parser.add_argument(
        "--no-network", action="store_true",
        help="禁止发起网络请求（只读本地快照 / 缓存，适合 CI）",
    )
    parser.add_argument("--no-cache", action="store_true", help="禁用响应磁盘缓存")
    parser.add_argument("--delay", type=float, default=None, help="同域请求最小间隔（秒）")
    parser.add_argument("--timeout", type=float, default=None, help="单次请求超时（秒）")
    args = parser.parse_args()

    # 城市基本面（省份 / 年收入）用于生成与校验
    city_df, _ = load_and_merge(DATA_DIR)
    province_map = dict(zip(city_df["city"], city_df["province"]))
    print(f"加载城市基本面：{len(city_df)} 个城市")

    if args.mode in {"all", "snapshot"}:
        print("① 生成离线页面快照（模拟公开统计网页）……")
        records = seed_records(city_df)
        write_snapshots(records_by_region(records, province_map))

    if args.mode == "snapshot":
        print("快照生成完成（未执行爬取）。")
        return

    sources = build_sources(args.url)
    if not sources:
        print(
            "未找到任何可爬取页面：请先执行 --mode snapshot 生成离线快照，"
            "或用 --url 指定页面地址。",
            file=sys.stderr,
        )
        raise SystemExit(2)

    print(f"② 开始爬取 {len(sources)} 个页面（礼貌抓取：限速 + 重试 + 缓存）……")
    policy = FetchPolicy(
        delay=args.delay if args.delay is not None else settings.crawl_delay,
        timeout=args.timeout if args.timeout is not None else settings.crawl_timeout,
        allow_network=not args.no_network,
        use_cache=not args.no_cache,
    )
    frame, report = crawl_industry(sources, policy=policy)

    if frame.empty:
        print("爬取结果为空，未写出数据文件。请检查页面结构与 --url 配置。", file=sys.stderr)
        raise SystemExit(1)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out_path, index=False, encoding="utf-8-sig")

    covered = set(frame["city"])
    missing = sorted(set(city_df["city"]) - covered)
    print(f"\n③ 已写出 {out_path}（{len(frame)} 条记录 / {len(covered)} 个城市）")
    print(
        f"   数据源：成功 {report.sources_ok}/{report.sources_total}"
        f"（网络 {report.sources_from_network} · 缓存 {report.sources_from_cache}"
        f" · 快照 {report.sources_from_snapshot}）"
    )
    print(
        f"   行业大类：{frame['category'].nunique()} 个 · "
        f"平均月薪中位数：{int(frame['avg_salary'].median())} 元"
    )
    top = (
        frame.groupby("category")["share_pct"].mean()
        .sort_values(ascending=False).head(3)
    )
    print("   平均就业占比最高的行业：" + "、".join(
        f"{name}({value:.1f}%)" for name, value in top.items()
    ))
    if missing:
        print(f"   ⚠️ {len(missing)} 个城市未覆盖：{'、'.join(missing[:10])}"
              + ("……" if len(missing) > 10 else ""))
    if report.errors:
        print(f"   ⚠️ {len(report.errors)} 个数据源存在异常：")
        for error in report.errors[:5]:
            print(f"     - {error}")


if __name__ == "__main__":
    main()
