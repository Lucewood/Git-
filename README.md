# 🏙️ 中国城市生活成本与幸福感分析可视化

基于全国 **248 个城市**的收入、房价、常住人口与幸福度数据，使用 Streamlit 构建的交互式数据分析网页应用。

> 数据为演示用合成数据集（口径见 `data/metadata.json`），非官方统计。

---

## ✨ 功能特性

| 模块 | 说明 |
| --- | --- |
| 📈 核心指标关联分析 | 收入/房价 vs 幸福度散点 + 回归线、全指标相关性热力图、指标分布 |
| 🔬 城市对比与画像 | 多城市多指标对比图、单城市指标百分位画像 |
| 🤖 房价趋势分析与预测 | 选定城市后基于 2005–2024 年历史序列 + 全样本梯度提升模型递归预测房价趋势（含置信区间与特征重要性） |
| 😊 幸福度排名 | Top/Bottom N 排名（条形图 + 表格） |
| 🏠 住房可负担性分析 | 可负担指数 = 年收入 ÷ 房价，全量分布 + 阈值参考线 |
| 🔍 异常值检测 | IQR 方法识别幸福度 / 可负担指数异常城市 |
| 🗺️ 省份聚合分析 | 省级平均指标排名与明细表 |
| 🗺️ 地理地图 | pyecharts 省级宜居度地图 + Top50 城市价值指数地图 |
| 📋 数据浏览与导出 | 城市明细 / 省份聚合 / 数据质量报告，支持 CSV / Excel / JSON 导出 |

侧边栏支持按**省份**、**城市关键词**与**四项数值范围**联动筛选，并支持配色主题切换。

---

## 📁 项目结构

```
├── src/
│   ├── streamlit_app.py          # Streamlit 入口（仅编排页面）
│   └── city_insight/             # 业务包（可测试、可复用）
│       ├── config.py             # 路径 / 常量 / 环境变量配置
│       ├── logging_setup.py      # 统一日志（控制台 + 滚动文件）
│       ├── data_loader.py        # CSV 加载 / 合并 / 派生指标 / 质量校验
│       ├── analysis.py           # 纯函数分析逻辑（相关、异常值、聚合）
│       ├── forecast.py           # 房价历史 + 特征工程 + 机器学习预测
│       ├── charts.py             # Matplotlib / Seaborn 图表工厂
│       ├── widgets.py            # Streamlit UI 组件封装
│       └── styles.py             # 页面 CSS
├── data/                         # 数据文件 + metadata.json 数据字典
├── notebooks/                    # pyecharts 生成的 HTML 地图
├── scripts/
│   ├── generate_population.py    # 人口数据生成（可复现）
│   ├── generate_house_price_history.py  # 房价历史序列生成（可复现）
│   └── generate_maps.py          # HTML 地图再生成
├── tests/                        # pytest 单元测试 + AppTest 端到端测试
├── .streamlit/config.toml        # Streamlit 服务配置
├── Dockerfile                    # 容器化部署
└── requirements*.txt             # 依赖锁定
```

---

## 🚀 快速开始

```bash
# 1. 安装依赖（建议使用虚拟环境）
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
# source .venv/bin/activate

pip install -r requirements.txt

# 2. 启动应用
streamlit run src/streamlit_app.py
```

浏览器访问 `http://localhost:8501`。

> 提示：Windows 下如需部署到服务器可执行 `streamlit run src/streamlit_app.py --server.address 0.0.0.0 --server.port 8501`。

---

## 🧪 测试

```bash
pip install -r requirements-dev.txt
pytest -v
```

- `tests/test_data_loader.py`：数据加载 / 合并 / 派生指标 / 质量校验
- `tests/test_analysis.py`：相关、异常值、聚合等纯函数逻辑
- `tests/test_forecast.py`：房价历史加载、特征工程、模型训练与递归预测
- `tests/test_charts.py`：图表工厂返回合法 Figure
- `tests/test_streamlit_app.py`：基于 Streamlit AppTest 的无头端到端测试

---

## 📊 数据说明

`data/` 下共 7 个 CSV（6 个截面文件各 248 行 + 1 个房价历史文件 4960 行）+ 1 个数据字典 `metadata.json`：

| 文件 | 字段 | 单位 |
| --- | --- | --- |
| `province.csv` | city, province | — |
| `happiness.csv` | city, happiness | 指数 0-100 |
| `income.csv` | city, income | 元/年 |
| `house_price.csv` | city, house_price | 元/㎡ |
| `house_price_history.csv` | city, year, house_price | 元/㎡（2005–2024，演示口径） |
| `population.csv` | city, population | 万人 |
| `location.csv` | city, longitude, latitude | 度 |

**派生指标**：
- `value_index` 住房可负担指数 = 年收入 ÷ 房价（元/㎡）
- `composite_score` 综合宜居评分（0-100）= 幸福度与可负担指数的加权标准化

数据管道（可复现）：
```bash
python scripts/generate_population.py   # 重新生成人口数据
python scripts/generate_house_price_history.py  # 重新生成房价历史序列
python scripts/generate_maps.py         # 重新生成 HTML 地图
```

---

## 🐳 Docker 部署

```bash
docker build -t city-insight .
docker run -p 8501:8501 city-insight
```

---

## ⚙️ 配置项

支持通过环境变量覆盖（参见 `.env.example`）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `APP_DEBUG` | `false` | 调试模式 |
| `MAP_RENDER_MODE` | `components` | 地图渲染方式：`components` / `iframe` |
| `MAX_COMPARISON_CITIES` | `8` | 城市对比最多数量 |
| `DEFAULT_MAP_HEIGHT` | `520` | 地图高度（px） |
| `N_BOOT_REGRESSION` | `100` | 回归重采样次数 |

---

## 🔁 CI / CD

`.github/workflows/ci.yml` 在 push / PR 时自动执行：依赖安装 → pytest（含 AppTest 端到端）→ 覆盖率报告。

---

## 📄 许可证

本项目为教学 / 演示用途，数据与代码仅供学习交流。
