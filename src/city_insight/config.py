"""全局配置模块：路径、数据常量、颜色主题与环境变量设置。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径（基于本文件位置推导，跨环境可移植）
# ---------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
DATA_DIR: Path = BASE_DIR / "data"
NOTEBOOKS_DIR: Path = BASE_DIR / "notebooks"  # pyecharts 生成的 HTML 地图
LOG_DIR: Path = BASE_DIR / "logs"
RAW_DIR: Path = DATA_DIR / "raw"                                # 爬虫原始页面快照
INDUSTRY_SNAPSHOT_DIR: Path = RAW_DIR / "industry"              # 支柱产业页面快照
CRAWL_CACHE_DIR: Path = DATA_DIR / "crawl_cache"                # 爬虫响应缓存

# ---------------------------------------------------------------------------
# 数据常量
# ---------------------------------------------------------------------------
APP_NAME = "中国城市生活成本与幸福感分析"
APP_VERSION = "2.4.0"
# 数据参考年份（各字段口径与来源说明见 data/metadata.json）
DATA_REF_YEAR = 2024

# 原始指标列（来自 CSV）
NUMERIC_COLS: tuple[str, ...] = ("happiness", "income", "house_price", "population")
# 派生指标列（加载时计算）
DERIVED_COLS: tuple[str, ...] = ("value_index", "composite_score")
# 参与分析的全部指标列
METRIC_COLS: tuple[str, ...] = NUMERIC_COLS + DERIVED_COLS

# 支柱产业（就业）数据集：文件名、长表列与数值列
# 该文件由 scripts/crawl_industry.py 爬取生成，属可选数据集（缺失时页面自动降级）
INDUSTRY_FILE = "industry.csv"
INDUSTRY_COLS: tuple[str, ...] = (
    "city", "industry", "category", "share_pct",
    "avg_salary", "demand_index", "growth_pct", "education", "skills",
)
INDUSTRY_NUMERIC_COLS: tuple[str, ...] = (
    "share_pct", "avg_salary", "demand_index", "growth_pct",
)
# 技能标签分隔符（CSV 中以该字符连接多个技能）
SKILL_SEPARATOR = "|"

# 表格展示中文列名
COLUMN_LABELS: dict[str, str] = {
    "city": "城市",
    "province": "省份",
    "happiness": "幸福度",
    "income": "年收入",
    "house_price": "房价(元/㎡)",
    "population": "常住人口(万)",
    "value_index": "可负担指数",
    "composite_score": "综合宜居分",
    # 支柱产业（就业）数据集
    "industry": "支柱产业",
    "category": "行业大类",
    "share_pct": "就业占比(%)",
    "avg_salary": "平均月薪(元)",
    "demand_index": "需求景气指数",
    "growth_pct": "岗位年增速(%)",
    "education": "学历门槛",
    "skills": "核心技能",
}

# 指标单位（用于图表轴标签与说明）
METRIC_UNITS: dict[str, str] = {
    "happiness": "幸福度指数",
    "income": "年收入（元）",
    "house_price": "房价（元/㎡）",
    "population": "常住人口（万人）",
    "value_index": "可负担指数（年收入 ÷ 房价）",
    "composite_score": "综合宜居评分（0-100）",
    "share_pct": "就业占比（%）",
    "avg_salary": "平均月薪（元/月）",
    "demand_index": "人才需求景气指数（0-100）",
    "growth_pct": "岗位年增速（%）",
}

# ---------------------------------------------------------------------------
# 绘图常量
# ---------------------------------------------------------------------------
FONT_SANS: list[str] = [
    "SimHei",
    "Microsoft YaHei",
    "PingFang SC",
    "Noto Sans CJK SC",
    "DejaVu Sans",
]

COLOR_MAPS: dict[str, str] = {
    "默认蓝": "steelblue",
    "暖橙": "#ff7f50",
    "森林绿": "#2e8b57",
    "深紫": "#8b5cf6",
}
DANGER_COLOR = "#e74c3c"  # 异常值 / 警戒色
REG_COLOR = "crimson"     # 回归线颜色

# ---------------------------------------------------------------------------
# 环境变量设置（可通过 .env / 环境变量覆盖，见 .env.example）
# ---------------------------------------------------------------------------
def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """应用运行设置。

    全部字段可由环境变量覆盖，便于不同部署环境（开发 / 测试 / 生产）差异化配置。
    """

    log_level: str = "INFO"             # 日志级别: DEBUG / INFO / WARNING / ERROR
    debug: bool = False                 # 调试模式（打印堆栈等）
    map_render_mode: str = "components"  # 地图渲染方式: "components" | "iframe"
    max_comparison_cities: int = 8      # 城市对比工具最多可选城市数
    default_map_height: int = 520       # 地图组件高度（px）
    n_boot_regression: int = 100        # seaborn 回归重采样次数（越小渲染越快）
    career_top_n: int = 10              # 就业推荐默认展示条数
    max_career_results: int = 30        # 就业推荐最多可展示条数
    crawl_delay: float = 1.0            # 爬虫同域请求最小间隔（秒）
    crawl_timeout: float = 10.0         # 爬虫单次请求超时（秒）

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            debug=_env_bool("APP_DEBUG", False),
            map_render_mode=os.getenv("MAP_RENDER_MODE", "components").strip().lower(),
            max_comparison_cities=_env_int("MAX_COMPARISON_CITIES", 8),
            default_map_height=_env_int("DEFAULT_MAP_HEIGHT", 520),
            n_boot_regression=_env_int("N_BOOT_REGRESSION", 100),
            career_top_n=_env_int("CAREER_TOP_N", 10),
            max_career_results=_env_int("MAX_CAREER_RESULTS", 30),
            crawl_delay=_env_float("CRAWL_DELAY", 1.0),
            crawl_timeout=_env_float("CRAWL_TIMEOUT", 10.0),
        )


def get_settings() -> Settings:
    """获取全局运行设置（每次调用重新读取环境变量）。"""
    return Settings.from_env()
