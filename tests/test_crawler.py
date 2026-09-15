"""爬虫框架测试：网页抓取策略、HTML 表格解析与数据清洗。"""

from __future__ import annotations

import pytest

from city_insight import crawler
from city_insight.crawler import (
    CrawlSource,
    FetchError,
    FetchPolicy,
    Fetcher,
    build_industry_frame,
    clean_number,
    crawl_industry,
    parse_html_table,
    parse_industry_page,
    split_skills,
)

SAMPLE_HTML = """<html lang="zh-CN"><body>
<nav><a href="/">首页</a></nav>
<table class="industry-table">
  <thead><tr>
    <th>城市</th><th>支柱产业</th><th>行业大类</th><th>就业占比(%)</th>
    <th>平均月薪(元)</th><th>需求景气指数</th><th>岗位年增速(%)</th>
    <th>学历门槛</th><th>核心技能</th>
  </tr></thead>
  <tbody>
    <tr><td>测试城</td><td>软件开发与信息服务</td><td>信息技术</td>
      <td>12.5%</td><td>15,800</td><td>82.3</td><td>+7.5%</td>
      <td>本科及以上</td><td>Python、数据分析、云计算</td></tr>
    <tr><td></td><td>脏数据行</td><td>信息技术</td><td>1.0%</td><td>1</td>
      <td>1</td><td>1%</td><td>本科</td><td>Python</td></tr>
  </tbody>
</table>
<table class="other-table"><tr><td>无关表格</td></tr></table>
</body></html>"""


def test_clean_number_variants():
    """数值清洗应兼容千分位、百分号、万、破折号等写法。"""
    assert clean_number("15,800") == 15800.0
    assert clean_number("12.5%") == 12.5
    assert clean_number("1.2万") == 12000.0
    assert clean_number("-3.4%") == -3.4
    assert clean_number("—") is None
    assert clean_number("N/A") is None
    assert clean_number(None) is None


def test_split_skills_keeps_slash_names():
    """技能拆分不应破坏 CAD/CAM 这类合成技能名。"""
    assert split_skills("Python、数据分析；云计算") == ("Python", "数据分析", "云计算")
    assert split_skills("CAD/CAM|PLC控制") == ("CAD/CAM", "PLC控制")
    assert split_skills("") == ()
    assert split_skills(None) == ()


@pytest.mark.parametrize("disable_bs4", [False, True])
def test_parse_html_table_supports_both_parsers(monkeypatch, disable_bs4):
    """BeautifulSoup 与 stdlib 回退解析器应得到一致的表格内容。"""
    if disable_bs4:
        monkeypatch.setattr(crawler, "BeautifulSoup", None)
    rows = parse_html_table(SAMPLE_HTML)
    assert len(rows) == 3  # 表头 + 2 数据行
    assert rows[0][0] == "城市"
    assert rows[1][0] == "测试城"
    assert "无关表格" not in [cell for row in rows for cell in row]


def test_parse_industry_page_normalizes_and_filters():
    """解析结果字段规范化，且丢弃城市 / 产业缺失的脏数据行。"""
    records = parse_industry_page(SAMPLE_HTML)
    assert len(records) == 1
    record = records[0]
    assert record["city"] == "测试城"
    assert record["share_pct"] == 12.5
    assert record["avg_salary"] == 15800.0
    assert record["growth_pct"] == 7.5
    assert record["skills"] == "Python|数据分析|云计算"


def test_parse_industry_page_requires_headers():
    """表头缺少必需列（城市 / 支柱产业 / 行业大类）时应返回空结果。"""
    html = (
        '<table class="industry-table"><tr><th>城市</th><th>名称</th></tr>'
        "<tr><td>A城</td><td>某产业</td></tr></table>"
    )
    assert parse_industry_page(html) == []
    assert parse_industry_page("<html></html>") == []


def test_build_industry_frame_dedup_and_dtypes():
    """长表应去重、强制数值类型，并剔除关键字段缺失的记录。"""
    frame = build_industry_frame(
        [
            {"city": "A城", "industry": "软件", "category": "信息技术",
             "share_pct": "10.5", "avg_salary": "15000.4", "demand_index": "80",
             "growth_pct": "5", "education": "本科", "skills": "Python"},
            {"city": "A城", "industry": "软件", "category": "信息技术",
             "share_pct": "9.0", "avg_salary": "15000", "demand_index": "70",
             "growth_pct": "4", "education": "本科", "skills": "Java"},
            {"city": "", "industry": "空城产业", "category": "信息技术",
             "share_pct": "1", "avg_salary": "1", "demand_index": "1",
             "growth_pct": "1", "education": "本科", "skills": "Python"},
        ]
    )
    assert len(frame) == 1  # 重复保留首次 + 空城市被剔除
    assert frame.loc[0, "share_pct"] == pytest.approx(10.5)
    assert int(frame.loc[0, "avg_salary"]) == 15000
    assert str(frame["city"].dtype) == "string"


def test_fetcher_local_snapshot(tmp_path):
    """file:// 数据源应能读取本地快照并把来源标记为 snapshot。"""
    path = tmp_path / "page.html"
    path.write_text(SAMPLE_HTML, encoding="utf-8")
    fetcher = Fetcher(FetchPolicy(delay=0.0, use_cache=False))
    text, origin = fetcher.fetch_with_origin(path.resolve().as_uri())
    assert origin == "snapshot"
    assert "industry-table" in text


def test_fetcher_network_disabled_raises():
    """禁用网络且无缓存时应抛出 FetchError。"""
    fetcher = Fetcher(FetchPolicy(allow_network=False, use_cache=False))
    with pytest.raises(FetchError):
        fetcher.fetch_with_origin("https://example.invalid/industry.html")


def test_fetcher_uses_disk_cache(monkeypatch, tmp_path):
    """同一 URL 第二次抓取应命中磁盘缓存（不再发起网络请求）。"""
    policy = FetchPolicy(delay=0.0, cache_dir=tmp_path / "cache")
    calls = {"n": 0}

    def fake_get(url, *, user_agent, timeout):  # noqa: ARG001 - 测试替身
        calls["n"] += 1
        return SAMPLE_HTML

    monkeypatch.setattr(crawler, "http_get", fake_get)
    monkeypatch.setattr(crawler.Fetcher, "_allowed_by_robots", lambda self, url: True)

    fetcher = Fetcher(policy)
    url = "https://example.com/industry.html"
    assert fetcher.fetch_with_origin(url)[1] == "network"
    assert fetcher.fetch_with_origin(url)[1] == "cache"
    assert calls["n"] == 1


def test_crawl_industry_collects_errors(tmp_path):
    """数据源缺失时不应中断流程，而是记入 CrawlReport.errors。"""
    frame, report = crawl_industry(
        [CrawlSource(name="缺失页面", url=(tmp_path / "missing.html").as_uri())],
        policy=FetchPolicy(delay=0.0, use_cache=False),
    )
    assert frame.empty
    assert report.sources_total == 1
    assert report.sources_ok == 0
    assert report.errors


def test_crawl_industry_from_local_snapshot(tmp_path):
    """完整链路（抓取 → 解析 → 清洗）应产出规范长表。"""
    path = tmp_path / "测试区域支柱产业与人才需求统计快报.html"
    path.write_text(SAMPLE_HTML, encoding="utf-8")
    frame, report = crawl_industry(
        [CrawlSource(name="测试区域", url=path.resolve().as_uri())],
        policy=FetchPolicy(delay=0.0, use_cache=False),
    )
    assert report.sources_ok == 1
    assert report.sources_from_snapshot == 1
    assert report.records == len(frame) == 1
    assert list(frame.columns) == [
        "city", "industry", "category", "share_pct",
        "avg_salary", "demand_index", "growth_pct", "education", "skills",
    ]
