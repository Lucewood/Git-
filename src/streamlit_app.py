"""
中国城市生活成本与幸福感分析可视化 —— Streamlit 交互式网页应用

v2.0 工业级重构说明
1. 模块化架构：业务逻辑拆分至 src/city_insight 包
   （config / logging_setup / data_loader / analysis / charts / widgets / styles），
   本入口脚本仅负责页面编排，便于维护与单元测试。
2. 数据管道化：data_loader 提供纯函数加载 + Streamlit 缓存包装，数据签名感知文件变化；
   新增常住人口数据与派生指标（住房可负担指数、综合宜居评分）。
3. 数据质量治理：加载时自动校验，页面提供可视化质量报告；数据口径见 data/metadata.json。
4. 健壮性：所有图表 / 统计对空数据、零方差、数据不足等边界情况做了防护。
5. 可部署性：提供 requirements*.txt、Dockerfile、.streamlit/config.toml、
   GitHub Actions CI 与 pytest 单元测试（tests/）。
"""
from __future__ import annotations

import hashlib
import sys
from io import BytesIO
from pathlib import Path

# 确保可将 src/ 下的 city_insight 包导入（兼容 streamlit 运行方式）
_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import matplotlib

matplotlib.use("Agg")  # 必须在导入 pyplot 之前设置，规避 GUI 后端

import logging

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from city_insight.config import (
    APP_NAME,
    APP_VERSION,
    DATA_DIR,
    NOTEBOOKS_DIR,
    DATA_REF_YEAR,
    METRIC_COLS,
    COLUMN_LABELS,
    COLOR_MAPS,
    METRIC_UNITS,
    get_settings,
)
from city_insight.logging_setup import setup_logging
from city_insight.styles import CUSTOM_CSS
from city_insight import analysis, charts, data_loader, forecast, widgets

settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)

# ---------------- 页面配置（须为第一个 st 调用） ----------------
st.set_page_config(
    page_title=f"{APP_NAME} v{APP_VERSION}",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
charts.setup_plot_style()

# ---------------- 辅助函数（与页面状态无关，统一在此定义） ----------------
def to_excel_bytes(data: pd.DataFrame) -> bytes:
    """将 DataFrame 序列化为 Excel 字节流。"""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        data.to_excel(writer, index=False, sheet_name="城市数据")
    return buffer.getvalue()


def _stable_digest(text: str) -> str:
    """HTML 内容稳定摘要（用于生成可复用的临时文件名，避免 hash() 随机化）。"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:16]


def _styled_table(
    df: pd.DataFrame,
    columns: list[str],
    fmt_dict: dict,
    gradient_col: str | None = None,
    cmap: str | None = None,
):
    """选取列 → 中文列名 → 1 起始索引，并统一套用表格样式。

    返回 pandas Styler，可直接传给 st.dataframe。
    """
    display = df[columns].copy()
    display.columns = [COLUMN_LABELS[c] for c in columns]
    display.index = range(1, len(display) + 1)
    return widgets.fmt_table(
        display, fmt_dict, gradient_col=gradient_col, cmap=cmap
    )


@st.cache_data(show_spinner=False)
def load_map_html(file_name: str) -> str | None:
    """读取并预处理 HTML 地图内容（缓存字符串，文件变化时自动失效）。"""
    path = NOTEBOOKS_DIR / file_name
    if not path.exists():
        return None
    # 替换固定宽度为 100% 以自适应容器
    return path.read_text(encoding="utf-8").replace("width:900px;", "width:100%;")


def render_map(file_name: str, fallback_msg: str, height: int | None = None) -> None:
    """渲染 HTML 地图组件，组件异常时降级为静态文件提示。

    说明：自 Streamlit 1.37 起官方推荐使用 st.iframe 替代已弃用的
    st.components.v1.html；st.iframe 可自动识别 HTML 字符串 / 本地文件并嵌入。
    """
    html = load_map_html(file_name)
    if html is None:
        st.warning(fallback_msg)
        return
    height = height or settings.default_map_height
    try:
        if settings.map_render_mode == "iframe":
            import tempfile

            tmp = Path(tempfile.gettempdir()) / f"city_map_{_stable_digest(html)}.html"
            if not tmp.exists():
                tmp.write_text(html, encoding="utf-8")
            st.iframe(src=tmp, height=height)  # 本地 HTML 文件由 st.iframe 直接读取嵌入
        else:
            st.iframe(html, height=height)  # HTML 字符串模式
    except Exception as exc:  # noqa: BLE001 - 组件失败不应中断页面
        logger.warning("地图组件渲染失败（%s），已降级为链接提示。", exc)
        st.warning(f"{fallback_msg}（组件渲染失败，可直接打开 notebooks/ 下对应文件查看）")


def render_quality_report(q: dict, metadata: dict) -> None:
    """渲染数据质量报告。"""
    st.markdown("#### 📋 数据质量报告")
    missing_core = sum(
        v for k, v in q.get("missing_values", {}).items() if k != "province"
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("城市总数", q["shape"]["rows"])
    c2.metric("字段数", q["shape"]["cols"])
    c3.metric("重复城市", q["duplicate_cities"])
    c4.metric("核心指标缺失值", missing_core)

    with st.expander("📖 数据字典（字段口径与来源）", expanded=False):
        if metadata:
            st.json(metadata)
        else:
            st.info("未找到 data/metadata.json。")

    with st.expander("🔬 数据完整性明细", expanded=False):
        missing_df = pd.DataFrame(
            [{"字段": k, "缺失值": v} for k, v in q.get("missing_values", {}).items()]
        )
        st.dataframe(missing_df, hide_index=True, width="stretch")

        num_summary = q.get("numeric_summary", {})
        if num_summary:
            summary_rows = []
            for col, stats in num_summary.items():
                row = {"指标": COLUMN_LABELS.get(col, col)}
                row.update(stats)
                summary_rows.append(row)
            st.dataframe(
                pd.DataFrame(summary_rows),
                hide_index=True,
                width="stretch",
            )

    src_counts = q.get("source_city_counts", {})
    if src_counts:
        st.markdown("##### 源文件城市覆盖度")
        cov_df = pd.DataFrame(
            [{"数据文件": k, "城市数": v} for k, v in src_counts.items()]
        )
        st.dataframe(cov_df, hide_index=True, width="stretch")
    st.caption(f"数据参考年份：{DATA_REF_YEAR} · 数据版本：v{APP_VERSION}")


@st.cache_resource(show_spinner=False)
def _load_forecast_pipeline(
    signature: tuple[tuple[str, int, int], ...], data_dir: Path
) -> dict:
    """构建并缓存房价预测机器学习流水线（跨 rerun 复用，数据变化自动失效）。

    仅接受可哈希的基本类型参数；模型对象（梯度提升树）保存在缓存中避免重复训练。
    """
    history = forecast.load_house_history(data_dir)
    cross_df, _ = data_loader.load_data(data_dir, signature)
    return forecast.build_pipeline(history, cross_df)


# ---------------- 数据加载（缓存 + 文件签名感知） ----------------
try:
    df, quality = data_loader.load_data(
        DATA_DIR, data_loader.data_signature(DATA_DIR)
    )
except FileNotFoundError as exc:
    st.error(f"❌ 数据文件缺失：{exc}")
    st.info("请确保 data/ 目录包含全部数据文件（清单见 data/metadata.json）。")
    st.stop()

# ---------------- 侧边栏：分析控制面板 ----------------
with st.sidebar:
    st.markdown("## 🏙️ 分析控制面板")
    st.caption(f"数据参考年份 {DATA_REF_YEAR} · 版本 v{APP_VERSION}")

    selected_provinces = st.multiselect(
        "选择省份（可多选，留空=全部）",
        options=sorted(df["province"].unique()),
        default=[],
    )

    city_keyword = st.text_input("🔎 城市关键词过滤（可留空）", value="")

    st.markdown("---")
    st.markdown("### 📊 数值筛选")
    happiness_range = widgets.range_slider(
        "幸福度范围", df["happiness"], 0.5, key="r_happy"
    )
    income_range = widgets.range_slider(
        "年收入范围（元）", df["income"], 1000, key="r_income", to_int=True
    )
    house_range = widgets.range_slider(
        "房价范围（元/㎡）", df["house_price"], 500, key="r_house", to_int=True
    )
    population_range = widgets.range_slider(
        "常住人口范围（万人）", df["population"], 10, key="r_pop", to_int=True
    )

    st.markdown("---")
    st.markdown("### 🎨 可视化设置")
    chart_theme = st.selectbox(
        "图表配色主题", options=list(COLOR_MAPS.keys()), key="theme"
    )
    main_color = COLOR_MAPS[chart_theme]

    show_maps = st.toggle("显示地理地图（HTML 组件）", value=True, key="toggle_maps")

# ---------------- 数据筛选 ----------------
mask = pd.Series(True, index=df.index)
if selected_provinces:
    mask &= df["province"].isin(selected_provinces)
if city_keyword.strip():
    # regex=False：按字面匹配关键词，避免 "[" / "(" / "*" 等正则特殊字符触发解析异常
    mask &= df["city"].str.contains(
        city_keyword.strip(), case=False, na=False, regex=False
    )
mask &= df["happiness"].between(*happiness_range)
mask &= df["income"].between(*income_range)
mask &= df["house_price"].between(*house_range)
mask &= df["population"].between(*population_range)
filtered_df = df.loc[mask].copy()

if filtered_df.empty:
    st.warning("当前筛选条件下没有任何符合条件的城市，请调整左侧筛选条件。")
    st.stop()

# ---------------- 页面主体：标题与指标卡片 ----------------
st.markdown(f'<h1 class="main-header">🏙️ {APP_NAME}</h1>', unsafe_allow_html=True)
st.markdown(
    f'<p style="text-align:center; color:#666; font-size:1.05rem; margin-bottom:1rem;">'
    f"基于全国 {len(df)} 个城市（当前筛选 {len(filtered_df)} 个）的收入、房价、人口与幸福度数据，"
    "深度探索城市宜居价值</p>",
    unsafe_allow_html=True,
)

avg_happiness = filtered_df["happiness"].mean()
avg_income = filtered_df["income"].mean()
avg_house = filtered_df["house_price"].mean()
avg_population = filtered_df["population"].mean()
avg_value = filtered_df["value_index"].mean()
avg_composite = filtered_df["composite_score"].mean()
total_pop = filtered_df["population"].sum()

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    widgets.metric_card("📋 城市总数", f"{len(filtered_df)}",
                        sub=f"{filtered_df['province'].nunique()} 个省份")
with c2:
    widgets.metric_card("😊 平均幸福度", f"{avg_happiness:.1f}", sub="满分 100")
with c3:
    widgets.metric_card("💰 平均年收入", f"¥{avg_income / 10000:.1f}万", sub="单位：元/年")
with c4:
    widgets.metric_card("🏠 平均房价", f"¥{avg_house:.0f}", sub="单位：元/㎡")
with c5:
    widgets.metric_card("📈 平均可负担指数", f"{avg_value:.2f}",
                        sub=f"总人口约 {total_pop / 10000:.1f} 亿")

# ===========================================================================
# 第一节：核心指标关联分析
# ===========================================================================
widgets.section_title("📈 核心指标关联分析")

col_left, col_right = st.columns(2)

with col_left:
    st.markdown("### 收入 vs 幸福度")
    fig = charts.scatter_with_regression(
        filtered_df, "income", "happiness",
        color=main_color,
        xlabel=METRIC_UNITS["income"],
        ylabel=METRIC_UNITS["happiness"],
        title="收入与幸福度的关系",
        n_boot=settings.n_boot_regression,
    )
    st.pyplot(fig)
    plt.close(fig)

    corr_income = analysis.safe_corr(filtered_df["income"], filtered_df["happiness"])
    summary = analysis.corr_summary_text(
        corr_income, 0.3,
        "表明收入与幸福度存在较强的正相关关系",
        "表明收入与幸福度的相关性较弱",
    )
    widgets.insight_box(f"<strong>📊 相关性洞察：</strong> {summary}")

with col_right:
    st.markdown("### 房价 vs 幸福度")
    fig = charts.scatter_with_regression(
        filtered_df, "house_price", "happiness",
        color="#ff6b6b",
        xlabel=METRIC_UNITS["house_price"],
        ylabel=METRIC_UNITS["happiness"],
        title="房价与幸福度的关系",
        n_boot=settings.n_boot_regression,
    )
    st.pyplot(fig)
    plt.close(fig)

    corr_house = analysis.safe_corr(filtered_df["house_price"], filtered_df["happiness"])
    summary = analysis.corr_summary_text(
        corr_house, 0.5,
        "高房价确实带来了更高的幸福感",
        "高房价并不意味着更高的幸福感",
    )
    widgets.insight_box(f"<strong>📊 相关性洞察：</strong> {summary}")

# 相关性热力图 + 指标分布
col_hm, col_dist = st.columns([1.15, 1])
with col_hm:
    st.markdown("### 指标相关性矩阵")
    if len(filtered_df) >= 3:
        fig = charts.correlation_heatmap(filtered_df, METRIC_COLS)
        st.pyplot(fig)
        plt.close(fig)
    else:
        st.info("筛选后的样本量不足，无法绘制相关性热力图。")

with col_dist:
    st.markdown("### 指标分布概览")
    dist_metric = st.selectbox(
        "选择指标查看分布", options=list(METRIC_COLS), key="dist_metric",
        format_func=lambda m: COLUMN_LABELS.get(m, m),
    )
    if len(filtered_df) >= 2:
        fig = charts.distribution_hist(
            filtered_df[dist_metric],
            color=main_color,
            title=f"{COLUMN_LABELS.get(dist_metric, dist_metric)} 分布",
            xlabel=METRIC_UNITS.get(dist_metric, dist_metric),
        )
        st.pyplot(fig)
        plt.close(fig)
    else:
        st.info("筛选后的样本量不足，无法绘制分布图。")

# ===========================================================================
# 第二节：城市对比与画像
# ===========================================================================
widgets.section_title("🔬 城市对比与画像")

province_map = df.set_index("city")["province"].to_dict()

cmp_col, profile_col = st.columns([1.3, 1])

with cmp_col:
    st.markdown("### 🆚 多城市指标对比")
    max_cities = settings.max_comparison_cities
    default_cities = [c for c in ("北京", "上海", "成都", "长沙") if c in set(filtered_df["city"])]
    selected_cities = st.multiselect(
        f"选择 2-{max_cities} 个城市进行对比",
        options=filtered_df["city"].tolist(),
        default=default_cities,
        key="cmp_cities",
        format_func=lambda c: f"{c}（{province_map.get(c, '-')}）",
    )

with profile_col:
    st.markdown("### 🧭 城市画像")
    profile_city = st.selectbox(
        "选择城市查看指标画像",
        options=filtered_df["city"].tolist(),
        key="profile_city",
        format_func=lambda c: f"{c}（{province_map.get(c, '-')}）",
    )

if len(selected_cities) >= 2:
    fig = charts.city_comparison(
        filtered_df, selected_cities, METRIC_COLS, color=main_color
    )
    st.pyplot(fig)
    plt.close(fig)
elif selected_cities:
    st.info("请至少选择 2 个城市以进行对比。")

if profile_city:
    row = filtered_df[filtered_df["city"] == profile_city].iloc[0]
    pct = pd.Series({
        m: float(analysis.percentile_rank(filtered_df[m]).loc[row.name]) * 100
        for m in METRIC_COLS
    })

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    with m1:
        widgets.metric_card("😊 幸福度", f"{row['happiness']:.1f}",
                            sub=f"领先 {pct['happiness']:.0f}% 城市")
    with m2:
        widgets.metric_card("💰 年收入", f"{row['income'] / 10000:.1f}万",
                            sub=f"领先 {pct['income']:.0f}% 城市")
    with m3:
        widgets.metric_card("🏠 房价", f"{row['house_price']:.0f}",
                            sub=f"领先 {pct['house_price']:.0f}% 城市")
    with m4:
        widgets.metric_card("👥 人口", f"{row['population']:.0f}万",
                            sub=f"领先 {pct['population']:.0f}% 城市")
    with m5:
        widgets.metric_card("📈 可负担指数", f"{row['value_index']:.2f}",
                            sub=f"领先 {pct['value_index']:.0f}% 城市")
    with m6:
        widgets.metric_card("🌟 综合宜居分", f"{row['composite_score']:.1f}",
                            sub=f"领先 {pct['composite_score']:.0f}% 城市")

    col_profile, col_detail = st.columns([1, 1.2])
    with col_profile:
        fig = charts.city_profile_chart(pct, color=main_color)
        st.pyplot(fig)
        plt.close(fig)
    with col_detail:
        st.markdown(f"#### 📋 {profile_city} 数据一览（筛选范围：{len(filtered_df)} 个城市）")
        detail = pd.DataFrame({
            "指标": ["幸福度", "年收入", "房价", "常住人口", "可负担指数", "综合宜居分"],
            "本城市": [
                f"{row['happiness']:.1f}",
                f"¥{row['income']:,.0f}",
                f"¥{row['house_price']:,.0f}",
                f"{row['population']:,.0f} 万",
                f"{row['value_index']:.2f}",
                f"{row['composite_score']:.1f}",
            ],
            "筛选范围均值": [
                f"{avg_happiness:.1f}",
                f"¥{avg_income:,.0f}",
                f"¥{avg_house:,.0f}",
                f"{avg_population:,.0f} 万",
                f"{avg_value:.2f}",
                f"{avg_composite:.1f}",
            ],
        })
        st.dataframe(detail, hide_index=True, width="stretch")

# ===========================================================================
# 第三节：房价趋势分析与机器学习预测
# ===========================================================================
widgets.section_title("🤖 房价趋势分析与机器学习预测")

with st.expander("📖 预测方法论与数据口径说明", expanded=False):
    st.markdown(
        f"**机器学习策略：全样本城市面板 + 递归多步预测**\n\n"
        f"1. **历史数据**：`data/house_price_history.csv` 提供 2005–{DATA_REF_YEAR} 年各城市年度住房均价"
        f"（{DATA_REF_YEAR} 年与房价快照完全一致；历史序列按演示口径重建，非官方统计）；\n"
        f"2. **特征工程**：对每个「城市 × 年份」样本构造滞后涨幅（1/3/5 年）、长期年均涨幅、"
        f"涨幅波动率、房价收入比（历年收入用宏观工资增速近似）与城市收入 / 人口等静态基本面，"
        f"并加入「全国上一年平均涨幅」刻画宏观周期；\n"
        f"3. **中心化建模**：目标 = 下一年城市涨幅 − 全国同期涨幅，去除共同宏观冲击后，"
        f"用梯度提升回归树（scikit-learn GradientBoosting；未安装时自动回退 numpy 岭回归）拟合，"
        f"最近 3 年作为外样本验证集；\n"
        f"4. **递归外推**：以 {DATA_REF_YEAR} 年价格为起点逐年滚动预测，"
        f"预测值 = 模型预测偏离 + 全国涨幅维持近期水平的宏观情景，并按验证残差标准差"
        f"给出 {forecast.DEFAULT_CONF * 100:.0f}% 置信区间。\n\n"
        f"> ⚠️ 数据为演示合成口径（见 data/metadata.json），预测仅用于展示机器学习建模流程，"
        f"不构成任何投资 / 购房建议。"
    )

# 一次性构建 / 训练预测流水线（模型跨 rerun 缓存，仅在数据变化时重训）
try:
    forecast_pipeline = _load_forecast_pipeline(data_loader.data_signature(DATA_DIR), DATA_DIR)
    forecast_ready = forecast_pipeline is not None and (
        forecast_pipeline["artifacts"]["model"] is not None
        or forecast_pipeline["artifacts"]["ridge"] is not None
    )
except FileNotFoundError as exc:
    st.warning(f"房价历史数据缺失，无法进行趋势预测：{exc}")
    forecast_pipeline, forecast_ready = None, False

if not forecast_ready:
    st.info("预测引擎暂不可用：请确认 data/house_price_history.csv 存在，且包含 2005–2024 完整历史序列。")
else:
    artifacts = forecast_pipeline["artifacts"]
    fc_metrics = artifacts["metrics"]

    fc_ctrl, fc_meta = st.columns([1.25, 1])
    with fc_ctrl:
        default_index = int(df.index[df["city"] == "北京"][0]) if (df["city"] == "北京").any() else 0
        fc_city = st.selectbox(
            "🏙️ 选择要预测的城市",
            options=df["city"].tolist(),
            index=default_index,
            key="fc_city",
            format_func=lambda c: f"{c}（{province_map.get(c, '-')}）",
        )
        fc_horizon = st.slider(
            f"📅 预测年数（自 {DATA_REF_YEAR + 1} 年起）",
            1, forecast.MAX_HORIZON, forecast.DEFAULT_HORIZON, key="fc_horizon",
        )
    with fc_meta:
        st.markdown("##### 🧠 模型概况")
        backend_name = forecast.MODEL_NAMES.get(artifacts["backend"], artifacts["backend"])
        st.markdown(
            f"- **算法**：{backend_name}\n"
            f"- **训练 / 验证样本**：{fc_metrics['train_samples']:,} / {fc_metrics['test_samples']:,} 条"
            f"（验证期 {fc_metrics['test_years'][0]}–{fc_metrics['test_years'][1]} 年）\n"
            f"- **外样本 RMSE / R²**：{fc_metrics['rmse'] * 100:.1f}% / {fc_metrics['r2']:.2f}，"
            f"方向命中率 {fc_metrics['hit_rate'] * 100:.0f}%"
        )

    # 递归预测
    fc = None
    try:
        fc = forecast.forecast_city(forecast_pipeline, fc_city, horizon=int(fc_horizon))
    except ValueError as exc:
        st.warning(str(exc))

    if fc is not None:
        hist_stats = forecast.city_history_stats(forecast_pipeline["history"], fc_city)
        fc_last_year = int(fc["forecast"]["year"].iloc[-1])

        g1, g2, g3, g4 = st.columns(4)
        with g1:
            widgets.metric_card(
                "🏠 参考年房价", f"¥{fc['last_price']:,.0f}",
                sub=f"{fc['province']} · {fc['start_year']}–{DATA_REF_YEAR} 序列",
            )
        with g2:
            widgets.metric_card(
                f"📈 {fc_horizon} 年后中位房价", f"¥{fc['future_point']:,.0f}",
                sub=f"机器学习递归预测（至 {fc_last_year}）",
            )
        with g3:
            low_pct = (fc["future_low"] / fc["last_price"] - 1.0) * 100.0
            high_pct = (fc["future_high"] / fc["last_price"] - 1.0) * 100.0
            widgets.metric_card(
                "📊 预测累计变化", f"{fc['total_change_pct']:+.1f}%",
                sub=f"{low_pct:+.1f}% ~ {high_pct:+.1f}%",
            )
        with g4:
            widgets.metric_card(
                "🧭 预测年均增速", f"{fc['cagr_pct']:+.2f}%/年",
                sub=f"置信水平 {fc['confidence'] * 100:.0f}%",
            )

        widgets.insight_box(
            forecast.build_narrative(fc_city, fc["province"], hist_stats, fc, artifacts)
        )

        f_plot, f_side = st.columns([1.65, 1])
        with f_plot:
            fig = charts.house_trend_forecast_chart(
                fc["hist"], fc["forecast"],
                hist_color=main_color,
                conf=fc["confidence"],
                title=f"「{fc_city}」房价历史走势与机器学习预测（{fc['start_year']}–{fc_last_year}）",
            )
            st.pyplot(fig)
            plt.close(fig)
        with f_side:
            st.markdown("#### 🧠 关键驱动特征（全样本模型）")
            imp_df = artifacts["importance"].head(8).copy()
            imp_df["特征"] = imp_df["feature"].map(forecast.FEATURE_LABELS)
            imp_df = imp_df.sort_values("importance").reset_index(drop=True)
            fig2 = charts.barh_ranking(
                imp_df, "importance", label_col="特征", color="#8b5cf6",
                title="对下一年房价涨幅的贡献",
                xlabel="特征重要性", fmt="{:.3f}", figsize=(6.4, 4.4),
            )
            st.pyplot(fig2)
            plt.close(fig2)
            st.caption("重要性来自全量 248 城面板模型；年份 / 全国动量等宏观特征用于刻画周期。")

        _fc_pct = lambda v: "—" if v is None else f"{v * 100:+.1f}%"

        fc_review, fc_detail = st.columns([1, 1.25])
        with fc_review:
            st.markdown(f"#### 📜 历史回顾（{fc['start_year']}–{DATA_REF_YEAR}）")
            recap_df = pd.DataFrame(
                {
                    "指标": [
                        f"起始年房价（{fc['start_year']}）",
                        f"参考年房价（{DATA_REF_YEAR}）",
                        f"{DATA_REF_YEAR - fc['start_year']} 年年均涨幅",
                        "近 5 年年均涨幅",
                        "近 10 年年均涨幅",
                        "历史年波动率（对数涨幅）",
                    ],
                    "数值": [
                        f"¥{hist_stats['start_price']:,.0f}",
                        f"¥{hist_stats['ref_price']:,.0f}",
                        _fc_pct(hist_stats["cagr_total"]),
                        _fc_pct(hist_stats["cagr_5y"]),
                        _fc_pct(hist_stats["cagr_10y"]),
                        f"{hist_stats['volatility'] * 100:.1f}%",
                    ],
                }
            )
            st.dataframe(recap_df, hide_index=True, width="stretch")

        with fc_detail:
            st.markdown(f"#### 🗓️ 逐年预测明细（{DATA_REF_YEAR + 1}–{fc_last_year}）")
            fc_detail_df = fc["forecast"].copy()
            fc_detail_df.columns = ["年份", "预测房价", "区间下限", "区间上限", "同比涨幅"]
            st.dataframe(
                widgets.fmt_table(
                    fc_detail_df,
                    {"预测房价": "{:,.0f}", "区间下限": "{:,.0f}",
                     "区间上限": "{:,.0f}", "同比涨幅": "{:+.2f}%"},
                    gradient_col="预测房价",
                    cmap="YlOrRd",
                ),
                hide_index=True,
                width="stretch",
            )
            st.download_button(
                "⬇️ 下载预测明细（CSV）",
                data=fc["forecast"].to_csv(index=False).encode("utf-8-sig"),
                file_name=f"{fc_city}房价趋势预测_{DATA_REF_YEAR + 1}-{fc_last_year}.csv",
                mime="text/csv",
            )

        st.caption(
            "注：预测为基于演示数据的机器学习外推，置信区间随预测期延长而变宽；"
            "房价单位为元/㎡，同比涨幅为预测年度涨幅（%）。"
        )

# ===========================================================================
# 第四节：城市幸福度排名
# ===========================================================================

widgets.section_title("😊 城市幸福度排名")

rank_col, table_col = st.columns([1.5, 1])

with rank_col:
    rank_direction = st.radio(
        "查看方向", ["Top N（最高）", "Bottom N（最低）"],
        horizontal=True, key="happy_dir",
    )
    n_cities = widgets.top_n_slider("happiness_n", len(filtered_df))
    if rank_direction.startswith("Top"):
        top_n_happy = analysis.top_n(filtered_df, "happiness", n_cities)
    else:
        top_n_happy = analysis.top_n(filtered_df, "happiness", n_cities, ascending=True)
    chart_data = top_n_happy.sort_values("happiness", ascending=True)

    fig = charts.barh_ranking(
        chart_data, "happiness",
        color=main_color,
        title=f"幸福度 {'Top' if rank_direction.startswith('Top') else 'Bottom'} {n_cities} 城市",
        xlabel=METRIC_UNITS["happiness"],
        fmt="{:.1f}",
    )
    st.pyplot(fig)
    plt.close(fig)

with table_col:
    st.markdown(f"#### 📋 幸福度排名表（{rank_direction[:6]} {n_cities}）")
    st.dataframe(
        _styled_table(
            top_n_happy.sort_values("happiness", ascending=False),
            ["city", "province", "happiness", "income", "house_price",
             "value_index", "composite_score"],
            {"年收入": "{:,.0f}", "房价(元/㎡)": "{:,.0f}", "幸福度": "{:.1f}",
             "可负担指数": "{:.2f}", "综合宜居分": "{:.1f}"},
        ),
        height=420,
    )

# ===========================================================================
# 第五节：住房可负担性指数分析
# ===========================================================================
widgets.section_title("🏠 住房可负担性指数分析")
widgets.insight_box(
    "<strong>💡 住房可负担性指数 = 年收入 ÷ 房价</strong><br>"
    "指数越高，说明该城市居民用年收入能购买的住房面积越大，住房压力相对越小。"
)

aff_col1, aff_col2 = st.columns(2)

with aff_col1:
    st.markdown("### 📊 可负担指数城市排名")
    n_value = widgets.top_n_slider("value_n", len(filtered_df))
    top_n_value = analysis.top_n(filtered_df, "value_index", n_value)
    chart_data = top_n_value.sort_values("value_index", ascending=True)

    fig = charts.barh_ranking(
        chart_data, "value_index",
        color="#f59e0b",
        title=f"住房可负担性 Top {n_value} 城市",
        xlabel=METRIC_UNITS["value_index"],
        fmt="{:.2f}",
    )
    st.pyplot(fig)
    plt.close(fig)

with aff_col2:
    st.markdown("### 📉 全量城市可负担指数分布")
    fig = charts.affordability_overview(filtered_df, color=main_color)
    st.pyplot(fig)
    plt.close(fig)

# ===========================================================================
# 第六节：TOP 20 住房可负担指数详表
# ===========================================================================
widgets.section_title("🏆 住房可负担指数 TOP 20 城市详情")

top20 = analysis.top_n(filtered_df, "value_index", 20)

col_a, col_b = st.columns([1.2, 1])

with col_a:
    st.dataframe(
        _styled_table(
            top20,
            ["city", "province", "happiness", "income", "house_price", "value_index"],
            {"年收入": "{:,.0f}", "房价(元/㎡)": "{:,.0f}", "幸福度": "{:.1f}",
             "可负担指数": "{:.2f}"},
            gradient_col="可负担指数",
            cmap="Greens",
        ),
        width="stretch",
    )

with col_b:
    sorted_top = top20.sort_values("value_index", ascending=True)
    fig = charts.barh_ranking(
        sorted_top, "value_index",
        color="#f59e0b",
        title="TOP 20 住房可负担指数",
        xlabel=METRIC_UNITS["value_index"],
        fmt="{:.2f}",
    )
    st.pyplot(fig)
    plt.close(fig)

# ===========================================================================
# 第七节：异常值检测
# ===========================================================================
widgets.section_title("🔍 异常值检测（IQR 方法）")

outlier_happy_mask = analysis.detect_outliers(filtered_df["happiness"])
outlier_value_mask = analysis.detect_outliers(filtered_df["value_index"])
combined_mask = outlier_happy_mask | outlier_value_mask
outlier_df = filtered_df.loc[combined_mask]

st.markdown(
    f"基于 IQR 规则（四分位距法）在**当前 {len(filtered_df)} 个城市**中识别出 "
    f"**{len(outlier_df)} 个异常值城市**（幸福度或可负担指数偏离总体较远）。"
)

out_col1, out_col2 = st.columns(2)
with out_col1:
    fig = charts.outlier_scatter(
        filtered_df, "happiness", "value_index", combined_mask,
        color=main_color,
        xlabel="幸福度指数",
        ylabel="可负担指数",
        title="幸福度 vs 可负担指数（红色为异常值）",
    )
    st.pyplot(fig)
    plt.close(fig)

with out_col2:
    if not outlier_df.empty:
        st.markdown(f"#### 📋 异常值城市明细（{len(outlier_df)} 个）")
        st.dataframe(
            _styled_table(
                outlier_df,
                ["city", "province", "happiness", "income", "house_price",
                 "value_index", "composite_score"],
                {"年收入": "{:,.0f}", "房价(元/㎡)": "{:,.0f}", "幸福度": "{:.1f}",
                 "可负担指数": "{:.2f}", "综合宜居分": "{:.1f}"},
                gradient_col="可负担指数",
                cmap="RdBu_r",
            ),
            height=420,
        )
    else:
        st.info("当前筛选范围内未发现异常值城市。")

with st.expander("📖 异常值检测方法说明"):
    st.markdown(
        "**IQR 方法（Tukey's fence）**：\n\n"
        "1. 计算指标的四分位数 Q1 与 Q3，IQR = Q3 - Q1；\n"
        "2. 判定下界 = Q1 - 1.5×IQR，上界 = Q3 + 1.5×IQR；\n"
        "3. 数值落在区间之外的样本即为异常值。\n\n"
        "本页面对「幸福度」与「可负担指数」两个指标分别检测，任一指标异常即标记。"
    )

# ===========================================================================
# 第八节：省份维度聚合分析
# ===========================================================================
widgets.section_title("🗺️ 省份维度聚合分析")

province_agg = analysis.aggregate_by_province(filtered_df)

prov_col1, prov_col2 = st.columns(2)

with prov_col1:
    st.markdown("### 各省平均幸福度排名")
    top_provinces = province_agg.head(15).sort_values("平均幸福度")

    fig = charts.barh_ranking(
        top_provinces, "平均幸福度",
        label_col="省份",
        color=main_color,
        title="平均幸福度 Top 15 省份",
        xlabel="平均幸福度",
        fmt="{:.1f}",
    )
    st.pyplot(fig)
    plt.close(fig)

with prov_col2:
    st.markdown("### 各省平均可负担指数")
    province_value = province_agg.sort_values("平均可负担指数", ascending=False).head(15)

    fig = charts.barh_ranking(
        province_value.sort_values("平均可负担指数"), "平均可负担指数",
        label_col="省份",
        color="#f59e0b",
        title="平均可负担指数 Top 15 省份",
        xlabel="平均可负担指数",
        fmt="{:.2f}",
    )
    st.pyplot(fig)
    plt.close(fig)

prov_table1, prov_table2 = st.columns(2)
with prov_table1:
    prov_show = province_agg[["省份", "平均幸福度", "城市数量"]].copy()
    prov_show.columns = ["省份", "平均幸福度", "城市数量"]
    prov_show.index = range(1, len(prov_show) + 1)
    st.dataframe(
        widgets.fmt_table(prov_show, {"平均幸福度": "{:.1f}"}),
        height=350,
        width="stretch",
    )
with prov_table2:
    prov_show2 = province_agg[["省份", "平均收入", "平均房价", "平均可负担指数", "城市数量"]].copy()
    prov_show2.index = range(1, len(prov_show2) + 1)
    st.dataframe(
        widgets.fmt_table(
            prov_show2,
            {"平均收入": "{:,.0f}", "平均房价": "{:,.0f}", "平均可负担指数": "{:.2f}"},
            gradient_col="平均可负担指数",
            cmap="Greens",
        ),
        height=350,
        width="stretch",
    )

# ===========================================================================
# 第九节：地理可视化地图（pyecharts 生成的静态 HTML）
# ===========================================================================
if show_maps:
    widgets.section_title("🗺️ 中国城市地理分布地图")
    map_col1, map_col2 = st.columns(2)
    with map_col1:
        st.markdown("### 中国各省市宜居度地图")
        render_map("中国各省市宜居度地图.html", "宜居度地图文件未找到")
    with map_col2:
        st.markdown("### Top50 城市生活价值指数分布")
        render_map("Top50的中国城市生活价值指数分布.html", "城市价值指数地图文件未找到")

# ===========================================================================
# 第十节：完整数据浏览与数据质量报告
# ===========================================================================
widgets.section_title("📋 完整数据浏览")

metadata = data_loader.load_metadata(DATA_DIR)


tab1, tab2, tab3 = st.tabs(["🏙️ 城市明细数据", "🗺️ 省份聚合数据", "✅ 数据质量报告"])

with tab1:
    city_display = filtered_df[
        ["city", "province", "happiness", "income", "house_price",
         "population", "value_index", "composite_score"]
    ].copy()
    city_display.columns = [COLUMN_LABELS[c] for c in city_display.columns]
    city_display = city_display.sort_values("可负担指数", ascending=False).reset_index(drop=True)
    city_display.index = range(1, len(city_display) + 1)

    st.dataframe(
        widgets.fmt_table(
            city_display,
            {"年收入": "{:,.0f}", "房价(元/㎡)": "{:,.0f}", "常住人口(万)": "{:,.0f}",
             "幸福度": "{:.1f}", "可负担指数": "{:.2f}", "综合宜居分": "{:.1f}"},
            gradient_col="可负担指数",
            cmap="YlOrRd",
        ),
        height=500,
    )

    dl_col1, dl_col2, dl_col3 = st.columns(3)
    with dl_col1:
        st.download_button(
            "📥 下载 CSV",
            data=city_display.to_csv(index=False).encode("utf-8-sig"),
            file_name="中国城市生活成本与幸福感数据.csv",
            mime="text/csv",
            width="stretch",
        )
    with dl_col2:
        st.download_button(
            "📥 下载 Excel",
            data=to_excel_bytes(city_display),
            file_name="中国城市生活成本与幸福感数据.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )
    with dl_col3:
        st.download_button(
            "📥 下载 JSON",
            data=city_display.to_json(orient="records", force_ascii=False, indent=2).encode("utf-8"),
            file_name="中国城市生活成本与幸福感数据.json",
            mime="application/json",
            width="stretch",
        )

with tab2:
    st.dataframe(
        widgets.fmt_table(
            province_agg,
            {"平均幸福度": "{:.1f}", "平均收入": "{:,.0f}", "平均房价": "{:,.0f}",
             "常住人口": "{:,.0f}", "平均可负担指数": "{:.2f}", "平均综合宜居分": "{:.1f}"},
            gradient_col="平均幸福度",
            cmap="RdYlGn",
        ),
        height=500,
        width="stretch",
    )

with tab3:
    render_quality_report(quality, metadata)

# ---------------- 页脚 ----------------
widgets.render_footer()