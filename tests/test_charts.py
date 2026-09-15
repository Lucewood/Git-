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


# ---------------------------------------------------------------------------
# 就业指导与支柱产业
# ---------------------------------------------------------------------------
def _career_frame():
    """构造就业推荐结果骨架（列名与 career.SCORE_COLUMNS 保持一致）。"""
    import pandas as pd

    return pd.DataFrame(
        {
            "city": ["甲城", "乙城", "丙城"],
            "industry": ["软件开发", "新能源汽车", "农产品加工"],
            "category": ["信息技术", "汽车与新能源", "农业食品"],
            "avg_salary": [18000.0, 12000.0, 6000.0],
            "demand_index": [85.0, 78.0, 45.0],
            "share_pct": [20.0, 15.0, 25.0],
            "w_skill_score": [20.0, 8.0, 0.0],
            "w_salary_score": [18.0, 12.0, 4.0],
            "w_demand_score": [15.0, 13.0, 6.0],
            "w_scale_score": [8.0, 6.0, 9.0],
            "w_life_score": [12.0, 10.0, 11.0],
        }
    )


def test_career_score_breakdown():
    """匹配度构成堆叠条形图应正常渲染。"""
    data = _career_frame()
    fig = charts.career_score_breakdown(
        data,
        columns=("w_skill_score", "w_salary_score", "w_demand_score",
                 "w_scale_score", "w_life_score"),
        labels=("技能匹配", "薪资待遇", "发展空间", "岗位规模", "生活宜居"),
        label_col="industry",
    )
    _assert_fig(fig)


def test_career_score_breakdown_empty():
    import pandas as pd

    empty = pd.DataFrame(columns=["industry", "w_skill_score"])
    fig = charts.career_score_breakdown(
        empty, columns=("w_skill_score",), labels=("技能匹配",), label_col="industry"
    )
    _assert_fig(fig)


def test_salary_demand_scatter_with_highlight():
    """薪资 × 需求散点图应支持推荐命中高亮，并在空数据时降级。"""
    import pandas as pd

    data = _career_frame()
    data["推荐命中"] = ["推荐", "", "推荐"]
    _assert_fig(
        charts.salary_demand_scatter(data, color="steelblue", highlight_col="推荐命中")
    )
    empty = pd.DataFrame(columns=["avg_salary", "demand_index"])
    _assert_fig(charts.salary_demand_scatter(empty, color="steelblue"))


def test_skill_demand_chart_with_ownership_flag():
    """技能需求热度图应支持「已具备 / 建议补强」双色标注。"""
    import pandas as pd

    data = pd.DataFrame(
        {
            "skill": ["Python", "CAD/CAM", "数据分析"],
            "demand_heat": [66.2, 30.0, 12.5],
            "owned": [True, False, True],
        }
    )
    _assert_fig(charts.skill_demand_chart(data, color="steelblue"))
    _assert_fig(charts.skill_demand_chart(pd.DataFrame(), color="steelblue"))
