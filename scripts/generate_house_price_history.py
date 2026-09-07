"""
生成 data/house_price_history.csv —— 城市年度住房均价历史序列（2005–2024）。

数据口径说明：
- 主数据（data/*.csv）仅提供 2024 年房价快照（data/house_price.csv），
  不包含时间序列。本脚本以 2024 年快照为锚点，结合「城市基本面热度
  （收入 / 人口 / 房价水平）」与「全国宏观房价增速节奏」反向重建各城市
  2005–2024 年的年度均价序列，供房价趋势分析与机器学习预测模块使用；
- 重建结果 2024 年数值与 house_price.csv 完全一致；
- 序列为演示用确定性合成口径（种子固定、可复现），非官方统计，
  仅用于展示分析 / 预测流程。

运行方式（在项目根目录）：
    python scripts/generate_house_price_history.py
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

# 全国宏观房价年度节奏（键为目标年份，值≈当年名义涨幅权重，仅用于在时间轴上
# 分配各城市的累计涨幅；越大代表当年全国行情越热）。
MACRO_WEIGHTS: dict[int, float] = {
    2006: 0.07, 2007: 0.11, 2008: 0.02, 2009: 0.13, 2010: 0.07,
    2011: 0.06, 2012: 0.03, 2013: 0.05, 2014: 0.01, 2015: 0.02,
    2016: 0.11, 2017: 0.06, 2018: 0.03, 2019: 0.03, 2020: 0.02,
    2021: 0.02, 2022: 0.006, 2023: 0.009, 2024: 0.007,
}

# 每年扰动的标准差（对数涨幅），用于产生城市间异质、可辨识的年度波动
NOISE_SIGMA = 0.05
# 单年对数涨幅裁剪区间（避免异常离群值）
MIN_GROWTH, MAX_GROWTH = -0.06, 0.32

SEED = 2024

# 重点城市 2005 年房价锚点（元/㎡，约 2005 年实际水平，近似值）。
# 非本表城市由下方“基本面热度”公式推算 2005 年起点。
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


def zscore(series: pd.Series) -> pd.Series:
    """z-score 标准化；零方差时返回 0 序列。"""
    std = series.std()
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=series.index)
    return (series - series.mean()) / std


def build_history(house: pd.DataFrame, income: pd.DataFrame, pop: pd.DataFrame) -> pd.DataFrame:
    """为每个城市生成 2005–2024 的年度均价序列（锚定 2024 = house_price.csv）。"""
    rng = np.random.default_rng(SEED)
    years = list(range(HISTORY_START_YEAR, REF_YEAR + 1))
    target_years = list(range(HISTORY_START_YEAR + 1, REF_YEAR + 1))
    weights = np.asarray([MACRO_WEIGHTS[y] for y in target_years], dtype=float)
    shares = weights / weights.sum()

    frame = house.merge(income, on="city", how="left").merge(pop, on="city", how="left")
    frame = frame.dropna(subset=["house_price", "income", "population"])

    # 城市基本面热度 → 2005-2024 累计涨幅（对数尺度）
    heat = (
        0.5 * zscore(np.log(frame["income"]))
        + 0.4 * zscore(np.log(frame["population"]))
        + 0.55 * zscore(np.log(frame["house_price"]))
    ).clip(-1.5, 3.0)
    log_total = (1.0 + 0.46 * heat).clip(lower=0.55)

    rows: list[dict[str, float | int]] = []
    for city, p2024, total in zip(frame["city"], frame["house_price"], log_total):
        noise = rng.normal(loc=0.0, scale=NOISE_SIGMA, size=len(target_years))
        # 城市 2005 年起点：重点城市用近似真实锚点，其余由基本面热度推算
        if city in KNOWN_2005:
            start_price = float(KNOWN_2005[city])
        else:
            start_price = float(p2024) / float(np.exp(total))
        start_price = max(start_price, 300.0)

        log_start, log_end = float(np.log(start_price)), float(np.log(p2024))
        raw = np.clip(shares * (log_end - log_start) + noise, MIN_GROWTH, MAX_GROWTH)
        # 统一漂移校正，保证首尾两个锚点（2005 起点、2024 快照）都精确命中
        raw = raw + (log_end - log_start - raw.sum()) / len(raw)

        # 从 2005 年起点正向构建路径
        log_prices = np.empty(len(years), dtype=float)
        log_prices[0] = log_start
        for j in range(1, len(years)):
            log_prices[j] = log_prices[j - 1] + raw[j - 1]

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

    # 校验：每个城市 20 个年份、无缺失、2024 年与快照完全一致
    counts = out.groupby("city")["year"].count()
    assert (counts == REF_YEAR - HISTORY_START_YEAR + 1).all(), "部分城市年份不完整！"
    snapshot = house[["city", "house_price"]].rename(
        columns={"house_price": "snapshot"}
    )
    merged = out[out["year"] == REF_YEAR].merge(snapshot, on="city")
    assert (merged["house_price"] == merged["snapshot"]).all(), "2024 年锚点与房价快照不一致！"

    out.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"已生成 {OUT_PATH}")
    print(f"城市数：{out['city'].nunique()} · 行数：{len(out)} · 年份：{out['year'].min()}-{out['year'].max()}")
    span = (
        out[out["year"] == REF_YEAR].set_index("city")["house_price"]
        / out[out["year"] == HISTORY_START_YEAR].set_index("city")["house_price"]
    )
    print(f"2005→{REF_YEAR} 累计涨幅倍数范围：[{span.min():.2f}, {span.max():.2f}]")


if __name__ == "__main__":
    main()
