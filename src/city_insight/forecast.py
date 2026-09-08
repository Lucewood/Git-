"""房价历史加载、特征工程与机器学习预测（纯函数，无 UI / 无 Streamlit 依赖）。

数据背景：
- data/house_price_history.csv 提供各城市 2005-2024 年年度住房均价（演示口径），
  2024 年与 data/house_price.csv 快照完全一致；
- 收入 / 人口等截面特征来自主数据（2024 年），历史年份收入由全国名义工资增速
  近似外推得到，仅用于构造“房价收入比（可负担性）”等时变特征。

方法（机器学习策略）：
1. 全样本面板特征工程：每个「城市 x 年份」样本的目标为“下一年房价对数涨幅”，
   特征包含滞后涨幅（1/3/5 年）、长周期年均涨幅、涨幅波动率、房价收入比、
   价格水平以及城市收入 / 人口 / 2024 价格等静态基本面；
2. 梯度提升回归树（scikit-learn GradientBoosting，缺依赖时自动回退到
   numpy 岭回归）采用 expanding walk-forward（滚动扩展窗口）训练与验证：
   对最近若干验证年，每个验证年都用“截止其上一年”的样本重新拟合一次模型，
   从而在所有验证样本上报告严格无前瞻偏差的 RMSE / MAE / R² / 方向命中率，
   并把各验证年的模型留存用于“外样本回测”；
3. 选定城市后以 2024 年价格为起点做“递归外推”多步预测（预测期特征中的
   年份变量被钳制在训练域内，避免树模型外推抖动），并按验证残差标准差
   构建给定置信度的置信区间。

模块内函数均为确定性 / 可复现的纯函数，便于单元测试与离线批处理。
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DATA_DIR, DATA_REF_YEAR

logger = logging.getLogger(__name__)

# 房价历史数据文件名（位于 data/ 下）
HISTORY_FILE = "house_price_history.csv"
HISTORY_START_YEAR = 2005
DEFAULT_HORIZON = 5
MAX_HORIZON = 10
DEFAULT_CONF = 0.8

# 可选机器学习后端
try:
    from sklearn.ensemble import GradientBoostingRegressor as _GBR
    from sklearn.metrics import r2_score as _r2

    HAVE_SKLEARN = True
except Exception:  # noqa: BLE001 - sklearn 缺失时回退到 numpy 实现
    _GBR = None
    HAVE_SKLEARN = False

# ---------------------------------------------------------------------------
# 特征定义
# ---------------------------------------------------------------------------
# 目标列：下一年房价对数涨幅相对全国同期涨幅的偏离（中心化目标）
TARGET_COL = "g_next"

FEATURE_COLS: tuple[str, ...] = (
    "year",            # 年份（捕捉全国周期）
    "macro_g1",        # 全国上年平均涨幅（全国动量）
    "pos_in_series",   # 处于历史序列中的阶段（0=起始年，1=参考年）
    "log_price",       # 价格对数水平
    "log_afford",      # 房价收入比（对数，越低越难负担）
    "g1",              # 上一年涨幅（对数）
    "g3_avg",          # 近 3 年平均涨幅
    "g5_avg",          # 近 5 年平均涨幅
    "long_cagr",       # 自起始年以来的年均复合涨幅
    "vol5",            # 近 5 年涨幅波动率
    "log_income",      # 城市收入水平（对数，静态）
    "log_population",  # 城市人口规模（对数，静态）
    "log_price2024",   # 2024 年价格水平（对数，静态）
)

FEATURE_LABELS: dict[str, str] = {
    "year": "年份",
    "macro_g1": "全国上年涨幅",
    "pos_in_series": "时间阶段",
    "log_price": "价格水平",
    "log_afford": "房价收入比",
    "g1": "上一年涨幅",
    "g3_avg": "近 3 年涨幅",
    "g5_avg": "近 5 年涨幅",
    "long_cagr": "长期年均涨幅",
    "vol5": "涨幅波动率",
    "log_income": "城市收入水平",
    "log_population": "城市人口规模",
    "log_price2024": "基准价格水平",
}

# 模型名称（展示用）
MODEL_NAMES = {
    "sklearn": "梯度提升回归树（scikit-learn GradientBoosting）",
    "numpy": "岭回归（numpy 最小二乘，scikit-learn 未安装时的回退实现）",
}

# 梯度提升回归树超参数（walk-forward 经验调优：兼顾拟合能力、泛化与训练速度）
GBR_PARAMS: dict = {
    "n_estimators": 200,
    "learning_rate": 0.08,
    "max_depth": 3,
    "min_samples_leaf": 6,
    "subsample": 0.85,
}
# 目标（涨幅偏离）的稳健裁剪边界，压制极端离群城市（如港澳台）的干扰
DEV_CLIP = (-0.20, 0.20)

# ---------------------------------------------------------------------------
# 收入近似外推（全国名义工资年度增速，仅用于构造房价收入比特征）
# ---------------------------------------------------------------------------
# 历史年份工资增速（键 = 目标年份，2006-2024）
_WAGE_YOY: dict[int, float] = {
    2006: 0.12, 2007: 0.13, 2008: 0.11, 2009: 0.10, 2010: 0.12,
    2011: 0.11, 2012: 0.10, 2013: 0.09, 2014: 0.08, 2015: 0.08,
    2016: 0.08, 2017: 0.09, 2018: 0.08, 2019: 0.07, 2020: 0.05,
    2021: 0.07, 2022: 0.05, 2023: 0.05, 2024: 0.04,
}
# 参考年之后的外推工资增速（用于多步预测期的房价收入比特征）
_FUTURE_WAGE_YOY = 0.045

# 收入缩放系数：income(t) = income(2024) x scale(t)
_INCOME_SCALE: dict[int, float] = {DATA_REF_YEAR: 1.0}
for _y in range(DATA_REF_YEAR - 1, HISTORY_START_YEAR - 1, -1):
    _INCOME_SCALE[_y] = _INCOME_SCALE[_y + 1] / (1 + _WAGE_YOY[_y + 1])


def income_scale(year: int) -> float:
    """把 2024 年收入换算到指定年份的缩放系数（<=2024 用历史增速，>2024 外推）。"""
    if year in _INCOME_SCALE:
        return _INCOME_SCALE[year]
    return float((1 + _FUTURE_WAGE_YOY) ** (year - DATA_REF_YEAR))


# ---------------------------------------------------------------------------
# 数据加载与对齐
# ---------------------------------------------------------------------------
def load_house_history(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """读取房价历史长表（city, year, house_price）。"""
    path = data_dir / HISTORY_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"房价历史数据缺失: {path}"
            "（可运行 python scripts/generate_house_price_history.py 生成）"
        )
    df = pd.read_csv(path)
    df.columns = [str(c).strip() for c in df.columns]
    df["city"] = df["city"].astype(str).str.strip()
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype(int)
    df["house_price"] = pd.to_numeric(df["house_price"], errors="coerce")
    df = df.dropna(subset=["house_price"]).drop_duplicates(
        subset=["city", "year"], keep="first"
    )
    return df.sort_values(["city", "year"]).reset_index(drop=True)


def align_data(
    history: pd.DataFrame, cross: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """裁剪历史与截面数据到公共城市集合，返回 (history, cross, missing_cities)。"""
    hist = history.copy()
    cross = cross.copy()
    cross_cols = [
        c for c in ("city", "province", "income", "population", "house_price")
        if c in cross.columns
    ]
    cross = cross[cross_cols].drop_duplicates(subset="city", keep="first")

    h_cities = set(hist["city"])
    c_cities = set(cross["city"])
    missing = sorted(h_cities - c_cities) + sorted(c_cities - h_cities)
    common = sorted(h_cities & c_cities)
    if missing:
        logger.warning("房价预测：%d 个城市数据不完整，已剔除。", len(missing))
    return hist[hist["city"].isin(common)], cross[cross["city"].isin(common)], missing


def national_growth_map(history: pd.DataFrame) -> dict[int, float]:
    """全国各年（t-1 → t）对数涨幅均值，返回 {目标年份: 平均涨幅}。"""
    h = history[["city", "year", "house_price"]].copy()
    years = sorted(int(y) for y in h["year"].unique())
    out: dict[int, float] = {}
    piv = h.pivot_table(index="year", columns="city", values="house_price")
    for y in years[1:]:
        if y - 1 not in piv.index or y not in piv.index:
            continue
        ratio = piv.loc[y] / piv.loc[y - 1]
        ratio = ratio[np.isfinite(ratio) & (ratio > 0)]
        if len(ratio) >= 2:
            out[y] = float(np.mean(np.log(ratio.to_numpy(dtype=float))))
    return out


def national_growth_rate(history: pd.DataFrame, year: int) -> float:
    """计算全国在指定年份的平均房价涨幅（对数，t-1 → t）。

    未来年份（history 覆盖范围之外）返回最近可观测年份的涨幅，便于递归外推。
    """
    m = national_growth_map(history)
    if not m:
        return float("nan")
    available = sorted(m)
    if year < available[0]:
        return float("nan")
    target = year if year in m else available[-1]
    return m[target]


# ---------------------------------------------------------------------------
# 特征工程
# ---------------------------------------------------------------------------
def prepare_panel(history: pd.DataFrame, cross: pd.DataFrame) -> pd.DataFrame:
    """把“城市 x 年份”历史序列转成带滞后特征与目标的建模面板。

    Returns:
        长表 DataFrame，列 = city / province / year + FEATURE_COLS + TARGET_COL。
    """
    h = history.merge(
        cross[["city", "province", "income", "population", "house_price"]]
        .rename(columns={"house_price": "price_2024"}),
        on="city", how="left",
    )
    h = h.dropna(subset=["year", "house_price", "income", "population", "price_2024"])
    # 全国各年涨幅（用于把目标转化为“相对全国的偏离”，消除共同周期）
    nat = national_growth_map(history)

    rows: list[dict[str, float | int | str]] = []
    start_year = int(h["year"].min())
    ref_year = int(h["year"].max())
    window = 5  # 近 5 年特征所需的最小历史跨度

    for city, sub in h.groupby("city", sort=False):
        sub = sub.sort_values("year").reset_index(drop=True)
        years = sub["year"].to_numpy(dtype=int)
        logp = np.log(sub["house_price"].to_numpy(dtype=float))
        n = len(years)
        if n < window + 2:  # 至少需要 window 年历史 + 1 年目标
            continue
        income = float(sub["income"].iloc[0])
        population = float(sub["population"].iloc[0])
        province = str(sub["province"].iloc[0])
        log_income = float(np.log(income))
        log_pop = float(np.log(population))
        log_price2024 = float(np.log(sub["price_2024"].iloc[-1]))

        growth = np.diff(logp)  # growth[j] = logp[j+1] - logp[j]
        # i: 特征所在年份索引；要求 i-window>=0（历史特征）且 i+1<n（目标存在）
        for i in range(window, n - 1):
            t = int(years[i])
            next_year = t + 1
            macro_next = nat.get(next_year, float("nan"))
            macro_next = float(macro_next) if np.isfinite(macro_next) else float("nan")
            # 目标 = 下一年城市涨幅 相对 全国同期涨幅 的偏离
            target_dev = float(growth[i]) if not np.isfinite(macro_next) else float(growth[i] - macro_next)
            feature = {
                "city": city,
                "province": province,
                "year": t,
                "pos_in_series": (t - start_year) / max(1, ref_year - start_year),
                "log_price": float(logp[i]),
                "log_afford": float(np.log(income * income_scale(t)) - logp[i]),
                "g1": float(growth[i - 1]),
                "g3_avg": float((logp[i] - logp[i - 3]) / 3.0),
                "g5_avg": float((logp[i] - logp[i - window]) / float(window)),
                "long_cagr": float((logp[i] - logp[0]) / max(1, t - start_year)),
                "vol5": float(growth[i - window: i].std()),
                "log_income": log_income,
                "log_population": log_pop,
                "log_price2024": log_price2024,
                TARGET_COL: target_dev,
                "macro_next": macro_next,
                "g_abs": float(growth[i]),  # 绝对涨幅（用于把指标换算回可读单位）
            }
            rows.append(feature)

    panel = pd.DataFrame(rows)
    # 全国动量：同一年各城市 g1 的均值（仅用当年及更早信息，无前瞻泄漏）
    if not panel.empty:
        macro = panel.groupby("year")["g1"].transform("mean")
        panel["macro_g1"] = macro
    panel = panel.dropna(subset=[*FEATURE_COLS, TARGET_COL])
    panel = panel.sort_values(["year", "city"]).reset_index(drop=True)
    return panel


# ---------------------------------------------------------------------------
# numpy 岭回归兜底（scikit-learn 不可用时的最小实现）
# ---------------------------------------------------------------------------
def _fit_ridge(x_train: np.ndarray, y_train: np.ndarray, lam: float = 1.0) -> dict:
    """标准化特征 + 带 L2 正则的线性回归闭合解。

    Returns:
        dict，包含 mu / sd / coef / intercept，可用于对单行特征做预测。
    """
    mu = x_train.mean(axis=0)
    sd = x_train.std(axis=0)
    sd[sd == 0] = 1.0
    xs = (x_train - mu) / sd
    y_mean = float(np.mean(y_train))
    coef = np.linalg.solve(
        xs.T @ xs + lam * np.eye(xs.shape[1]), xs.T @ (y_train - y_mean)
    )
    return {"mu": mu, "sd": sd, "coef": coef, "intercept": y_mean}


def _predict_ridge(state: dict, x_row: np.ndarray) -> float:
    """按训练集标准化统计对单行特征做岭回归预测。"""
    xs = (x_row - state["mu"]) / state["sd"]
    return float(xs @ state["coef"] + state["intercept"])


def _safe_r2(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """不依赖 sklearn 的 R2 计算。"""
    ss_res = float(np.sum(np.square(y_true - y_pred)))
    ss_tot = float(np.sum(np.square(y_true - np.mean(y_true))))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")


def _growth_metrics(
    y_true: np.ndarray, y_pred: np.ndarray
) -> tuple[float, float, float, float]:
    """返回 (rmse, mae, r2, hit_rate)。"""
    resid = y_true - y_pred
    rmse = float(np.sqrt(np.mean(np.square(resid))))
    mae = float(np.mean(np.abs(resid)))
    r2 = _safe_r2(y_true, y_pred)
    hit = float(np.mean(np.sign(y_pred) == np.sign(y_true))) if len(y_pred) else float("nan")
    return rmse, mae, r2, hit


# ---------------------------------------------------------------------------
# 模型训练
# ---------------------------------------------------------------------------
def _fit_model(x_train: np.ndarray, y_train: np.ndarray, seed: int) -> tuple:
    """按当前可用后端拟合一个回归模型，返回 (模型, ridge状态)，二者必有其一。"""
    if HAVE_SKLEARN and _GBR is not None:
        model = _GBR(random_state=seed, **GBR_PARAMS)
        model.fit(x_train, y_train)
        return model, None
    return None, _fit_ridge(x_train, y_train)


def _predict_model(model, ridge_state, x_row: np.ndarray) -> float:
    """用任意后端模型对单行特征做预测。"""
    if model is not None:
        return float(model.predict(np.asarray([x_row], dtype=float))[0])
    return _predict_ridge(ridge_state, np.asarray(x_row, dtype=float))


def train_growth_model(panel: pd.DataFrame, seed: int = 42, test_years: int = 3) -> dict:
    """在面板上以 expanding walk-forward 方式训练与验证“下一年涨幅”模型。

    对验证窗中每个年份 fy，仅用“特征年份 < fy”的样本拟合并在 fy 上预测
    （严格无前瞻），从而聚合得到逐年重训后的 OOS 指标；每个验证年的模型
    存于 artifacts["models_by_year"]，供 city_backtest 回测复用，避免重复
    训练；返回的 artifacts["model"] 是“全量拟合的部署模型”，用于未来递归外推。

    Returns:
        - backend / model / ridge / feature_cols：最终部署模型
        - metrics：绝对涨幅空间 rmse/mae/r2/hit_rate + _dev 偏离空间同名指标
        - folds：逐年验证明细；models_by_year：{验证年 -> {model, ridge}}
        - resid_std：偏离空间聚合残差标准差（置信区间用）
        - max_feature_year：模型见过的最大特征年份（预测期钳制用）
        - importance：DataFrame[feature, importance]（按贡献降序）
    """
    missing = [c for c in FEATURE_COLS if c not in panel.columns]
    if missing or TARGET_COL not in panel.columns:
        raise ValueError("面板缺少必要列：" + str(missing))

    x = panel[list(FEATURE_COLS)].to_numpy(dtype=float)
    y = np.clip(panel[TARGET_COL].to_numpy(dtype=float), *DEV_CLIP)
    years = panel["year"].to_numpy(dtype=int)
    unique_years = sorted(int(v) for v in np.unique(years))
    if len(unique_years) < test_years + 1:
        raise ValueError("可用于训练 / 验证的年份过少。")

    has_abs = {"g_abs", "macro_next"}.issubset(panel.columns)
    g_abs = panel["g_abs"].to_numpy(dtype=float) if has_abs else y.copy()
    macro = panel["macro_next"].to_numpy(dtype=float) if has_abs else np.zeros(len(y))

    test_year_list = unique_years[-test_years:]
    dev_y, dev_p, abs_y, abs_p, abs_ok = [], [], [], [], []
    fold_records: list[dict] = []
    models_by_year: dict[int, dict] = {}
    train_total = test_total = 0

    for fy in test_year_list:
        tr = years < fy
        te = years == fy
        model, ridge_state = _fit_model(x[tr], y[tr], seed)
        models_by_year[fy] = {"model": model, "ridge": ridge_state}

        dev_true = y[te]
        dev_pred = np.asarray(
            [_predict_model(model, ridge_state, row) for row in x[te]], dtype=float
        )
        y_abs_te, macro_te = g_abs[te], macro[te]
        pred_abs_te = dev_pred + macro_te
        ok = np.isfinite(y_abs_te) & np.isfinite(macro_te) & np.isfinite(pred_abs_te)

        dm = _growth_metrics(dev_true, dev_pred)
        am = _growth_metrics(y_abs_te[ok], pred_abs_te[ok]) if ok.any() else (float("nan"),) * 4

        train_total += int(tr.sum())
        test_total += int(te.sum())
        dev_y.append(dev_true)
        dev_p.append(dev_pred)
        abs_y.append(y_abs_te)
        abs_p.append(pred_abs_te)
        abs_ok.append(ok)
        fold_records.append({
            "test_feature_year": fy, "target_year": fy + 1,
            "train_samples": int(tr.sum()), "test_samples": int(te.sum()),
            "rmse": am[0], "mae": am[1], "r2": am[2], "hit_rate": am[3],
            "rmse_dev": dm[0], "mae_dev": dm[1], "r2_dev": dm[2], "hit_rate_dev": dm[3],
        })

    # 聚合（偏离 + 绝对空间）指标与残差标准差
    dev_y = np.concatenate(dev_y)
    dev_p = np.concatenate(dev_p)
    resid = dev_y - dev_p
    dev_rmse, dev_mae, dev_r2, dev_hit = _growth_metrics(dev_y, dev_p)
    abs_y = np.concatenate(abs_y)
    abs_p = np.concatenate(abs_p)
    abs_ok = np.concatenate(abs_ok)
    if abs_ok.any():
        rmse, mae, r2, hit = _growth_metrics(abs_y[abs_ok], abs_p[abs_ok])
    else:
        rmse, mae, r2, hit = (float("nan"),) * 4

    # 最终部署模型：在全量面板上拟合，用于未来年份递归外推
    final_model, final_ridge = _fit_model(x, y, seed)
    if final_model is not None:
        importances = np.asarray(final_model.feature_importances_, dtype=float)
        backend = "sklearn"
    else:
        importances = np.abs(final_ridge["coef"])
        backend = "numpy"
        logger.info("scikit-learn 不可用，房价预测回退到 numpy 岭回归。")

    importance_df = (
        pd.DataFrame({"feature": list(FEATURE_COLS), "importance": importances})
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )
    metrics = {
        "rmse": rmse, "mae": mae, "r2": r2, "hit_rate": hit,
        "rmse_dev": dev_rmse, "mae_dev": dev_mae,
        "r2_dev": dev_r2, "hit_rate_dev": dev_hit,
        "train_samples": train_total, "test_samples": test_total,
        "train_years": (unique_years[0], test_year_list[0] - 1),
        "test_years": (test_year_list[0], test_year_list[-1]),
    }
    logger.info(
        "房价预测模型 walk-forward 训练完成：backend=%s，验证 "
        "RMSE=%.4f，R2=%.3f，方向命中率=%.3f", backend, rmse, r2, hit,
    )
    return {
        "backend": backend,
        "model": final_model,
        "ridge": final_ridge,
        "feature_cols": list(FEATURE_COLS),
        "metrics": metrics,
        "folds": fold_records,
        "models_by_year": models_by_year,
        "resid_std": float(np.std(resid)) if len(resid) else 0.0,
        "max_feature_year": int(unique_years[-1]),
        "importance": importance_df,
        "seed": seed,
    }


def build_pipeline(
    history: pd.DataFrame, cross: pd.DataFrame, seed: int = 42
) -> dict:
    """对齐数据 → 特征工程 → 训练，返回可直接用于预测的流水线工件。"""
    hist, cross_df, missing = align_data(history, cross)
    panel = prepare_panel(hist, cross_df)
    artifacts = train_growth_model(panel, seed=seed)
    return {
        "history": hist,
        "cross": cross_df,
        "panel": panel,
        "artifacts": artifacts,
        "missing_cities": missing,
    }


# ---------------------------------------------------------------------------
# 置信区间辅助
# ---------------------------------------------------------------------------
def _z_for_conf(conf: float) -> float:
    """中心置信度 → 标准正态分位数（查表 + 二分近似）。"""
    table = {
        0.5: 0.6745, 0.6: 0.8416, 0.7: 1.0364, 0.8: 1.2816,
        0.9: 1.6449, 0.95: 1.96,
    }
    if conf in table:
        return table[conf]
    conf = min(0.999, max(0.001, conf))
    q = 1.0 - (1.0 - conf) / 2.0
    lo, hi = -5.0, 5.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if 0.5 * (1.0 + _erf(mid / np.sqrt(2.0))) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _erf(x: float) -> float:
    """误差函数近似（当 scipy 不可用时使用）。"""
    sign = 1.0 if x >= 0 else -1.0
    ax = abs(x)
    t = 1.0 / (1.0 + 0.3275911 * ax)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t
                 - 0.284496736) * t + 0.254829592) * t * np.exp(-ax * ax)
    return sign * y


# ---------------------------------------------------------------------------
# 单城市递归预测
# ---------------------------------------------------------------------------
def _features_from_series(
    years: list[int], log_prices: list[float], static: dict,
    start_year: int, ref_year: int, macro_g: float,
    max_year: int | None = None,
) -> list[float]:
    """根据当前（含历史）序列构造最新一期特征向量（顺序 = FEATURE_COLS）。

    Args:
        max_year: 训练域内最大“年份”特征值。递归预测超出训练年份时把
                  year 特征钳制在 max_year，避免树模型在域外区间抖动。
    """
    logp = np.asarray(log_prices, dtype=float)
    t = years[-1]
    growth = np.diff(logp)
    n = len(logp)
    if n >= 6:
        g3 = (logp[-1] - logp[-4]) / 3.0
        g5 = (logp[-1] - logp[-6]) / 5.0
        vol = float(growth[-5:].std())
    elif n >= 2:
        g3 = g5 = float(growth.mean())
        vol = float(growth.std())
    else:
        g3 = g5 = vol = 0.0
    if not np.isfinite(vol) or pd.isna(vol):
        vol = 0.0
    long_cagr = (logp[-1] - logp[0]) / max(1, t - years[0])
    income = float(static["income"])
    feat = {
        "year": float(min(t, max_year)) if max_year is not None else float(t),
        "macro_g1": float(macro_g) if np.isfinite(macro_g) else 0.0,
        "pos_in_series": min(1.0, (t - start_year) / max(1, ref_year - start_year)),
        "log_price": float(logp[-1]),
        "log_afford": float(np.log(income * income_scale(t)) - logp[-1]),
        "g1": float(growth[-1]) if len(growth) else 0.0,
        "g3_avg": float(g3),
        "g5_avg": float(g5),
        "long_cagr": float(long_cagr),
        "vol5": vol,
        "log_income": float(static["log_income"]),
        "log_population": float(static["log_population"]),
        "log_price2024": float(static["log_price2024"]),
    }
    return [feat[c] for c in FEATURE_COLS]


def forecast_city(
    pipeline: dict,
    city: str,
    horizon: int = DEFAULT_HORIZON,
    conf: float = DEFAULT_CONF,
    macro_adj: float | None = None,
) -> dict:
    """对指定城市做未来 horizon 年房价的递归预测。

    Args:
        macro_adj: 全国宏观情景调整量（对数年度涨幅，基准 = 延续最近一年
            可观测走势）。例如 -0.015 表示“全国年涨幅在近一年基础上再低
            1.5 个百分点”，+0.015 表示更乐观。

    Returns:
        dict：city / province / hist / forecast（year, point, low, high,
        growth_pct）以及 last_price / future_point / cagr_pct 等关键量。
    """
    hist = pipeline["history"]
    cross = pipeline["cross"]
    artifacts = pipeline["artifacts"]

    sub = hist[hist["city"] == city].sort_values("year").reset_index(drop=True)
    if sub.empty:
        raise ValueError(f"未找到城市「{city}」的历史房价数据。")
    cross_row = cross[cross["city"] == city]
    if cross_row.empty:
        raise ValueError(f"未找到城市「{city}」的截面基本面数据。")
    cr = cross_row.iloc[0]

    horizon = max(1, min(int(horizon), MAX_HORIZON))
    conf = min(0.95, max(0.5, conf))
    start_year = int(sub["year"].min())
    years = [int(y) for y in sub["year"].tolist()]
    logp = np.log(sub["house_price"].to_numpy(dtype=float)).tolist()
    static = {
        "income": float(cr["income"]),
        "log_income": float(np.log(cr["income"])),
        "log_population": float(np.log(cr["population"])),
        "log_price2024": float(np.log(cr["house_price"])),
    }

    model = artifacts["model"]
    ridge = artifacts["ridge"]
    max_year = artifacts.get("max_feature_year")
    # 全国情景：最近可观测全国涨幅 + 情景调整量；未来逐年沿用该情景。
    macro_obs = national_growth_rate(hist, DATA_REF_YEAR)
    if not np.isfinite(macro_obs):
        macro_obs = 0.0
    adj = float(macro_adj) if macro_adj is not None else 0.0
    scenario_g = macro_obs + adj
    future_log: list[float] = []
    pred_growth: list[float] = []
    future_years: list[int] = []

    for _ in range(horizon):
        # 特征中的 macro_g1 保持“最近可观测全国涨幅”，保证城市偏离预测不受
        # 情景假设干扰；宏观情景只作为“全国加成项”参与绝对涨幅，方向单调。
        feat = _features_from_series(
            years, logp, static, start_year, DATA_REF_YEAR, macro_obs, max_year=max_year
        )
        if model is not None:
            dev = float(model.predict(np.asarray([feat], dtype=float))[0])
        elif ridge is not None:
            dev = _predict_ridge(ridge, np.asarray(feat, dtype=float))
        else:
            raise RuntimeError("流水线缺少可用模型。")
        g = min(0.35, max(-0.20, dev + scenario_g))  # 偏离 + 全国情景，限幅防极端
        logp.append(logp[-1] + g)
        years.append(years[-1] + 1)
        future_log.append(logp[-1])
        pred_growth.append(g)
        future_years.append(years[-1])

    point_log = np.asarray(future_log, dtype=float)
    z = _z_for_conf(conf)
    k = np.arange(1, horizon + 1, dtype=float)
    half = z * artifacts["resid_std"] * np.sqrt(k)
    forecast = pd.DataFrame(
        {
            "year": future_years,
            "point": np.exp(point_log),
            "low": np.exp(point_log - half),
            "high": np.exp(point_log + half),
            "growth_pct": np.asarray(pred_growth) * 100.0,
        }
    )
    hist_out = sub[["year", "house_price"]].copy()
    last_price = float(hist_out["house_price"].iloc[-1])
    start_price = float(hist_out["house_price"].iloc[0])
    future_point = float(forecast["point"].iloc[-1])
    cagr = (future_point / last_price) ** (1.0 / horizon) - 1.0

    return {
        "city": city,
        "province": str(cr["province"]),
        "hist": hist_out,
        "forecast": forecast,
        "last_price": last_price,
        "start_year": start_year,
        "start_price": start_price,
        "future_point": future_point,
        "future_low": float(forecast["low"].iloc[-1]),
        "future_high": float(forecast["high"].iloc[-1]),
        "cagr_pct": cagr * 100.0,
        "total_change_pct": (future_point / last_price - 1.0) * 100.0,
        "confidence": conf,
    }


# ---------------------------------------------------------------------------
# 城市外样本回测（walk-forward 逐年生重训模型）
# ---------------------------------------------------------------------------
def city_backtest(
    pipeline: dict, city: str, conf: float = DEFAULT_CONF
) -> pd.DataFrame:
    """对指定城市做“逐年外样本回测”。

    对每个 walk-forward 验证年 fy，用“仅用 fy 之前样本训练”的模型，结合截至
    fy 的真实历史，预测 fy→fy+1 的房价并与真实值对比。宏观（全国）涨幅在
    回测期使用当年的真实观测，因此本回测衡量的是机器学习“城市偏离”部分的
    真实外推能力，可作为预测可靠性的直观证据。

    Returns:
        DataFrame：year / prev_price / point / low / high / actual / error_pct
    """
    hist = pipeline["history"]
    cross = pipeline["cross"]
    artifacts = pipeline["artifacts"]
    models_by_year = artifacts.get("models_by_year")
    if not models_by_year:
        raise ValueError("流水线缺少逐年验证模型（walk-forward 未启用），无法回测。")

    sub = hist[hist["city"] == city].sort_values("year").reset_index(drop=True)
    if sub.empty:
        raise ValueError(f"未找到城市「{city}」的历史房价数据。")
    cross_row = cross[cross["city"] == city]
    if cross_row.empty:
        raise ValueError(f"未找到城市「{city}」的截面基本面数据。")
    cr = cross_row.iloc[0]

    start_year = int(sub["year"].min())
    z = _z_for_conf(conf)
    resid_std = float(artifacts.get("resid_std") or 0.0)
    static = {
        "income": float(cr["income"]),
        "log_income": float(np.log(cr["income"])),
        "log_population": float(np.log(cr["population"])),
        "log_price2024": float(np.log(cr["house_price"])),
    }

    rows: list[dict[str, float | int]] = []
    for fy in sorted(int(k) for k in models_by_year):
        upto = sub[sub["year"] <= fy]
        if len(upto) < 6:
            continue
        years = [int(y) for y in upto["year"].tolist()]
        logp = np.log(upto["house_price"].to_numpy(dtype=float)).tolist()
        macro_now = national_growth_rate(hist, fy)  # 截至 fy 的可观测全国涨幅
        feat = _features_from_series(
            years, logp, static, start_year, DATA_REF_YEAR, macro_now
        )
        entry = models_by_year[fy]
        if entry["model"] is not None:
            dev = float(entry["model"].predict(np.asarray([feat], dtype=float))[0])
        elif entry["ridge"] is not None:
            dev = _predict_ridge(entry["ridge"], np.asarray(feat, dtype=float))
        else:
            continue
        macro_next = national_growth_rate(hist, fy + 1)  # 回测年真实宏观涨幅
        if not np.isfinite(macro_next):
            continue
        actual_rows = sub[sub["year"] == fy + 1]["house_price"]
        if actual_rows.empty:
            continue
        prev_price = float(upto["house_price"].iloc[-1])
        actual = float(actual_rows.iloc[0])
        log_growth = dev + macro_next
        point = prev_price * float(np.exp(log_growth))
        half = z * resid_std
        rows.append({
            "year": int(fy + 1),
            "prev_price": prev_price,
            "point": point,
            "low": prev_price * float(np.exp(log_growth - half)),
            "high": prev_price * float(np.exp(log_growth + half)),
            "actual": actual,
            "error_pct": (point / actual - 1.0) * 100.0,
        })

    out = pd.DataFrame(rows, columns=[
        "year", "prev_price", "point", "low", "high", "actual", "error_pct",
    ])
    if out.empty:
        raise ValueError(f"城市「{city}」没有可用于回测的验证年份。")
    return out



def city_history_stats(history: pd.DataFrame, city: str) -> dict:
    """返回城市历史序列的回顾统计（总 / 5年 / 10年 CAGR、波动、峰值）。"""
    sub = history[history["city"] == city].sort_values("year").reset_index(drop=True)
    if sub.empty:
        raise ValueError(f"未找到城市「{city}」的历史房价数据。")
    prices = sub["house_price"].to_numpy(dtype=float)
    years = sub["year"].to_numpy(dtype=int)
    last = float(prices[-1])
    ref = int(years[-1])

    def cagr(target_year: int) -> float | None:
        rows = sub[sub["year"] == target_year]
        if rows.empty:
            return None
        base = float(rows["house_price"].iloc[0])
        span = ref - target_year
        if base <= 0 or span <= 0:
            return None
        return (last / base) ** (1.0 / span) - 1.0

    growth = np.diff(np.log(prices))
    peak_idx = int(np.argmax(prices))
    return {
        "start_year": int(years[0]),
        "start_price": float(prices[0]),
        "ref_year": ref,
        "ref_price": last,
        "cagr_total": cagr(int(years[0])),
        "cagr_5y": cagr(ref - 5),
        "cagr_10y": cagr(ref - 10),
        "volatility": float(growth.std()) if len(growth) > 1 else 0.0,
        "peak_year": int(years[peak_idx]),
        "peak_price": float(prices[peak_idx]),
    }


def _fmt_cny(value: float) -> str:
    """金额展示：低于 1 万显示整元，否则显示万元。"""
    return f"¥{value:,.0f}" if value < 10000 else f"¥{value / 10000:.1f}万"


def build_narrative(city: str, province: str, stats: dict, fc: dict, artifacts: dict) -> str:
    """把城市历史回顾统计与模型预测拼装成一段中文分析结论文本。"""
    def fmt_cagr(value: float | None) -> str:
        return "—" if value is None else f"{value * 100:+.1f}%"

    past = (
        f"{stats['start_year']} 年约 {_fmt_cny(stats['start_price'])}/㎡，"
        f"{stats['ref_year']} 年约 {_fmt_cny(stats['ref_price'])}/㎡，"
        f"{stats['ref_year'] - stats['start_year']} 年年均复合涨幅 {fmt_cagr(stats['cagr_total'])}"
        f"（近 5 年 {fmt_cagr(stats['cagr_5y'])}，近 10 年 {fmt_cagr(stats['cagr_10y'])}）。"
    )
    metrics = artifacts["metrics"]
    backend_name = MODEL_NAMES.get(artifacts["backend"], artifacts["backend"])
    model_part = (
        f"模型在最近 {metrics['test_samples']} 个城市×年份外样本"
        f"（{metrics['test_years'][0]}–{metrics['test_years'][1]} 年）上"
        f"RMSE≈{metrics['rmse'] * 100:.1f}%、R²≈{metrics['r2']:.2f}，"
        f"预测基准为 {backend_name}。"
    )
    last_year = int(fc["forecast"]["year"].iloc[-1])
    return (
        f"<strong>{city}（{province}）</strong>：{past}"
        f"模型预测未来 {len(fc['forecast'])} 年（至 {last_year}）年均复合增速 "
        f"{fc['cagr_pct']:+.2f}%，期末中位房价约 {_fmt_cny(fc['future_point'])}/㎡，"
        f"{fc['confidence'] * 100:.0f}% 置信区间约 "
        f"{_fmt_cny(fc['future_low'])}~{_fmt_cny(fc['future_high'])}/㎡。"
        f"{model_part}"
    )





