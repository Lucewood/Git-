"""就业指导推荐引擎（纯函数，无 UI / 无 Streamlit 依赖）。

推荐模型（可解释的五维加权打分）：
    match_score = 100 × 学历修正系数 × Σ wᵢ·sᵢ / Σ wᵢ
其中五个维度的子得分 sᵢ 均归一到 [0, 1]：
1. **技能匹配 skill**：用户技能对「该产业核心技能」的覆盖率
   （命中数 ÷ 产业核心技能数），是决定「能不能干」的硬门槛；
2. **薪资匹配 salary**：min(该产业平均月薪 ÷ 期望月薪, 1.2) ÷ 1.2，
   达到期望即 0.83，超过期望 20% 得满分；
3. **发展空间 growth**：需求景气指数（0-100）与岗位年增速在该候选集内的
   百分位加权（0.6 / 0.4），刻画「岗位多不多、涨得快不快」；
4. **岗位规模 scale**：该产业就业占比在候选集内的百分位（体量越大越稳）；
5. **生活宜居 life**：城市幸福度 / 可负担指数 / 房价压力的百分位合成，
   （可选）「优先低生活成本」会提高可负担与房价压力的权重。
以上五个维度权重可在前端用滑块调整；未填写技能时自动把技能权重并入其余维度，
避免整体得分被无意义地压低。

学历门槛：产业学历要求高于用户学历时按每档 6% 折减（0.94^gap），
并在结果中显式给出 education_gap 供前端提示「需提升学历」。

健壮性约定：
- 支柱产业表由爬虫 / 外部 CSV 产出，字段可能不完整；本模块对缺失列统一补位，
  以「该维度 0 分」降级参与打分，而不是抛出 KeyError 中断整页；
- 样本不足 / 零方差 / 非法数值均回退中位数或 0 分，保证打分恒可用。

输出全部为普通 DataFrame / 字符串，便于单元测试与前端复用。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from .config import SKILL_SEPARATOR
from .industry_kb import (
    DEFAULT_EDUCATION,
    education_gap,
    occupations_for,
)

logger = logging.getLogger(__name__)

# 偏好权重维度（键 → 中文名，前端滑块与权重说明共用）
WEIGHT_LABELS: dict[str, str] = {
    "skill": "技能匹配",
    "salary": "薪资待遇",
    "growth": "发展空间",
    "scale": "岗位规模",
    "life": "生活宜居",
}
# 默认权重（可在前端调整；引擎内部自动归一化）
DEFAULT_WEIGHTS: dict[str, float] = {
    "skill": 0.30, "salary": 0.25, "growth": 0.20, "scale": 0.10, "life": 0.15,
}
# 薪资维度上限：达到期望薪资的 1.2 倍即满分
SALARY_RATIO_CAP = 1.2
# 需求维度中「景气指数」与「增速百分位」的组合权重
DEMAND_MIX = (0.6, 0.4)
# 学历每差一档的匹配度折减系数
EDUCATION_PENALTY = 0.94
# 城市级聚合中「覆盖行业大类」最多展示的大类数
CATEGORY_MIX_LIMIT = 3

# 结果表标准列（供前端与测试引用，避免拼写漂移）
SCORE_COLUMNS: tuple[str, ...] = (
    "city", "province", "industry", "category",
    "avg_salary", "demand_index", "growth_pct", "share_pct",
    "education", "skills", "education_gap", "matched_skills", "missing_skills",
    "occupations", "skill_score", "salary_score", "demand_score",
    "scale_score", "life_score", "match_score",
)
CITY_COLUMNS: tuple[str, ...] = (
    "city", "province", "best_industry", "best_category", "match_score",
    "matched_industries", "avg_salary", "category_mix",
    "happiness", "house_price", "value_index", "composite_score",
)


@dataclass(frozen=True)
class CareerProfile:
    """求职者画像（前端表单 → 本结构 → 打分）。"""

    skills: tuple[str, ...] = ()
    education: str = DEFAULT_EDUCATION
    target_salary: float = 10000.0
    categories: tuple[str, ...] = ()          # 期望行业大类（空 = 不限）
    weights: Mapping[str, float] = field(
        default_factory=lambda: dict(DEFAULT_WEIGHTS)
    )
    prefer_low_cost: bool = False             # 是否更看重低生活成本
    top_n: int = 10

    @property
    def skill_set(self) -> frozenset[str]:
        return frozenset(parse_skills(self.skills))

    @property
    def normalized_weights(self) -> dict[str, float]:
        """归一化偏好权重；未填写技能时把技能权重并入其余维度。

        非法 / 全零 / 缺键均回退默认权重，保证打分恒可用。
        """
        values: dict[str, float] = {}
        for key in WEIGHT_LABELS:
            try:
                values[key] = max(0.0, float(self.weights.get(key, 0.0)))
            except (TypeError, ValueError):
                values[key] = 0.0
        if not self.skill_set:
            values["skill"] = 0.0  # 无技能输入时技能维度不参与打分
        total = sum(values.values())
        if total <= 0:
            values = {key: 0.0 if key == "skill" else value
                      for key, value in DEFAULT_WEIGHTS.items()}
            total = sum(values.values())
        return {key: value / total for key, value in values.items()}


def profile_key(profile: CareerProfile) -> tuple[Any, ...]:
    """把求职画像压缩为可哈希键（供 Streamlit 缓存等场景使用）。

    说明：仅保留参与打分的字段；技能与行业大类均排序后入键——两者顺序都不影响
    打分结果，归一化后「同一组选项、不同勾选顺序」可命中同一份缓存。
    """
    weights = tuple(
        (key, _safe_float(profile.weights.get(key, 0.0))) for key in WEIGHT_LABELS
    )
    return (
        tuple(sorted(parse_skills(profile.skills))),
        str(profile.education),
        _safe_float(profile.target_salary),
        tuple(sorted(str(item) for item in profile.categories)),
        weights,
        bool(profile.prefer_low_cost),
        int(profile.top_n),
    )


def profile_from_key(key: tuple[Any, ...]) -> CareerProfile:
    """profile_key() 的逆操作：由缓存键还原求职画像。"""
    skills, education, target_salary, categories, weights, prefer_low_cost, top_n = key
    return CareerProfile(
        skills=tuple(skills),
        education=str(education),
        target_salary=float(target_salary),
        categories=tuple(categories),
        weights=dict(weights),
        prefer_low_cost=bool(prefer_low_cost),
        top_n=int(top_n),
    )


# ---------------------------------------------------------------------------
# 基础工具（纯函数）
# ---------------------------------------------------------------------------
def _safe_float(value: Any, default: float = 0.0) -> float:
    """把任意输入安全转成 float；非法 / 缺失值回退 default。"""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return number if np.isfinite(number) else default


def parse_skills(value: Any) -> tuple[str, ...]:
    """把技能字段（"A|B"、列表、NaN 等）统一解析为去重后的技能元组。"""
    if value is None:
        return ()
    if isinstance(value, float) and pd.isna(value):
        return ()
    if isinstance(value, str):
        parts: Iterable[Any] = value.split(SKILL_SEPARATOR)
    elif isinstance(value, (list, tuple, set, frozenset)):
        parts = value
    else:
        parts = [value]

    seen: dict[str, None] = {}
    for part in parts:
        token = str(part).strip()
        if token:
            seen.setdefault(token, None)
    return tuple(seen)


def _percentile(series: pd.Series, *, ascending: bool = True) -> pd.Series:
    """百分位排名（0-1）；样本不足或零方差时返回 0.5 常量序列。"""
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() < 2 or numeric.nunique(dropna=True) < 2:
        return pd.Series(0.5, index=series.index, dtype=float)
    return numeric.rank(pct=True, ascending=ascending).fillna(0.5).astype(float)


def _column_or_nan(frame: pd.DataFrame, column: str) -> pd.Series:
    """取列；列缺失时返回与 frame 同索引的 NaN 序列（避免索引错位）。"""
    if column in frame.columns:
        return pd.to_numeric(frame[column], errors="coerce")
    return pd.Series(np.nan, index=frame.index, dtype=float)


def _column_or_text(frame: pd.DataFrame, column: str, default: str = "") -> pd.Series:
    """取文本列；列缺失或为空值时统一回退 default（避免 KeyError / nan 外溢）。"""
    if column in frame.columns:
        series = frame[column]
    else:
        series = pd.Series(default, index=frame.index, dtype=object)
    return series.fillna(default).astype(str)


def _skill_hit_ratio(required: tuple[str, ...], owned: frozenset[str]) -> float:
    """技能覆盖率快速路径：required 已解析为技能元组，owned 已归一化为集合。"""
    if not required:
        return 0.0
    return sum(1 for token in required if token in owned) / len(required)


def skill_match_score(user_skills: Iterable[str], industry_skills: Iterable[str]) -> float:
    """技能覆盖率：用户技能命中「产业核心技能」的比例（0-1）。"""
    return _skill_hit_ratio(parse_skills(industry_skills), frozenset(parse_skills(user_skills)))


def salary_score(avg_salary: float | None, target_salary: float | None) -> float:
    """薪资满足度（0-1）：达到期望得 0.83，超过期望 20% 得满分。"""
    try:
        salary = float(avg_salary)  # type: ignore[arg-type]
        target = float(target_salary)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if not np.isfinite(salary) or not np.isfinite(target) or salary <= 0:
        return 0.0
    if target <= 0:
        target = 1.0
    return float(min(salary / target, SALARY_RATIO_CAP) / SALARY_RATIO_CAP)


def salary_score_series(salaries: pd.Series, target_salary: float | None) -> pd.Series:
    """salary_score() 的向量化实现（逐元素口径完全一致，供批量打分使用）。"""
    values = pd.to_numeric(salaries, errors="coerce").to_numpy(dtype=float)
    try:
        target = float(target_salary)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        target = 0.0
    if not np.isfinite(target) or target <= 0:
        target = 1.0
    if values.size == 0:
        return pd.Series([], index=salaries.index, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.clip(values / target, None, SALARY_RATIO_CAP) / SALARY_RATIO_CAP
    valid = np.isfinite(values) & (values > 0)
    scores = np.where(valid, ratio, 0.0)
    return pd.Series(np.clip(scores, 0.0, 1.0), index=salaries.index, dtype=float)


def demand_score(
    demand_index: float | None,
    growth_percentile: float | None,
    *,
    mix: tuple[float, float] = DEMAND_MIX,
) -> float:
    """发展空间得分（0-1）：景气指数与岗位增速百分位的加权合成。"""
    try:
        demand = float(demand_index)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        demand = 50.0
    if not np.isfinite(demand):
        demand = 50.0
    demand_norm = min(max(demand, 0.0), 100.0) / 100.0

    try:
        growth = float(growth_percentile)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        growth = 0.5
    if not np.isfinite(growth):
        growth = 0.5
    growth_norm = min(max(growth, 0.0), 1.0)

    w_demand, w_growth = mix
    return float(w_demand * demand_norm + w_growth * growth_norm)


def demand_score_series(
    demand_index: pd.Series,
    growth_percentile: pd.Series,
    *,
    mix: tuple[float, float] = DEMAND_MIX,
) -> pd.Series:
    """demand_score() 的向量化实现（口径一致，供批量打分使用）。"""
    demand = pd.to_numeric(demand_index, errors="coerce").astype(float)
    demand = demand.where(np.isfinite(demand), 50.0).fillna(50.0)
    demand_norm = demand.clip(lower=0.0, upper=100.0) / 100.0

    growth = pd.to_numeric(growth_percentile, errors="coerce").astype(float)
    growth = growth.where(np.isfinite(growth), 0.5).fillna(0.5)
    growth_norm = growth.clip(lower=0.0, upper=1.0)

    w_demand, w_growth = mix
    return (w_demand * demand_norm + w_growth * growth_norm).clip(0.0, 1.0).astype(float)


def city_life_score(
    city_rows: pd.DataFrame, *, prefer_low_cost: bool = False
) -> pd.Series:
    """城市生活宜居得分（0-1）：幸福度 / 可负担指数 / 房价压力的百分位合成。

    Args:
        city_rows: 候选集（城市 × 产业明细）DataFrame，需含城市指标列。
        prefer_low_cost: 为 True 时提高可负担指数与低房价的权重。
    """
    happiness = _percentile(_column_or_nan(city_rows, "happiness"))
    value = _percentile(_column_or_nan(city_rows, "value_index"))
    price_pressure = 1.0 - _percentile(_column_or_nan(city_rows, "house_price"))
    if prefer_low_cost:
        score = 0.25 * happiness + 0.45 * value + 0.30 * price_pressure
    else:
        score = 0.40 * happiness + 0.40 * value + 0.20 * price_pressure
    return score.clip(0.0, 1.0).astype(float)


# ---------------------------------------------------------------------------
# 主流程：打分 → 排序 → 聚合 → 建议
# ---------------------------------------------------------------------------
# 需要从城市主数据带入的指标列（缺失时自动跳过，不影响打分）
CITY_METRIC_COLS: tuple[str, ...] = (
    "province", "happiness", "income", "house_price",
    "population", "value_index", "composite_score",
)


def _empty_scores() -> pd.DataFrame:
    return pd.DataFrame(columns=list(SCORE_COLUMNS))


def _empty_cities() -> pd.DataFrame:
    return pd.DataFrame(columns=list(CITY_COLUMNS))


def score_industries(
    profile: CareerProfile,
    industry_df: pd.DataFrame | None,
    city_df: pd.DataFrame | None,
) -> pd.DataFrame:
    """对「城市 × 支柱产业」逐条打分，返回按匹配度降序的推荐明细表。

    Args:
        profile: 求职者画像。
        industry_df: 支柱产业长表（data/industry.csv 加载结果）。
        city_df: 城市主数据（含 city / province / 幸福度 / 房价等指标）。

    Returns:
        明细表（列为 SCORE_COLUMNS）；输入为空时返回空表而不抛异常。
        支柱产业表字段缺失时按「该维度 0 分」降级，不会因缺列抛 KeyError。
    """
    if industry_df is None or industry_df.empty:
        logger.info("支柱产业数据为空，无法生成就业推荐。")
        return _empty_scores()
    if "city" not in industry_df.columns:
        logger.warning("支柱产业数据缺少 city 列，无法生成就业推荐。")
        return _empty_scores()
    if city_df is None or city_df.empty or "city" not in city_df.columns:
        logger.info("城市主数据为空，无法生成就业推荐。")
        return _empty_scores()

    metric_cols = [c for c in CITY_METRIC_COLS if c in city_df.columns]
    data = industry_df.merge(
        city_df[["city", *metric_cols]].drop_duplicates(subset=["city"]),
        on="city",
        how="inner",
    )
    if data.empty:
        logger.info("筛选后无候选产业，未生成推荐。")
        return _empty_scores()
    data = data.reset_index(drop=True)

    # 字段补位：缺失列以空值 / NaN 兜底，保证外部数据不完整时仍可降级打分
    missing = [
        column for column in (CITY_METRIC_COLS + ("industry", "category", "skills"))
        if column not in data.columns
    ]
    if missing:
        logger.warning("支柱产业数据缺少字段 %s，相关维度将按 0 分参与打分。", sorted(missing))
    data["industry"] = _column_or_text(data, "industry")
    data["category"] = _column_or_text(data, "category")
    data["skills"] = _column_or_text(data, "skills")
    data["education"] = _column_or_text(data, "education")
    data["province"] = _column_or_text(data, "province", "—")
    for column in ("avg_salary", "demand_index", "growth_pct", "share_pct"):
        data[column] = _column_or_nan(data, column)

    if profile.categories:
        data = data[data["category"].isin(list(profile.categories))]
        if data.empty:
            logger.info("筛选后无候选产业，未生成推荐。")
            return _empty_scores()
        data = data.reset_index(drop=True)

    # ---- 维度一：技能匹配（覆盖率；技能列只解析一次，命中数复用）----
    user_skills = profile.skill_set
    industry_skills = data["skills"].map(parse_skills)
    data["matched_skills"] = industry_skills.map(
        lambda skills: SKILL_SEPARATOR.join(s for s in skills if s in user_skills)
    )
    data["missing_skills"] = industry_skills.map(
        lambda skills: SKILL_SEPARATOR.join(s for s in skills if s not in user_skills)
    )
    data["skill_score"] = [
        _skill_hit_ratio(skills, user_skills) for skills in industry_skills
    ]

    # ---- 维度二：薪资满足度（向量化，与 salary_score() 同口径）----
    data["salary_score"] = salary_score_series(
        data["avg_salary"], profile.target_salary
    )

    # ---- 维度三：发展空间（景气指数 + 增速百分位，向量化同口径）----
    growth_rank = _percentile(data["growth_pct"])
    data["demand_score"] = demand_score_series(data["demand_index"], growth_rank)

    # ---- 维度四：岗位规模与生活宜居 ----
    data["scale_score"] = _percentile(data["share_pct"])
    data["life_score"] = city_life_score(
        data, prefer_low_cost=profile.prefer_low_cost
    )

    # ---- 学历门槛修正 ----
    data["education_gap"] = [
        education_gap(required, profile.education) for required in data["education"]
    ]

    weights = profile.normalized_weights
    weighted = (
        weights["skill"] * data["skill_score"]
        + weights["salary"] * data["salary_score"]
        + weights["growth"] * data["demand_score"]
        + weights["scale"] * data["scale_score"]
        + weights["life"] * data["life_score"]
    )
    penalty = np.power(EDUCATION_PENALTY, data["education_gap"].clip(lower=0))
    data["match_score"] = (weighted * penalty * 100.0).clip(0.0, 100.0).round(1)
    data["occupations"] = data["category"].map(
        lambda category: "、".join(occupations_for(category))
    )

    # 子得分转换为 0-100 便于前端展示（加权计算已在上面完成）
    for col in ("skill_score", "salary_score", "demand_score", "scale_score", "life_score"):
        data[col] = (data[col].astype(float) * 100.0).round(1)

    data = data.sort_values(
        ["match_score", "avg_salary"], ascending=[False, False]
    ).reset_index(drop=True)
    # reindex 而非按列索引：即使上游缺列也只会产生 NaN，不会抛 KeyError
    return data.reindex(columns=list(SCORE_COLUMNS))


def rank_cities(
    scored: pd.DataFrame | None,
    *,
    top_n: int = 10,
    city_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """把明细推荐聚合为城市级推荐（每城取匹配度最高的产业为代表）。

    Args:
        scored: score_industries() 的明细结果。
        top_n: 返回的城市数量。
        city_df: 可选的城市主数据；提供时会补充幸福度 / 房价 / 可负担指数等
            城市指标列（明细结果只保留评分相关列，不含这些指标）。

    Returns:
        城市级表（列为 CITY_COLUMNS），按代表产业匹配度降序，取前 top_n 个城市。
    """
    if scored is None or scored.empty:
        return _empty_cities()

    # 文本列归一化：空值以空串参与分组，避免聚合时 float 触发 join 异常
    ordered = scored.sort_values("match_score", ascending=False).copy()
    for column in ("city", "industry", "category"):
        if column in ordered.columns:
            ordered[column] = ordered[column].fillna("").astype(str)

    # 每城取匹配度最高的产业为代表（keep="first" 即最优行，语义比 groupby.first 的
    # 「首个非空值」更明确，且无需执行全列聚合）
    best = ordered.drop_duplicates(subset=["city"], keep="first")

    # 命中产业数：按行数统计（即便 industry 为空也计入候选数）
    counts = ordered.groupby("city")["industry"].size().rename("matched_industries")

    # 覆盖行业大类：按匹配度顺序去重后取前 CATEGORY_MIX_LIMIT 个（向量化，避免逐组 apply）
    categories = ordered.drop_duplicates(subset=["city", "category"])
    categories = categories.assign(
        _category_rank=categories.groupby("city").cumcount()
    )
    mix = (
        categories[categories["_category_rank"] < CATEGORY_MIX_LIMIT]
        .groupby("city")["category"]
        .agg("、".join)
        .rename("category_mix")
    )

    stats = pd.concat([counts, mix], axis=1).reset_index()
    merged = best.merge(stats, on="city", how="left")
    if city_df is not None and not city_df.empty and "city" in city_df.columns:
        # 仅补充尚未存在的指标列（如 province 已随明细带入，避免 merge 产生 _x/_y 后缀）
        metric_cols = [
            c for c in CITY_METRIC_COLS
            if c in city_df.columns and c not in merged.columns
        ]
        if metric_cols:
            merged = merged.merge(
                city_df[["city", *metric_cols]].drop_duplicates(subset=["city"]),
                on="city",
                how="left",
            )
    merged = merged.rename(
        columns={"industry": "best_industry", "category": "best_category"}
    )
    # 用 reindex 一次性补齐缺失列（缺列补 NaN，不会抛 KeyError）
    return (
        merged.reindex(columns=list(CITY_COLUMNS))
        .sort_values("match_score", ascending=False)
        .head(max(1, int(top_n)))
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# 技能需求图谱与差距分析
# ---------------------------------------------------------------------------
CATEGORY_TABLE_COLUMNS: tuple[str, ...] = (
    "category", "city_count", "industry_count",
    "avg_salary", "avg_demand", "avg_share", "avg_match",
)


def category_summary(scored: pd.DataFrame | None) -> pd.DataFrame:
    """行业大类维度聚合：候选范围内的薪资 / 景气 / 就业占比 / 城市覆盖。

    Returns:
        表（列为 CATEGORY_TABLE_COLUMNS），按平均月薪降序。
    """
    if scored is None or scored.empty:
        return pd.DataFrame(columns=list(CATEGORY_TABLE_COLUMNS))

    grouped = scored.groupby("category")
    table = pd.DataFrame(
        {
            "city_count": grouped["city"].nunique(),
            "industry_count": grouped["industry"].count(),
            "avg_salary": grouped["avg_salary"].mean().round().astype("Int64"),
            "avg_demand": grouped["demand_index"].mean().round(1),
            "avg_share": grouped["share_pct"].mean().round(1),
            "avg_match": grouped["match_score"].mean().round(1),
        }
    ).reset_index()
    return table.sort_values("avg_salary", ascending=False).reset_index(drop=True)[
        list(CATEGORY_TABLE_COLUMNS)
    ]


SKILL_TABLE_COLUMNS: tuple[str, ...] = (
    "skill", "industry_count", "city_count", "avg_demand",
    "avg_salary", "demand_heat", "sample_categories",
)


def top_skills(
    industry_df: pd.DataFrame | None, *, top_n: int = 15
) -> pd.DataFrame:
    """市场技能需求榜：出现产业数 × 平均景气指数的热度排序。

    Returns:
        表（列为 SKILL_TABLE_COLUMNS），按需求热度降序取前 top_n 个技能。
    """
    if industry_df is None or industry_df.empty:
        return pd.DataFrame(columns=list(SKILL_TABLE_COLUMNS))

    exploded = industry_df.assign(
        skill=industry_df["skills"].map(parse_skills)
    ).explode("skill")
    exploded = exploded[
        exploded["skill"].notna() & (exploded["skill"].astype(str).str.len() > 0)
    ]
    if exploded.empty:
        return pd.DataFrame(columns=list(SKILL_TABLE_COLUMNS))

    grouped = exploded.groupby("skill")
    table = pd.DataFrame(
        {
            "industry_count": grouped["industry"].count(),
            "city_count": grouped["city"].nunique(),
            "avg_demand": grouped["demand_index"].mean().round(1),
            "avg_salary": grouped["avg_salary"].mean().round().astype("Int64"),
            "sample_categories": grouped["category"].apply(
                lambda series: "、".join(list(dict.fromkeys(series.astype(str)))[:2])
            ),
        }
    ).reset_index()
    table["demand_heat"] = (
        table["industry_count"] * table["avg_demand"] / 100.0
    ).round(1)
    return (
        table.sort_values(["demand_heat", "industry_count"], ascending=False)
        .head(max(1, int(top_n)))
        .reset_index(drop=True)[list(SKILL_TABLE_COLUMNS)]
    )


def skill_gap_analysis(
    profile: CareerProfile,
    industry_df: pd.DataFrame | None,
    *,
    top_n: int = 12,
) -> dict[str, pd.DataFrame]:
    """技能供需缺口分析：区分「已具备的高需求技能」与「建议补强的技能」。

    Returns:
        {"matched": ...已命中技能表, "gaps": ...缺口技能表}，两表列同 top_skills()。
    """
    table = top_skills(industry_df, top_n=max(top_n * 3, top_n))
    if table.empty:
        return {
            "matched": pd.DataFrame(columns=list(SKILL_TABLE_COLUMNS)),
            "gaps": pd.DataFrame(columns=list(SKILL_TABLE_COLUMNS)),
        }
    owned = profile.skill_set
    is_owned = table["skill"].isin(owned)
    matched = table[is_owned].head(top_n).reset_index(drop=True)
    gaps = table[~is_owned].head(top_n).reset_index(drop=True)
    return {"matched": matched, "gaps": gaps}


# ---------------------------------------------------------------------------
# 建议文本（纯文本 + 前端用 HTML 摘要）
# ---------------------------------------------------------------------------
def _fmt_salary(value: Any) -> str:
    """月薪格式化；非法值返回「—」。"""
    try:
        salary = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"
    if not np.isfinite(salary):
        return "—"
    return f"¥{salary:,.0f}/月"


def _fmt_metric(value: Any, fmt: str = "{:.1f}") -> str:
    """通用指标格式化；NaN / 缺失值统一显示为「—」，避免出现 nan 字样。"""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"
    if not np.isfinite(number):
        return "—"
    return fmt.format(number)


def build_advice(profile: CareerProfile, row: Mapping[str, Any]) -> str:
    """针对单条推荐生成一句「行动建议」（纯文本，前端可自行加样式）。"""
    city = str(row.get("city", ""))
    industry = str(row.get("industry", ""))
    category = str(row.get("category", ""))
    matched = parse_skills(row.get("matched_skills"))
    missing = parse_skills(row.get("missing_skills"))
    occupations = str(row.get("occupations", "") or "").strip()
    try:
        gap = int(float(row.get("education_gap", 0) or 0))
    except (TypeError, ValueError):
        gap = 0
    try:
        score = float(row.get("match_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        score = 0.0

    parts = [
        f"{city}的{industry}（{category}）匹配度 {_fmt_metric(score)} 分，"
        f"平均月薪约 {_fmt_salary(row.get('avg_salary'))}。"
    ]
    if occupations:
        parts.append(f"可投递的典型岗位方向：{occupations}；")
    if matched:
        parts.append(f"你的 {'、'.join(matched)} 与该产业核心技能吻合；")
    if missing:
        parts.append(f"建议补强 {'、'.join(missing)}。")
    if gap > 0:
        parts.append(
            f"该岗位学历门槛为 {row.get('education')}，"
            f"比你当前学历（{profile.education}）高 {gap} 档，"
            "建议同步提升学历，或优先考虑门槛更低的产业方向。"
        )
    elif gap < 0:
        parts.append("你的学历高于该产业门槛，求职时具备一定竞争优势。")
    else:
        parts.append("学历与岗位门槛匹配。")
    if not profile.skill_set:
        parts.append("（提示：填写技能标签可显著提升推荐精度。）")
    return "".join(parts)


def build_summary(
    profile: CareerProfile,
    scored: pd.DataFrame | None,
    city_rank: pd.DataFrame | None,
) -> str:
    """生成推荐结果的整体摘要（HTML，供 widgets.insight_box 使用）。"""
    if scored is None or scored.empty:
        return (
            "<strong>🧭 暂无推荐结果：</strong>"
            "请在下方补充技能标签，或放宽行业 / 筛选条件后重试。"
        )

    top = scored.iloc[0]
    best_city = city_rank.iloc[0] if city_rank is not None and not city_rank.empty else None
    skill_hit = _safe_float(top.get("skill_score", 0.0))
    weight_text = " / ".join(
        f"{WEIGHT_LABELS[key]} {value:.0%}"
        for key, value in profile.normalized_weights.items()
    )
    lines = [
        f"<strong>🧑🎓 求职画像：</strong>{profile.education} · "
        f"期望月薪 {profile.target_salary:,.0f} 元 · 技能 {len(profile.skill_set)} 项 · "
        f"偏好权重 {weight_text}。<br>",
        f"<strong>🎯 首选推荐：</strong>{top['city']} · {top['industry']}"
        f"（{top['category']}），匹配度 <strong>{_fmt_metric(top['match_score'])}</strong> 分，"
        f"平均月薪约 {_fmt_salary(top['avg_salary'])}，"
        f"人才需求景气指数 {_fmt_metric(top['demand_index'], '{:.0f}')}、"
        f"岗位年增速 {_fmt_metric(top['growth_pct'], '{:+.1f}%')}。<br>",
        f"<strong>🧩 技能命中率：</strong>{_fmt_metric(skill_hit, '{:.0f}')}%（"
        + (
            f"已命中 {'、'.join(parse_skills(top['matched_skills']))}；"
            if parse_skills(top["matched_skills"])
            else "暂未命中该产业核心技能；"
        )
        + "）。<br>",
    ]
    if best_city is not None:
        lines.append(
            f"<strong>🏙️ 综合最优城市：</strong>{best_city['city']}"
            f"（{best_city.get('province', '-')}），代表产业 {best_city['best_industry']}，"
            f"匹配度 {_fmt_metric(best_city['match_score'])} 分，"
            f"可负担指数 {_fmt_metric(best_city.get('value_index'), '{:.2f}')}、"
            f"幸福度 {_fmt_metric(best_city.get('happiness'))}。<br>"
        )
    gaps = parse_skills(top.get("missing_skills"))
    if gaps:
        lines.append(
            f"<strong>📚 建议补强：</strong>{'、'.join(gaps)}。"
            "（可在「技能需求图谱」查看全市场热度更高、薪资更优的技能。）"
        )
    else:
        lines.append(
            "<strong>✅ 技能储备充分：</strong>推荐产业的核心技能你已全部覆盖，可重点关注城市与薪资匹配度。"
        )
    return "".join(lines)
