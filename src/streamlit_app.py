"""
中国城市生活成本与幸福感分析可视化 - Streamlit 交互式网页应用

【优化说明】
1. 数据加载 / 文件签名 / HTML 地图读取均使用 @st.cache_data 缓存，避免每次交互重复 I/O；
   数据文件内容变化时（mtime+size 签名）缓存自动失效。
2. 对空筛选结果、零方差相关系数、数据不足等边界情况进行防护，避免 NaN / 异常导致页面崩溃。
3. 使用 Agg 无界面后端提升运行稳定性；降低 seaborn 回归重采样开销，加快图表渲染。
4. 清理未使用的导入与变量；使用新版 Streamlit 的 width 参数，规避弃用告警。
"""
import matplotlib

matplotlib.use("Agg")  # 必须在导入 pyplot 之前设置，规避 GUI 后端

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import logging
from pathlib import Path

# 抑制 matplotlib 字体族告警（如 SimHei 缺少 bold 字重时的提示）
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

# ---------------- 路径与全局常量 ----------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
NOTEBOOKS_DIR = BASE_DIR / "notebooks"

FONT_SANS = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
NUMERIC_COLS = ("happiness", "income", "house_price")

COLOR_MAPS = {
    "默认蓝": "steelblue",
    "暖橙": "#ff7f50",
    "森林绿": "#2e8b57",
    "深紫": "#8b5cf6",
}

CUSTOM_CSS = """
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
"""

# ---------------- 页面配置（须为第一个 st 调用） ----------------
st.set_page_config(
    page_title="中国城市生活成本与幸福感分析",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ---------------- 中文字体设置 ----------------
matplotlib.rcParams["font.sans-serif"] = FONT_SANS
matplotlib.rcParams["axes.unicode_minus"] = False

# ---------------- 通用辅助函数 ----------------
def metric_card(title: str, value: str) -> None:
    """渲染顶部指标卡片。"""
    st.markdown(
        f'<div class="metric-card"><h3>{title}</h3><h1>{value}</h1></div>',
        unsafe_allow_html=True,
    )


def safe_corr(a: pd.Series, b: pd.Series) -> float:
    """安全计算相关系数；样本不足或零方差时返回 NaN，避免运行时告警。"""
    if len(a) < 2 or a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(a.corr(b))


def corr_summary(corr, strong_threshold, strong_msg, weak_msg):
    """生成相关性洞察文本；数据不足时给出友好提示。"""
    if not np.isfinite(corr):
        return "数据量不足，无法计算有效相关性。"
    desc = strong_msg if abs(corr) > strong_threshold else weak_msg
    return f"相关系数为 {corr:.3f}，{desc}。"


def add_bar_labels(ax, bars, values, fmt="{:.1f}", offset=0.05, fontsize=9):
    """在水平条形图右侧标注数值。"""
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_width() + offset,
            bar.get_y() + bar.get_height() / 2,
            fmt.format(val),
            va="center",
            fontsize=fontsize,
        )


def range_slider(label, series, step, key=None, to_int=False):
    """创建数值范围滑块；自动处理 min==max / 非有限值等异常情况。"""
    lo, hi = float(series.min()), float(series.max())
    if not (np.isfinite(lo) and np.isfinite(hi)):
        lo, hi = 0.0, 1.0
    if to_int:
        lo, hi = int(np.floor(lo)), int(np.ceil(hi))
    if lo >= hi:
        hi = lo + step
    return st.slider(label, lo, hi, (lo, hi), step=step, key=key)


def top_n_slider(key: str, n_rows: int) -> int:
    """“显示城市数量”滑块；数据不足时自动收缩范围，避免 min>=max 报错。"""
    limit = min(50, n_rows)
    if limit <= 1:
        return max(1, limit)
    lo = min(10, limit)
    val = min(20, limit)
    if lo >= limit:
        return limit
    return st.slider("显示城市数量", lo, limit, val, key=key)


def fmt_table(df, fmt_dict, gradient_col=None, cmap=None):
    """统一格式化表格，可选添加渐变底色。"""
    style = df.style.format(fmt_dict)
    if gradient_col is not None and cmap is not None:
        style = style.background_gradient(subset=[gradient_col], cmap=cmap)
    return style


# ---------------- 数据加载（带缓存，签名感知文件变化） ----------------
def _data_signature():
    """生成数据文件签名（文件名 + mtime + 大小），文件变化时缓存自动失效。"""
    files = sorted(DATA_DIR.glob("*.csv"))
    return tuple((f.name, f.stat().st_mtime_ns, f.stat().st_size) for f in files)


@st.cache_data(show_spinner=False)
def load_data(signature):
    """加载并合并所有数据源。signature 仅用于缓存键。"""
    happiness = pd.read_csv(DATA_DIR / "happiness.csv")
    income = pd.read_csv(DATA_DIR / "income.csv")
    house = pd.read_csv(DATA_DIR / "house_price.csv")
    province = pd.read_csv(DATA_DIR / "province.csv")
    location = pd.read_csv(DATA_DIR / "location.csv")

    df = (
        province.merge(happiness, on="city", how="left")
        .merge(income, on="city", how="left")
        .merge(house, on="city", how="left")
        .merge(location, on="city", how="left")
        .drop_duplicates(subset="city", keep="first")
    )

    # 数值列强制转换，异常值置为 NaN
    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 安全计算住房可负担指数：房价缺失或 <=0 时记为 NaN（随后剔除）
    df["value_index"] = np.where(
        df["house_price"].gt(0), df["income"] / df["house_price"], np.nan
    )
    return df.dropna(subset=[*NUMERIC_COLS, "value_index"]).reset_index(drop=True)


df = load_data(_data_signature())

# ---------------- 侧边栏 ----------------
with st.sidebar:
    st.image("https://img.icons8.com/color/96/city-buildings.png", width=72)
    st.markdown("## 🔍 分析控制面板")

    selected_provinces = st.multiselect(
        "选择省份（可多选，留空=全部）",
        options=sorted(df["province"].unique()),
        default=[],
    )

    st.markdown("---")
    st.markdown("### 📊 数值筛选")
    happiness_range = range_slider("幸福度范围", df["happiness"], 0.5)
    income_range = range_slider("年收入范围（元）", df["income"], 1000, to_int=True)
    house_range = range_slider("房价范围（元/㎡）", df["house_price"], 500, to_int=True)

    st.markdown("---")
    st.markdown("### 🎨 可视化设置")
    chart_theme = st.selectbox("图表配色主题", options=list(COLOR_MAPS.keys()))
    main_color = COLOR_MAPS[chart_theme]

# ---------------- 数据筛选 ----------------
mask = pd.Series(True, index=df.index)
if selected_provinces:
    mask &= df["province"].isin(selected_provinces)
mask &= df["happiness"].between(*happiness_range)
mask &= df["income"].between(*income_range)
mask &= df["house_price"].between(*house_range)
filtered_df = df.loc[mask]

if filtered_df.empty:
    st.warning("⚠️ 当前筛选条件下没有任何符合条件的城市，请调整左侧筛选条件。")
    st.stop()

# ---------------- 页面主体：标题与指标卡片 ----------------
st.markdown('<h1 class="main-header">🏙️ 中国城市生活成本与幸福感分析</h1>', unsafe_allow_html=True)
st.markdown(
    '<p style="text-align:center; color:#666; font-size:1.1rem; margin-bottom:1rem;">'
    "基于全国300+城市的收入、房价与幸福度数据，深度探索城市宜居价值</p>",
    unsafe_allow_html=True,
)

avg_happiness = filtered_df["happiness"].mean()
avg_income = filtered_df["income"].mean()
avg_house = filtered_df["house_price"].mean()
avg_value = filtered_df["value_index"].mean()

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    metric_card("📋 城市总数", f"{len(filtered_df)}")
with c2:
    metric_card("😊 平均幸福度", f"{avg_happiness:.1f}")
with c3:
    metric_card("💰 平均年收入", f"¥{avg_income / 10000:.1f}万")
with c4:
    metric_card("🏠 平均房价", f"¥{avg_house:.0f}")
with c5:
    metric_card("📈 平均可负担指数", f"{avg_value:.2f}")


# ---------------- 第一行：核心指标关联分析 ----------------
st.markdown('<h2 class="section-title">📈 核心指标关联分析</h2>', unsafe_allow_html=True)

col_left, col_right = st.columns(2)

with col_left:
    st.markdown("### 收入 vs 幸福度")
    fig, ax = plt.subplots(figsize=(6, 4.5))
    sns.scatterplot(
        data=filtered_df, x="income", y="happiness",
        alpha=0.6, s=60, color=main_color, edgecolors="white", linewidth=0.5, ax=ax,
    )
    # n_boot 降低重采样开销，显著加快回归线绘制；样本过少时跳过回归线
    if len(filtered_df) >= 2:
        sns.regplot(
            data=filtered_df, x="income", y="happiness",
            scatter=False, color="red", n_boot=100,
            line_kws={"linewidth": 2, "linestyle": "--"}, ax=ax,
        )
    ax.set_xlabel("年收入（元）", fontsize=11)
    ax.set_ylabel("幸福度指数", fontsize=11)
    ax.set_title("收入与幸福度的关系", fontsize=13, fontweight="bold")
    ax.grid(True, alpha=0.3, linestyle="--")
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

    corr_income = safe_corr(filtered_df["income"], filtered_df["happiness"])
    summary = corr_summary(
        corr_income, 0.3,
        "表明收入与幸福度存在较强的正相关关系",
        "表明收入与幸福度的相关性较弱",
    )
    st.markdown(
        f'<div class="insight-box"><strong>📊 相关性洞察：</strong> {summary}</div>',
        unsafe_allow_html=True,
    )

with col_right:
    st.markdown("### 房价 vs 幸福度")
    fig, ax = plt.subplots(figsize=(6, 4.5))
    sns.scatterplot(
        data=filtered_df, x="house_price", y="happiness",
        alpha=0.6, s=60, color="#ff6b6b", edgecolors="white", linewidth=0.5, ax=ax,
    )
    if len(filtered_df) >= 2:
        sns.regplot(
            data=filtered_df, x="house_price", y="happiness",
            scatter=False, color="red", n_boot=100,
            line_kws={"linewidth": 2, "linestyle": "--"}, ax=ax,
        )
    ax.set_xlabel("房价（元/㎡）", fontsize=11)
    ax.set_ylabel("幸福度指数", fontsize=11)
    ax.set_title("房价与幸福度的关系", fontsize=13, fontweight="bold")
    ax.grid(True, alpha=0.3, linestyle="--")
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

    corr_house = safe_corr(filtered_df["house_price"], filtered_df["happiness"])
    summary = corr_summary(
        corr_house, 0.5,
        "高房价确实带来了更高的幸福感",
        "高房价并不意味着更高的幸福感",
    )
    st.markdown(
        f'<div class="insight-box"><strong>📊 相关性洞察：</strong> {summary}</div>',
        unsafe_allow_html=True,
    )

# ---------------- 第二行：幸福度排名 ----------------
st.markdown('<h2 class="section-title">😊 城市幸福度排名</h2>', unsafe_allow_html=True)

col_chart, col_table = st.columns([1.5, 1])

with col_chart:
    n_cities = top_n_slider("happiness_n", len(filtered_df))
    top_n_happy = filtered_df.nlargest(n_cities, "happiness").sort_values(
        "happiness", ascending=True
    )

    fig, ax = plt.subplots(figsize=(8, max(6, n_cities * 0.25)))
    bars = ax.barh(
        top_n_happy["city"], top_n_happy["happiness"],
        color=main_color, edgecolor="white",
    )
    ax.set_xlabel("幸福度指数", fontsize=11)
    ax.set_title(f"幸福度 Top {n_cities} 城市", fontsize=13, fontweight="bold")
    ax.grid(axis="x", alpha=0.3, linestyle="--")
    add_bar_labels(ax, bars, top_n_happy["happiness"], fmt="{:.1f}", offset=0.3)
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

with col_table:
    st.markdown("#### 📋 幸福度排名表")
    display_df = (
        top_n_happy.sort_values("happiness", ascending=False)[
            ["city", "province", "happiness", "income", "house_price", "value_index"]
        ].copy()
    )
    display_df.columns = ["城市", "省份", "幸福度", "年收入", "房价", "可负担指数"]
    display_df.index = range(1, len(display_df) + 1)
    st.dataframe(
        fmt_table(
            display_df,
            {"年收入": "{:,.0f}", "房价": "{:,.0f}", "幸福度": "{:.1f}", "可负担指数": "{:.2f}"},
        ),
        height=400,
    )

# ---------------- 第三行：住房可负担性指数 ----------------
st.markdown('<h2 class="section-title">🏠 住房可负担性指数分析</h2>', unsafe_allow_html=True)
st.markdown(
    """
    <div class="insight-box">
        <strong>💡 住房可负担性指数 = 年收入 ÷ 房价</strong><br>
        指数越高，说明该城市居民用年收入能购买的住房面积越大，住房压力相对越小。
    </div>
    """,
    unsafe_allow_html=True,
)

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 📊 可负担指数城市排名")
    n_value = top_n_slider("value_n", len(filtered_df))
    top_n_value = filtered_df.nlargest(n_value, "value_index").sort_values(
        "value_index", ascending=True
    )

    fig, ax = plt.subplots(figsize=(7, max(6, n_value * 0.25)))
    bars = ax.barh(
        top_n_value["city"], top_n_value["value_index"],
        color="#f59e0b", edgecolor="white",
    )
    ax.set_xlabel("住房可负担性指数", fontsize=11)
    ax.set_title(f"住房可负担性 Top {n_value} 城市", fontsize=13, fontweight="bold")
    ax.grid(axis="x", alpha=0.3, linestyle="--")
    add_bar_labels(ax, bars, top_n_value["value_index"], fmt="{:.2f}")
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

with col2:
    st.markdown("### 📉 全量城市可负担指数分布")
    sorted_df = filtered_df.sort_values("value_index", ascending=False).reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(range(len(sorted_df)), sorted_df["value_index"], color=main_color, alpha=0.8, width=1.0)
    ax.axhline(y=10, color="red", linestyle="--", alpha=0.7, label="高可负担线 (10)")
    ax.axhline(y=5, color="orange", linestyle="--", alpha=0.7, label="中等可负担线 (5)")
    ax.set_xlabel("城市排名", fontsize=11)
    ax.set_ylabel("可负担指数", fontsize=11)
    ax.set_title("全国城市住房可负担性全貌", fontsize=13, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

# ---------------- 第四行：TOP 20 住房可负担指数详表 ----------------
st.markdown('<h2 class="section-title">🏆 住房可负担指数 TOP 20 城市详情</h2>', unsafe_allow_html=True)

top20 = filtered_df.nlargest(20, "value_index").sort_values("value_index", ascending=False)
top20_display = top20[
    ["city", "province", "happiness", "income", "house_price", "value_index"]
].copy()
top20_display.columns = ["城市", "省份", "幸福度", "年收入", "房价(元/㎡)", "可负担指数"]
# 动态设置行号，防止筛选后数据不足20行时报错
top20_display.index = range(1, len(top20_display) + 1)

col_a, col_b = st.columns([1.2, 1])

with col_a:
    st.dataframe(
        fmt_table(
            top20_display,
            {"年收入": "{:,.0f}", "房价(元/㎡)": "{:,.0f}", "幸福度": "{:.1f}", "可负担指数": "{:.2f}"},
            gradient_col="可负担指数",
            cmap="Greens",
        )
    )

with col_b:
    # 可视化 TOP 20 的对比
    sorted_top = top20.sort_values("value_index", ascending=True)
    fig, ax = plt.subplots(figsize=(6, 5.5))
    bars = ax.barh(
        range(len(sorted_top)), sorted_top["value_index"],
        color="#f59e0b", label="可负担指数", edgecolor="white",
    )
    ax.set_yticks(range(len(sorted_top)))
    ax.set_yticklabels(sorted_top["city"], fontsize=9)
    ax.set_xlabel("可负担指数", fontsize=11)
    ax.set_title("TOP 20 住房可负担指数", fontsize=13, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(axis="x", alpha=0.3, linestyle="--")
    add_bar_labels(ax, bars, sorted_top["value_index"], fmt="{:.2f}", fontsize=8)
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

# ---------------- 第五行：省份聚合分析 ----------------
st.markdown('<h2 class="section-title">🗺️ 省份维度聚合分析</h2>', unsafe_allow_html=True)

province_agg = (
    filtered_df.groupby("province")
    .agg(
        happiness=("happiness", "mean"),
        income=("income", "mean"),
        house_price=("house_price", "mean"),
        value_index=("value_index", "mean"),
        city_count=("city", "count"),
    )
    .reset_index()
)
province_agg.columns = ["省份", "平均幸福度", "平均收入", "平均房价", "平均可负担指数", "城市数量"]
province_agg = province_agg.sort_values("平均幸福度", ascending=False)

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 各省平均幸福度排名")
    top_provinces = province_agg.head(15)

    fig, ax = plt.subplots(figsize=(7, 6))
    bars = ax.barh(
        range(len(top_provinces)), top_provinces["平均幸福度"],
        color=main_color, edgecolor="white",
    )
    ax.set_yticks(range(len(top_provinces)))
    ax.set_yticklabels(top_provinces["省份"])
    ax.set_xlabel("平均幸福度", fontsize=11)
    ax.set_title("平均幸福度 Top 15 省份", fontsize=13, fontweight="bold")
    ax.grid(axis="x", alpha=0.3, linestyle="--")
    ax.invert_yaxis()
    add_bar_labels(ax, bars, top_provinces["平均幸福度"], fmt="{:.1f}", offset=0.3)
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

with col2:
    st.markdown("### 各省平均可负担指数")
    province_value = province_agg.sort_values("平均可负担指数", ascending=False).head(15)

    fig, ax = plt.subplots(figsize=(7, 6))
    bars = ax.barh(
        range(len(province_value)), province_value["平均可负担指数"],
        color="#f59e0b", edgecolor="white",
    )
    ax.set_yticks(range(len(province_value)))
    ax.set_yticklabels(province_value["省份"])
    ax.set_xlabel("平均可负担指数", fontsize=11)
    ax.set_title("平均可负担指数 Top 15 省份", fontsize=13, fontweight="bold")
    ax.grid(axis="x", alpha=0.3, linestyle="--")
    ax.invert_yaxis()
    add_bar_labels(ax, bars, province_value["平均可负担指数"], fmt="{:.2f}")
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

# ---------------- 地理可视化地图 ----------------
@st.cache_data(show_spinner=False)
def load_map_html(file_name):
    """读取并预处理 HTML 地图内容（缓存字符串，文件变化时自动失效）。"""
    path = NOTEBOOKS_DIR / file_name
    if not path.exists():
        return None
    # 替换固定宽度为 100% 以自适应容器
    return path.read_text(encoding="utf-8").replace("width:900px;", "width:100%;")


@st.cache_resource(show_spinner=False)
def _map_iframe_file(html):
    """将预处理后的 HTML 写入临时文件，供 st.iframe 加载（仅首次写入）。"""
    import tempfile

    tmp = Path(tempfile.gettempdir()) / f"city_map_{abs(hash(html))}.html"
    if not tmp.exists():
        tmp.write_text(html, encoding="utf-8")
    return tmp


def render_map(file_name, fallback_msg, height=520):
    """渲染 HTML 地图组件（使用 st.iframe，替代已弃用的 st.components.v1.html）。"""
    html = load_map_html(file_name)
    if html is None:
        st.warning(fallback_msg)
        return
    src = _map_iframe_file(html)
    st.iframe(src=str(src), height=height)


st.markdown('<h2 class="section-title">🗺️ 中国城市地理分布地图</h2>', unsafe_allow_html=True)

col_map1, col_map2 = st.columns(2)
with col_map1:
    st.markdown("### 中国各省市宜居度地图")
    render_map("中国各省市宜居度地图.html", "宜居度地图文件未找到")
with col_map2:
    st.markdown("### Top50 城市生活价值指数分布")
    render_map("Top50的中国城市生活价值指数分布.html", "城市价值指数地图文件未找到")

# ---------------- 第六行：数据表格 ----------------
st.markdown('<h2 class="section-title">📋 完整数据浏览</h2>', unsafe_allow_html=True)

tab1, tab2 = st.tabs(["🏙️ 城市明细数据", "🗺️ 省份聚合数据"])

with tab1:
    display_df = filtered_df[
        ["city", "province", "happiness", "income", "house_price", "value_index"]
    ].copy()
    display_df.columns = ["城市", "省份", "幸福度", "年收入", "房价(元/㎡)", "可负担指数"]
    display_df = display_df.sort_values("可负担指数", ascending=False).reset_index(drop=True)
    display_df.index = range(1, len(display_df) + 1)

    st.dataframe(
        fmt_table(
            display_df,
            {"年收入": "{:,.0f}", "房价(元/㎡)": "{:,.0f}", "幸福度": "{:.1f}", "可负担指数": "{:.2f}"},
            gradient_col="可负担指数",
            cmap="YlOrRd",
        ),
        height=500,
    )

    st.download_button(
        label="📥 下载当前筛选数据 (CSV)",
        data=display_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="中国城市生活成本与幸福感数据.csv",
        mime="text/csv",
    )

with tab2:
    st.dataframe(
        fmt_table(
            province_agg,
            {"平均幸福度": "{:.1f}", "平均收入": "{:,.0f}", "平均房价": "{:,.0f}", "平均可负担指数": "{:.2f}"},
            gradient_col="平均幸福度",
            cmap="RdYlGn",
        ),
        height=500,
    )

# ---------------- 页脚 ----------------
st.markdown("---")
st.markdown(
    """
    <div class="footer">
        <p>📊 中国城市生活成本与幸福感分析可视化 | 数据来源：全国300+城市统计数据</p>
        <p>💡 住房可负担性指数 = 年收入 ÷ 房价（元/㎡），数值越高代表住房压力越小</p>
        <p>Made with ❤️ using Streamlit · Matplotlib · Seaborn · Pandas</p>
    </div>
    """,
    unsafe_allow_html=True,
)


df = load_data(_data_signature())
