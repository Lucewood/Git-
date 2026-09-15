"""数据加载与质量校验模块。

设计要点：
- 纯函数（load_and_merge / validate_data）不依赖 Streamlit，可直接在
  单元测试与离线批处理（scripts/）中调用；
- 提供带缓存的 Streamlit 包装（load_data），缓存键包含数据文件签名，
  数据文件内容变化（mtime + size）时缓存自动失效。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from .config import (
    DATA_DIR,
    DATA_REF_YEAR,
    DERIVED_COLS,
    INDUSTRY_COLS,
    INDUSTRY_FILE,
    INDUSTRY_NUMERIC_COLS,
    NUMERIC_COLS,
)

logger = logging.getLogger(__name__)

# 必须存在的数据文件（加载与合并顺序，首个文件作为主表）
REQUIRED_FILES: tuple[str, ...] = (
    "province.csv",
    "happiness.csv",
    "income.csv",
    "house_price.csv",
    "location.csv",
    "population.csv",
)

# 可选数据集（缺失时主流程照常运行，对应功能自动降级）
OPTIONAL_FILES: tuple[str, ...] = (INDUSTRY_FILE,)

# 综合宜居评分权重：幸福度 + 可负担指数
COMPOSITE_WEIGHTS: dict[str, float] = {"happiness": 0.6, "value_index": 0.4}


# ---------------------------------------------------------------------------
# 纯函数核心（无 Streamlit 依赖，可单元测试）
# ---------------------------------------------------------------------------
def data_signature(
    data_dir: Path = DATA_DIR,
    extra: tuple[str, ...] = (),
) -> tuple[tuple[str, int, int], ...]:
    """生成数据文件签名（文件名 + mtime + size），文件变化时缓存自动失效。

    Args:
        extra: 需要一并纳入签名的附加数据文件名（如房价预测模块使用的
            house_price_history.csv），保证此类文件被重建后缓存同步失效。
    """
    names = REQUIRED_FILES + tuple(extra)
    files = sorted(
        (data_dir / name for name in names if (data_dir / name).exists())
    )
    signature: list[tuple[str, int, int]] = []
    for file in files:
        stat = file.stat()  # 仅调用一次 stat，避免重复系统调用
        signature.append((file.name, stat.st_mtime_ns, stat.st_size))
    return tuple(signature)


def _read_csv(path: Path) -> pd.DataFrame:
    """读取 CSV 并做基础清洗（去首尾空格、城市列去重）。"""
    if not path.exists():
        raise FileNotFoundError(f"数据文件不存在: {path}")
    frame = pd.read_csv(path)
    frame.columns = [str(c).strip() for c in frame.columns]
    if "city" in frame.columns:
        frame["city"] = frame["city"].astype(str).str.strip()
        frame = frame.drop_duplicates(subset="city", keep="first")
    return frame


def _merge_sources(data_dir: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    """读取全部 CSV 并按 city 左连接合并。

    Returns:
        (merged, source_counts) —— merged 为合并宽表；
        source_counts 为各源文件清洗后的城市数（用于数据质量报告）。
    """
    source_counts: dict[str, int] = {}
    merged: pd.DataFrame | None = None

    for fname in REQUIRED_FILES:
        frame = _read_csv(data_dir / fname)
        source_counts[fname] = int(len(frame))
        merged = frame if merged is None else merged.merge(frame, on="city", how="left")

    assert merged is not None, "至少需要一个数据文件"
    return merged, source_counts


def _zscore(series: pd.Series) -> pd.Series:
    """z-score 标准化；零方差 / 缺失时返回 0 序列，避免 NaN 扩散。"""
    std = series.std()
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=series.index)
    return (series - series.mean()) / std


def compute_derived(df: pd.DataFrame) -> pd.DataFrame:
    """计算派生指标：
    - value_index      住房可负担指数 = 年收入 ÷ 房价（元/㎡）
    - composite_score  综合宜居评分（0-100）= 幸福度与可负担指数的加权标准化
    """
    out = df.copy()
    out["value_index"] = np.where(
        out["house_price"].gt(0), out["income"] / out["house_price"], np.nan
    )

    z_happy = _zscore(out["happiness"])
    z_value = _zscore(out["value_index"])
    composite = (
        COMPOSITE_WEIGHTS["happiness"] * z_happy
        + COMPOSITE_WEIGHTS["value_index"] * z_value
    )
    lo, hi = composite.min(), composite.max()
    if np.isfinite(lo) and np.isfinite(hi) and hi > lo:
        out["composite_score"] = (composite - lo) / (hi - lo) * 100.0
    else:
        out["composite_score"] = np.nan
    return out


def _fmt_float(value: float | None, ndigits: int = 2) -> float | None:
    """浮点数安全格式化；NaN / None 一律转为 None。"""
    if value is None or not np.isfinite(value):
        return None
    return round(float(value), ndigits)


def validate_data(
    df: pd.DataFrame,
    source_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """生成数据质量报告（缺失值、重复、数值范围、源覆盖度等）。"""
    report: dict[str, Any] = {
        "shape": {"rows": int(df.shape[0]), "cols": int(df.shape[1])},
        "duplicate_cities": int(df["city"].duplicated().sum()),
        "missing_values": {str(c): int(df[c].isna().sum()) for c in df.columns},
        "numeric_summary": {},
    }
    if source_counts:
        report["source_city_counts"] = {k: int(v) for k, v in source_counts.items()}

    for col in NUMERIC_COLS + DERIVED_COLS:
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        report["numeric_summary"][col] = {
            "count": int(len(s)),
            "mean": _fmt_float(float(s.mean()) if len(s) else None),
            "std": _fmt_float(float(s.std()) if len(s) else None),
            "min": _fmt_float(float(s.min()) if len(s) else None),
            "median": _fmt_float(float(s.median()) if len(s) else None),
            "max": _fmt_float(float(s.max()) if len(s) else None),
        }
    return report


def load_and_merge(data_dir: Path = DATA_DIR) -> tuple[pd.DataFrame, dict[str, Any]]:
    """加载、合并并清洗全部数据（纯函数）。

    Returns:
        (df, quality_report) —— df 为清洗后的城市级宽表（含派生指标）；
        quality_report 为数据质量报告字典。
    """
    raw, source_counts = _merge_sources(data_dir)

    # 数值列强制转换，非法值置为 NaN
    for col in NUMERIC_COLS:
        raw[col] = pd.to_numeric(raw[col], errors="coerce")

    df = compute_derived(raw)

    # 核心指标任一缺失即剔除，保证后续分析质量
    df = df.dropna(subset=[*NUMERIC_COLS, "value_index"]).reset_index(drop=True)

    quality = validate_data(df, source_counts)
    logger.info(
        "数据加载完成：%d 个城市，源文件城市数=%s，参考年份=%d",
        len(df), source_counts, DATA_REF_YEAR,
    )
    return df, quality


# ---------------------------------------------------------------------------
# Streamlit 缓存包装（带签名感知）
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_data(
    data_dir: Path = DATA_DIR,
    signature: tuple[tuple[str, int, int], ...] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """带缓存的加载入口（Streamlit 专用）。

    Args:
        data_dir: 数据目录。
        signature: 由 data_signature() 生成，仅用于构成缓存键；
                   数据文件变化后签名改变，缓存自动失效。
    """
    return load_and_merge(data_dir)


@st.cache_data(show_spinner=False)
def load_metadata(data_dir: Path = DATA_DIR) -> dict[str, Any]:
    """读取数据字典 metadata.json（不存在时返回空字典）。"""
    path = data_dir / "metadata.json"
    if not path.exists():
        logger.warning("metadata.json 不存在，数据字典为空。")
        return {}
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def load_industry(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """加载支柱产业长表（可选数据集，纯函数）。

    与主数据的区别：该表是「城市 × 支柱产业」长表（一个城市多行），
    因此不能按 city 去重，也不能直接并入城市宽表。

    Returns:
        规范化长表（列为 config.INDUSTRY_COLS 中实际存在的列）；
        文件不存在时返回带完整列名的空表，调用方据此降级提示。
    """
    path = data_dir / INDUSTRY_FILE
    if not path.exists():
        logger.warning("未找到支柱产业数据文件 %s，就业指导功能将降级。", path)
        return pd.DataFrame(columns=list(INDUSTRY_COLS))

    frame = pd.read_csv(path)
    frame.columns = [str(c).strip() for c in frame.columns]
    for col in ("city", "industry", "category", "education", "skills"):
        if col in frame.columns:
            frame[col] = frame[col].astype("string").fillna("").str.strip()
    for col in INDUSTRY_NUMERIC_COLS:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")

    keep = [col for col in INDUSTRY_COLS if col in frame.columns]
    frame = frame[keep]
    if {"city", "industry"} <= set(frame.columns):
        frame = frame[(frame["city"] != "") & (frame["industry"] != "")]
    logger.info("支柱产业数据加载完成：%d 条记录（%s）", len(frame), path.name)
    return frame.reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_industry_cached(
    data_dir: Path = DATA_DIR,
    signature: tuple[tuple[str, int, int], ...] | None = None,
) -> pd.DataFrame:
    """带缓存的支柱产业数据加载入口（Streamlit 专用）。

    Args:
        signature: 由 data_signature(data_dir, OPTIONAL_FILES) 生成，仅用于构成
                   缓存键；爬虫重新生成 industry.csv 后签名变化、缓存自动失效。
    """
    return load_industry(data_dir)
