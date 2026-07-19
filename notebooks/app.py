# ======================================================
# 中国城市生活成本与幸福感分析 Dashboard
# Streamlit Final Version
# ======================================================


import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit.components.v1 as components
import os



# ======================================================
# 页面配置
# ======================================================

st.set_page_config(

    page_title="中国城市幸福感分析平台",

    page_icon="🏙️",

    layout="wide"

)



# ======================================================
# CSS美化
# ======================================================


st.markdown(
"""
<style>


.main-title{

font-size:42px;
font-weight:800;
color:#163a5f;

}


.sub-title{

font-size:22px;
font-weight:600;

}


.card{

padding:20px;

border-radius:15px;

background:#f8f9fa;

box-shadow:
0px 4px 12px rgba(0,0,0,0.08);

}


</style>

""",
unsafe_allow_html=True
)




# ======================================================
# 数据读取
# ======================================================


@st.cache_data
def load_data():


    base="./data"


    happiness=pd.read_csv(
        os.path.join(
            base,
            "happiness.csv"
        )
    )


    income=pd.read_csv(
        os.path.join(
            base,
            "income.csv"
        )
    )


    house=pd.read_csv(
        os.path.join(
            base,
            "house_price.csv"
        )
    )


    province=pd.read_csv(
        os.path.join(
            base,
            "province.csv"
        )
    )


    location=pd.read_csv(
        os.path.join(
            base,
            "location.csv"
        )
    )



    # -------------------------
    # 字段清洗
    # -------------------------


    for df in [
        happiness,
        income,
        house
    ]:

        df["city"] = (
            df["city"]
            .astype(str)
            .str.strip()
        )



    # -------------------------
    # 数据合并
    # -------------------------


    data = (

        happiness

        .merge(
            income,
            on="city",
            how="inner"
        )

        .merge(
            house,
            on="city",
            how="inner"
        )

    )



    # 添加省份

    if "province" in province.columns:


        data=data.merge(

            province,

            on="city",

            how="left"

        )


    else:

        data["province"]="未知"



    # -------------------------
    # 指标计算
    # -------------------------


    data["value_index"]=(

        data["income"]

        /

        data["house_price"]

    )


    data["income_house_ratio"]=(

        data["house_price"]

        /

        data["income"]

    )


    return data



# 加载

df=load_data()



# ======================================================
# 标题
# ======================================================


st.markdown(

"""
<div class="main-title">

🏙️ 中国城市生活成本与幸福感分析平台

</div>

""",

unsafe_allow_html=True

)



st.write(

"""

基于城市幸福感、居民收入以及房价数据，

分析中国城市居民幸福水平、

住房压力以及生活性价比。

"""

)





# ======================================================
# 侧边栏
# ======================================================


st.sidebar.header(
"🔎 数据筛选"
)


province_list=sorted(

df["province"]

.dropna()

.unique()

)



selected_province=st.sidebar.multiselect(

"选择省份",

province_list,

default=province_list

)



filtered=df[

df["province"]

.isin(selected_province)

]



# ======================================================
# KPI
# ======================================================


st.subheader(
"📌 城市核心指标"
)



c1,c2,c3,c4=st.columns(4)



c1.metric(

"城市数量",

len(filtered)

)



c2.metric(

"平均幸福感",

round(

filtered["happiness"]

.mean(),

2

)

)



c3.metric(

"平均收入",

round(

filtered["income"]

.mean(),

0

)

)



c4.metric(

"平均性价比",

round(

filtered["value_index"]

.mean(),

3

)

)



# ======================================================
# 数据展示
# ======================================================


st.subheader(
"📋 城市综合数据"
)


show=filtered.sort_values(

"happiness",

ascending=False

)



st.dataframe(

show,

use_container_width=True

)





# ======================================================
# 幸福感排名
# ======================================================


st.subheader(

"🏆 城市幸福感排名"

)



rank=filtered.sort_values(

"happiness",

ascending=False

)



fig1=px.bar(

rank,

x="city",

y="happiness",

color="happiness",

text="happiness"

)


fig1.update_layout(

template="plotly_white",

xaxis_tickangle=-45

)



st.plotly_chart(

fig1,

use_container_width=True

)





# ======================================================
# 收入幸福感
# ======================================================


st.subheader(

"💰 收入与幸福感关系"

)



fig2=px.scatter(

filtered,

x="income",

y="happiness",

size="value_index",

color="province",

hover_name="city"

)



fig2.update_layout(

template="plotly_white"

)



st.plotly_chart(

fig2,

use_container_width=True

)




# ======================================================
# 房价压力
# ======================================================


st.subheader(

"🏠 房价压力分析"

)



fig3=px.scatter(

filtered,

x="house_price",

y="happiness",

size="income",

color="province",

hover_name="city"

)



st.plotly_chart(

fig3,

use_container_width=True

)





# ======================================================
# 性价比TOP
# ======================================================


st.subheader(

"⭐ 高幸福高性价比城市"

)



top=df.sort_values(

"value_index",

ascending=False

).head(10)



fig4=px.bar(

top,

x="city",

y="value_index",

color="value_index"

)


st.plotly_chart(

fig4,

use_container_width=True

)





# ======================================================
# 相关性
# ======================================================


st.subheader(

"📊 指标相关性"

)



corr=filtered[

[
"happiness",
"income",
"house_price",
"value_index"
]

].corr()



fig5=px.imshow(

corr,

text_auto=True

)



st.plotly_chart(

fig5,

use_container_width=True

)






# ======================================================
# 地图
# ======================================================


st.subheader(

"🗺️ 中国城市幸福感地图"

)



map_file="happiness_map.html"



if os.path.exists(map_file):


    with open(

        map_file,

        encoding="utf-8"

    ) as f:


        html=f.read()



    components.html(

        html,

        height=650

    )


else:


    st.info(

    "未找到 happiness_map.html"

    )






# ======================================================
# 下载
# ======================================================


st.subheader(

"⬇️ 数据导出"

)



csv=filtered.to_csv(

index=False,

encoding="utf-8-sig"

)



st.download_button(

"下载分析结果",

csv,

"city_happiness.csv",

"text/csv"

)



st.success(

"Dashboard运行完成 🚀"

)