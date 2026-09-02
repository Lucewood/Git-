"""数据加载模块测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from city_insight.config import DATA_DIR
from city_insight.data_loader import (
    REQUIRED_FILES,
    compute_derived,
    data_signature,
    load_and_merge,
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
