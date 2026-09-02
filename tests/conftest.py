"""pytest 共享配置：将 src/ 加入 sys.path，并提供公共 fixtures。"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd
import pytest

# 将 src/ 加入导入路径，使 city_insight 包可被测试直接导入
SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# 抑制无 Streamlit 运行时导入缓存装饰器时的噪音日志
logging.getLogger("streamlit").setLevel(logging.ERROR)
logging.getLogger("city_insight").setLevel(logging.CRITICAL)


@pytest.fixture(scope="session")
def sample_df() -> pd.DataFrame:
    """构造一个小的合成宽表，用于纯函数（analysis / charts）测试。"""
    return pd.DataFrame(
        {
            "city": ["A城", "B城", "C城", "D城", "E城"],
            "province": ["甲省", "甲省", "乙省", "乙省", "乙省"],
            "happiness": [90.0, 80.0, 70.0, 60.0, 50.0],
            "income": [200000, 150000, 100000, 50000, 30000],
            "house_price": [40000, 30000, 20000, 10000, 15000],
            "population": [2000.0, 1500.0, 1000.0, 500.0, 300.0],
            "value_index": [5.0, 5.0, 5.0, 5.0, 2.0],
            "composite_score": [80.0, 70.0, 60.0, 50.0, 20.0],
        }
    )


@pytest.fixture(scope="session")
def real_df() -> pd.DataFrame:
    """加载真实数据文件（data/ 下 CSV 合并结果），用于集成级测试。"""
    from city_insight.config import DATA_DIR
    from city_insight.data_loader import load_and_merge

    df, _ = load_and_merge(DATA_DIR)
    return df
