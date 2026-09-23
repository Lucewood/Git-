# 内置中文字体（assets/fonts/）

| 文件 | 说明 |
| --- | --- |
| `NotoSansSC-Regular.otf` | Noto Sans SC Regular（简体中文 Subset OTF，31,036 字形，约 7.9 MB） |
| `LICENSE-OFL.txt` | 该字体附带的 SIL Open Font License 1.1 许可证文本 |

- **来源**：<https://github.com/notofonts/noto-cjk> 的
  `Sans/SubsetOTF/SC/NotoSansSC-Regular.otf`（拉取镜像：jsDelivr CDN）。
- **用途**：由 `src/city_insight/fonts.py` 在应用启动时（`charts.setup_plot_style()`）
  注册进 matplotlib，作为 `config.FONT_SANS` 的首选字体。
- **为什么内置**：matplotlib 默认字体 DejaVu Sans 不含 CJK 字形，而
  Streamlit Community Cloud / `python:*-slim` 等 Linux 环境默认不安装中文字体，
  于是图表标题、坐标轴、刻度与图例中的中文会显示成「方框 + 字」的缺字占位。
  把字体随代码一起部署后，**无需系统字体、无需运行时联网**，各平台表现一致。
- **许可证**：SIL OFL 1.1，允许随软件一起分发（分发时保留 `LICENSE-OFL.txt`）。
- **重新获取**：`python scripts/fetch_fonts.py --force`（jsDelivr 多镜像自动重试，可 `--url` 指定其它字体源）。
