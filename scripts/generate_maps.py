"""
重新生成 notebooks/ 下的两幅 pyecharts 地理地图（HTML 静态文件）。

- 中国各省市宜居度地图.html          —— 省级平均幸福度 Choropleth
- Top50的中国城市生活价值指数分布.html —— 可负担指数 Top50 城市气泡 Geo

运行方式（在项目根目录）：
    python scripts/generate_maps.py

依赖：pyecharts（见 requirements-dev.txt）。地图 JS 由浏览器运行时从 CDN 加载。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from city_insight.config import DATA_DIR, NOTEBOOKS_DIR
from city_insight.data_loader import load_and_merge

from pyecharts import options as opts
from pyecharts.charts import Geo, Map
from pyecharts.globals import ChartType


def render_province_happiness_map(df) -> None:
    """省级平均幸福度地图。"""
    prov_data = df.groupby("province")["happiness"].mean().reset_index()
    map_data = list(zip(prov_data["province"], prov_data["happiness"]))

    chart = Map()
    chart.add("宜居度", map_data, "china")
    chart.set_global_opts(
        title_opts=opts.TitleOpts(title="中国各省市宜居度地图"),
        visualmap_opts=opts.VisualMapOpts(
            min_=float(prov_data["happiness"].min()),
            max_=float(prov_data["happiness"].max()),
            is_piecewise=True,
            pieces=[
                {"min": 90, "label": "极高"},
                {"min": 80, "max": 90, "label": "较高"},
                {"min": 70, "max": 80, "label": "中等"},
                {"max": 70, "label": "较低"},
            ],
        ),
        tooltip_opts=opts.TooltipOpts(formatter="省市:{b}<br>宜居度:{c}"),
    )
    chart.set_series_opts(label_opts=opts.LabelOpts(is_show=False))
    chart.render(str(NOTEBOOKS_DIR / "中国各省市宜居度地图.html"))
    print("已生成: 中国各省市宜居度地图.html")


def render_top50_value_map(df) -> None:
    """可负担指数 Top50 城市气泡地图。"""
    top50 = df.sort_values("value_index", ascending=False).head(50)

    geo = Geo()
    geo.add_schema(maptype="china")
    for _, row in top50.iterrows():
        geo.add_coordinate(row["city"], float(row["longitude"]), float(row["latitude"]))

    geo_data = [
        (row["city"], float(row["value_index"])) for _, row in top50.iterrows()
    ]
    geo.add(
        "城市价值指数", geo_data,
        type_=ChartType.EFFECT_SCATTER,
        symbol_size=15,
    )
    geo.set_global_opts(
        title_opts=opts.TitleOpts(title="Top50的中国城市生活价值指数分布"),
        visualmap_opts=opts.VisualMapOpts(
            min_=float(top50["value_index"].min()),
            max_=float(top50["value_index"].max()),
            is_piecewise=True,
            pieces=[
                {"min": 13, "label": "极高"},
                {"min": 12, "max": 13, "label": "较高"},
                {"min": 11, "max": 12, "label": "中等"},
                {"max": 11, "label": "较低"},
            ],
        ),
    )
    geo.set_series_opts(label_opts=opts.LabelOpts(is_show=False))
    geo.render(str(NOTEBOOKS_DIR / "Top50的中国城市生活价值指数分布.html"))
    print("已生成: Top50的中国城市生活价值指数分布.html")


def main() -> None:
    df, _ = load_and_merge(DATA_DIR)
    print(f"加载 {len(df)} 个城市，开始生成地图……")
    render_province_happiness_map(df)
    render_top50_value_map(df)
    print("全部地图生成完成。")


if __name__ == "__main__":
    main()
