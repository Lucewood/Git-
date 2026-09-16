"""
中国城市生活成本与幸福感分析可视化 —— Streamlit 交互式网页应用

v2.1 结构优化说明
1. 模块化架构：业务逻辑拆分至 src/city_insight 包
   （config / logging_setup / data_loader / analysis / charts / widgets / styles），
   本入口脚本只负责页面编排与章节渲染。
2. 章节函数化：将页面各内容区块拆分为 render_* 局部渲染函数，主流程仅负责
   数据加载、侧边栏筛选、KPI 概览与按序调用各章节，可读性与可维护性显著提升。
3. 健壮性：
   - 图表统一经 render_fig() 输出并在 finally 中自动关闭 figure，杜绝句柄泄漏；
   - 预测 / 地图等依赖外部文件或组件的环节失败时降级为提示，不中断整页；
   - 数值筛选、Top-N、相关性、百分位画像等对空数据 / 零方差 / 极小样本均做了防护；
   - 就业指导章节：引擎结果按「求职画像 + 筛选范围」缓存（st.cache_data），
     支柱产业表缺列 / 字段全空时按维度 0 分降级并给出字段级提示，不抛异常；
   - 表格样式与列格式由 _styled_table() / TABLE_FORMAT 集中管理。
4. 数据管道化：data_loader 提供纯函数加载 + Streamlit 缓存包装，数据签名感知文件变化；
   常住人口、住房可负担指数与综合宜居评分等派生指标口径见 data/metadata.json。
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import sys
import tempfile
from io import BytesIO
from pathlib import Path

# 确保可将 src/ 下的 city_insight 包导入（兼容 streamlit 运行方式）
_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import matplotlib

matplotlib.use("Agg")  # 必须在导入 pyplot 之前设置，规避 GUI 后端

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from city_insight import analysis, career, charts, data_loader, forecast, widgets
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
from city_insight.industry_kb import CATEGORIES, EDUCATION_LEVELS, SKILL_TAGS
from city_insight.logging_setup import setup_logging
from city_insight.styles import CUSTOM_CSS

settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 页面配置（必须是第一个 st 调用）
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title=f"{APP_NAME} v{APP_VERSION}",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
charts.setup_plot_style()

# 城市级表格列格式（键 = COLUMN_LABELS 中文列名），供 _styled_table 统一使用
TABLE_FORMAT: dict[str, str] = {
    "幸福度": "{:.1f}",
    "年收入": "{:,.0f}",
    "房价(元/㎡)": "{:,.0f}",
    "常住人口(万)": "{:,.0f}",
    "可负担指数": "{:.2f}",
    "综合宜居分": "{:.1f}",
}

# 就业推荐表格列格式（键 = COLUMN_LABELS 中文列名）
INDUSTRY_TABLE_FORMAT: dict[str, str] = {
    "就业占比(%)": "{:.1f}",
    "平均月薪(元)": "{:,.0f}",
    "需求景气指数": "{:.1f}",
    "岗位年增速(%)": "{:+.1f}",
    "匹配度": "{:.1f}",
    "技能得分": "{:.0f}",
    "薪资得分": "{:.0f}",
    "发展得分": "{:.0f}",
    "规模得分": "{:.0f}",
    "宜居得分": "{:.0f}",
    "需求热度": "{:.1f}",
    "城市数": "{:,.0f}",
}

# 评分 / 技能相关列 → 中文表头（补足 COLUMN_LABELS 未覆盖的字段）
SCORE_LABELS: dict[str, str] = {
    "skill_score": "技能得分",
    "salary_score": "薪资得分",
    "demand_score": "发展得分",
    "scale_score": "规模得分",
    "life_score": "宜居得分",
    "match_score": "匹配度",
    "matched_skills": "已具备技能",
    "missing_skills": "待补强技能",
    "occupations": "典型岗位",
    "education_gap": "学历差距",
}
# 就业推荐展示 / 导出的统一表头映射
CAREER_LABELS: dict[str, str] = {**COLUMN_LABELS, **SCORE_LABELS}


# ---------------------------------------------------------------------------
# 通用辅助函数（不依赖页面状态的纯逻辑）
# ---------------------------------------------------------------------------
def to_excel_bytes(data: pd.DataFrame) -> bytes:
    """将 DataFrame 序列化为 Excel 字节流。"""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        data.to_excel(writer, index=False, sheet_name="城市数据")
    return buffer.getvalue()


def _stable_digest(text: str) -> str:
    """HTML 内容稳定摘要（用于生成可复用的临时文件名，避免 hash() 随机化）。"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:16]


def render_fig(fig: plt.Figure | None) -> None:
    """渲染 matplotlib 图，并在 finally 中自动关闭 figure 释放内存。

    即使 st.pyplot 抛出异常也会执行 plt.close(fig)，防止句柄泄漏。
    """
    if fig is None:
        return
    try:
        st.pyplot(fig)
    finally:
        plt.close(fig)


def _styled_table(
    df: pd.DataFrame,
    columns: list[str],
    fmt_dict: dict[str, str] | None = None,
    gradient_col: str | None = None,
    cmap: str | None = None,
):
    """选取列 → 中文列名 → 1 起始索引，并统一套用表格样式。

    fmt_dict 仅保留与实际列匹配的键，列集合变化时不会触发 Styler 异常。
    """
    display = df[columns].copy()
    display.columns = [COLUMN_LABELS[c] for c in columns]
    display.index = range(1, len(display) + 1)
    fmt = {k: v for k, v in (fmt_dict or TABLE_FORMAT).items() if k in display.columns}
    return widgets.fmt_table(display, fmt, gradient_col=gradient_col, cmap=cmap)


def _means(df: pd.DataFrame) -> dict[str, float]:
    """筛选范围常用汇总量（供 KPI 卡片与城市画像“均值列”使用）。"""
    return {
        "happiness": float(df["happiness"].mean()),
        "income": float(df["income"].mean()),
        "house_price": float(df["house_price"].mean()),
        "population": float(df["population"].mean()),
        "value_index": float(df["value_index"].mean()),
        "composite_score": float(df["composite_score"].mean()),
        "population_sum": float(df["population"].sum()),
    }


def _city_label_mapper(province_map: dict[str, str]):
    """返回 selectbox format_func：显示为“城市（省份）”。"""
    return lambda c: f"{c}（{province_map.get(c, '-')}）"


def _num_text(value: object, fmt: str, fallback: str = "—") -> str:
    """数值 → 文本；缺失 / 非法值统一显示 fallback，避免页面出现 nan 字样。"""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(number):
        return fallback
    return fmt.format(number)

# ---------------------------------------------------------------------------
# 地图 / 数据质量 / 预测流水线组件
# ---------------------------------------------------------------------------
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

    说明：Streamlit 1.37+ 官方推荐使用 st.iframe（取代已弃用的
    st.components.v1.html），可自动识别 HTML 字符串 / 本地文件。
    """
    html = load_map_html(file_name)
    if html is None:
        st.warning(fallback_msg)
        return
    height = height or settings.default_map_height
    try:
        if settings.map_render_mode == "iframe":
            # 写入稳定临时文件供 iframe 引用；文件名由内容摘要决定，内容不变即可复用。
            # 先写带进程号的临时文件再原子替换，避免多会话并发时读到半截 HTML。
            tmp = Path(tempfile.gettempdir()) / f"city_map_{_stable_digest(html)}.html"
            if not tmp.exists():
                tmp_partial = tmp.with_name(f"{tmp.name}.{os.getpid()}.tmp")
                tmp_partial.write_text(html, encoding="utf-8")
                os.replace(tmp_partial, tmp)
            st.iframe(src=tmp, height=height)
        else:
            st.iframe(html, height=height)
    except Exception as exc:  # noqa: BLE001 - 组件失败不应中断页面
        logger.warning("地图组件渲染失败（%s），已降级为链接提示。", exc)
        st.warning(
            f"{fallback_msg}（组件渲染失败，可直接打开 notebooks/ 下对应文件查看）"
        )


def render_quality_report(q: dict, metadata: dict) -> None:
    """渲染数据质量报告（完整数据浏览 · 第三个 Tab）。"""
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
                pd.DataFrame(summary_rows), hide_index=True, width="stretch"
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

# ===========================================================================
# 章节渲染函数（每个函数对应页面一个内容区块，按主流程顺序调用）
# ===========================================================================
def render_association(filtered_df: pd.DataFrame, main_color: str) -> None:
    """第一节：核心指标关联分析。"""
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
        render_fig(fig)

        corr_income = analysis.safe_corr(
            filtered_df["income"], filtered_df["happiness"]
        )
        widgets.insight_box(
            "<strong>📊 相关性洞察：</strong> "
            + analysis.corr_summary_text(
                corr_income, 0.3,
                "表明收入与幸福度存在较强的正相关关系",
                "表明收入与幸福度的相关性较弱",
            )
        )

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
        render_fig(fig)

        corr_house = analysis.safe_corr(
            filtered_df["house_price"], filtered_df["happiness"]
        )
        widgets.insight_box(
            "<strong>📊 相关性洞察：</strong> "
            + analysis.corr_summary_text(
                corr_house, 0.5,
                "高房价确实带来了更高的幸福感",
                "高房价并不意味着更高的幸福感",
            )
        )

    col_hm, col_dist = st.columns([1.15, 1])
    with col_hm:
        st.markdown("### 指标相关性矩阵")
        if len(filtered_df) >= 3:
            render_fig(charts.correlation_heatmap(filtered_df, METRIC_COLS))
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
            render_fig(fig)
        else:
            st.info("筛选后的样本量不足，无法绘制分布图。")

def render_city_comparison(
    filtered_df: pd.DataFrame,
    main_color: str,
    province_map: dict[str, str],
) -> None:
    """第二节：城市对比与画像。"""
    widgets.section_title("🔬 城市对比与画像")

    city_options = filtered_df["city"].tolist()
    fmt_city = _city_label_mapper(province_map)

    cmp_col, profile_col = st.columns([1.3, 1])
    with cmp_col:
        st.markdown("### 🆚 多城市指标对比")
        max_cities = settings.max_comparison_cities
        default_cities = [c for c in ("北京", "上海", "成都", "长沙") if c in set(city_options)]
        selected_cities = st.multiselect(
            f"选择 2-{max_cities} 个城市进行对比",
            options=city_options,
            default=default_cities,
            key="cmp_cities",
            format_func=fmt_city,
        )

    with profile_col:
        st.markdown("### 🧭 城市画像")
        profile_city = st.selectbox(
            "选择城市查看指标画像",
            options=city_options,
            key="profile_city",
            format_func=fmt_city,
        )

    if len(selected_cities) >= 2:
        fig = charts.city_comparison(
            filtered_df, selected_cities, METRIC_COLS, color=main_color
        )
        render_fig(fig)
    elif selected_cities:
        st.info("请至少选择 2 个城市以进行对比。")

    if profile_city:
        _render_city_profile(filtered_df, profile_city, main_color)


def _render_city_profile(
    filtered_df: pd.DataFrame, profile_city: str, main_color: str
) -> None:
    """渲染单个城市的指标画像（百分位卡片 + 画像图 + 明细表）。"""
    row = filtered_df[filtered_df["city"] == profile_city].iloc[0]
    # 六个指标百分位一次批量 rank（等价于逐列 rank，但只需一次向量化计算）
    pct = (
        filtered_df[list(METRIC_COLS)].rank(pct=True) * 100.0
    ).loc[row.name].astype(float)

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    profile_cards = [
        ("😊 幸福度", f"{row['happiness']:.1f}", f"领先 {pct['happiness']:.0f}% 城市"),
        ("💰 年收入", f"{row['income'] / 10000:.1f}万", f"领先 {pct['income']:.0f}% 城市"),
        ("🏠 房价", f"{row['house_price']:.0f}", f"领先 {pct['house_price']:.0f}% 城市"),
        ("👥 人口", f"{row['population']:.0f}万", f"领先 {pct['population']:.0f}% 城市"),
        ("📈 可负担指数", f"{row['value_index']:.2f}", f"领先 {pct['value_index']:.0f}% 城市"),
        ("🌟 综合宜居分", f"{row['composite_score']:.1f}",
         f"领先 {pct['composite_score']:.0f}% 城市"),
    ]
    for col, (title, value, sub) in zip(
        (m1, m2, m3, m4, m5, m6), profile_cards
    ):
        with col:
            widgets.metric_card(title, value, sub=sub)

    col_profile, col_detail = st.columns([1, 1.2])
    with col_profile:
        render_fig(charts.city_profile_chart(pct, color=main_color))
    with col_detail:
        stats = _means(filtered_df)
        st.markdown(
            f"#### 📋 {profile_city} 数据一览（筛选范围：{len(filtered_df)} 个城市）"
        )
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
                f"{stats['happiness']:.1f}",
                f"¥{stats['income']:,.0f}",
                f"¥{stats['house_price']:,.0f}",
                f"{stats['population']:,.0f} 万",
                f"{stats['value_index']:.2f}",
                f"{stats['composite_score']:.1f}",
            ],
        })
        st.dataframe(detail, hide_index=True, width="stretch")

def render_forecast(
    all_df: pd.DataFrame,
    main_color: str,
    province_map: dict[str, str],
) -> None:
    """第三节：房价趋势分析与机器学习预测。"""
    widgets.section_title("🤖 房价趋势分析与机器学习预测")

    with st.expander("📖 预测方法论与数据口径说明", expanded=False):
        st.markdown(
            f"**机器学习策略：全样本城市面板 + 递归多步预测**\n\n"
            f"1. **历史数据**：`data/house_price_history.csv` 提供 2005–{DATA_REF_YEAR} 年各城市年度住房均价"
            f"（{DATA_REF_YEAR} 年与房价快照完全一致；历史序列按演示口径重建，非官方统计）；\n"
            f"2. **特征工程**：对每个「城市 × 年份」样本构造滞后涨幅（1/3/5 年）、长期年均涨幅、"
            f"涨幅波动率、房价收入比（历年收入用宏观工资增速近似）与城市收入 / 人口等静态基本面，"
            f"并加入「全国上一年平均涨幅」刻画宏观周期；\n"
            f"3. **中心化建模与滚动验证**：目标 = 下一年城市涨幅 − 全国同期涨幅（去除共同"
            f"宏观冲击），用梯度提升回归树（scikit-learn GradientBoosting；未安装时自动回退 "
            f"numpy 岭回归）拟合。采用 expanding walk-forward（滚动扩展窗口）评估："
            f"对最近 3 个验证年逐年重训并外推，各验证年模型不接触当年及以后数据，"
            f"严格避免前瞻偏差，逐年生模型留存用于下方「外样本回测」；\n"
            f"4. **递归外推**：以 {DATA_REF_YEAR} 年价格为起点逐年滚动预测（预测期年份特征被"
            f"钳制在训练域内，避免树模型外推抖动），预测值 = 模型预测偏离 + 全国涨幅宏观情景"
            f"（可在下方切换保守 / 基准 / 乐观），并按验证残差标准差"
            f"给出 {forecast.DEFAULT_CONF * 100:.0f}% 置信区间。\n\n"
            f"> ⚠️ 数据为演示合成口径（见 data/metadata.json），预测仅用于展示机器学习建模流程，"
            f"不构成任何投资 / 购房建议。"
        )

    # 构建 / 训练预测流水线（模型跨 rerun 缓存，仅在数据变化时重训）
    pipeline = None
    try:
        pipeline = _load_forecast_pipeline(
            data_loader.data_signature(DATA_DIR, (forecast.HISTORY_FILE,)), DATA_DIR
        )
    except FileNotFoundError as exc:
        st.warning(f"房价历史数据缺失，无法进行趋势预测：{exc}")

    artifacts = (pipeline or {}).get("artifacts")
    model_ready = artifacts is not None and (
        artifacts.get("model") is not None or artifacts.get("ridge") is not None
    )
    if not model_ready:
        st.info(
            "预测引擎暂不可用：请确认 data/house_price_history.csv 存在，"
            f"且包含 2005–{DATA_REF_YEAR} 完整历史序列。"
        )
        return

    fc_metrics = artifacts["metrics"]
    fmt_city = _city_label_mapper(province_map)

    fc_ctrl, fc_meta = st.columns([1.25, 1])
    with fc_ctrl:
        fc_city_options = all_df["city"].tolist()
        # 下拉框默认值使用“选项列表中的位置”，避免依赖 DataFrame 索引标签
        default_index = (
            fc_city_options.index("北京") if "北京" in fc_city_options else 0
        )
        fc_city = st.selectbox(
            "🏙️ 选择要预测的城市",
            options=fc_city_options,
            index=default_index,
            key="fc_city",
            format_func=fmt_city,
        )
        fc_horizon = st.slider(
            f"📅 预测年数（自 {DATA_REF_YEAR + 1} 年起）",
            1, forecast.MAX_HORIZON, forecast.DEFAULT_HORIZON, key="fc_horizon",
        )
        fc_scenario_label = st.radio(
            "🎚️ 全国宏观情景（以近一年走势为基准，±1.5 个百分点）",
            options=(
                "保守（下调 1.5 个百分点）",
                "基准（延续近一年走势）",
                "乐观（上调 1.5 个百分点）",
            ),
            index=1, horizontal=True, key="fc_scenario",
        )
        fc_macro_adj = {
            "保守（下调 1.5 个百分点）": -0.015,
            "基准（延续近一年走势）": None,
            "乐观（上调 1.5 个百分点）": 0.015,
        }[fc_scenario_label]
    with fc_meta:
        st.markdown("##### 🧠 模型概况")
        backend_name = forecast.MODEL_NAMES.get(artifacts["backend"], artifacts["backend"])
        st.markdown(
            f"- **算法**：{backend_name}\n"
            f"- **训练样本（逐年累计）/ 验证**：{fc_metrics['train_samples']:,} / "
            f"{fc_metrics['test_samples']:,} 条\n"
            f"- **验证方式**：walk-forward 逐年重训（{fc_metrics['test_years'][0]}–"
            f"{fc_metrics['test_years'][1]} 年各外推 1 年）\n"
            f"- **外样本 RMSE / R²**：{fc_metrics['rmse'] * 100:.1f}% / {fc_metrics['r2']:.2f}，"
            f"方向命中率 {fc_metrics['hit_rate'] * 100:.0f}%"
        )

    # 递归预测（单城市失败不中断整页）
    fc = None
    try:
        fc = forecast.forecast_city(
            pipeline, fc_city, horizon=int(fc_horizon), macro_adj=fc_macro_adj
        )
    except Exception as exc:  # noqa: BLE001 - 预测失败仅提示并记录日志
        logger.exception("城市「%s」房价预测失败", fc_city)
        st.warning(f"城市「{fc_city}」预测失败：{exc}")

    if fc is None:
        return
    fc["macro_adj"] = fc_macro_adj
    fc["scenario_label"] = fc_scenario_label
    _render_forecast_result(fc, fc_city, fc_horizon, artifacts, pipeline, main_color)
    _render_forecast_validation(pipeline, fc_city, main_color)

def _render_forecast_result(
    fc: dict,
    fc_city: str,
    fc_horizon: int,
    artifacts: dict,
    pipeline: dict,
    main_color: str,
) -> None:
    """渲染单城市预测结果（KPI、走势图、特征重要性、逐年明细表）。"""
    try:
        hist_stats = forecast.city_history_stats(pipeline["history"], fc_city)
    except ValueError as exc:
        logger.warning("城市历史回顾统计失败：%s", exc)
        hist_stats = None
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

    if hist_stats is not None:
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
        render_fig(fig)
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
        render_fig(fig2)
        st.caption("重要性来自全量 248 城面板模型；年份 / 全国动量等宏观特征用于刻画周期。")

    def _fmt_pct(value: float | None) -> str:
        return "—" if value is None else f"{value * 100:+.1f}%"

    fc_review, fc_detail = st.columns([1, 1.25])
    with fc_review:
        st.markdown(f"#### 📜 历史回顾（{fc['start_year']}–{DATA_REF_YEAR}）")
        if hist_stats is not None:
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
                        _fmt_pct(hist_stats["cagr_total"]),
                        _fmt_pct(hist_stats["cagr_5y"]),
                        _fmt_pct(hist_stats["cagr_10y"]),
                        f"{hist_stats['volatility'] * 100:.1f}%",
                    ],
                }
            )
            st.dataframe(recap_df, hide_index=True, width="stretch")
        else:
            st.info("暂无该城市的历史回顾统计。")

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

def _render_forecast_validation(
    pipeline: dict, fc_city: str, main_color: str
) -> None:
    """渲染“模型验证与外样本回测”折叠面板（逐年指标 + 选定城市回测）。"""
    artifacts = pipeline["artifacts"]
    folds = artifacts.get("folds") or []
    with st.expander("🎯 模型验证与外样本回测（walk-forward）", expanded=False):
        st.markdown(
            "**无前瞻验证**：对每个验证年，用截止其上一年（含）的真实数据重新训练模型"
            "并外推下一年，验证集不参与训练。下方指标为逐年重训后在外样本上聚合得到，"
            "可视为模型真实外推能力的估计。"
        )
        if folds:
            st.markdown("##### 📐 逐年外样本指标（验证年 → 预测下一年）")
            fv = pd.DataFrame(folds)
            view = pd.DataFrame({
                "预测年度": fv["target_year"],
                "验证样本": fv["test_samples"],
                "RMSE(%)": (fv["rmse"] * 100.0).round(2),
                "MAE(%)": (fv["mae"] * 100.0).round(2),
                "R²": fv["r2"].round(3),
                "方向命中率(%)": (fv["hit_rate"] * 100.0).round(1),
                "偏离RMSE(%)": (fv["rmse_dev"] * 100.0).round(2),
                "偏离R²": fv["r2_dev"].round(3),
            })
            st.dataframe(
                widgets.fmt_table(
                    view,
                    {"RMSE(%)": "{:.2f}", "MAE(%)": "{:.2f}", "R²": "{:.3f}",
                     "方向命中率(%)": "{:.1f}", "偏离RMSE(%)": "{:.2f}",
                     "偏离R²": "{:.3f}"},
                    gradient_col="R²",
                    cmap="RdYlGn",
                ),
                hide_index=True,
                width="stretch",
            )
            st.caption(
                "RMSE / MAE / R² / 命中率基于「下一年实际涨幅」口径（验证期全国涨幅按当年"
                "真实值计入）；带“偏离”前缀的同名指标去掉全国共同涨落后、仅评估城市偏离"
                "部分的预测能力，与模型的目标空间一致。"
            )
        else:
            st.info("当前流水线未启用逐年 walk-forward 验证（可能是旧版工件）。")

        st.markdown(f"#### 🧭 「{fc_city}」逐年外样本回测（预测 vs 实际）")
        try:
            bt = forecast.city_backtest(pipeline, fc_city)
        except (ValueError, RuntimeError) as exc:
            st.info(f"该城市暂无可用的回测结果：{exc}")
            return

        mape = float(bt["error_pct"].abs().mean())
        max_abs = float(bt["error_pct"].abs().max())
        v_col1, v_col2, v_col3 = st.columns(3)
        v_col1.metric("回测年份数", f"{len(bt)} 年")
        v_col2.metric("平均绝对相对误差", f"{mape:.1f}%")
        v_col3.metric("最大绝对误差", f"{max_abs:.1f}%")

        v_plot, v_tab = st.columns([1.55, 1])
        with v_plot:
            fig = charts.house_backtest_chart(
                pipeline["history"], bt,
                conf=forecast.DEFAULT_CONF,
                title=f"「{fc_city}」walk-forward 外样本回测",
            )
            render_fig(fig)
            st.caption(
                "回测口径：各验证年使用“截止上一年的模型”外推一个年度；验证期的全国涨幅取"
                "当年真实值，用于单独衡量机器学习“城市偏离”部分的预测力（不含宏观情景假设）。"
            )
        with v_tab:
            bt_view = bt.copy()
            bt_view.columns = [
                "年份", "上一年房价", "预测", "区间下限", "区间上限", "实际", "相对误差(%)"
            ]
            st.dataframe(
                widgets.fmt_table(
                    bt_view,
                    {"上一年房价": "{:,.0f}", "预测": "{:,.0f}",
                     "区间下限": "{:,.0f}", "区间上限": "{:,.0f}",
                     "实际": "{:,.0f}", "相对误差(%)": "{:+.1f}"},
                    gradient_col="相对误差(%)",
                    cmap="RdBu_r",
                ),
                hide_index=True,
                width="stretch",
            )
            st.caption("房价单位：元/㎡；相对误差 =（预测 ÷ 实际 − 1）× 100%。")



def render_happiness_ranking(
    filtered_df: pd.DataFrame, main_color: str
) -> None:
    """第四节：城市幸福度排名。"""
    widgets.section_title("😊 城市幸福度排名")

    rank_col, table_col = st.columns([1.5, 1])

    with rank_col:
        rank_direction = st.radio(
            "查看方向", ["Top N（最高）", "Bottom N（最低）"],
            horizontal=True, key="happy_dir",
        )
        n_cities = widgets.top_n_slider("happiness_n", len(filtered_df))
        ascending = rank_direction.startswith("Bottom")
        top_n_happy = analysis.top_n(
            filtered_df, "happiness", n_cities, ascending=ascending
        )
        chart_data = top_n_happy.sort_values("happiness", ascending=True)

        fig = charts.barh_ranking(
            chart_data, "happiness",
            color=main_color,
            title=f"幸福度 {'Top' if not ascending else 'Bottom'} {n_cities} 城市",
            xlabel=METRIC_UNITS["happiness"],
            fmt="{:.1f}",
        )
        render_fig(fig)

    with table_col:
        st.markdown(f"#### 📋 幸福度排名表（{rank_direction[:6]} {n_cities}）")
        st.dataframe(
            _styled_table(
                top_n_happy.sort_values("happiness", ascending=False),
                ["city", "province", "happiness", "income", "house_price",
                 "value_index", "composite_score"],
            ),
            height=420,
        )


def render_affordability(filtered_df: pd.DataFrame, main_color: str) -> None:
    """第五节：住房可负担性指数分析。"""
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
        render_fig(fig)

    with aff_col2:
        st.markdown("### 📉 全量城市可负担指数分布")
        fig = charts.affordability_overview(filtered_df, color=main_color)
        render_fig(fig)

def render_top20(filtered_df: pd.DataFrame) -> None:
    """第六节：TOP 20 住房可负担指数详表。"""
    widgets.section_title("🏆 住房可负担指数 TOP 20 城市详情")

    top20 = analysis.top_n(filtered_df, "value_index", 20)

    col_a, col_b = st.columns([1.2, 1])

    with col_a:
        st.dataframe(
            _styled_table(
                top20,
                ["city", "province", "happiness", "income", "house_price",
                 "value_index"],
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
        render_fig(fig)


def render_outliers(filtered_df: pd.DataFrame, main_color: str) -> None:
    """第七节：异常值检测（IQR 方法）。"""
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
        render_fig(fig)

    with out_col2:
        if not outlier_df.empty:
            st.markdown(f"#### 📋 异常值城市明细（{len(outlier_df)} 个）")
            st.dataframe(
                _styled_table(
                    outlier_df,
                    ["city", "province", "happiness", "income", "house_price",
                     "value_index", "composite_score"],
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
# 就业指导与产业推荐（数据来自 scripts/crawl_industry.py 的爬虫管道）
# ===========================================================================
# 技能供需缺口分析取数条数（「已具备」与「待补强」各取该数量）
SKILL_GAP_TOP_N = 12
# 行业大类横向对比 / 单城市产业结构的图表展示条数
CAREER_COMPARE_TOP = 15
CAREER_STRUCTURE_TOP = 10
# 推荐明细的多维视图：视图名 → 字段顺序（表头由 CAREER_LABELS 统一映射）
CAREER_DETAIL_VIEWS: dict[str, tuple[str, ...]] = {
    "📋 推荐总览": (
        "city", "province", "industry", "category", "avg_salary",
        "demand_index", "growth_pct", "share_pct", "match_score",
    ),
    "🎯 五维得分": (
        "city", "province", "industry", "category", "skill_score",
        "salary_score", "demand_score", "scale_score", "life_score", "match_score",
    ),
    "🧩 技能与岗位": (
        "city", "province", "industry", "education", "education_gap",
        "skills", "matched_skills", "missing_skills", "occupations", "match_score",
    ),
}


@st.cache_data(show_spinner=False, max_entries=16)
def career_engine_cached(
    profile_key: tuple,
    industry_df: pd.DataFrame,
    city_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """缓存就业推荐引擎结果（画像 / 筛选范围 / 数据文件变化时自动失效）。

    打分与城市聚合是全页较重的纯计算环节，缓存后调整其它控件（配色主题、
    地图开关等）无需重复计算；Streamlit 按参数值做哈希，profile_key 由
    career.profile_key() 生成（仅含参与打分的字段，且与勾选顺序无关）。

    Returns:
        (scored 明细推荐表, city_rank 城市级推荐表)
    """
    profile = career.profile_from_key(profile_key)
    scored = career.score_industries(profile, industry_df, city_df)
    city_rank = career.rank_cities(scored, top_n=profile.top_n, city_df=city_df)
    return scored, city_rank


@st.cache_data(show_spinner=False, max_entries=16)
def career_skill_gap_cached(
    profile_key: tuple,
    industry_df: pd.DataFrame,
    top_n: int = SKILL_GAP_TOP_N,
) -> dict[str, pd.DataFrame]:
    """缓存技能供需缺口分析结果（与个性化推荐共用同一求职画像）。"""
    profile = career.profile_from_key(profile_key)
    return career.skill_gap_analysis(profile, industry_df, top_n=top_n)


def _education_gap_text(value: object) -> str:
    """学历门槛差距 → 可读文本（达标 / 需高 N 档 / 超出 N 档）。"""
    try:
        gap = int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"
    if gap > 0:
        return f"需高 {gap} 档"
    if gap < 0:
        return f"超出 {-gap} 档"
    return "达标"


def _career_detail_view(rows: pd.DataFrame, fields: tuple[str, ...]) -> pd.DataFrame:
    """按视图字段构造推荐明细展示表（中文表头 + 1 起始序号 + 语义化学历差距）。"""
    available = [field for field in fields if field in rows.columns]
    data = rows[available].copy()
    if "education_gap" in data.columns:
        data["education_gap"] = data["education_gap"].map(_education_gap_text)
    if "occupations" in data.columns:
        data["occupations"] = data["occupations"].fillna("").replace("", "（暂无口径）")
    data = data.rename(columns=CAREER_LABELS)
    data.index = range(1, len(data) + 1)
    return data


def _render_career_health(health: dict) -> None:
    """支柱产业字段可用性提示（仅在字段缺失 / 全空时展示，说明降级原因）。"""
    issues: list[str] = []
    if health.get("missing_columns"):
        issues.append("缺失字段：" + "、".join(f"`{c}`" for c in health["missing_columns"]))
    if health.get("blank_columns"):
        issues.append("无内容字段：" + "、".join(f"`{c}`" for c in health["blank_columns"]))
    if health.get("empty_numeric_columns"):
        issues.append(
            "全空数值字段：" + "、".join(f"`{c}`" for c in health["empty_numeric_columns"])
        )
    if not issues:
        return
    st.warning(
        "⚠️ 支柱产业数据字段不完整（"
        + "；".join(issues)
        + "），相关维度在推荐中按 0 分计入。请重新运行 `python scripts/crawl_industry.py`"
        f" 生成完整的 `data/industry.csv`（当前可用 {health.get('rows', 0)} 条记录）。"
    )


def render_career_guidance(
    filtered_df: pd.DataFrame,
    industry_df: pd.DataFrame,
    main_color: str,
    province_map: dict[str, str],
) -> None:
    """第十一节：就业指导与产业推荐（基于爬取的城市支柱产业数据库）。"""
    widgets.section_title("🧭 就业指导与产业推荐")

    if industry_df is None or industry_df.empty:
        st.info(
            "未找到支柱产业数据（`data/industry.csv`），就业指导功能暂不可用。\n\n"
            "请先在项目根目录执行数据管道 `python scripts/crawl_industry.py`，"
            "爬取城市支柱产业数据后刷新本页。"
        )
        return

    health = data_loader.industry_health(industry_df)
    _render_career_health(health)
    _render_career_methodology(industry_df, filtered_df, health)

    profile = _render_career_profile_form()
    st.caption(
        f"🎯 推荐范围为侧边栏筛选结果（当前 {len(filtered_df)} 个城市 × "
        f"{health['categories']} 个行业大类）；"
        "在左侧「分析控制面板」切换省份或数值区间即可改变推荐范围。"
    )

    try:
        scored, city_rank = career_engine_cached(
            career.profile_key(profile), industry_df, filtered_df
        )
    except Exception as exc:  # noqa: BLE001 - 推荐失败仅提示，不中断整页
        logger.exception("就业推荐引擎执行失败")
        st.error(
            f"就业推荐计算失败：{exc}；"
            "请检查 `data/industry.csv` 字段完整性后刷新页面。"
        )
        return

    if scored.empty:
        st.warning(
            "当前筛选范围内没有可匹配的支柱产业记录，"
            "请放宽筛选条件或清空「期望行业大类」后重试。"
        )
        return

    tab_personal, tab_city, tab_skill = st.tabs(
        ["🎯 个性化推荐", "🏙️ 城市产业全景", "🧩 技能需求图谱"]
    )
    with tab_personal:
        _render_career_recommendations(profile, scored, city_rank, main_color)
    with tab_city:
        _render_career_city_panorama(
            profile, scored, city_rank, industry_df, main_color, province_map
        )
    with tab_skill:
        _render_career_skill_map(profile, industry_df, main_color)


def _render_career_methodology(
    industry_df: pd.DataFrame, filtered_df: pd.DataFrame, health: dict
) -> None:
    """渲染「数据来源 / 爬虫口径 / 推荐模型」说明面板。"""
    with st.expander("📖 数据来源、爬虫口径与推荐模型说明", expanded=False):
        st.markdown(
            "**1️⃣ 支柱产业数据库（爬虫管道产出）**\n\n"
            "- 数据管道：`python scripts/crawl_industry.py`（两阶段）\n"
            "  ① *snapshot*：把种子口径渲染成 8 个区域「支柱产业与人才需求统计快报」"
            "HTML 页面（`data/raw/industry/`），模拟公开统计网页结构；\n"
            "  ② *crawl*：用 `city_insight.crawler` 的礼貌抓取器抓取这些页面——"
            "自定义 User-Agent 标识身份、robots.txt 准入检查、同域请求限速、"
            "失败指数退避重试、响应按 URL 摘要落盘缓存，再由 "
            "BeautifulSoup（缺失时回退 stdlib `html.parser`）解析表格，"
            "最后清洗规范化写入 `data/industry.csv`。\n"
            "- 合规与可复现：默认只抓取仓库内置离线快照（`file://`），"
            "不产生对外网络请求；如需对接真实公开统计站点，用 "
            "`--url https://...` 追加数据源，并请先确认站点 robots.txt 与使用条款。\n\n"
            "**2️⃣ 字段口径**（口径说明见 `data/metadata.json`）\n\n"
            "| 字段 | 含义 |\n| --- | --- |\n"
            f"| 支柱产业 / 行业大类 | 具体产业名录与其所属行业大类（共 {len(CATEGORIES)} 类） |\n"
            "| 就业占比(%) | 该产业从业人员占城镇就业的比重（演示口径） |\n"
            "| 平均月薪(元) | 该产业岗位中位月薪，按城市收入水平缩放 |\n"
            "| 需求景气指数 | 人才需求热度（0-100，越高越缺人） |\n"
            "| 岗位年增速(%) | 近年岗位数量年均变化 |\n"
            "| 学历门槛 / 核心技能 | 岗位典型学历要求与产业核心技能标签 |\n\n"
            "**3️⃣ 推荐打分模型**（可解释的加权模型，权重可在下方滑块调整）\n\n"
            "```\n"
            "匹配度 = 100 × 学历修正 × Σ wᵢ·sᵢ / Σ wᵢ\n"
            "```\n"
            "- **技能匹配**：你的技能对「该产业核心技能」的覆盖率；\n"
            "- **薪资待遇**：min(产业平均月薪 ÷ 期望月薪, 1.2) ÷ 1.2；\n"
            "- **发展空间**：需求景气指数（权重 0.6）+ 岗位增速百分位（权重 0.4）；\n"
            "- **岗位规模**：该产业就业占比在候选集中的百分位；\n"
            "- **生活宜居**：城市幸福度 / 可负担指数 / 房价压力百分位合成"
            "（勾选「优先低生活成本」会加大可负担与房价权重）；\n"
            "- **学历修正**：学历低于岗位门槛时每档折减 6%（0.94^档差）。\n\n"
            "**4️⃣ 结果视图**\n\n"
            "- 「🎯 五维得分」逐项展示各维度子得分（0-100）与最终匹配度；\n"
            "- 「🧩 技能与岗位」给出学历门槛差距、已具备 / 待补强技能与典型岗位方向；\n"
            "- 推荐明细与城市级推荐均可导出 CSV，便于线下二次分析。\n\n"
            f"> 当前库覆盖 **{health['cities']} 个城市 / {health['rows']} 条"
            f"「城市 × 支柱产业」记录**（{health['categories']} 个行业大类），"
            f"本次推荐候选为筛选后的 {len(filtered_df)} 个城市。\n"
            "> ⚠️ 产业数据为演示口径合成数据（非官方统计），推荐结果仅用于展示分析流程，"
            "不构成任何求职 / 报考建议。"
        )


def _render_career_profile_form() -> career.CareerProfile:
    """渲染求职画像表单（学历 / 期望薪资 / 技能 / 偏好权重），返回 CareerProfile。"""
    st.markdown("### 🧑‍🎓 求职画像（调整后推荐结果实时刷新）")
    col_basic, col_skill, col_weight = st.columns([1, 1.25, 1])

    with col_basic:
        education = st.selectbox(
            "最高学历",
            options=list(EDUCATION_LEVELS),
            index=list(EDUCATION_LEVELS).index(career.DEFAULT_EDUCATION),
            key="career_education",
        )
        target_salary = st.slider(
            "期望月薪（元/月）", 3000, 40000, 12000, step=500, key="career_salary"
        )
        prefer_low_cost = st.toggle(
            "优先考虑低生活成本城市", value=False, key="career_low_cost",
            help="开启后会提高「可负担指数」与「低房价」在宜居维度中的权重",
        )
        max_results = max(5, int(settings.max_career_results))
        top_n = st.slider(
            "展示推荐条数", 5, max_results,
            min(max(settings.career_top_n, 5), max_results),
            key="career_top_n",
        )

    with col_skill:
        skills = st.multiselect(
            "技能标签（可多选；选得越准，技能匹配维度越可靠）",
            options=list(SKILL_TAGS),
            default=[tag for tag in ("Python", "数据分析") if tag in SKILL_TAGS],
            key="career_skills",
            help=f"标签来自 {len(CATEGORIES)} 个行业大类的核心技能库（industry_kb.SKILL_TAGS）",
        )
        categories = st.multiselect(
            "期望行业大类（留空 = 不限）",
            options=list(CATEGORIES),
            default=[],
            key="career_categories",
        )

    with col_weight:
        st.markdown("**偏好权重**（0-5，越大越看重）")
        weights: dict[str, float] = {}
        for key, label in career.WEIGHT_LABELS.items():
            # 步长 0.5 + 浮点默认值：滑块初值与 career.DEFAULT_WEIGHTS 完全一致
            weights[key] = float(
                st.slider(
                    label, 0.0, 5.0, float(career.DEFAULT_WEIGHTS[key] * 10),
                    step=0.5, key=f"career_w_{key}",
                )
            )

    return career.CareerProfile(
        skills=tuple(skills),
        education=education,
        target_salary=float(target_salary),
        categories=tuple(categories),
        weights=weights,
        prefer_low_cost=bool(prefer_low_cost),
        top_n=int(top_n),
    )


# 匹配度构成图的维度定义：(权重键, 子得分列, 中文名)
CONTRIBUTION_DIMS: tuple[tuple[str, str, str], ...] = (
    ("skill", "skill_score", "技能匹配"),
    ("salary", "salary_score", "薪资待遇"),
    ("growth", "demand_score", "发展空间"),
    ("scale", "scale_score", "岗位规模"),
    ("life", "life_score", "生活宜居"),
)


def _career_contributions(
    profile: career.CareerProfile, frame: pd.DataFrame
) -> pd.DataFrame:
    """把各维度子得分按权重折算为「加权得分贡献」，供堆叠条形图使用。"""
    weights = profile.normalized_weights
    data = frame.copy()
    data["推荐项"] = data["city"].astype(str) + " · " + data["industry"].astype(str)
    for key, column, _label in CONTRIBUTION_DIMS:
        data[f"w_{column}"] = (
            pd.to_numeric(data[column], errors="coerce").fillna(0.0) * weights[key]
        )
    return data


def _render_career_recommendations(
    profile: career.CareerProfile,
    scored: pd.DataFrame,
    city_rank: pd.DataFrame,
    main_color: str,
) -> None:
    """Tab 1：个性化推荐（KPI 卡片 + 摘要 + 匹配度构成 + 多维明细表 + 逐条建议）。"""
    top = scored.iloc[0]
    matched = career.parse_skills(top.get("matched_skills"))
    industry_skills = career.parse_skills(top.get("skills"))
    top_rows = scored.head(max(1, int(profile.top_n)))
    top_industry = str(top["industry"]) or "（未标注产业）"
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        widgets.metric_card(
            "🎯 首选城市", str(top["city"]),
            sub=f"{top.get('province', '—')} · {top_industry}",
        )
    with k2:
        widgets.metric_card(
            "📊 综合匹配度", _num_text(top["match_score"], "{:.1f}"),
            sub=f"共评估 {len(scored)} 条「城市 × 产业」",
        )
    with k3:
        widgets.metric_card(
            "💰 预估月薪", _num_text(top["avg_salary"], "¥{:,.0f}"),
            sub=f"期望 ¥{profile.target_salary:,.0f}/月",
        )
    with k4:
        widgets.metric_card(
            "🧩 技能命中率", _num_text(top["skill_score"], "{:.0f}%"),
            sub=f"命中 {len(matched)} / {len(industry_skills)} 项核心技能",
        )
    with k5:
        widgets.metric_card(
            "📈 需求景气", _num_text(top["demand_index"], "{:.0f}"),
            sub=f"岗位年增速 {_num_text(top['growth_pct'], '{:+.1f}%')}",
        )

    widgets.insight_box(career.build_summary(profile, scored, city_rank))

    chart_col, table_col = st.columns([1, 1.35])
    with chart_col:
        st.markdown("#### 📊 匹配度构成（各维度加权贡献）")
        contributions = _career_contributions(profile, top_rows)
        columns = tuple(f"w_{column}" for _key, column, _label in CONTRIBUTION_DIMS)
        labels = tuple(label for _key, _column, label in CONTRIBUTION_DIMS)
        render_fig(
            charts.career_score_breakdown(
                contributions,
                columns=columns,
                labels=labels,
                label_col="推荐项",
                title="推荐项匹配度构成（加权得分）",
                figsize=(6.6, max(3.6, len(contributions) * 0.42 + 2)),
            )
        )
        st.caption(
            "条形总长 ≈ 匹配度（未含学历修正项），每段代表一个维度的加权得分；"
            "权重为 0 的维度不会出现在条形中。"
        )

    with table_col:
        st.markdown(f"#### 📋 推荐明细 TOP {len(top_rows)}")
        view = st.radio(
            "明细视图",
            options=list(CAREER_DETAIL_VIEWS),
            horizontal=True,
            key="career_detail_view",
            help="总览看薪资与景气度；五维得分看各维度子得分；技能与岗位看学历门槛与岗位方向",
        )
        detail = _career_detail_view(top_rows, CAREER_DETAIL_VIEWS[view])
        st.dataframe(
            widgets.fmt_table(
                detail, INDUSTRY_TABLE_FORMAT,
                gradient_col="匹配度", cmap="RdYlGn",
            ),
            height=380,
        )
        if view == "🎯 五维得分":
            st.caption(
                "五个维度子得分均为 0-100 分；匹配度 = Σ(权重 × 子得分) × 学历修正系数。"
            )
        elif view == "🧩 技能与岗位":
            st.caption(
                "学历差距为「岗位门槛 − 你的学历」：为正表示需提升学历（每差一档匹配度折减 6%），"
                "为负表示学历高于门槛、具备竞争优势。"
            )
        st.download_button(
            "⬇️ 下载推荐结果（CSV）",
            data=top_rows.rename(columns=CAREER_LABELS).to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name="就业推荐结果.csv",
            mime="text/csv",
        )

    advice_rows = scored.head(min(5, len(scored)))
    with st.expander(f"📝 逐条推荐理由与提升建议（TOP {len(advice_rows)}）", expanded=False):
        for rank, (_idx, row) in enumerate(advice_rows.iterrows(), start=1):
            st.markdown(
                f"**{rank}. {row['city']} · {row['industry']}**"
                f"（{row['category']}｜匹配度 {float(row['match_score']):.1f}）  \n"
                f"{career.build_advice(profile, row)}"
            )


# 城市级推荐表列名 / 格式映射
CITY_RANK_LABELS: dict[str, str] = {
    "city": "城市", "province": "省份", "best_industry": "代表产业",
    "best_category": "行业大类", "match_score": "匹配度",
    "matched_industries": "匹配产业数", "avg_salary": "平均月薪(元)",
    "category_mix": "覆盖行业大类", "happiness": "幸福度",
    "house_price": "房价(元/㎡)", "value_index": "可负担指数",
    "composite_score": "综合宜居分",
}
CITY_RANK_FORMAT: dict[str, str] = {
    "匹配度": "{:.1f}", "匹配产业数": "{:,.0f}", "平均月薪(元)": "{:,.0f}",
    "幸福度": "{:.1f}", "房价(元/㎡)": "{:,.0f}", "可负担指数": "{:.2f}",
    "综合宜居分": "{:.1f}",
}
# 行业大类汇总表列名 / 格式映射
CATEGORY_LABELS: dict[str, str] = {
    "category": "行业大类", "city_count": "覆盖城市数",
    "industry_count": "产业数", "avg_salary": "平均月薪(元)",
    "avg_demand": "需求景气指数", "avg_share": "就业占比(%)",
    "avg_match": "平均匹配度",
}
CATEGORY_FORMAT: dict[str, str] = {
    "覆盖城市数": "{:,.0f}", "产业数": "{:,.0f}", "平均月薪(元)": "{:,.0f}",
    "需求景气指数": "{:.1f}", "就业占比(%)": "{:.1f}", "平均匹配度": "{:.1f}",
}
# 技能需求表列名 / 格式映射
SKILL_LABELS: dict[str, str] = {
    "skill": "技能", "industry_count": "覆盖产业数", "city_count": "覆盖城市数",
    "avg_demand": "平均需求景气", "avg_salary": "平均月薪(元)",
    "demand_heat": "需求热度", "sample_categories": "典型行业",
}
SKILL_FORMAT: dict[str, str] = {
    "覆盖产业数": "{:,.0f}", "覆盖城市数": "{:,.0f}",
    "平均需求景气": "{:.1f}", "平均月薪(元)": "{:,.0f}", "需求热度": "{:.1f}",
}


def _render_career_city_panorama(
    profile: career.CareerProfile,
    scored: pd.DataFrame,
    city_rank: pd.DataFrame,
    industry_df: pd.DataFrame,
    main_color: str,
    province_map: dict[str, str],
) -> None:
    """Tab 2：城市产业全景（城市级推荐 + 薪资×需求散点 + 行业大类 + 单城市结构）。"""
    st.markdown("#### 🏙️ 城市级推荐（每城取匹配度最高的代表产业）")
    if city_rank.empty:
        st.info("暂无可聚合的城市级推荐结果。")
    else:
        city_display = city_rank.rename(columns=CITY_RANK_LABELS).copy()
        city_display.index = range(1, len(city_display) + 1)
        st.dataframe(
            widgets.fmt_table(
                city_display, CITY_RANK_FORMAT,
                gradient_col="匹配度", cmap="RdYlGn",
            ),
            height=340,
        )
        st.download_button(
            "⬇️ 下载城市级推荐（CSV）",
            data=city_display.to_csv(index=False).encode("utf-8-sig"),
            file_name="就业城市级推荐.csv",
            mime="text/csv",
        )
        st.caption(
            "「覆盖行业大类」为该城市在候选范围内命中的行业大类（最多展示 "
            f"{career.CATEGORY_MIX_LIMIT} 个），覆盖越宽说明产业面越广、可选择的岗位越多。"
        )

    plot_col, cat_col = st.columns([1.15, 1])
    top_n = max(1, int(profile.top_n))
    top_rows = scored.head(top_n)
    with plot_col:
        st.markdown("#### 🎯 候选产业「薪资 × 需求」分布")
        plot_df = scored.copy()
        # 以「城市 × 产业」为主键标记推荐命中：不依赖行号，重排 / 过滤后仍然准确
        hit_pairs = set(
            zip(top_rows["city"].astype(str), top_rows["industry"].astype(str))
        )
        plot_df["推荐命中"] = [
            "推荐" if (str(city), str(industry)) in hit_pairs else ""
            for city, industry in zip(plot_df["city"], plot_df["industry"])
        ]
        render_fig(
            charts.salary_demand_scatter(
                plot_df,
                color=main_color,
                highlight_col="推荐命中",
                title=f"候选产业薪资 × 需求景气（高亮 = TOP {top_n} 推荐）",
            )
        )
        st.caption("气泡大小 = 该产业就业占比；越靠右上代表「高薪 + 高需求」。")

    with cat_col:
        st.markdown("#### 🧭 行业大类概览")
        summary = career.category_summary(scored)
        if summary.empty:
            st.info("暂无可聚合的行业大类数据。")
        else:
            summary_display = summary.rename(columns=CATEGORY_LABELS).copy()
            summary_display.index = range(1, len(summary_display) + 1)
            st.dataframe(
                widgets.fmt_table(
                    summary_display, CATEGORY_FORMAT,
                    gradient_col="平均月薪(元)", cmap="YlOrRd",
                ),
                height=340,
            )

    st.markdown("#### 🔎 单行业大类的城市横向对比")
    categories = sorted(scored["category"].astype(str).unique())
    picked = st.selectbox(
        "选择行业大类查看城市排名", options=categories, key="career_panorama_category"
    )
    subset = (
        scored[scored["category"].astype(str) == picked]
        .nlargest(CAREER_COMPARE_TOP, "match_score")
        .sort_values("match_score")
    )
    if subset.empty:
        st.info("该行业大类的候选数据不足。")
    else:
        render_fig(
            charts.barh_ranking(
                subset, "match_score",
                label_col="city",
                color=main_color,
                title=f"{picked} · 匹配度 TOP {len(subset)} 城市",
                xlabel="匹配度（0-100）",
                fmt="{:.1f}",
            )
        )

    st.markdown(f"#### 🏗️ 单城市产业结构（就业占比 TOP {CAREER_STRUCTURE_TOP}）")
    drill_cities = sorted(scored["city"].dropna().astype(str).unique().tolist())
    drill_city = st.selectbox(
        "选择城市查看其支柱产业构成",
        options=drill_cities,
        key="career_drill_city",
        format_func=_city_label_mapper(province_map),
    )
    structure = (
        scored[scored["city"].astype(str) == drill_city]
        .nlargest(CAREER_STRUCTURE_TOP, "share_pct")
        .sort_values("share_pct")
    )
    if structure.empty:
        st.info("该城市在当前筛选范围内没有支柱产业记录。")
    else:
        render_fig(
            charts.barh_ranking(
                structure, "share_pct",
                label_col="industry",
                color=main_color,
                title=f"「{drill_city}」支柱产业就业占比 TOP {len(structure)}",
                xlabel=METRIC_UNITS["share_pct"],
                fmt="{:.1f}",
                figsize=(8, max(4, len(structure) * 0.34 + 2)),
            )
        )
        best_here = structure.sort_values("match_score", ascending=False)
        st.caption(
            "条形长度 = 该产业从业人员占城镇就业比重（产业结构规模）；"
            f"该城市候选产业中与你匹配度最高的是「{best_here.iloc[0]['industry']}」"
            f"（匹配度 {float(best_here.iloc[0]['match_score']):.1f}）。"
        )

    provinces = sorted({province_map.get(city, "-") for city in scored["city"].unique()})
    st.caption(
        f"候选范围覆盖 {len(provinces)} 个省级行政区："
        + "、".join(provinces[:8]) + ("……" if len(provinces) > 8 else "")
        + f"；支柱产业库共覆盖 {int(industry_df['city'].nunique())} 个城市。"
    )


def _render_career_skill_map(
    profile: career.CareerProfile,
    industry_df: pd.DataFrame,
    main_color: str,
) -> None:
    """Tab 3：技能需求图谱与供需缺口分析。"""
    try:
        gap = career_skill_gap_cached(
            career.profile_key(profile), industry_df, SKILL_GAP_TOP_N
        )
    except Exception as exc:  # noqa: BLE001 - 技能图谱失败仅提示，不中断整页
        logger.exception("技能需求图谱计算失败")
        st.info(f"技能需求图谱暂不可用：{exc}")
        return

    owned, missing = gap["matched"], gap["gaps"]
    combined = pd.concat(
        [owned.assign(owned=True), missing.assign(owned=False)], ignore_index=True
    ).sort_values("demand_heat", ascending=False).head(CAREER_COMPARE_TOP)

    if combined.empty:
        st.info(
            "暂无技能需求数据：支柱产业表的 `skills` 字段为空或缺失，"
            "可重新运行 `python scripts/crawl_industry.py` 生成完整数据。"
        )
        return

    st.markdown("#### 🧩 全市场技能需求热度（绿色 = 你已具备）")
    chart_col, table_col = st.columns([1.25, 1])
    with chart_col:
        render_fig(
            charts.skill_demand_chart(
                combined, color=main_color,
                title=f"技能需求热度 TOP {len(combined)}",
            )
        )
        st.caption(
            "需求热度 = 覆盖产业数 × 平均需求景气指数 ÷ 100，"
            "综合反映技能的「市场广度」与「紧缺程度」。"
        )

    with table_col:
        st.markdown(f"##### ✅ 已具备的高需求技能（{len(owned)} 项）")
        if owned.empty:
            st.caption("所选技能暂未进入全市场高需求榜，可参考下方建议补强项。")
        else:
            view = owned.rename(columns=SKILL_LABELS).copy()
            view.index = range(1, len(view) + 1)
            st.dataframe(
                widgets.fmt_table(
                    view, SKILL_FORMAT, gradient_col="需求热度", cmap="Greens"
                ),
                height=210,
            )

        st.markdown(f"##### 📚 建议补强的技能（{len(missing)} 项）")
        if missing.empty:
            st.caption("你已覆盖全部高需求技能，属于稀缺复合型人才。")
        else:
            view = missing.rename(columns=SKILL_LABELS).copy()
            view.index = range(1, len(view) + 1)
            st.dataframe(
                widgets.fmt_table(
                    view, SKILL_FORMAT, gradient_col="需求热度", cmap="Oranges"
                ),
                height=210,
            )

    st.download_button(
        "⬇️ 下载技能需求榜（CSV）",
        data=(
            combined.assign(是否具备=combined["owned"])
            .drop(columns=["owned"])
            .rename(columns=SKILL_LABELS)
            .to_csv(index=False)
            .encode("utf-8-sig")
        ),
        file_name="技能需求热度榜.csv",
        mime="text/csv",
    )
    st.caption(
        "提示：优先补强「需求热度高 + 平均月薪高」的技能，"
        "对提升匹配度与薪资议价能力的效果最明显。"
    )


def render_province_aggregate(
    filtered_df: pd.DataFrame, main_color: str
) -> pd.DataFrame:
    """第八节：省份维度聚合分析，返回省份聚合表供末节 Tab 复用。"""
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
        render_fig(fig)

    with prov_col2:
        st.markdown("### 各省平均可负担指数")
        province_value = province_agg.sort_values(
            "平均可负担指数", ascending=False
        ).head(15).sort_values("平均可负担指数")

        fig = charts.barh_ranking(
            province_value, "平均可负担指数",
            label_col="省份",
            color="#f59e0b",
            title="平均可负担指数 Top 15 省份",
            xlabel="平均可负担指数",
            fmt="{:.2f}",
        )
        render_fig(fig)

    prov_table1, prov_table2 = st.columns(2)
    with prov_table1:
        prov_show = province_agg[["省份", "平均幸福度", "城市数量"]].copy()
        prov_show.index = range(1, len(prov_show) + 1)
        st.dataframe(
            widgets.fmt_table(prov_show, {"平均幸福度": "{:.1f}"}),
            height=350,
            width="stretch",
        )
    with prov_table2:
        prov_show2 = province_agg[
            ["省份", "平均收入", "平均房价", "平均可负担指数", "城市数量"]
        ].copy()
        prov_show2.index = range(1, len(prov_show2) + 1)
        st.dataframe(
            widgets.fmt_table(
                prov_show2,
                {"平均收入": "{:,.0f}", "平均房价": "{:,.0f}",
                 "平均可负担指数": "{:.2f}"},
                gradient_col="平均可负担指数",
                cmap="Greens",
            ),
            height=350,
            width="stretch",
        )

    return province_agg


def render_maps() -> None:
    """第九节：地理可视化地图（pyecharts 生成的静态 HTML）。"""
    widgets.section_title("🗺️ 中国城市地理分布地图")
    map_col1, map_col2 = st.columns(2)
    with map_col1:
        st.markdown("### 中国各省市宜居度地图")
        render_map("中国各省市宜居度地图.html", "宜居度地图文件未找到")
    with map_col2:
        st.markdown("### Top50 城市生活价值指数分布")
        render_map(
            "Top50的中国城市生活价值指数分布.html", "城市价值指数地图文件未找到"
        )

def render_data_browser(
    filtered_df: pd.DataFrame,
    province_agg: pd.DataFrame,
    quality: dict,
    metadata: dict,
    industry_df: pd.DataFrame | None = None,
) -> None:
    """第十节：完整数据浏览与数据质量报告。"""
    widgets.section_title("📋 完整数据浏览")

    tab1, tab2, tab3 = st.tabs(["🏙️ 城市明细数据", "🗺️ 省份聚合数据", "✅ 数据质量报告"])

    with tab1:
        city_display = filtered_df[
            ["city", "province", "happiness", "income", "house_price",
             "population", "value_index", "composite_score"]
        ].copy()
        city_display.columns = [COLUMN_LABELS[c] for c in city_display.columns]
        city_display = city_display.sort_values(
            "可负担指数", ascending=False
        ).reset_index(drop=True)
        city_display.index = range(1, len(city_display) + 1)

        st.dataframe(
            widgets.fmt_table(
                city_display,
                {"年收入": "{:,.0f}", "房价(元/㎡)": "{:,.0f}",
                 "常住人口(万)": "{:,.0f}", "幸福度": "{:.1f}",
                 "可负担指数": "{:.2f}", "综合宜居分": "{:.1f}"},
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
                data=city_display.to_json(
                    orient="records", force_ascii=False, indent=2
                ).encode("utf-8"),
                file_name="中国城市生活成本与幸福感数据.json",
                mime="application/json",
                width="stretch",
            )

    with tab2:
        st.dataframe(
            widgets.fmt_table(
                province_agg,
                {"平均幸福度": "{:.1f}", "平均收入": "{:,.0f}", "平均房价": "{:,.0f}",
                 "常住人口": "{:,.0f}", "平均可负担指数": "{:.2f}",
                 "平均综合宜居分": "{:.1f}"},
                gradient_col="平均幸福度",
                cmap="RdYlGn",
            ),
            height=500,
            width="stretch",
        )

    with tab3:
        render_quality_report(quality, metadata)
        _render_industry_quality(industry_df)


def _render_industry_quality(industry_df: pd.DataFrame | None) -> None:
    """数据质量报告 Tab 内：支柱产业数据集（爬虫采集）概览与导出。"""
    if industry_df is None or industry_df.empty:
        st.info(
            "未找到支柱产业数据集（`data/industry.csv`）；"
            "运行 `python scripts/crawl_industry.py` 后即可在此查看。"
        )
        return

    st.markdown("#### 🏭 支柱产业数据集（爬虫采集）")
    health = data_loader.industry_health(industry_df)
    skills = {
        tag for value in industry_df["skills"] for tag in career.parse_skills(value)
    }
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("记录数（城市 × 产业）", health["rows"])
    c2.metric("覆盖城市", health["cities"])
    c3.metric("行业大类", health["categories"])
    c4.metric("技能标签", len(skills))
    if (
        health["missing_columns"]
        or health["blank_columns"]
        or health["empty_numeric_columns"]
    ):
        _render_career_health(health)

    preview = industry_df.rename(
        columns={c: COLUMN_LABELS.get(c, c) for c in industry_df.columns}
    ).copy()
    preview.index = range(1, len(preview) + 1)
    st.dataframe(
        widgets.fmt_table(
            preview.head(100),
            {"就业占比(%)": "{:.1f}", "平均月薪(元)": "{:,.0f}",
             "需求景气指数": "{:.1f}", "岗位年增速(%)": "{:+.1f}"},
            gradient_col="平均月薪(元)",
            cmap="YlOrRd",
        ),
        height=360,
    )
    st.caption(
        "数据来源：`scripts/crawl_industry.py`（离线页面快照 → 礼貌抓取 → 表格解析 → 清洗落库）；"
        "字段口径见 `data/metadata.json` 的 industry.csv 条目。"
    )
    st.download_button(
        "📥 下载支柱产业数据（CSV）",
        data=preview.to_csv(index=False).encode("utf-8-sig"),
        file_name="中国城市支柱产业与人才需求数据.csv",
        mime="text/csv",
    )

# ===========================================================================
# 主流程：数据加载 → 侧边栏筛选 → KPI 概览 → 各章节渲染
# ===========================================================================
# 数据加载（缓存 + 文件签名感知）
try:
    df, quality = data_loader.load_data(
        DATA_DIR, data_loader.data_signature(DATA_DIR)
    )
except FileNotFoundError as exc:
    st.error(f"❌ 数据文件缺失：{exc}")
    st.info("请确保 data/ 目录包含全部数据文件（清单见 data/metadata.json）。")
    st.stop()

# 支柱产业（就业）数据集：可选加载，缺失时就业指导章节自动降级提示
industry_df = data_loader.load_industry_cached(
    DATA_DIR, data_loader.data_signature(DATA_DIR, data_loader.OPTIONAL_FILES)
)

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
    # regex=False：按字面匹配关键词，避免正则特殊字符触发解析异常
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

stats = _means(filtered_df)
if stats["population_sum"] > 0:
    total_pop_text = f"总人口约 {stats['population_sum'] / 10000:.1f} 亿"
else:
    total_pop_text = "总人口数据不可用"

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    widgets.metric_card("📋 城市总数", f"{len(filtered_df)}",
                        sub=f"{filtered_df['province'].nunique()} 个省份")
with c2:
    widgets.metric_card("😊 平均幸福度", f"{stats['happiness']:.1f}", sub="满分 100")
with c3:
    widgets.metric_card("💰 平均年收入", f"¥{stats['income'] / 10000:.1f}万",
                        sub="单位：元/年")
with c4:
    widgets.metric_card("🏠 平均房价", f"¥{stats['house_price']:.0f}",
                        sub="单位：元/㎡")
with c5:
    widgets.metric_card("📈 平均可负担指数", f"{stats['value_index']:.2f}",
                        sub=total_pop_text)

# ---------------- 章节渲染（顺序即页面展示顺序） ----------------
province_map = df.set_index("city")["province"].to_dict()

render_association(filtered_df, main_color)
render_city_comparison(filtered_df, main_color, province_map)
render_forecast(df, main_color, province_map)
render_happiness_ranking(filtered_df, main_color)
render_affordability(filtered_df, main_color)
render_top20(filtered_df)
render_outliers(filtered_df, main_color)
render_career_guidance(filtered_df, industry_df, main_color, province_map)
province_agg = render_province_aggregate(filtered_df, main_color)
if show_maps:
    render_maps()

# ---------------- 完整数据浏览与数据质量报告 ----------------
metadata = data_loader.load_metadata(DATA_DIR)
render_data_browser(filtered_df, province_agg, quality, metadata, industry_df)

# ---------------- 页脚 ----------------
widgets.render_footer()










