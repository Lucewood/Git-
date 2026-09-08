"""
生成 data/house_price_history.csv —— 城市年度住房均价历史序列（2005–2024）。

口径：主数据仅含 2024 年房价快照（house_price.csv）。本脚本以 2024 快照为
锚点，结合「城市基本面强度（收入 / 人口 / 房价水平）」与「全国宏观房价
周期」反向重建各城市 2005–2024 年度均价序列，供趋势分析与机器学习预测。
- 2024 年数值与 house_price.csv 完全一致；确定性合成（种子固定、可复现）；
- 非官方统计，仅用于展示分析 / 预测流程。

结构化生成模型（把“可学习信号”与“随机扰动”分离，提升可预测性与稳定性）：
1. 全国宏观周期：全国平均房价各年相对涨速由 MACRO_REL 定义并归一化为年度
   份额（2007 / 2009 / 2016 为牛市，2021 年后持续降温，扩张与调整交替）；
2. 城市基本面强度：收入 / 人口 / 房价水平 z 分数合成热度 heat，决定城市
   2005–2024 长期累计对数涨幅总目标 G（与 2005 / 2024 双锚点严格一致）；
3. 涨幅偏离过程：把城市年度涨幅拆成「全国共同周期 A(t) + 城市偏离
   w(t) + c」，其中 w(t) 是 AR(1) 动量偏离（热者恒热 / 冷者恒冷），常数 c
   使各城市累计涨幅与双锚点严格一致。动量与截面倾斜对宏观阶段不敏感，
   因此模型在训练期任意阶段学到的“偏离规律”都可以稳定外推；
4. 随机扰动：AR(1) 过程 w(t) 的新息是唯一的不可预测成分（幅度适中）。

运行方式（项目根目录）：python scripts/generate_house_price_history.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUT_PATH = DATA_DIR / "house_price_history.csv"

HISTORY_START_YEAR = 2005
REF_YEAR = 2024  # 锚点年份，须与 data/metadata.json 的 reference_year 一致

# 全国宏观房价年度相对景气强度（键 = 目标年份；>0 扩张 / <0 调整；
# 只决定年份间相对涨幅分配，绝对值无业务含义）。
# 结构参考 2005–2024 中国房地产真实节奏：2007 / 2009 / 2016 大牛市，
# 2008 金融危机、2014–2015 调整、2021 年后持续降温——扩张与调整两阶段
# 均出现在训练期内，便于机器学习学习“弹性城市双向放大”的规律。
MACRO_REL: dict[int, float] = {
    2006: 1.1, 2007: 1.8, 2008: -0.4, 2009: 1.4, 2010: 1.1,
    2011: 0.6, 2012: 0.2, 2013: 0.8, 2014: -0.7, 2015: -0.2,
    2016: 1.6, 2017: 1.1, 2018: 0.5, 2019: 0.6, 2020: 0.4,
    2021: 0.2, 2022: -0.6, 2023: -0.6, 2024: -0.4,
}

# 城市涨幅偏离过程参数
MOMENTUM_PHI = 0.55   # AR(1) 系数：>0 表示偏离动量（热者恒热 / 冷者恒冷）
MOMENTUM_SIG = 0.040  # 每期不可预测新息的标准差（对数尺度）

SEED = 2024

# 重点城市 2005 年房价锚点（元/㎡，近似真实水平）。
# 非本表城市由“基本面强度”公式推算 2005 年起点。
KNOWN_2005: dict[str, int] = {
    "北京": 6200, "上海": 7100, "深圳": 7200, "广州": 5500,
    "杭州": 5000, "南京": 4200, "苏州": 4500, "天津": 4200,
    "成都": 3000, "重庆": 2500, "武汉": 3200, "西安": 2700,
    "郑州": 2400, "长沙": 2600, "合肥": 2300, "青岛": 3200,
    "宁波": 3500, "厦门": 4800, "济南": 2500, "福州": 2700,
    "昆明": 2400, "哈尔滨": 2300, "沈阳": 2800, "大连": 3500,
    "长春": 2300, "无锡": 3800, "佛山": 2800, "东莞": 3000,
    "珠海": 3200, "三亚": 3500, "海口": 2200,
}

# 单年对数涨幅安全边界（超出触发断言，防止离群）
MIN_GROWTH, MAX_GROWTH = -0.35, 0.60


def zscore(series: pd.Series) -> pd.Series:
    """z-score 标准化；零方差时返回 0 序列。"""
    std = series.std()
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=series.index)
    return (series - series.mean()) / std


def _city_rng(city: str, salt: str) -> np.random.Generator:
    """按城市名派生确定性随机源（与进程/顺序无关，保证可复现）。

    不使用内置 hash()（进程间随机加盐），改用 hashlib 摘要生成稳定种子。
    """
    import hashlib

    digest = hashlib.md5(f"{salt}:{city}".encode("utf-8")).hexdigest()
    seed = int(digest[:8], 16)
    return np.random.default_rng(seed)


def _momentum_growth(rng: np.random.Generator, n_incr: int) -> np.ndarray:
    """生成城市年度涨幅相对全国的 AR(1) 动量偏离 w(t)（长度 n_incr）。

    w(1) = η1；w(t) = φ·w(t-1) + ηt，η ~ N(0, MOMENTUM_SIG)。
    """
    w = np.empty(n_incr, dtype=float)
    prev = 0.0
    for j in range(n_incr):
        prev = MOMENTUM_PHI * prev + rng.normal(0.0, MOMENTUM_SIG)
        w[j] = prev
    return w


def build_history(house: pd.DataFrame, income: pd.DataFrame, pop: pd.DataFrame) -> pd.DataFrame:
    """为每个城市生成 2005–2024 的年度均价序列（锚定 2024 = house_price.csv）。

    城市年度对数涨幅 g(t) = A(t) + w(t) + c：
    - A(t)：全国共同周期 = 全国平均累计涨幅 NG × 年度份额（随年份变化）；
    - w(t)：城市涨幅偏离的 AR(1) 动量偏离（涨跌市均成立、可学习）；
    - c：常数倾斜 = (G − NG − Σw) / 期数，使累计涨幅严格等于城市 G（双锚点）。
    """
    years = list(range(HISTORY_START_YEAR, REF_YEAR + 1))
    n_years = len(years)
    n_incr = n_years - 1  # 2006–2024 的年度涨幅期数

    frame = house.merge(income, on="city", how="left").merge(pop, on="city", how="left")
    frame = frame.dropna(subset=["house_price", "income", "population"])

    # 城市基本面强度 → 长期累计涨幅（对数尺度）的“热度”
    heat = (
        0.5 * zscore(np.log(frame["income"]))
        + 0.4 * zscore(np.log(frame["population"]))
        + 0.55 * zscore(np.log(frame["house_price"]))
    ).clip(-1.5, 3.0)

    # 全国宏观周期份额（相对景气强度归一化，允许负值表达调整年份）
    macro = np.asarray(
        [MACRO_REL[y] for y in range(HISTORY_START_YEAR + 1, REF_YEAR + 1)], dtype=float
    )
    shares = macro / macro.sum()

    def start_price_for(city: str, h: float, p2024: float) -> float:
        """2005 年起点：重点城市用近似真实锚点，其余由基本面强度推算。"""
        if city in KNOWN_2005:
            return float(KNOWN_2005[city])
        total_log_heat = max(0.55, 1.0 + 0.46 * h)
        return max(300.0, p2024 / float(np.exp(total_log_heat)))

    # 第一遍：求各城市累计对数涨幅 G，以及全国平均累计涨幅 NG
    total_g_list: list[float] = []
    starts: list[float] = []
    for city, p2024, h in zip(frame["city"], frame["house_price"], heat):
        city = str(city)
        p2024 = float(p2024)
        h = float(h)
        log_start = float(np.log(max(start_price_for(city, h, p2024), 300.0)))
        log_end = float(np.log(p2024))
        starts.append(log_start)
        total_g_list.append(log_end - log_start)

    ng = float(np.mean(total_g_list))          # 全国平均累计涨幅（对数）
    A = shares * ng                            # 全国共同周期（逐年对数涨幅）

    rows: list[dict[str, float | int]] = []
    for idx, (city, p2024) in enumerate(zip(frame["city"], frame["house_price"])):
        city = str(city)
        p2024 = float(p2024)
        total_g = total_g_list[idx]
        if total_g <= 0:
            continue  # 起点不合理的城市不应发生，直接跳过
        rng = _city_rng(city, "momentum")

        # 城市涨幅偏离：AR(1) 动量 w(t) + 常数倾斜 c（保证累计涨幅 = total_g）
        w = _momentum_growth(rng, n_incr)
        c = (total_g - ng - float(w.sum())) / n_incr
        growth = A + (w + c)                   # 逐年对数涨幅（2006–2024）
        step = np.concatenate(([0.0], np.cumsum(growth)))  # 20 期：首期为 0

        log_start = starts[idx]
        log_end = float(np.log(p2024))
        log_prices = log_start + step
        # 首尾锚点精确校验
        assert abs(float(log_prices[0]) - log_start) < 1e-9
        assert abs(float(log_prices[-1]) - log_end) < 1e-6

        assert MIN_GROWTH <= float(growth.min()) and float(growth.max()) <= MAX_GROWTH, (
            f"{city} 存在异常年度涨幅 [{growth.min():.3f}, {growth.max():.3f}]"
        )

        prices = np.round(np.exp(log_prices)).astype(int)
        for yr, pr in zip(years, prices):
            rows.append({"city": city, "year": yr, "house_price": pr})

    out = pd.DataFrame(rows, columns=["city", "year", "house_price"])
    out["city"] = out["city"].astype(str).str.strip()
    out["year"] = out["year"].astype(int)
    out["house_price"] = out["house_price"].astype(int)
    return out.sort_values(["city", "year"]).reset_index(drop=True)



def main() -> None:
    house = pd.read_csv(DATA_DIR / "house_price.csv")
    income = pd.read_csv(DATA_DIR / "income.csv")
    pop = pd.read_csv(DATA_DIR / "population.csv")
    province = pd.read_csv(DATA_DIR / "province.csv")

    expected_cities = province["city"].astype(str).str.strip().tolist()
    assert len(expected_cities) == len(set(expected_cities)), "省份清单存在重复城市！"

    out = build_history(house, income, pop)
    out = out[out["city"].isin(expected_cities)].reset_index(drop=True)

    # 校验：每城 20 个年份、无缺失、2024 年与房价快照完全一致
    counts = out.groupby("city")["year"].count()
    assert (counts == REF_YEAR - HISTORY_START_YEAR + 1).all(), "部分城市年份不完整！"
    snapshot = house[["city", "house_price"]].rename(columns={"house_price": "snapshot"})
    merged = out[out["year"] == REF_YEAR].merge(snapshot, on="city")
    assert (merged["house_price"] == merged["snapshot"]).all(), "2024 年锚点与快照不一致！"

    out.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"已生成 {OUT_PATH}")
    print(f"城市数：{out['city'].nunique()} · 行数：{len(out)} · "
          f"年份：{out['year'].min()}-{out['year'].max()}")
    span = (
        out[out["year"] == REF_YEAR].set_index("city")["house_price"]
        / out[out["year"] == HISTORY_START_YEAR].set_index("city")["house_price"]
    )
    print(f"2005→{REF_YEAR} 累计涨幅倍数范围：[{span.min():.2f}, {span.max():.2f}]")
    log_growth = out.sort_values(["city", "year"]).groupby("city")["house_price"].apply(
        lambda s: np.log(s).diff().dropna()
    )
    print(f"单年对数涨幅中位数：{log_growth.median():.3f} · "
          f"城市内标准差均值：{log_growth.groupby(level=0).std().mean():.3f}")


if __name__ == "__main__":
    main()

