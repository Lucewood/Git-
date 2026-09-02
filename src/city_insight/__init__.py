"""city_insight —— 中国城市生活成本与幸福感分析业务包。

模块职责划分：
- config:         全局配置（路径、常量、颜色主题、环境变量设置）
- logging_setup:  统一日志配置（控制台 + 滚动文件）
- data_loader:    CSV 加载 / 合并 / 派生指标计算 / 数据质量校验
- analysis:       核心分析逻辑（纯函数，便于单元测试）
- charts:         Matplotlib/Seaborn 图表工厂（返回 Figure，无 UI 依赖）
- widgets:        Streamlit UI 组件封装（指标卡片、滑块、表格格式化）
- styles:         页面自定义 CSS

本包仅导入 stdlib / 第三方库，不依赖 app 运行上下文，可直接被 pytest 等工具导入。
"""

from __future__ import annotations

__version__ = "2.0.0"
__app_name__ = "中国城市生活成本与幸福感分析"
