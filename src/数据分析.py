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

#查看数据规模
print(f"数据集大小：{df.shape[0]} 行 × {df.shape[1]} 列")

#显示数据类型
df.info()

#数据描述统计
df.describe().round(2)