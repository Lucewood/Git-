"""支柱产业数据（爬虫产出）与种子口径一致性测试。"""

from __future__ import annotations

import pandas as pd
import pytest

from city_insight.config import (
    DATA_DIR,
    INDUSTRY_COLS,
    INDUSTRY_NUMERIC_COLS,
    INDUSTRY_SNAPSHOT_DIR,
)
from city_insight.crawler import CrawlSource, FetchPolicy, crawl_industry
from city_insight.data_loader import load_industry
from city_insight.industry_kb import CATEGORIES, SKILL_TAGS
from city_insight.industry_seed import (
    CATEGORY_COUNT_RANGE,
    CITY_LEADING_INDUSTRIES,
    PROVINCE_INDUSTRY_POOL,
    REGION_PROVINCES,
    seed_records,
)


@pytest.fixture(scope="module")
def industry_df() -> pd.DataFrame:
    return load_industry(DATA_DIR)


@pytest.fixture(scope="module")
def province_df() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "province.csv")


def test_industry_file_schema(industry_df):
    """data/industry.csv 应存在、列齐全且数值列为数值类型。"""
    assert not industry_df.empty, "请先运行 python scripts/crawl_industry.py"
    for column in INDUSTRY_COLS:
        assert column in industry_df.columns
    for column in INDUSTRY_NUMERIC_COLS:
        assert pd.api.types.is_numeric_dtype(industry_df[column])
    assert industry_df["city"].notna().all()
    assert not industry_df.duplicated(subset=["city", "industry"]).any()


def test_industry_covers_all_cities(industry_df, province_df):
    """支柱产业库应覆盖 province.csv 中的全部城市。"""
    missing = set(province_df["city"]) - set(industry_df["city"])
    assert not missing, f"以下城市缺少支柱产业记录：{sorted(missing)[:10]}"


def test_industry_values_in_valid_range(industry_df):
    """数值字段应落在合理区间，技能字段非空。"""
    assert industry_df["share_pct"].between(0, 100).all()
    assert (industry_df["avg_salary"] > 0).all()
    assert industry_df["demand_index"].between(0, 100).all()
    assert industry_df["growth_pct"].between(-20, 30).all()
    assert (industry_df["skills"].str.len() > 0).all()
    assert industry_df["education"].isin(
        ["高中及以下", "大专及以上", "本科及以上", "硕士及以上", "博士及以上"]
    ).all()
    per_city = industry_df.groupby("city")["share_pct"].sum()
    assert per_city.min() >= 30.0, "支柱产业合计就业占比过低"
    assert per_city.max() <= 80.0, "支柱产业合计就业占比过高"


def test_industry_categories_and_skills_in_kb(industry_df):
    """行业大类与技能标签必须来自知识库定义（保证推荐引擎可解释）。"""
    assert set(industry_df["category"]) <= set(CATEGORIES)
    tags = {
        tag
        for value in industry_df["skills"]
        for tag in str(value).split("|")
        if tag
    }
    assert tags <= set(SKILL_TAGS), f"未收录技能：{sorted(tags - set(SKILL_TAGS))}"


def test_seed_records_are_deterministic(province_df):
    """种子生成必须完全可复现（同输入两次调用结果一致）。"""
    cities = province_df.head(30).assign(income=100000.0)
    first = seed_records(cities)
    second = seed_records(cities)
    assert first == second
    # 每城至少 3 个支柱产业
    assert len(first) >= CATEGORY_COUNT_RANGE[0] * len(cities)
    assert {row["city"] for row in first} == set(cities["city"])


def test_seed_categories_are_known():
    """人工收录的城市主导产业必须是合法行业大类。"""
    for city, categories in CITY_LEADING_INDUSTRIES.items():
        assert categories, f"{city} 未配置主导产业"
        assert set(categories) <= set(CATEGORIES), city


def test_region_and_pool_coverage(province_df):
    """每个省级行政区都应归入某个区域，且配置了产业池。"""
    regions = {province for group in REGION_PROVINCES.values() for province in group}
    provinces = set(province_df["province"])
    assert provinces <= regions, f"未归入区域：{sorted(provinces - regions)}"
    assert provinces <= set(PROVINCE_INDUSTRY_POOL), "存在未配置产业池的省份"
    for pool in PROVINCE_INDUSTRY_POOL.values():
        assert set(pool) <= set(CATEGORIES)


def test_load_industry_missing_file(tmp_path):
    """支柱产业文件缺失时返回空表（含完整列名），不抛异常。"""
    empty = load_industry(tmp_path)
    assert empty.empty
    assert list(empty.columns) == list(INDUSTRY_COLS)


def test_snapshots_reproduce_committed_dataset(industry_df):
    """爬取本地快照应能复现 data/industry.csv（验证管道端到端一致）。"""
    snapshots = sorted(INDUSTRY_SNAPSHOT_DIR.glob("*.html"))
    if not snapshots:
        pytest.skip("未找到离线页面快照，跳过管道复现校验")
    sources = [
        CrawlSource(name=path.stem, url=path.resolve().as_uri())
        for path in snapshots
    ]
    frame, report = crawl_industry(
        sources, policy=FetchPolicy(delay=0.0, use_cache=False, allow_network=False)
    )
    assert report.sources_ok == len(sources)
    assert not report.errors
    assert len(frame) == len(industry_df)
    assert set(frame["city"]) == set(industry_df["city"])
    assert frame["category"].nunique() == industry_df["category"].nunique()