"""核心分析逻辑测试（纯函数）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from city_insight.analysis import (
    aggregate_by_province,
    corr_summary_text,
    describe_series,
    detect_outliers,
    percentile_rank,
    safe_corr,
    top_n,
)


class TestSafeCorr:
    def test_perfect_positive_correlation(self):
        a = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        b = pd.Series([2.0, 4.0, 6.0, 8.0, 10.0])
        assert np.isclose(safe_corr(a, b), 1.0)

    def test_constant_series_returns_nan(self):
        a = pd.Series([3.0, 3.0, 3.0, 3.0])
        b = pd.Series([1.0, 2.0, 3.0, 4.0])
        assert np.isnan(safe_corr(a, b))

    def test_short_series_returns_nan(self):
        a = pd.Series([1.0])
        b = pd.Series([2.0])
        assert np.isnan(safe_corr(a, b))


class TestCorrSummary:
    def test_strong_correlation_message(self):
        text = corr_summary_text(0.85, 0.3, "强相关", "弱相关")
        assert "0.850" in text and "强相关" in text

    def test_nan_returns_friendly_message(self):
        assert "数据量不足" in corr_summary_text(float("nan"), 0.3, "强", "弱")


class TestOutliers:
    def test_detects_high_outlier(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 100.0])
        mask = detect_outliers(s)
        assert mask.tolist() == [False] * 5 + [True]

    def test_detects_low_outlier(self):
        s = pd.Series([-500.0, 10.0, 11.0, 12.0, 13.0])
        mask = detect_outliers(s)
        assert mask.iloc[0] and not mask.iloc[1:].any()

    def test_no_outliers_in_clean_data(self):
        s = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0, 15.0])
        assert not detect_outliers(s).any()


class TestAggregation:
    def test_groupby_means_and_counts(self, sample_df):
        agg = aggregate_by_province(sample_df)
        assert list(agg["省份"]) == ["甲省", "乙省"]  # 按平均幸福度降序
        jia = agg[agg["省份"] == "甲省"].iloc[0]
        assert jia["平均幸福度"] == pytest.approx(85.0)
        assert jia["城市数量"] == 2
        yi = agg[agg["省份"] == "乙省"].iloc[0]
        assert yi["城市数量"] == 3


class TestTopN:
    def test_top_n_sorted_descending(self, sample_df):
        result = top_n(sample_df, "happiness", 3)
        assert len(result) == 3
        assert result["happiness"].tolist() == [90.0, 80.0, 70.0]

    def test_bottom_n(self, sample_df):
        result = top_n(sample_df, "happiness", 2, ascending=True)
        assert result["happiness"].tolist() == [50.0, 60.0]

    def test_n_greater_than_rows(self, sample_df):
        assert len(top_n(sample_df, "happiness", 100)) == len(sample_df)


class TestPercentileAndDescribe:
    def test_percentile_rank_bounds(self, sample_df):
        ranks = percentile_rank(sample_df["happiness"])
        assert ranks.between(0, 1).all()
        assert ranks.max() == 1.0

    def test_describe_series(self):
        stats = describe_series(pd.Series([1.0, 2.0, 3.0, 4.0]))
        assert stats["count"] == 4.0
        assert stats["mean"] == pytest.approx(2.5)
        assert stats["min"] == 1.0 and stats["max"] == 4.0

    def test_describe_empty_series(self):
        stats = describe_series(pd.Series([], dtype=float))
        assert stats["count"] == 0.0
