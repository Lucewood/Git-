"""API 密钥与调用参数配置（Streamlit secrets 优先，环境变量兜底）。

背景：云端部署（Streamlit Community Cloud / Docker / 内网服务器）不允许把密钥写进
代码或提交进仓库，统一放到 Streamlit 的「后台 secrets」——即 `.streamlit/secrets.toml`
（本地 / 自建服务器）或 Cloud 控制台「应用 → Settings → Secrets」（云端）。

读取优先级（从高到低，取首个非空值）：

| 优先级 | 位置 | 写法示例（secrets.toml） |
| --- | --- | --- |
| 1 | `[api.<服务名>]` 小节（推荐） | `[api.deepseek]` + `api_key = "sk-…"` |
| 2 | `[api]` 单服务小节 | `[api]` + `api_key = "sk-…"` |
| 3 | 顶层扁平键（与环境变量同名） | `DEEPSEEK_API_KEY = "sk-…"` / `API_KEY = "sk-…"` |
| 4 | 环境变量 / `.env`（本地开发 / CI） | `DEEPSEEK_API_KEY=sk-…` / `API_KEY=sk-…` |

同一优先级内，服务专属名（`DEEPSEEK_API_KEY`）优先于通用名（`API_KEY`）。

设计要点：
1. **零副作用**：`secrets.toml` 不存在、键缺失、TOML 语法错误、值类型非法等任何情况
   都只返回「未配置」状态，绝不抛异常，应用主流程照常渲染（CI 首次克隆可直接跑通）；
2. **脱敏**：对外只提供 `masked_key`（形如 `sk-abc********1234`），日志 / 页面 / 导出
   都不会回显完整密钥；
3. **不依赖 Streamlit 运行时**：`st.secrets` 采用函数内延迟导入，`scripts/` 与 pytest
   在没有 Streamlit 会话上下文时同样可用（缺失 streamlit 时自动跳过 secrets 层）；
4. **可扩展**：`PROVIDERS` 覆盖常见服务，未知服务名按 `<NAME>_API_KEY` 约定自动适配。

用法示例：

```python
from city_insight.api_config import get_api_credentials, has_api_credentials

creds = get_api_credentials("deepseek")      # 也可省略，取 [api].provider 声明的默认服务
if creds.usable:
    headers = creds.headers()                 # {"Authorization": "Bearer sk-…"}
    url = creds.endpoint("chat/completions")  # base_url 与 path 自动拼接
else:
    print("未配置 API 密钥，功能降级")
```
"""

from __future__ import annotations

import logging
import math
import os
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量（页面文案、测试与调用方共用）
# ---------------------------------------------------------------------------
API_SECTION = "api"
DEFAULT_PROVIDER = "openai"
DEFAULT_TIMEOUT = 30.0
DEFAULT_ENABLED = True

SECRETS_FILE = ".streamlit/secrets.toml"
SECRETS_EXAMPLE_FILE = ".streamlit/secrets.toml.example"

SOURCE_SECRETS = "streamlit-secrets"
SOURCE_ENV = "environment"
SOURCE_NONE = "none"

SOURCE_LABELS: dict[str, str] = {
    SOURCE_SECRETS: "Streamlit secrets",
    SOURCE_ENV: "环境变量 / .env",
    SOURCE_NONE: "未配置",
}


@dataclass(frozen=True)
class ApiProvider:
    """一个 API 服务的配置口径（标识 / 展示名 / 环境变量名 / 默认接入点）。

    Attributes:
        key: 服务标识（secrets 小节名与环境变量前缀，小写）。
        label: 页面展示名。
        env_key: 服务专属环境变量名（如 DEEPSEEK_API_KEY）。
        default_base_url: 未配置 base_url 时的默认接入点（高德等无此概念，留空）。
        default_model: 未配置 model 时的默认模型名。
        console: 密钥申请地址（写入配置指引文案）。
    """

    key: str
    label: str
    env_key: str
    default_base_url: str = ""
    default_model: str = ""
    console: str = ""


PROVIDERS: dict[str, ApiProvider] = {
    "openai": ApiProvider(
        key="openai",
        label="OpenAI / 兼容接口",
        env_key="OPENAI_API_KEY",
        default_base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        console="https://platform.openai.com/api-keys",
    ),
    "deepseek": ApiProvider(
        key="deepseek",
        label="DeepSeek",
        env_key="DEEPSEEK_API_KEY",
        default_base_url="https://api.deepseek.com/v1",
        # 2026 年 DeepSeek 当前模型（支持 thinking 开关）；旧版 API 可在 secrets 中
        # 显式改为 "deepseek-chat" / "deepseek-reasoner"。
        default_model="deepseek-flash",
        console="https://platform.deepseek.com/api_keys",
    ),
    "dashscope": ApiProvider(
        key="dashscope",
        label="阿里云百炼 / 通义千问",
        env_key="DASHSCOPE_API_KEY",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-plus",
        console="https://bailian.console.aliyun.com/",
    ),
    "amap": ApiProvider(
        key="amap",
        label="高德地图 Web 服务",
        env_key="AMAP_API_KEY",
        console="https://console.amap.com/dev/key/app",
    ),
    "custom": ApiProvider(
        key="custom",
        label="自定义服务",
        env_key="CUSTOM_API_KEY",
    ),
}

# 字段别名：同一字段在 secrets 中允许的多种写法（按顺序尝试）
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "api_key": ("api_key", "apikey", "key", "token"),
    "base_url": ("base_url", "baseUrl", "api_base", "endpoint", "url"),
    "model": ("model", "model_name", "modelName"),
    "timeout": ("timeout", "request_timeout"),
    "enabled": ("enabled",),
}


@dataclass(frozen=True)
class ApiCredentials:
    """一个 API 服务的可用凭证与调用参数（不可变，可安全缓存 / 跨函数传参）。

    `source` 记录密钥的实际来源（secrets / 环境变量），便于排查「为什么没生效」。
    """

    provider: str = DEFAULT_PROVIDER
    label: str = ""
    # repr=False：即使意外打印 / 记录对象，也不会把完整密钥写进日志或页面。
    api_key: str = field(default="", repr=False)
    base_url: str = ""
    model: str = ""
    timeout: float = DEFAULT_TIMEOUT
    enabled: bool = DEFAULT_ENABLED
    source: str = SOURCE_NONE

    @property
    def configured(self) -> bool:
        """是否读到密钥（不关心是否被 enabled=false 关闭）。"""
        return bool(self.api_key and self.api_key.strip())

    @property
    def usable(self) -> bool:
        """是否可直接使用：密钥非空且未被显式关闭。"""
        return self.configured and self.enabled

    @property
    def source_label(self) -> str:
        """密钥来源的展示名。"""
        return SOURCE_LABELS.get(self.source, self.source)

    @property
    def masked_key(self) -> str:
        """脱敏密钥（仅用于页面 / 日志展示，绝不返回完整密钥）。"""
        key = self.api_key.strip()
        if not key:
            return "未配置"
        if len(key) <= 8:
            return f"{key[:1]}{'*' * max(len(key) - 1, 1)}"
        return f"{key[:6]}********{key[-4:]}"

    def headers(self) -> dict[str, str]:
        """构造 HTTP 请求头（Bearer 认证 + JSON），未配置密钥时省略 Authorization。"""
        headers = {"Content-Type": "application/json"}
        if self.configured:
            headers["Authorization"] = f"Bearer {self.api_key.strip()}"
        return headers

    def endpoint(self, path: str = "") -> str:
        """拼接接入点地址（自动处理 base_url 尾斜杠与 path 首斜杠）。"""
        if not self.base_url:
            return path.lstrip("/")
        if not path:
            return self.base_url
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def as_status(self) -> dict[str, Any]:
        """状态字典（已脱敏），安全用于日志、页面展示与导出。"""
        return {
            "provider": self.provider,
            "label": self.label or self.provider,
            "configured": self.configured,
            "usable": self.usable,
            "enabled": self.enabled,
            "masked_key": self.masked_key,
            "base_url": self.base_url,
            "model": self.model,
            "timeout": self.timeout,
            "source": self.source,
            "source_label": self.source_label,
        }



# ---------------------------------------------------------------------------
# Streamlit secrets 读取（任何异常都降级为空字典）
# ---------------------------------------------------------------------------
def _secrets_mapping() -> dict[str, Any]:
    """把 Streamlit secrets 读成普通字典；任何异常都降级为空字典。

    覆盖三种「没有 secrets」的真实场景（首次克隆 / CI / 未部署 secrets）：
    - 未安装或未导入 streamlit → 空字典；
    - `.streamlit/secrets.toml` 不存在 → Streamlit 抛 FileNotFoundError 子类
      （StreamlitSecretNotFoundError）；键缺失时抛 KeyError；
    - secrets.toml 语法错误 / 类型非法 → 同样降级，仅记一条告警日志。
    """
    try:
        import streamlit as st  # 延迟导入，避免 scripts / pytest 强依赖
    except Exception as exc:  # noqa: BLE001 - 缺少 streamlit 时直接走环境变量
        logger.debug("未读取到 Streamlit secrets（%s），回退环境变量。", exc)
        return {}

    try:
        secrets = st.secrets
        try:
            items = secrets.items()
        except AttributeError:  # pragma: no cover - 非 Mapping 实现
            return {}
        return {str(key): value for key, value in items}
    except KeyError:  # 访问空 secrets 时 Streamlit 可能抛 KeyError
        return {}
    except FileNotFoundError as exc:  # 本地无 secrets.toml / CI 场景
        logger.debug("未读取到 Streamlit secrets（%s），回退环境变量。", exc)
        return {}
    except Exception as exc:  # noqa: BLE001 - 语法错误等一律降级
        # 只记录异常类型：TOML 解析错误信息可能带出文件片段，避免把密钥写进日志。
        logger.warning(
            "解析 Streamlit secrets 失败（%s），回退环境变量。",
            type(exc).__name__,
        )
        return {}


def _dig(data: Mapping[str, Any], path: str) -> Any:
    """按路径深入嵌套映射取值，任一层缺失返回 None。"""
    node: Any = data
    for key in path.split("."):
        if not isinstance(node, Mapping):
            return None
        node = node.get(key)
    return node


def _as_text(value: Any) -> str | None:
    """把标量转成去空白的字符串；None / 容器类型 / 空串返回 None。"""
    if value is None:
        return None
    if isinstance(value, (Mapping, list, tuple, set)):
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    try:
        text = str(value).strip()
    except Exception:  # noqa: BLE001
        return None
    return text or None


def _to_float(value: Any) -> float | None:
    """转正浮点数；非法值或非正数返回 None（走默认值）。"""
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _to_bool(value: Any) -> bool | None:
    """宽松布尔解析；无法识别（拼写错误等）时返回 None，交由调用方走默认值。

    返回 None 而不是 False，是为了避免 `enabled = "ture"` 这类笔误把服务意外关停。
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value) if value in (0, 1) else None
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on", "y"}:
            return True
        if text in {"0", "false", "no", "off", "n"}:
            return False
    return None



def _env_prefix(provider: ApiProvider) -> str:
    """服务前缀（用于环境变量 / 顶层键名），如 deepseek → DEEPSEEK。"""
    return provider.key.upper().replace("-", "_").replace(".", "_")


def _secret_paths(field: str, provider: ApiProvider) -> tuple[tuple[str, ...], ...]:
    """该字段在 secrets 中允许的嵌套路径（服务小节在前，通用 api 小节在后）。"""
    names = FIELD_ALIASES.get(field, (field,))
    provider_paths = tuple(
        (API_SECTION, provider.key, name) for name in names
    )
    shared_paths = tuple((API_SECTION, name) for name in names)
    return provider_paths + shared_paths


def _flat_names(field: str, provider: ApiProvider) -> tuple[str, ...]:
    """该字段在「secrets 顶层键 / 环境变量」中的名称（服务专属名在前，通用名在后）。"""
    prefix = _env_prefix(provider)
    if field == "api_key":
        return (f"{prefix}_API_KEY", f"{prefix}_KEY", "API_KEY")
    upper = field.upper()
    return (f"{prefix}_{upper}", f"API_{upper}")


def _iter_candidates(
    field: str,
    provider: ApiProvider,
    secrets: Mapping[str, Any],
) -> Iterator[tuple[Any, str]]:
    """按优先级产出候选原始值：(值, 来源标识)。"""
    for path in _secret_paths(field, provider):
        raw = _dig(secrets, ".".join(path))
        if raw is not None:
            yield raw, SOURCE_SECRETS

    for name in _flat_names(field, provider):
        raw = secrets.get(name)
        if raw is not None:
            yield raw, SOURCE_SECRETS

        env_value = os.getenv(name)
        if env_value is not None:
            yield env_value, SOURCE_ENV


def _resolve_text(
    field: str,
    provider: ApiProvider,
    secrets: Mapping[str, Any],
    default: str = "",
) -> tuple[str, str]:
    """取文本字段（api_key / base_url / model），返回 (值, 来源)。"""
    for raw, source in _iter_candidates(field, provider, secrets):
        value = _as_text(raw)
        if value is not None:
            return value, source
    return default, SOURCE_NONE


def _resolve_value(
    field: str,
    provider: ApiProvider,
    secrets: Mapping[str, Any],
    convert,
    default: Any,
) -> tuple[Any, str]:
    """取数值 / 布尔字段（timeout / enabled）；转换失败则继续尝试下一候选，最终用默认值。"""
    for raw, source in _iter_candidates(field, provider, secrets):
        value = convert(raw)
        if value is not None:
            return value, source
    return default, SOURCE_NONE


# ---------------------------------------------------------------------------
# 对外 API
# ---------------------------------------------------------------------------
def resolve_provider(provider: str | None = None) -> ApiProvider:
    """把服务标识规范化为 ApiProvider；未列出的服务按 <NAME>_API_KEY 约定自动适配。"""
    if not provider:
        provider = default_provider()
    key = str(provider).strip().lower().replace("-", "_").replace(".", "_")
    if key in PROVIDERS:
        return PROVIDERS[key]

    label = str(provider).strip() or key
    return ApiProvider(
        key=key,
        label=label,
        env_key=f"{key.upper()}_API_KEY",
    )


def default_provider() -> str:
    """默认服务标识：`secrets[api].provider` → 环境变量 `API_PROVIDER` → DEFAULT_PROVIDER。"""
    secrets = _secrets_mapping()
    candidates: list[Any] = [_dig(secrets, f"{API_SECTION}.provider")]
    shared = secrets.get(API_SECTION)
    if isinstance(shared, Mapping):
        candidates.append(shared.get("service"))
    candidates.append(os.getenv("API_PROVIDER"))

    for raw in candidates:
        value = _as_text(raw)
        if value:
            return value.lower()
    return DEFAULT_PROVIDER



def get_api_credentials(provider: str | None = None) -> ApiCredentials:
    """读取指定服务的 API 凭证与调用参数（secrets 优先，环境变量兜底）。

    Args:
        provider: 服务标识（openai / deepseek / dashscope / amap / custom / 自定义名）；
            省略时取 `default_provider()`。

    Returns:
        ApiCredentials —— 无论是否配置成功都会返回对象（未配置时 `configured=False`），
        调用方只需判断 `creds.usable`，无需 try/except。
    """
    spec = resolve_provider(provider)
    secrets = _secrets_mapping()

    api_key, key_source = _resolve_text("api_key", spec, secrets)
    base_url, _ = _resolve_text(
        "base_url", spec, secrets, spec.default_base_url
    )
    model, _ = _resolve_text("model", spec, secrets, spec.default_model)
    timeout, _ = _resolve_value(
        "timeout", spec, secrets, _to_float, DEFAULT_TIMEOUT
    )
    enabled, _ = _resolve_value(
        "enabled", spec, secrets, _to_bool, DEFAULT_ENABLED
    )

    creds = ApiCredentials(
        provider=spec.key,
        label=spec.label or spec.key,
        api_key=api_key,
        base_url=(base_url or "").rstrip("/"),
        model=model,
        timeout=float(timeout),
        enabled=bool(enabled),
        source=key_source,
    )

    if creds.configured:
        logger.debug(
            "API 凭证就绪：%s（来源 %s，密钥 %s）",
            creds.label or creds.provider,
            creds.source_label,
            creds.masked_key,
        )
    else:
        logger.debug(
            "API 服务 %s 未配置，可通过 %s 或环境变量注入。",
            creds.provider,
            SECRETS_FILE,
        )
    return creds


def has_api_credentials(provider: str | None = None) -> bool:
    """是否已具备可用的 API 凭证（密钥非空且未被 enabled=false 关闭）。"""
    return get_api_credentials(provider).usable


def api_status(providers: Sequence[str] | None = None) -> list[dict[str, Any]]:
    """全部（或指定）服务的配置状态，供页面展示 / 日志输出（密钥已脱敏）。"""
    if providers is None:
        keys = list(PROVIDERS)
    elif isinstance(providers, str):
        keys = [providers]
    else:
        keys = list(providers)
    return [get_api_credentials(key).as_status() for key in keys]


def api_setup_hint(provider: str | None = None) -> str:
    """未配置密钥时的 Markdown 配置指引（secrets 两种写法 + 环境变量兜底）。"""
    spec = resolve_provider(provider)
    console = f"（密钥申请地址：{spec.console}）" if spec.console else ""
    return (
        f"**{spec.label}{console} 尚未配置 API 密钥**\n\n"
        f"1. **本地 / 自建服务器**：复制 `{SECRETS_EXAMPLE_FILE}` 为 "
        f"`{SECRETS_FILE}`，填入真实密钥后重启应用\n\n"
        f"```toml\n[api]\nprovider = \"{spec.key}\"\n\n"
        f"[api.{spec.key}]\napi_key = \"你的密钥\"\n```\n\n"
        f"2. **Streamlit Community Cloud**：应用页 → `Settings` → `Secrets`，"
        f"粘贴上面的 TOML 片段并保存（应用会自动重启）；\n\n"
        f"3. **环境变量（本地开发 / CI / Docker）**：设置 "
        f"`{spec.env_key}=你的密钥`（也支持通用名 `API_KEY`）。\n\n"
        f"> `{SECRETS_FILE}` 已加入 `.gitignore`，密钥不会进入版本库；"
        f"未配置时依赖该 API 的功能自动降级，其余分析照常可用。"
    )





