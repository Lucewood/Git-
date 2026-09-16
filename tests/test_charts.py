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


def _stack_colors(fig, per_dim: int) -> list[str]:
    """按「每维度一组条形」的顺序取出堆叠条形的填充色（hex 字符串）。"""
    from matplotlib.colors import to_hex

    patches = fig.axes[0].patches
    assert per_dim > 0 and len(patches) % per_dim == 0
    return [
        to_hex(patches[index * per_dim].get_facecolor())
        for index in range(len(patches) // per_dim)
    ]


def test_career_score_breakdown_dimension_colors_are_distinct():
    """匹配度构成图的各维度应各用一种颜色（不得所有分段同为兜底灰）。"""
    from matplotlib.colors import to_hex

    data = _career_frame()
    columns = ("w_skill_score", "w_salary_score", "w_demand_score",
               "w_scale_score", "w_life_score")
    labels = ("技能匹配", "薪资待遇", "发展空间", "岗位规模", "生活宜居")
    fig = charts.career_score_breakdown(
        data, columns=columns, labels=labels, label_col="industry"
    )

    colors = _stack_colors(fig, len(data))
    assert len(colors) == len(columns)
    assert len(set(colors)) == len(columns), f"各维度颜色应互不相同，实际为 {colors}"
    assert "#999999" not in colors, "维度颜色不应退化为兜底灰色"

    # w_ 前缀 / _score 后缀 / demand 别名均应命中内置维度配色
    expected = [
        to_hex(charts.CAREER_DIM_COLORS[key])
        for key in ("skill", "salary", "growth", "scale", "life")
    ]
    assert colors == expected
    legend_labels = [text.get_text() for text in fig.axes[0].get_legend().get_texts()]
    assert legend_labels == list(labels)


def test_career_score_breakdown_color_map_override_and_fallback():
    """color_map 支持列名 / 中文图例名 / 维度关键词，未命中维度自动取兜底色且不撞色。"""
    data = _career_frame()
    data["w_custom_score"] = [3.0, 2.0, 1.0]
    fig = charts.career_score_breakdown(
        data,
        columns=("w_skill_score", "w_demand_score", "w_custom_score"),
        labels=("技能匹配", "发展空间", "自定义维度"),
        label_col="industry",
        color_map={"w_skill_score": "#123456", "发展空间": "#abcdef", "scale": "#654321"},
    )

    colors = _stack_colors(fig, len(data))
    assert colors[0] == "#123456", "列名精确命中时应使用覆盖色"
    assert colors[1] == "#abcdef", "中文图例名命中时应使用覆盖色"
    assert colors[2] not in {"#123456", "#abcdef"}
    assert len(set(colors)) == len(colors), f"兜底配色不得与其它维度撞色：{colors}"


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
