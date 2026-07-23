"""
中国城市生活成本与幸福感分析可视化 - Streamlit 交互式网页应用
"""
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib
from io import BytesIO
from pathlib import Path

# 获取数据目录的绝对路径（相对于当前脚本文件）
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# ============ 页面配置 ============
st.set_page_config(
    page_title="中国城市生活成本与幸福感分析",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============ 中文字体设置 ============
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

# ============ 自定义CSS样式 ============
st.markdown("""
<style>
    .main-header {
        font-size: 2.8rem;
        font-weight: 700;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 1rem 0;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 16px;
        padding: 1.5rem;
        color: white;
        text-align: center;
        box-shadow: 0 8px 32px rgba(102, 126, 234, 0.25);
    }
    .metric-card h3 {
        font-size: 1rem;
        opacity: 0.9;
        margin-bottom: 0.5rem;
    }
    .metric-card h1 {
        font-size: 2.2rem;
        font-weight: 700;
    }
    .section-title {
        font-size: 1.6rem;
        font-weight: 600;
        color: #1a1a2e;
        border-left: 5px solid #667eea;
        padding-left: 1rem;
        margin: 2rem 0 1rem 0;
    }
    .insight-box {
        background: #f8f9ff;
        border-radius: 12px;
        padding: 1.2rem;
        border: 1px solid #e0e5ff;
        margin: 1rem 0;
    }
    .footer {
        text-align: center;
        padding: 2rem;
        color: #999;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

# ============ 数据加载（带缓存） ============
@st.cache_data
def load_data():
    """加载并合并所有数据源"""
    happiness = pd.read_csv(DATA_DIR / "happiness.csv")
    income = pd.read_csv(DATA_DIR / "income.csv")
    house = pd.read_csv(DATA_DIR / "house_price.csv")
    province = pd.read_csv(DATA_DIR / "province.csv")
    location = pd.read_csv(DATA_DIR / "location.csv")

    # 去重
    for data in [happiness, income, house, province, location]:
        data.drop_duplicates("city", inplace=True)

    # 以 province 为基准进行左连接，确保保留所有有省份归属的城市
    df = (province
          .merge(happiness, on="city", how="left")
          .merge(income, on="city", how="left")
          .merge(house, on="city", how="left")
          .merge(location, on="city", how="left"))

    # 计算住房可负担性指数
    df['value_index'] = df['income'] / df['house_price']
    # 仅剔除缺失关键指标（幸福度、收入、房价）的行，location 可缺失
    df.dropna(subset=['happiness', 'income', 'house_price'], inplace=True)

    return df, province


df, province_df = load_data()

# ============ 侧边栏 ============
with st.sidebar:
    st.image("https://img.icons8.com/color/96/city-buildings.png", width=72)
    st.markdown("## 🔍 分析控制面板")

    # 省份筛选
    all_provinces = sorted(df['province'].unique())
    selected_provinces = st.multiselect(
        "选择省份（可多选，留空=全部）",
        options=all_provinces,
        default=[]
    )

    # 数值范围筛选
    st.markdown("---")
    st.markdown("### 📊 数值筛选")

    happiness_range = st.slider(
        "幸福度范围",
        min_value=float(df['happiness'].min()),
        max_value=float(df['happiness'].max()),
        value=(float(df['happiness'].min()), float(df['happiness'].max())),
        step=0.5
    )

    income_range = st.slider(
        "年收入范围（元）",
        min_value=int(df['income'].min()),
        max_value=int(df['income'].max()),
        value=(int(df['income'].quantile(0.05)), int(df['income'].quantile(0.95))),
        step=1000
    )

    house_range = st.slider(
        "房价范围（元/㎡）",
        min_value=int(df['house_price'].min()),
        max_value=int(df['house_price'].max()),
        value=(int(df['house_price'].quantile(0.05)), int(df['house_price'].quantile(0.95))),
        step=500
    )

    # 图表类型选择
    st.markdown("---")
    st.markdown("### 🎨 可视化设置")
    chart_theme = st.selectbox("图表配色主题", ["默认蓝", "暖橙", "森林绿", "深紫"])
    color_maps = {
        "默认蓝": "steelblue",
        "暖橙": "#ff7f50",
        "森林绿": "#2e8b57",
        "深紫": "#8b5cf6"
    }
    main_color = color_maps[chart_theme]

# ============ 数据筛选 ============
filtered_df = df.copy()
if selected_provinces:
    filtered_df = filtered_df[filtered_df['province'].isin(selected_provinces)]

filtered_df = filtered_df[
    (filtered_df['happiness'] >= happiness_range[0]) &
    (filtered_df['happiness'] <= happiness_range[1]) &
    (filtered_df['income'] >= income_range[0]) &
    (filtered_df['income'] <= income_range[1]) &
    (filtered_df['house_price'] >= house_range[0]) &
    (filtered_df['house_price'] <= house_range[1])
]

# ============ 页面主体 ============
st.markdown('<h1 class="main-header">🏙️ 中国城市生活成本与幸福感分析</h1>', unsafe_allow_html=True)
st.markdown(
    '<p style="text-align:center; color:#666; font-size:1.1rem; margin-bottom:1rem;">'
    '基于全国300+城市的收入、房价与幸福度数据，深度探索城市宜居价值</p>',
    unsafe_allow_html=True
)

# ============ 顶部指标卡片 ============
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.markdown(f"""
    <div class="metric-card">
        <h3>📋 城市总数</h3>
        <h1>{len(filtered_df)}</h1>
    </div>
    """, unsafe_allow_html=True)

with col2:
    avg_happiness = filtered_df['happiness'].mean()
    st.markdown(f"""
    <div class="metric-card">
        <h3>😊 平均幸福度</h3>
        <h1>{avg_happiness:.1f}</h1>
    </div>
    """, unsafe_allow_html=True)

with col3:
    avg_income = filtered_df['income'].mean()
    st.markdown(f"""
    <div class="metric-card">
        <h3>💰 平均年收入</h3>
        <h1>¥{avg_income/10000:.1f}万</h1>
    </div>
    """, unsafe_allow_html=True)

with col4:
    avg_house = filtered_df['house_price'].mean()
    st.markdown(f"""
    <div class="metric-card">
        <h3>🏠 平均房价</h3>
        <h1>¥{avg_house:.0f}</h1>
    </div>
    """, unsafe_allow_html=True)

with col5:
    avg_value = filtered_df['value_index'].mean()
    st.markdown(f"""
    <div class="metric-card">
        <h3>📈 平均可负担指数</h3>
        <h1>{avg_value:.2f}</h1>
    </div>
    """, unsafe_allow_html=True)

# ============ 第一行：两个散点图 ============
st.markdown('<h2 class="section-title">📈 核心指标关联分析</h2>', unsafe_allow_html=True)

col_left, col_right = st.columns(2)

with col_left:
    st.markdown("### 收入 vs 幸福度")
    fig, ax = plt.subplots(figsize=(6, 4.5))
    sns.scatterplot(
        data=filtered_df, x="income", y="happiness",
        alpha=0.6, s=60, color=main_color, edgecolors='white', linewidth=0.5,
        ax=ax
    )
    # 添加趋势线
    sns.regplot(
        data=filtered_df, x="income", y="happiness",
        scatter=False, color='red', line_kws={'linewidth': 2, 'linestyle': '--'},
        ax=ax
    )
    ax.set_xlabel("年收入（元）", fontsize=11)
    ax.set_ylabel("幸福度指数", fontsize=11)
    ax.set_title("收入与幸福度的关系", fontsize=13, fontweight='bold')
    ax.grid(True, alpha=0.3, linestyle='--')
    st.pyplot(fig)
    plt.close()

    # 洞察
    corr_income = filtered_df['income'].corr(filtered_df['happiness'])
    st.markdown(f"""
    <div class="insight-box">
        <strong>📊 相关性洞察：</strong> 收入与幸福度的相关系数为 {corr_income:.3f}，
        表明{'较强的正相关关系' if abs(corr_income) > 0.3 else '相关性较弱'}。
    </div>
    """, unsafe_allow_html=True)

with col_right:
    st.markdown("### 房价 vs 幸福度")
    fig, ax = plt.subplots(figsize=(6, 4.5))
    sns.scatterplot(
        data=filtered_df, x="house_price", y="happiness",
        alpha=0.6, s=60, color="#ff6b6b", edgecolors='white', linewidth=0.5,
        ax=ax
    )
    sns.regplot(
        data=filtered_df, x="house_price", y="happiness",
        scatter=False, color='red', line_kws={'linewidth': 2, 'linestyle': '--'},
        ax=ax
    )
    ax.set_xlabel("房价（元/㎡）", fontsize=11)
    ax.set_ylabel("幸福度指数", fontsize=11)
    ax.set_title("房价与幸福度的关系", fontsize=13, fontweight='bold')
    ax.grid(True, alpha=0.3, linestyle='--')
    st.pyplot(fig)
    plt.close()

    corr_house = filtered_df['house_price'].corr(filtered_df['happiness'])
    st.markdown(f"""
    <div class="insight-box">
        <strong>📊 相关性洞察：</strong> 房价与幸福度的相关系数为 {corr_house:.3f}，
        高房价{'并不意味着' if abs(corr_house) < 0.5 else '确实带来了'}更高的幸福感。
    </div>
    """, unsafe_allow_html=True)

# ============ 第二行：幸福度排名条形图 ============
st.markdown('<h2 class="section-title">😊 城市幸福度排名</h2>', unsafe_allow_html=True)

col_chart, col_table = st.columns([1.5, 1])

with col_chart:
    n_cities = st.slider("显示城市数量", 10, min(50, len(filtered_df)), 20, key="happiness_n")
    top_n_happy = filtered_df.nlargest(n_cities, 'happiness').sort_values('happiness', ascending=True)

    fig, ax = plt.subplots(figsize=(8, max(6, n_cities * 0.25)))
    bars = ax.barh(top_n_happy['city'], top_n_happy['happiness'], color=main_color, edgecolor='white')
    ax.set_xlabel("幸福度指数", fontsize=11)
    ax.set_title(f"幸福度 Top {n_cities} 城市", fontsize=13, fontweight='bold')
    ax.grid(axis='x', alpha=0.3, linestyle='--')

    # 在条形上标数值
    for bar, val in zip(bars, top_n_happy['happiness']):
        ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                f'{val:.1f}', va='center', fontsize=9)

    st.pyplot(fig)
    plt.close()

with col_table:
    st.markdown("#### 📋 幸福度排名表")
    display_df = top_n_happy.sort_values('happiness', ascending=False)[['city', 'province', 'happiness', 'income', 'house_price', 'value_index']]
    display_df.columns = ['城市', '省份', '幸福度', '年收入', '房价', '可负担指数']
    display_df = display_df.reset_index(drop=True)
    display_df.index = range(1, len(display_df) + 1)
    st.dataframe(display_df.style.format({
        '年收入': '{:,.0f}',
        '房价': '{:,.0f}',
        '幸福度': '{:.1f}',
        '可负担指数': '{:.2f}'
    }), use_container_width=True, height=400)

# ============ 第三行：住房可负担性指数 ============
st.markdown('<h2 class="section-title">🏠 住房可负担性指数分析</h2>', unsafe_allow_html=True)
st.markdown("""
<div class="insight-box">
    <strong>💡 住房可负担性指数 = 年收入 ÷ 房价</strong><br>
    指数越高，说明该城市居民用年收入能购买的住房面积越大，住房压力相对越小。
</div>
""", unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 📊 可负担指数城市排名")
    n_value = st.slider("显示城市数量", 10, min(50, len(filtered_df)), 20, key="value_n")
    top_n_value = filtered_df.nlargest(n_value, 'value_index').sort_values('value_index', ascending=True)

    fig, ax = plt.subplots(figsize=(7, max(6, n_value * 0.25)))
    bars = ax.barh(top_n_value['city'], top_n_value['value_index'], color='#f59e0b', edgecolor='white')
    ax.set_xlabel("住房可负担性指数", fontsize=11)
    ax.set_title(f"住房可负担性 Top {n_value} 城市", fontsize=13, fontweight='bold')
    ax.grid(axis='x', alpha=0.3, linestyle='--')

    for bar, val in zip(bars, top_n_value['value_index']):
        ax.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height() / 2,
                f'{val:.2f}', va='center', fontsize=9)

    st.pyplot(fig)
    plt.close()

with col2:
    st.markdown("### 📉 全量城市可负担指数分布")

    sorted_df = filtered_df.sort_values('value_index', ascending=False).reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(range(len(sorted_df)), sorted_df['value_index'], color=main_color, alpha=0.8, width=1.0)

    # 高亮标注
    ax.axhline(y=10, color='red', linestyle='--', alpha=0.7, label='高可负担线 (10)')
    ax.axhline(y=5, color='orange', linestyle='--', alpha=0.7, label='中等可负担线 (5)')

    ax.set_xlabel("城市排名", fontsize=11)
    ax.set_ylabel("可负担指数", fontsize=11)
    ax.set_title("全国城市住房可负担性全貌", fontsize=13, fontweight='bold')
    ax.legend(fontsize=9)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    st.pyplot(fig)
    plt.close()

# ============ 第四行：省份聚合分析 ============
st.markdown('<h2 class="section-title">🗺️ 省份维度聚合分析</h2>', unsafe_allow_html=True)

province_agg = filtered_df.groupby('province').agg({
    'happiness': 'mean',
    'income': 'mean',
    'house_price': 'mean',
    'value_index': 'mean',
    'city': 'count'
}).reset_index()
province_agg.columns = ['省份', '平均幸福度', '平均收入', '平均房价', '平均可负担指数', '城市数量']
province_agg = province_agg.sort_values('平均幸福度', ascending=False)

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 各省平均幸福度排名")
    top_provinces = province_agg.head(15)

    fig, ax = plt.subplots(figsize=(7, 6))
    bars = ax.barh(range(len(top_provinces)), top_provinces['平均幸福度'], color=main_color, edgecolor='white')
    ax.set_yticks(range(len(top_provinces)))
    ax.set_yticklabels(top_provinces['省份'])
    ax.set_xlabel("平均幸福度", fontsize=11)
    ax.set_title(f"平均幸福度 Top 15 省份", fontsize=13, fontweight='bold')
    ax.grid(axis='x', alpha=0.3, linestyle='--')
    ax.invert_yaxis()

    for bar, val in zip(bars, top_provinces['平均幸福度']):
        ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                f'{val:.1f}', va='center', fontsize=9)

    st.pyplot(fig)
    plt.close()

with col2:
    st.markdown("### 各省平均可负担指数")
    province_value = province_agg.sort_values('平均可负担指数', ascending=False).head(15)

    fig, ax = plt.subplots(figsize=(7, 6))
    bars = ax.barh(range(len(province_value)), province_value['平均可负担指数'], color='#f59e0b', edgecolor='white')
    ax.set_yticks(range(len(province_value)))
    ax.set_yticklabels(province_value['省份'])
    ax.set_xlabel("平均可负担指数", fontsize=11)
    ax.set_title(f"平均可负担指数 Top 15 省份", fontsize=13, fontweight='bold')
    ax.grid(axis='x', alpha=0.3, linestyle='--')
    ax.invert_yaxis()

    for bar, val in zip(bars, province_value['平均可负担指数']):
        ax.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height() / 2,
                f'{val:.2f}', va='center', fontsize=9)

    st.pyplot(fig)
    plt.close()

# ============ 第五行：数据表格 ============
st.markdown('<h2 class="section-title">📋 完整数据浏览</h2>', unsafe_allow_html=True)

tab1, tab2 = st.tabs(["🏙️ 城市明细数据", "🗺️ 省份聚合数据"])

with tab1:
    display_cols = ['city', 'province', 'happiness', 'income', 'house_price', 'value_index']
    display_df = filtered_df[display_cols].copy()
    display_df.columns = ['城市', '省份', '幸福度', '年收入', '房价(元/㎡)', '可负担指数']
    display_df = display_df.sort_values('可负担指数', ascending=False).reset_index(drop=True)
    display_df.index = range(1, len(display_df) + 1)

    st.dataframe(
        display_df.style.format({
            '年收入': '{:,.0f}',
            '房价(元/㎡)': '{:,.0f}',
            '幸福度': '{:.1f}',
            '可负担指数': '{:.2f}'
        }).background_gradient(subset=['可负担指数'], cmap='YlOrRd'),
        use_container_width=True,
        height=500
    )

    # 下载按钮
    csv = display_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 下载当前筛选数据 (CSV)",
        data=csv,
        file_name="中国城市生活成本与幸福感数据.csv",
        mime="text/csv"
    )

with tab2:
    st.dataframe(
        province_agg.style.format({
            '平均幸福度': '{:.1f}',
            '平均收入': '{:,.0f}',
            '平均房价': '{:,.0f}',
            '平均可负担指数': '{:.2f}'
        }).background_gradient(subset=['平均幸福度'], cmap='RdYlGn'),
        use_container_width=True,
        height=500
    )

# ============ 第六行：TOP 20 住房可负担指数详表 ============
st.markdown('<h2 class="section-title">🏆 住房可负担指数 TOP 20 城市详情</h2>', unsafe_allow_html=True)

top20 = filtered_df.nlargest(20, 'value_index').reset_index(drop=True)
top20_display = top20[['city', 'province', 'happiness', 'income', 'house_price', 'value_index']].copy()
top20_display.columns = ['城市', '省份', '幸福度', '年收入', '房价(元/㎡)', '可负担指数']
# 动态设置行号，防止筛选后数据不足20行时报错
top20_display.index = range(1, len(top20_display) + 1)

col_a, col_b = st.columns([1.2, 1])

with col_a:
    st.dataframe(
        top20_display.style.format({
            '年收入': '{:,.0f}',
            '房价(元/㎡)': '{:,.0f}',
            '幸福度': '{:.1f}',
            '可负担指数': '{:.2f}'
        }).background_gradient(subset=['可负担指数'], cmap='Greens'),
        use_container_width=True
    )

with col_b:
    # 可视化 TOP 20 的对比
    fig, ax = plt.subplots(figsize=(6, 5.5))
    x = range(len(top20))
    width = 0.35

    sorted_top = top20.sort_values('value_index', ascending=True)
    bars1 = ax.barh([i + width / 2 for i in range(len(sorted_top))],
                    sorted_top['value_index'], width, color='#f59e0b', label='可负担指数', edgecolor='white')
    ax.set_yticks(range(len(sorted_top)))
    ax.set_yticklabels(sorted_top['city'], fontsize=9)
    ax.set_xlabel("可负担指数", fontsize=11)
    ax.set_title("TOP 20 住房可负担指数", fontsize=13, fontweight='bold')
    ax.legend(fontsize=9)
    ax.grid(axis='x', alpha=0.3, linestyle='--')

    for bar, val in zip(bars1, sorted_top['value_index']):
        ax.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height() / 2,
                f'{val:.2f}', va='center', fontsize=8)

    st.pyplot(fig)
    plt.close()

# ============ 页脚 ============
st.markdown("---")
st.markdown("""
<div class="footer">
    <p>📊 中国城市生活成本与幸福感分析可视化 | 数据来源：全国300+城市统计数据</p>
    <p>💡 住房可负担性指数 = 年收入 ÷ 房价（元/㎡），数值越高代表住房压力越小</p>
    <p>Made with ❤️ using Streamlit · Matplotlib · Seaborn · Pandas</p>
</div>
""", unsafe_allow_html=True)