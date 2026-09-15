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
| 🧭 **就业指导与产业推荐** | **基于爬虫采集的城市支柱产业数据库**（就业占比 / 平均月薪 / 需求景气指数 / 岗位年增速 / 学历门槛 / 核心技能），按「技能匹配 + 薪资 + 发展空间 + 岗位规模 + 生活宜居」五维加权打分，输出个性化工种 / 城市推荐、匹配度构成图、技能供需缺口与逐条提升建议 |
| 🗺️ 省份聚合分析 | 省级平均指标排名与明细表 |
| 🗺️ 地理地图 | pyecharts 省级宜居度地图 + Top50 城市价值指数地图 |
| 📋 数据浏览与导出 | 城市明细 / 省份聚合 / 数据质量报告，支持 CSV / Excel / JSON 导出 |

侧边栏支持按**省份**、**城市关键词**与**四项数值范围**联动筛选，并支持配色主题切换。
就业推荐的范围同样受侧边栏筛选（如「浙江省」）约束，可直接用于「想去某省就业」的场景。

---

## 📁 项目结构

```
├── src/
│   ├── streamlit_app.py          # Streamlit 入口（仅编排页面）
│   └── city_insight/             # 业务包（可测试、可复用）
│       ├── config.py             # 路径 / 常量 / 数据集列定义 / 环境变量配置
│       ├── logging_setup.py      # 统一日志（控制台 + 滚动文件）
│       ├── data_loader.py        # CSV 加载 / 合并 / 派生指标 / 质量校验
│       ├── analysis.py           # 纯函数分析逻辑（相关、异常值、聚合）
│       ├── career.py             # 就业指导推荐引擎（五维加权打分与建议生成）
│       ├── crawler.py            # 通用爬虫框架（robots / 限速 / 重试 / 缓存 / 解析）
│       ├── industry_kb.py        # 行业知识库（16 个行业大类的技能与岗位口径）
│       ├── industry_seed.py      # 支柱产业数据源种子（确定性可复现）
│       ├── forecast.py           # 房价历史 + 特征工程 + 机器学习预测
│       ├── charts.py             # Matplotlib / Seaborn 图表工厂
│       ├── widgets.py            # Streamlit UI 组件封装
│       └── styles.py             # 页面 CSS
├── data/                         # 数据文件 + metadata.json 数据字典
│   ├── industry.csv              # 支柱产业与人才需求（爬虫产出）
│   ├── raw/industry/*.html       # 区域统计快报页面快照（爬虫数据源）
│   └── crawl_cache/              # 爬虫响应缓存（.gitignore）
├── notebooks/                    # pyecharts 生成的 HTML 地图
├── scripts/
│   ├── crawl_industry.py         # 支柱产业爬虫管道（快照 + 抓取 + 解析 + 落库）
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
- `tests/test_crawler.py`：爬虫抓取策略、双解析器回退、页面解析与清洗
- `tests/test_career.py`：就业推荐打分、城市聚合、技能缺口与建议文本
- `tests/test_industry_data.py`：支柱产业数据完整性 + 爬虫管道端到端复现校验
- `tests/test_streamlit_app.py`：基于 Streamlit AppTest 的无头端到端测试

---

## 🕷️ 支柱产业爬虫管道（就业推荐数据来源）

`scripts/crawl_industry.py` 采用「数据源快照 → 礼貌抓取 → 解析清洗 → 落库」两阶段流程：

```bash
python scripts/crawl_industry.py                  # 生成离线页面快照并爬取（默认，离线可复现）
python scripts/crawl_industry.py --mode snapshot  # 仅重新生成 data/raw/industry/*.html 页面快照
python scripts/crawl_industry.py --mode crawl --no-network   # 仅爬取本地快照（CI 场景）
python scripts/crawl_industry.py --mode crawl \
    --url https://example.com/pillar-industry.html           # 追加真实公开页面数据源
```

| 阶段 | 说明 |
| --- | --- |
| ① snapshot | 依据 `city_insight.industry_seed` 的种子口径，渲染 8 个区域「支柱产业与人才需求统计快报」HTML 页面（含导航 / 脚注等噪音节点，数据表 `class="industry-table"`），模拟公开统计网页结构 |
| ② crawl | 使用 `city_insight.crawler` 的礼貌抓取器抓取页面并解析成结构化记录，清洗后写出 `data/industry.csv` |

爬虫工程要素（均可在单元测试中验证）：

- **合规**：自定义 User-Agent 标识身份、`robots.txt` 准入检查（按主机缓存解析结果）、同域请求最小间隔限速、失败指数退避重试；
- **可复现**：响应按 URL 摘要落盘到 `data/crawl_cache/`，重复运行不重复打网络；默认只抓取仓库内置 `file://` 快照，零对外请求；
- **稳健**：HTTP 客户端优先 `requests`、缺失时回退 `urllib.request`；HTML 解析优先 `BeautifulSoup`、缺失时回退 stdlib `html.parser`；数值清洗兼容千分位 / 百分号 / 万 / `—` 等写法；
- **可测试**：解析（`parse_industry_page`）与清洗（`build_industry_frame`）分离，`CrawlReport` 记录每源成功 / 缓存 / 快照命中与错误。

> ⚠️ 合规提示：如需抓取真实站点，请先确认目标站点 `robots.txt` 与使用条款；本仓库默认配置不会产生任何对外网络请求。

### 🧭 就业推荐打分模型

```
匹配度 = 100 × 学历修正系数 × Σ wᵢ·sᵢ / Σ wᵢ
```

| 维度 | 口径 |
| --- | --- |
| 技能匹配 | 用户技能对「该产业核心技能」的覆盖率（命中数 ÷ 核心技能数） |
| 薪资待遇 | min(产业平均月薪 ÷ 期望月薪, 1.2) ÷ 1.2 |
| 发展空间 | 需求景气指数（权重 0.6）+ 岗位增速在候选集内的百分位（权重 0.4） |
| 岗位规模 | 该产业就业占比在候选集内的百分位 |
| 生活宜居 | 城市幸福度 / 可负担指数 / 房价压力百分位合成（可切换「优先低生活成本」） |
| 学历修正 | 学历低于岗位门槛时每档折减 6%（0.94^档差），并在结果中给出提示 |

五个维度权重均可在页面上用滑块调整；未填写技能标签时自动把技能权重并入其余维度。

---

## 📊 数据说明

`data/` 下共 8 个 CSV（6 个截面文件各 248 行 + 1 个房价历史文件 4960 行 + 1 个支柱产业长表 792 行）+ 1 个数据字典 `metadata.json`：

| 文件 | 字段 | 单位 |
| --- | --- | --- |
| `province.csv` | city, province | — |
| `happiness.csv` | city, happiness | 指数 0-100 |
| `income.csv` | city, income | 元/年 |
| `house_price.csv` | city, house_price | 元/㎡ |
| `house_price_history.csv` | city, year, house_price | 元/㎡（2005–2024，演示口径） |
| `population.csv` | city, population | 万人 |
| `location.csv` | city, longitude, latitude | 度 |
| `industry.csv` | city, industry, category, share_pct, avg_salary, demand_index, growth_pct, education, skills | % / 元·月⁻¹ / 指数 / %（爬虫采集，长表） |

**派生指标**：
- `value_index` 住房可负担指数 = 年收入 ÷ 房价（元/㎡）
- `composite_score` 综合宜居评分（0-100）= 幸福度与可负担指数的加权标准化

数据管道（可复现）：
```bash
python scripts/generate_population.py   # 重新生成人口数据
python scripts/generate_house_price_history.py  # 重新生成房价历史序列
python scripts/crawl_industry.py        # 重新爬取支柱产业数据（含页面快照）
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
| `CAREER_TOP_N` | `10` | 就业推荐默认展示条数 |
| `MAX_CAREER_RESULTS` | `30` | 就业推荐最多可展示条数 |
| `CRAWL_DELAY` | `1.0` | 爬虫同域请求最小间隔（秒） |
| `CRAWL_TIMEOUT` | `10.0` | 爬虫单次请求超时（秒） |

---

## 🔁 CI / CD

`.github/workflows/ci.yml` 在 push / PR 时自动执行：依赖安装 → pytest（含 AppTest 端到端）→ 覆盖率报告。

---

## 📄 许可证

本项目为教学 / 演示用途，数据与代码仅供学习交流。
