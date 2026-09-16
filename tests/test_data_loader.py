"""数据加载模块测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from city_insight.config import DATA_DIR, INDUSTRY_COLS, INDUSTRY_NUMERIC_COLS
from city_insight.data_loader import (
    REQUIRED_FILES,
    compute_derived,
    data_signature,
    industry_health,
    load_and_merge,
    load_industry,
    validate_data,
)


def test_data_signature_has_all_files():
    """数据签名应覆盖全部必需数据文件。"""
    sig = data_signature(DATA_DIR)
    names = {name for name, _, _ in sig}
    assert names == set(REQUIRED_FILES)


def test_load_and_merge_real_data(real_df):
    """真实数据合并后：无重复城市、含全部指标列、无核心缺失。"""
    df = real_df
    assert len(df) > 200, "城市数量应超过 200"
    assert df["city"].is_unique
    assert {"city", "province", "happiness", "income", "house_price",
            "population", "value_index", "composite_score"} <= set(df.columns)
    core_cols = ["happiness", "income", "house_price", "population", "value_index"]
    assert df[core_cols].notna().all().all(), "核心指标不应有缺失值"


def test_value_index_formula(real_df):
    """可负担指数 = 年收入 ÷ 房价。"""
    expected = real_df["income"] / real_df["house_price"]
    assert np.allclose(real_df["value_index"], expected)


def test_composite_score_in_range(real_df):
    """综合宜居评分应归一化到 [0, 100]。"""
    assert real_df["composite_score"].between(0, 100).all()


def test_quality_report_structure(real_df):
    """质量报告应包含形状、重复、缺失与数值摘要等关键信息。"""
    _, quality = load_and_merge(DATA_DIR)
    assert quality["shape"]["rows"] == len(real_df)
    assert "duplicate_cities" in quality
    assert "missing_values" in quality
    assert "numeric_summary" in quality
    assert "source_city_counts" in quality
    assert set(quality["source_city_counts"]) == set(REQUIRED_FILES)


def test_compute_derived_edge_cases():
    """含非法房价（0）时派生指标不崩溃；非退化数据下综合评分应有限。"""
    df = pd.DataFrame(
        {
            "city": ["A", "B", "C"],
            "happiness": [50.0, 50.0, 60.0],
            "income": [100000, 200000, 300000],
            "house_price": [10000, 20000, 0],  # 含非法房价
        }
    )
    out = compute_derived(df)
    assert out["value_index"].isna().tolist() == [False, False, True]
    assert out["composite_score"].notna().all()


def test_validate_data_missing_values():
    """缺失值报告应准确统计；缺少数值列的 DataFrame 也不应崩溃。"""
    df = pd.DataFrame({"city": ["A"], "happiness": [np.nan], "income": [1.0]})
    report = validate_data(df)
    assert report["missing_values"]["happiness"] == 1
    assert report["numeric_summary"]["income"]["count"] == 1
    assert report["numeric_summary"]["income"]["mean"] == 1.0


# ---------------------------------------------------------------------------
# 支柱产业（就业）数据集：可选加载、字段补位与健康检查
# ---------------------------------------------------------------------------
def _write_industry(data_dir, text: str):
    path = data_dir / "industry.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_industry_missing_file_returns_full_schema(tmp_path):
    """文件缺失时返回全列空表（调用方据此降级提示），而非抛异常。"""
    frame = load_industry(tmp_path)
    assert frame.empty
    assert list(frame.columns) == list(INDUSTRY_COLS)


def test_load_industry_normalizes_schema_and_dedupes(tmp_path):
    """缺列补位 + 空值清洗 + (城市, 产业) 去重，保证下游不会因字段缺失崩溃。"""
    _write_industry(
        tmp_path,
        "city,industry,avg_salary\n"
        " A , 软件开发 ,10000\n"     # 首尾空格应被清洗
        "A,软件开发,99999\n"          # 重复「城市 × 产业」保留首条
        "B,,\n"                       # 空产业应剔除
        ",装饰装修,8000\n",           # 空城市应剔除
    )
    frame = load_industry(tmp_path)
    assert list(frame.columns) == list(INDUSTRY_COLS)
    assert frame["city"].tolist() == ["A"]
    assert frame["industry"].tolist() == ["软件开发"]
    assert frame.loc[0, "avg_salary"] == 10000  # 去重保留首条
    for column in INDUSTRY_NUMERIC_COLS:
        assert pd.api.types.is_numeric_dtype(frame[column]), column
    assert not frame.duplicated(subset=["city", "industry"]).any()
    # 补齐的文本列不应残留 NaN
    assert frame["skills"].isna().sum() == 0


def test_industry_health_flags_degraded_fields(tmp_path):
    """健康检查应准确报出缺失 / 空白 / 全空数值字段，供前端解释降级原因。"""
    _write_industry(tmp_path, "city,industry,avg_salary\n甲城,软件开发,10000\n")
    frame = load_industry(tmp_path)
    health = industry_health(frame)
    assert health["rows"] == 1
    assert health["cities"] == 1
    assert health["missing_columns"] == []           # 已在加载阶段补齐
    assert "skills" in health["blank_columns"]        # 文本列全空
    assert "demand_index" in health["empty_numeric_columns"]

    healthy = industry_health(load_industry(DATA_DIR))
    assert healthy["rows"] > 0
    assert healthy["cities"] > 0
    assert healthy["categories"] > 0
    assert healthy["missing_columns"] == []
    assert healthy["blank_columns"] == []
    assert healthy["empty_numeric_columns"] == []
    # 空输入不应抛异常
    assert industry_health(None)["rows"] == 0
    assert industry_health(pd.DataFrame())["rows"] == 0
