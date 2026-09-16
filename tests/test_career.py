"""就业推荐引擎测试（打分、聚合、技能缺口与建议文本）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from city_insight import career
from city_insight.career import (
    CareerProfile,
    build_advice,
    build_summary,
    category_summary,
    demand_score,
    parse_skills,
    rank_cities,
    salary_score,
    score_industries,
    skill_gap_analysis,
    skill_match_score,
    top_skills,
)


@pytest.fixture(scope="module")
def industry_df() -> pd.DataFrame:
    """合成支柱产业长表：覆盖技能命中 / 未命中与学历门槛差异。"""
    return pd.DataFrame(
        {
            "city": ["甲城", "甲城", "乙城", "乙城", "丙城"],
            "industry": ["软件开发与信息服务", "新能源汽车整车制造",
                         "软件开发与信息服务", "会计审计与咨询", "农产品加工"],
            "category": ["信息技术", "汽车与新能源", "信息技术", "金融商务", "农业食品"],
            "share_pct": [20.0, 15.0, 12.0, 10.0, 25.0],
            "avg_salary": [18000, 12000, 14000, 11000, 6000],
            "demand_index": [85.0, 80.0, 70.0, 55.0, 45.0],
            "growth_pct": [6.0, 7.5, 4.0, 1.0, -1.0],
            "education": [
                "本科及以上", "本科及以上", "本科及以上", "本科及以上", "大专及以上",
            ],
            "skills": [
                "Python|数据分析|机器学习|云计算",
                "三电系统|电池技术|嵌入式开发|CAN总线",
                "Python|Java|数据分析|系统架构",
                "财务分析|风险控制|会计实务|数据建模",
                "食品工艺|质量检测|食品安全法规|品牌营销",
            ],
        }
    )


@pytest.fixture(scope="module")
def city_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "city": ["甲城", "乙城", "丙城"],
            "province": ["甲省", "乙省", "丙省"],
            "happiness": [90.0, 70.0, 60.0],
            "income": [200000, 120000, 60000],
            "house_price": [40000, 15000, 8000],
            "population": [1500.0, 800.0, 300.0],
            "value_index": [5.0, 8.0, 7.5],
            "composite_score": [85.0, 65.0, 55.0],
        }
    )


def test_parse_skills_variants():
    """技能字段解析应兼容分隔符字符串、序列与 NaN。"""
    assert parse_skills("Python|数据分析") == ("Python", "数据分析")
    assert parse_skills(["Python", "Python", " Java "]) == ("Python", "Java")
    assert parse_skills(float("nan")) == ()
    assert parse_skills(None) == ()


def test_skill_and_salary_scores():
    """技能覆盖率与薪资满足度应落在 [0, 1] 且符合口径。"""
    assert skill_match_score(
        ["Python", "数据分析"], "Python|数据分析|机器学习|云计算"
    ) == 0.5
    assert skill_match_score(["Python"], "") == 0.0
    assert salary_score(12000, 12000) == pytest.approx(1 / career.SALARY_RATIO_CAP)
    assert salary_score(24000, 12000) == pytest.approx(1.0)  # 超期望 20% 封顶
    assert salary_score(0, 12000) == 0.0
    assert salary_score(None, 12000) == 0.0


def test_demand_score_bounds():
    """发展空间得分应在 [0, 1] 内，异常输入回退中位。"""
    assert demand_score(100, 1.0) == pytest.approx(1.0)
    assert demand_score(0, 0.0) == pytest.approx(0.0)
    assert 0.0 <= demand_score(None, None) <= 1.0


def test_score_industries_columns_and_order(industry_df, city_df):
    """打分结果应包含全部标准列、匹配度降序且落在 [0, 100]。"""
    profile = CareerProfile(
        skills=("Python", "数据分析"), education="本科", target_salary=12000
    )
    scored = score_industries(profile, industry_df, city_df)
    assert list(scored.columns) == list(career.SCORE_COLUMNS)
    assert scored["match_score"].between(0, 100).all()
    assert scored["match_score"].is_monotonic_decreasing
    assert scored.loc[0, "skill_score"] == 50.0  # 命中 2 项 / 核心技能 4 项
    assert set(scored.loc[0, "matched_skills"].split("|")) == {"Python", "数据分析"}


def test_score_industries_respects_filters_and_empty_input(industry_df, city_df):
    """行业大类过滤生效；空输入返回空表而不抛异常。"""
    profile = CareerProfile(skills=("Python",), categories=("农业食品",))
    scored = score_industries(profile, industry_df, city_df)
    assert set(scored["category"]) == {"农业食品"}

    empty = score_industries(CareerProfile(), pd.DataFrame(), city_df)
    assert empty.empty
    assert list(empty.columns) == list(career.SCORE_COLUMNS)
    assert score_industries(CareerProfile(), industry_df, pd.DataFrame()).empty


def test_education_threshold_penalty(industry_df, city_df):
    """学历低于门槛时匹配度应被折减，且 education_gap 为正值。"""
    base = {"skills": ("Python", "数据分析"), "target_salary": 12000}
    bachelor = score_industries(
        CareerProfile(education="本科", **base), industry_df, city_df
    )
    high_school = score_industries(
        CareerProfile(education="高中及以下", **base), industry_df, city_df
    )
    assert high_school["education_gap"].max() >= 1
    assert high_school["match_score"].max() < bachelor["match_score"].max()


def test_weights_normalization_without_skills():
    """未填写技能时技能权重应被置零，其余维度权重归一化。"""
    profile = CareerProfile(
        weights={"skill": 5, "salary": 5, "growth": 0, "scale": 0, "life": 0}
    )
    weights = profile.normalized_weights
    assert weights["skill"] == 0.0
    assert weights["salary"] == pytest.approx(1.0)
    assert sum(weights.values()) == pytest.approx(1.0)
    assert sum(CareerProfile(weights={}).normalized_weights.values()) == pytest.approx(1.0)


def test_rank_cities_aggregates_per_city(industry_df, city_df):
    """城市级推荐应每城一行、按匹配度降序，并携带代表产业与覆盖行业。"""
    scored = score_industries(
        CareerProfile(skills=("Python", "数据分析"), target_salary=12000),
        industry_df, city_df,
    )
    ranked = rank_cities(scored, top_n=3, city_df=city_df)
    assert list(ranked.columns) == list(career.CITY_COLUMNS)
    assert ranked["city"].is_unique
    assert ranked["match_score"].is_monotonic_decreasing
    assert ranked["matched_industries"].min() >= 1
    assert "、" in ranked.loc[0, "category_mix"]
    # 提供 city_df 时应补齐城市指标（幸福度 / 可负担指数），而非 NaN
    assert ranked["happiness"].notna().all()
    assert ranked["value_index"].notna().all()
    assert ranked["province"].notna().all()  # 省份不应因 merge 变成 NaN
    # 不提供 city_df 时列仍齐全（城市指标为缺失）
    assert rank_cities(scored, top_n=2)["happiness"].isna().all()


def test_top_skills_and_gap_analysis(industry_df):
    """技能需求榜按热度降序；缺口分析正确区分已具备与建议补强。"""
    table = top_skills(industry_df, top_n=10)
    assert list(table.columns) == list(career.SKILL_TABLE_COLUMNS)
    assert table["demand_heat"].is_monotonic_decreasing
    assert table["industry_count"].max() >= 1

    gap = skill_gap_analysis(
        CareerProfile(skills=("Python", "数据分析")), industry_df, top_n=5
    )
    assert set(gap["matched"]["skill"]) <= {"Python", "数据分析"}
    assert "Python" not in set(gap["gaps"]["skill"])
    assert not gap["matched"].empty and not gap["gaps"].empty


def test_category_summary(industry_df, city_df):
    """行业大类聚合应给出城市覆盖数与平均薪资（按薪资降序）。"""
    scored = score_industries(
        CareerProfile(skills=("Python",), target_salary=10000), industry_df, city_df
    )
    summary = category_summary(scored)
    assert list(summary.columns) == list(career.CATEGORY_TABLE_COLUMNS)
    assert summary["avg_salary"].is_monotonic_decreasing
    assert summary["city_count"].min() >= 1
    assert category_summary(pd.DataFrame()).empty


def test_advice_and_summary_text(industry_df, city_df):
    """建议文本与摘要应包含关键信息且不抛异常。"""
    profile = CareerProfile(
        skills=("Python", "数据分析"), education="大专", target_salary=12000
    )
    scored = score_industries(profile, industry_df, city_df)
    advice = build_advice(profile, scored.iloc[0])
    assert scored.iloc[0]["city"] in advice
    assert "匹配度" in advice
    assert "学历" in advice
    # 典型岗位方向应来自 industry_kb 的岗位口径
    assert "典型岗位方向" in advice
    assert "软件开发工程师" in advice

    summary = build_summary(profile, scored, rank_cities(scored, top_n=3))
    assert "首选推荐" in summary
    assert "技能命中率" in summary
    assert build_summary(profile, pd.DataFrame(), pd.DataFrame()).startswith(
        "<strong>🧭 暂无推荐结果"
    )


# ---------------------------------------------------------------------------
# 健壮性 / 缓存键 / 向量化实现等价性（回归）
# ---------------------------------------------------------------------------
def test_score_industries_tolerates_missing_columns(industry_df, city_df):
    """支柱产业表缺列时应降级打分而非抛 KeyError（爬虫产出可能字段不全）。"""
    profile = CareerProfile(skills=("Python",), education="本科", target_salary=12000)
    for column in career.SCORE_COLUMNS:
        if column in ("city",):
            continue  # city 为连接键，缺失时返回空表
        subset = industry_df.drop(columns=[column], errors="ignore")
        scored = score_industries(profile, subset, city_df)
        assert list(scored.columns) == list(career.SCORE_COLUMNS), column
        assert scored["match_score"].between(0, 100).all(), column

    # 城市主数据缺 province 时不应崩溃，且列仍完整
    without_province = score_industries(profile, industry_df, city_df.drop(columns=["province"]))
    assert list(without_province.columns) == list(career.SCORE_COLUMNS)

    # 缺 city 列（无法连接）应返回空表
    assert score_industries(profile, industry_df.drop(columns=["city"]), city_df).empty


def test_vectorized_scores_match_scalar_reference():
    """向量化薪资 / 发展空间得分应与标量参考实现逐元素一致。"""
    salaries = pd.Series([0.0, 6000.0, 12000.0, 20000.0, 99999.0, np.nan])
    series = career.salary_score_series(salaries, 12000)
    expected = [salary_score(v, 12000) for v in salaries]
    assert np.allclose(series.to_numpy(), expected)

    demand = pd.Series([85.0, 0.0, 120.0, np.nan, -10.0])
    growth = pd.Series([0.9, 0.1, 0.5, np.nan, 1.4])
    got = career.demand_score_series(demand, growth)
    expected_demand = [
        demand_score(d, g) for d, g in zip(demand, growth.fillna(0.5))
    ]
    assert np.allclose(got.to_numpy(), expected_demand)


def test_profile_key_is_hashable_and_order_insensitive():
    """画像缓存键应可哈希、与行业大类勾选顺序无关，且能还原出等价画像。"""
    profile = CareerProfile(
        skills=("数据分析", "Python", "Python"),
        education="本科",
        target_salary=12000.0,
        categories=("信息技术", "金融商务"),
        weights={"skill": 3, "salary": 2.5, "growth": 2, "scale": 1, "life": 1.5},
        prefer_low_cost=True,
        top_n=12,
    )
    key = career.profile_key(profile)
    assert hash(key)  # 可哈希（可作缓存键）

    shuffled = CareerProfile(
        skills=("Python", "数据分析"),
        education="本科",
        target_salary=12000.0,
        categories=("金融商务", "信息技术"),
        weights=dict(profile.weights),
        prefer_low_cost=True,
        top_n=12,
    )
    assert career.profile_key(shuffled) == key

    restored = career.profile_from_key(key)
    assert restored.skill_set == profile.skill_set
    assert restored.normalized_weights == profile.normalized_weights
    assert restored.education == profile.education
    assert restored.top_n == profile.top_n
    assert restored.prefer_low_cost is True


def test_rank_cities_keeps_best_row_per_city(industry_df, city_df):
    """城市级聚合：每城一行、代表产业取匹配度最高者、命中数按候选行数统计。"""
    scored = score_industries(
        CareerProfile(skills=("Python", "数据分析"), target_salary=12000),
        industry_df, city_df,
    )
    ranked = rank_cities(scored, top_n=10, city_df=city_df)
    assert ranked["city"].is_unique
    best = scored.sort_values("match_score", ascending=False).drop_duplicates("city")
    for _idx, row in ranked.iterrows():
        candidate = best[best["city"] == row["city"]].iloc[0]
        assert row["best_industry"] == candidate["industry"]
        assert row["match_score"] == candidate["match_score"]
        assert row["matched_industries"] == int((scored["city"] == row["city"]).sum())
        assert len(str(row["category_mix"]).split("、")) <= career.CATEGORY_MIX_LIMIT


def test_rank_cities_handles_blank_category(industry_df, city_df):
    """行业大类为空（缺列 / 空值）时聚合不应抛异常。"""
    scored = score_industries(
        CareerProfile(skills=("Python",)), industry_df.drop(columns=["category"]), city_df
    )
    ranked = rank_cities(scored, top_n=5, city_df=city_df)
    assert list(ranked.columns) == list(career.CITY_COLUMNS)
    assert ranked["category_mix"].eq("").all()
