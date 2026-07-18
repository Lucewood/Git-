import pandas as pd

happiness = pd.read_csv("../data/happiness.csv")
income = pd.read_csv("../data/income.csv")
house = pd.read_csv("../data/house_price.csv")
province = pd.read_csv("../data/province.csv")
location = pd.read_csv("../data/location.csv")

happiness.head()

#数据重复性检查及处理
df = (
    happiness
    .merge(income, on="city")
    .merge(house, on="city")
    .merge(province, on="city")
    .merge(location, on="city")
)

duplicates = df["city"].duplicated().sum()

print(f"Duplicate cities: {duplicates}")

for name, data in {
    "happiness": happiness,
    "income": income,
    "house": house,
    "province": province,
    "longitude": location,
    "latitude": location
}.items():

    before = len(data)
    data.drop_duplicates("city", inplace=True)
    after = len(data)

    print(
        f"{name}: 删除 {before-after} 条重复数据，剩余 {after} 条"
    )

df.head()

#数据缺失值检查及处理
df.isnull().sum()

print("Missing Values:")
print(df.isnull().sum())

df.dropna(inplace=True)

print("After Dropping Missing Values:")
print(df.isnull().sum())

df = (
    happiness
    .merge(income, on="city")
    .merge(house, on="city")
    .merge(province, on="city")
    .merge(location, on="city")
)

df.head()