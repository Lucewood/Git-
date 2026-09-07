"""图表工厂测试：各绘图函数应返回合法 matplotlib Figure 且不抛异常。"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.figure
import pytest

from city_insight import charts

# 与生产环境一致：先初始化绘图风格（含中文字体），再绘图
charts.setup_plot_style()


def _assert_fig(fig: matplotlib.figure.Figure) -> None:
    assert isinstance(fig, matplotlib.figure.Figure)
    assert len(fig.axes) >= 1


def test_scatter_with_regression(sample_df):
    fig = charts.scatter_with_regression(
        sample_df, "income", "happiness",
        color="steelblue", xlabel="x", ylabel="y", title="t",
    )
    _assert_fig(fig)


def test_scatter_single_row_skips_regression():
    import pandas as pd

    tiny = pd.DataFrame({"x": [1.0], "y": [2.0]})
    fig = charts.scatter_with_regression(
        tiny, "x", "y", color="steelblue", xlabel="x", ylabel="y", title="t",
    )
    _assert_fig(fig)


def test_correlation_heatmap(sample_df):
    cols = ("happiness", "income", "value_index")
    fig = charts.correlation_heatmap(sample_df, cols)
    _assert_fig(fig)


def test_barh_ranking(sample_df):
    data = sample_df.sort_values("happiness")
    fig = charts.barh_ranking(
        data, "happiness", color="steelblue", title="t", xlabel="x", fmt="{:.1f}",
    )
    _assert_fig(fig)


def test_affordability_overview(sample_df):
    _assert_fig(charts.affordability_overview(sample_df, color="steelblue"))


def test_distribution_hist(sample_df):
    _assert_fig(
        charts.distribution_hist(sample_df["happiness"], color="steelblue", title="t", xlabel="x")
    )


def test_city_comparison(sample_df):
    fig = charts.city_comparison(
        sample_df, ["A城", "B城"], ("happiness", "income", "population"), color="steelblue",
    )
    _assert_fig(fig)


def test_city_profile_chart(sample_df):
    import pandas as pd

    profile = pd.Series({"happiness": 90.0, "income": 80.0, "population": 70.0})
    _assert_fig(charts.city_profile_chart(profile, color="steelblue"))


def test_outlier_scatter(sample_df):
    import pandas as pd

    mask = pd.Series([False, False, False, False, True])
    _assert_fig(
        charts.outlier_scatter(
            sample_df, "happiness", "income", mask,
            color="steelblue", xlabel="x", ylabel="y", title="t",
        )
    )


def test_house_trend_forecast_chart():
    import pandas as pd

    hist = pd.DataFrame({
        "year": [2005 + i for i in range(5)],
        "house_price": [1000.0 * (1.05 ** i) for i in range(5)],
    })
    fcst = pd.DataFrame({
        "year": [2010, 2011, 2012],
        "point": [1300.0, 1400.0, 1500.0],
        "low": [1250.0, 1300.0, 1350.0],
        "high": [1350.0, 1500.0, 1650.0],
    })
    fig = charts.house_trend_forecast_chart(hist, fcst, hist_color="steelblue", conf=0.8)
    _assert_fig(fig)


def test_house_trend_forecast_chart_empty_forecast():
    import pandas as pd

    hist = pd.DataFrame({"year": [2005, 2006], "house_price": [100.0, 110.0]})
    empty = pd.DataFrame(columns=["year", "point", "low", "high"])
    fig = charts.house_trend_forecast_chart(hist, empty)
    _assert_fig(fig)
