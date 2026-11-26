# ECharts 地图静态资源

本目录用于替代 `notebooks/*.html` 中 pyecharts 默认引用的外部 CDN，
避免运行时网络 / 证书问题导致地图空白。

| 文件 | 来源 | SHA-256 |
| --- | --- | --- |
| `v6/echarts.min.js` | https://assets.pyecharts.org/assets/v6/echarts.min.js | `baa8dfe7e1d9336b98e8986ba7e20ea15e7cdbea1ef42a59d59478632fa45a1d` |
| `v6/maps/china.js` | https://assets.pyecharts.org/assets/v6/maps/china.js | `56ce8e163d7e71808f604800a0e3956009938172a2de805a6dbedb1c7f894eaf` |

## 为什么放在仓库里

2026-11 起 `assets.pyecharts.org` 的证书已过期，浏览器会报
`ERR_CERT_DATE_INVALID`，随后地图脚本报 `echarts is not defined` / 地图空白。
本地浏览器可能因缓存偶尔成功，Cloud 新会话则更容易失败，导致“本地正常、
云端地图空白”的差异。

应用在读取地图 HTML 时会把

```text
https://assets.pyecharts.org/assets/
```

改写为相对路径

```text
app/static/pyecharts/
```

并依赖 `.streamlit/config.toml` 中的 `server.enableStaticServing = true`
由 Streamlit 同源提供文件；不再发起任何外部 CDN 请求。

> 必须使用相对路径：本地应用解析为 `/app/static/pyecharts/...`；Streamlit
> Cloud 的应用 iframe 位于 `/~/+/`，相对路径解析为
> `/~/+/app/static/pyecharts/...`。根路径 `/app/static/...` 在 Cloud 会返回
> 外壳 HTML（200 text/html），不能用于脚本。

## 许可证与更新

- ECharts 为 Apache Software Foundation 的 Apache ECharts 项目，
  许可证：Apache License 2.0（`echarts.min.js` 文件头保留了许可证声明）。
- `china.js` 为中国地图注册数据，随 pyecharts / ECharts 官方资源分发，
  同样按 Apache License 2.0 使用。
- 更新时请保持 pyecharts 版本目录一致，例如：

```bash
# 仅在更新资源时使用；-k 是因为旧 CDN 证书已过期
curl -k -L https://assets.pyecharts.org/assets/v6/echarts.min.js \
  -o src/static/pyecharts/v6/echarts.min.js
curl -k -L https://assets.pyecharts.org/assets/v6/maps/china.js \
  -o src/static/pyecharts/v6/maps/china.js
```

更新后同步修改上表的 SHA-256，并运行 `pytest tests/test_map_assets.py`。
