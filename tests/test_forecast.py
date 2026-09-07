"""房价预测模块测试（历史加载 / 特征工程 / 模型训练 / 递归预测）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from city_insight import forecast
from city_insight.config import DATA_DIR, DATA_REF_YEAR


@pytest.fixture(scope="module")
def pipeline(real_df) -> dict:
    """用真实数据构建一次完整流水线（模块内复用，避免重复训练）。"""
    history = forecast.load_house_history(DATA_DIR)
    return forecast.build_pipeline(history, real_df)


def test_load_house_history_anchored():
    """历史序列应为 248 城 × 2005–2024，且 2024 年与房价快照完全一致。"""
    hist = forecast.load_house_history(DATA_DIR)
    assert {"city", "year", "house_price"} <= set(hist.columns)
    assert hist["city"].nunique() == 248
    assert hist["year"].min() == 2005 and hist["year"].max() == DATA_REF_YEAR
    assert not hist.duplicated(subset=["city", "year"]).any()
    snapshot = pd.read_csv(DATA_DIR / "house_price.csv")
    merged = hist[hist["year"] == DATA_REF_YEAR][["city", "house_price"]].merge(
        snapshot, on="city", suffixes=("_h", "_s")
    )
    assert (merged["house_price_h"] == merged["house_price_s"]).all()


def test_prepare_panel_columns_and_no_nan(pipeline):
    """面板应包含全部特征列与目标，且无缺失值。"""
    panel = pipeline["panel"]
    for col in (*forecast.FEATURE_COLS, forecast.TARGET_COL):
        assert col in panel.columns, f"面板缺少列 {col}"
    assert panel[list(forecast.FEATURE_COLS) + [forecast.TARGET_COL]].notna().all().all()
    assert panel["year"].min() >= 2010  # 预留 5 年滞后特征
    assert len(panel) > 2000


def test_metrics_are_finite(pipeline):
    """模型工件应包含可读指标与排序后的特征重要性。"""
    artifacts = pipeline["artifacts"]
    metrics = artifacts["metrics"]
    for key in ("rmse", "mae", "r2", "hit_rate"):
        assert np.isfinite(metrics[key]), f"{key} 不应为 NaN"
    assert metrics["test_years"][0] > metrics["train_years"][1]
    imp = artifacts["importance"]
    assert set(imp["feature"]) == set(forecast.FEATURE_COLS)
    assert imp["importance"].is_monotonic_decreasing


def test_forecast_city_is_deterministic_and_bounded(pipeline):
    """预测应确定、逐年单调向后扩展，且低<点<高。"""
    a = forecast.forecast_city(pipeline, "北京", horizon=5)
    b = forecast.forecast_city(pipeline, "北京", horizon=5)
    assert a["forecast"].equals(b["forecast"])
    assert len(a["forecast"]) == 5
    assert int(a["forecast"]["year"].iloc[0]) == DATA_REF_YEAR + 1
    assert int(a["forecast"]["year"].iloc[-1]) == DATA_REF_YEAR + 5
    assert (a["forecast"]["low"] < a["forecast"]["point"]).all()
    assert (a["forecast"]["point"] < a["forecast"]["high"]).all()
    assert a["forecast"]["point"].gt(0).all()
    assert a["last_price"] == pytest.approx(pd.read_csv(DATA_DIR / "house_price.csv")
                                            .set_index("city").loc["北京", "house_price"])


def test_forecast_unknown_city_raises(pipeline):
    with pytest.raises(ValueError):
        forecast.forecast_city(pipeline, "不存在的城市xyz")


def test_city_history_stats_fields(pipeline):
    stats = forecast.city_history_stats(pipeline["history"], "成都")
    assert stats["ref_year"] == DATA_REF_YEAR
    assert stats["start_year"] == 2005
    assert stats["ref_price"] > 0 and stats["start_price"] > 0
    assert stats["cagr_total"] is not None and stats["cagr_5y"] is not None


def test_build_narrative_mentions_city_and_model(pipeline):
    fc = forecast.forecast_city(pipeline, "上海", horizon=3)
    stats = forecast.city_history_stats(pipeline["history"], "上海")
    text = forecast.build_narrative(
        "上海", fc["province"], stats, fc, pipeline["artifacts"]
    )
    assert "上海" in text
    assert "RMSE" in text or "R²" in text


def test_train_growth_model_numpy_fallback(monkeypatch, pipeline):
    """scikit-learn 缺失时应自动回退到 numpy 岭回归且预测仍可用。"""
    monkeypatch.setattr(forecast, "HAVE_SKLEARN", False)
    monkeypatch.setattr(forecast, "_GBR", None)
    artifacts = forecast.train_growth_model(pipeline["panel"], seed=7)
    assert artifacts["backend"] == "numpy"
    assert artifacts["model"] is None
    assert artifacts["ridge"] is not None
    m = artifacts["metrics"]
    assert np.isfinite(m["rmse"]) and np.isfinite(m["r2"])

    numpy_pipeline = dict(pipeline)
    numpy_pipeline["artifacts"] = artifacts
    fc = forecast.forecast_city(numpy_pipeline, "成都", horizon=3)
    assert len(fc["forecast"]) == 3
    assert (fc["forecast"]["low"] < fc["forecast"]["point"]).all()
