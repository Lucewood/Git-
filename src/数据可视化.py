import pandas as pd

happiness = pd.read_csv("../data/happiness.csv")
income = pd.read_csv("../data/income.csv")
house = pd.read_csv("../data/house_price.csv")
province = pd.read_csv("../data/province.csv")
location = pd.read_csv("../data/location.csv")

happiness.head()

df = (
    happiness
    .merge(income, on="city")
    .merge(house, on="city")
    .merge(province, on="city")
    .merge(location, on="city")
)
#!!!!!!!!!!!!!!!!!!!!
#性价比指标计算和各省市数据平均值的聚合与重命名
#!!!!!!!!!!!!!!!!!!!!
import numpy as np

# 计算性价比指标
df['value_index'] = df['income'] / df['house_price']

# 按省份聚合平均值
province_summary = df.groupby('province', as_index=False).agg({
    'happiness': 'mean',
    'income': 'mean',
    'house_price': 'mean',
    'value_index': 'mean'
})
# 重命名列为平均值
province_summary = province_summary.rename(columns={
    'happiness': 'avg_happiness',
    'income': 'avg_income',
    'house_price': 'avg_house_price',
    'value_index': 'avg_value_index'
})
print("\n省级聚合样例：\n", province_summary.head(5), sep="")

#!!!!!!!!!!!!!!!!!!!!
#住房可负担性指数排名前20的城市的数据显示
#!!!!!!!!!!!!!!!!!!!!
import pandas as pd

# 取 Top20
top20 = (
    df.sort_values("value_index", ascending=False)
      .head(20)
      .reset_index(drop=True)
)

top20

#!!!!!!!!!!!!!!!!!!!!
#全国300个主要城市的住房可负担性指数的柱状图分布分析
#!!!!!!!!!!!!!!!!!!!!
import matplotlib.pyplot as plt
import numpy as np
#按价值指数降序排序
top = df.sort_values("value_index", ascending=False).reset_index(drop=True)
#创建画布
fig, ax = plt.subplots(figsize=(12, 6))
#绘制柱状图
ax.bar(range(len(top)), top["value_index"], color="steelblue")
#每50个城市显示一个排名
step = 50
ticks = np.arange(0, len(top), step)

ax.set_xticks(ticks)
ax.set_xticklabels([str(i + 1) for i in ticks])
#设置标题和坐标轴标签
ax.set_title("City Value Index (Income / House Price)", fontsize=16)
ax.set_xlabel("City Rank", fontsize=12)
ax.set_ylabel("Value Index", fontsize=12)
#添加横向网格线
ax.grid(axis="y", linestyle="--", alpha=0.5)

plt.tight_layout()
plt.show()

#!!!!!!!!!!!!!!!!!!!!
#全国300个主要城市的幸福度的条形图分布分析
#!!!!!!!!!!!!!!!!!!!!
import matplotlib.pyplot as plt
#按幸福度排序
df_sorted = df.sort_values("happiness").reset_index(drop=True)

fig, ax = plt.subplots(figsize=(12, 10))

ax.barh(range(len(df_sorted)), df_sorted["happiness"], color="steelblue")
#每50个城市显示一个刻度
step = 50
ticks = list(range(0, len(df_sorted), step))
ax.set_yticks(ticks)
ax.set_yticklabels([str(i + 1) for i in ticks])

ax.set_xlabel("Happiness Index")
ax.set_ylabel("City Rank")
ax.set_title("City Happiness Ranking")
ax.grid(axis="x", linestyle="--", alpha=0.5)

plt.tight_layout()
plt.show()

#!!!!!!!!!!!!!!!!!!!!
#全国300个主要城市的收入与幸福度之间的散点图分布分析
#!!!!!!!!!!!!!!!!!!!!
import seaborn as sns

sns.scatterplot(data=df, x="income", y="happiness")
plt.title("Income vs Happiness")
plt.show()

#!!!!!!!!!!!!!!!!!!!!
#全国300个主要城市的房价与幸福度之间的散点图分布分析
#!!!!!!!!!!!!!!!!!!!!
sns.scatterplot(data=df, x="house_price", y="happiness")
plt.title("House Price vs Happiness")
plt.show()

#!!!!!!!!!!!!!!!!!!!!
#中国城市生活成本与幸福感分析的可视化宜居度map地图
#!!!!!!!!!!!!!!!!!!!!
from pyecharts.charts import Map
from pyecharts import options as opts

# 按省份计算平均宜居度
prov_data = df.groupby('province')['happiness'].mean().reset_index()
# 生成地图数据项列表
map_data = list(zip(prov_data['province'], prov_data['happiness']))

# 创建 Map 实例并添加数据
m = Map()
m.add("宜居度", map_data, "china")

# 配置全局选项：标题和视觉映射组件（分段）
m.set_global_opts(
    title_opts=opts.TitleOpts(title="中国各省市宜居度地图"),
    visualmap_opts=opts.VisualMapOpts(
        min_=prov_data['happiness'].min(),
        max_=prov_data['happiness'].max(),
        is_piecewise=True,  # 分段式视觉映射
        pieces=[
            {"min": 90, "label": "极高"},
            {"min": 80, "max": 90, "label": "较高"},
            {"min": 70, "max": 80, "label": "中等"},
            {"max": 70, "label": "较低"},
        ]
    ),

    tooltip_opts=opts.TooltipOpts(formatter="省市:{b}<br>宜居度:{c}")
)
# 不显示地图上每个省的标签
m.set_series_opts(label_opts=opts.LabelOpts(is_show=False))
# 渲染HTML文件
m.render("中国各省市宜居度地图.html")

#!!!!!!!!!!!!!!!!!!!!
#Top50的中国各城市住房可负担性指数分布Geo地图
#!!!!!!!!!!!!!!!!!!!!
from pyecharts.charts import Geo
from pyecharts import options as opts
from pyecharts.globals import ChartType

geo = Geo()

# 添加地图
geo.add_schema(
    maptype="china"
)

# Top50城市
top50 = (
    df.sort_values(
        "value_index",
        ascending=False
    )
    .head(50)
)

# 读取城市坐标
for _, row in top50.iterrows():
    geo.add_coordinate(
        row["city"],
        row["longitude"],
        row["latitude"]
    )

# 构造绘图数据
geo_data = []

for _, row in top50.iterrows():
    geo_data.append(
        (
            row["city"],
            float(row["value_index"])
        )
    )

print("气泡数量:", len(geo_data))

# 添加散点
geo.add(
    "城市价值指数",
    geo_data,
    type_=ChartType.EFFECT_SCATTER,
    symbol_size=15
)

# 全局设置
geo.set_global_opts(
    title_opts=opts.TitleOpts(
        title="Top50的中国城市生活价值指数分布"
    ),
    visualmap_opts=opts.VisualMapOpts(
        min_=top50["value_index"].min(),
        max_=top50["value_index"].max(),
        is_piecewise=True,  # 分段式视觉映射
        pieces=[
            {"min": 13, "label": "极高"},
            {"min": 12, "max": 13, "label": "较高"},
            {"min": 11, "max": 12, "label": "中等"},
            {"max": 11, "label": "较低"},
        ]
    )
)

# 标签设置
geo.set_series_opts(
    label_opts=opts.LabelOpts(
        is_show=False
    )
)

geo.render(
    "Top50的中国城市生活价值指数分布.html"
)