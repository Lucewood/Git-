"""city_insight —— 中国城市生活成本与幸福感分析业务包。

模块职责划分：
- config:         全局配置（路径、常量、数据集列定义、颜色主题、环境变量设置）
- logging_setup:  统一日志配置（控制台 + 滚动文件）
- fonts:          中文字体注册与解析（内置字体优先，修复 Linux 部署缺字方框）
- data_loader:    CSV 加载 / 合并 / 派生指标计算 / 数据质量校验
- analysis:       核心分析逻辑（纯函数，便于单元测试）
- career:         就业指导推荐引擎（技能 / 薪资 / 景气 / 规模 / 宜居五维打分）
- charts:         Matplotlib/Seaborn 图表工厂（返回 Figure，无 UI 依赖）
- crawler:        通用网络爬虫框架（礼貌抓取、缓存、重试、HTML 表格解析）
- industry_kb:    行业知识库（行业大类 / 薪资基准 / 学历门槛 / 核心技能 / 典型岗位）
- industry_seed:  支柱产业数据源种子（区域划分、省份产业池、确定性记录生成）
- forecast:       房价历史加载、特征工程与机器学习预测（纯函数）
- widgets:        Streamlit UI 组件封装（指标卡片、滑块、表格格式化）
- styles:         页面自定义 CSS

本包仅导入 stdlib / 第三方库，不依赖 app 运行上下文，可直接被 pytest 等工具导入。
"""

from __future__ import annotations

__version__ = "2.3.0"
__app_name__ = "中国城市生活成本与幸福感分析"
