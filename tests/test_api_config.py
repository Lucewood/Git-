"""API 配置层测试：secrets 优先级、脱敏、环境变量兜底与模板有效性。"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from city_insight import api_config

FULL_KEY = "sk-1234567890abcdefghijklmnopqrstuvwxyz"
EXAMPLE_PATH = (
    Path(__file__).resolve().parent.parent / api_config.SECRETS_EXAMPLE_FILE
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """清理可能影响断言的环境变量（CI / 本地 .env 都可能存在）。"""
    for name in (
        "API_KEY", "API_PROVIDER", "API_BASE_URL", "API_MODEL", "API_TIMEOUT",
        "API_ENABLED", "DEEPSEEK_API_KEY", "DEEPSEEK_KEY", "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL", "DEEPSEEK_TIMEOUT", "DEEPSEEK_ENABLED",
        "OPENAI_API_KEY", "CUSTOM_API_KEY", "FOO_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    yield


def _secrets(monkeypatch, data: dict) -> None:
    monkeypatch.setattr(api_config, "_secrets_mapping", lambda: data)


def test_no_secrets_no_env_returns_unconfigured(monkeypatch):
    _secrets(monkeypatch, {})
    creds = api_config.get_api_credentials("deepseek")
    assert creds.configured is False
    assert creds.usable is False
    assert creds.source == api_config.SOURCE_NONE
    assert creds.masked_key == "未配置"
    assert api_config.has_api_credentials("deepseek") is False


def test_nested_provider_section_wins(monkeypatch):
    _secrets(
        monkeypatch,
        {
            "api": {
                "api_key": "flat-key-in-api-section",
                "deepseek": {
                    "api_key": FULL_KEY,
                    "model": "deepseek-reasoner",
                    "timeout": 12.5,
                },
            },
            "DEEPSEEK_API_KEY": "top-level-secret-key",
        },
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    creds = api_config.get_api_credentials("deepseek")
    assert creds.provider == "deepseek"
    assert creds.api_key == FULL_KEY
    assert creds.model == "deepseek-reasoner"
    assert creds.timeout == 12.5
    assert creds.source == api_config.SOURCE_SECRETS


def test_api_section_single_service_used(monkeypatch):
    _secrets(
        monkeypatch,
        {
            "api": {
                "api_key": FULL_KEY,
                "base_url": "https://example.com/v1/",
            }
        },
    )
    creds = api_config.get_api_credentials("custom")
    assert creds.api_key == FULL_KEY
    assert creds.base_url == "https://example.com/v1"
    assert creds.source == api_config.SOURCE_SECRETS


def test_top_level_flat_secret_used(monkeypatch):
    _secrets(monkeypatch, {"DEEPSEEK_API_KEY": FULL_KEY})
    creds = api_config.get_api_credentials("deepseek")
    assert creds.api_key == FULL_KEY
    assert creds.source == api_config.SOURCE_SECRETS


def test_env_fallback_prefers_provider_specific_name(monkeypatch):
    _secrets(monkeypatch, {})
    monkeypatch.setenv("API_KEY", "generic-env-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", FULL_KEY)
    creds = api_config.get_api_credentials("deepseek")
    assert creds.api_key == FULL_KEY
    assert creds.source == api_config.SOURCE_ENV


def test_env_generic_fallback_applies_provider_defaults(monkeypatch):
    _secrets(monkeypatch, {})
    monkeypatch.setenv("API_KEY", "generic-env-key")
    creds = api_config.get_api_credentials("deepseek")
    spec = api_config.PROVIDERS["deepseek"]
    assert creds.api_key == "generic-env-key"
    assert creds.base_url == spec.default_base_url
    assert creds.model == spec.default_model
    assert creds.timeout == api_config.DEFAULT_TIMEOUT
    assert creds.enabled is True
    assert creds.usable is True


def test_default_provider_resolution(monkeypatch):
    _secrets(monkeypatch, {"api": {"provider": "DeepSeek"}})
    assert api_config.default_provider() == "deepseek"

    _secrets(monkeypatch, {})
    monkeypatch.setenv("API_PROVIDER", "DashScope")
    assert api_config.default_provider() == "dashscope"

    monkeypatch.delenv("API_PROVIDER")
    assert api_config.default_provider() == api_config.DEFAULT_PROVIDER


def test_unknown_provider_uses_name_convention(monkeypatch):
    _secrets(monkeypatch, {})
    monkeypatch.setenv("FOO_API_KEY", FULL_KEY)
    creds = api_config.get_api_credentials("foo")
    assert creds.provider == "foo"
    assert creds.api_key == FULL_KEY
    assert api_config.resolve_provider("foo").env_key == "FOO_API_KEY"


def test_enabled_false_disables_credentials(monkeypatch):
    _secrets(
        monkeypatch,
        {"api": {"deepseek": {"api_key": FULL_KEY, "enabled": False}}},
    )
    creds = api_config.get_api_credentials("deepseek")
    assert creds.configured is True
    assert creds.usable is False
    assert api_config.has_api_credentials("deepseek") is False


def test_invalid_values_fall_back_to_defaults(monkeypatch):
    _secrets(
        monkeypatch,
        {
            "api": {
                "deepseek": {
                    "api_key": FULL_KEY,
                    "timeout": "not-a-number",
                    "enabled": "ture",
                }
            }
        },
    )
    creds = api_config.get_api_credentials("deepseek")
    assert creds.timeout == api_config.DEFAULT_TIMEOUT
    assert creds.enabled is True


def test_container_value_ignored(monkeypatch):
    _secrets(
        monkeypatch,
        {
            "api": {
                "deepseek": {
                    "api_key": ["sk-a", "sk-b"],
                    "base_url": {"url": "https://example.com"},
                }
            },
            "DEEPSEEK_API_KEY": FULL_KEY,
        },
    )
    creds = api_config.get_api_credentials("deepseek")
    assert creds.api_key == FULL_KEY
    assert creds.base_url == api_config.PROVIDERS["deepseek"].default_base_url



def test_masked_key_never_exposes_full_key():
    creds = api_config.ApiCredentials(api_key=FULL_KEY)
    masked = creds.masked_key
    assert masked != FULL_KEY
    assert FULL_KEY not in masked
    assert masked.startswith("sk-123")
    assert masked.endswith("wxyz")
    assert "********" in masked
    assert FULL_KEY not in repr(creds)

    short = api_config.ApiCredentials(api_key="abcdefgh")
    assert short.masked_key == "a*******"
    assert api_config.ApiCredentials().masked_key == "未配置"


def test_endpoint_and_headers():
    creds = api_config.ApiCredentials(
        api_key="  sk-test  ",
        base_url="https://api.deepseek.com/v1/",
        provider="deepseek",
        label="DeepSeek",
    )
    headers = creds.headers()
    assert headers["Authorization"] == "Bearer sk-test"
    assert headers["Content-Type"] == "application/json"
    assert creds.endpoint("chat/completions") == (
        "https://api.deepseek.com/v1/chat/completions"
    )
    assert creds.endpoint("/chat/completions") == (
        "https://api.deepseek.com/v1/chat/completions"
    )
    assert api_config.ApiCredentials().headers() == {
        "Content-Type": "application/json"
    }


def test_api_status_is_redacted(monkeypatch):
    _secrets(monkeypatch, {"api": {"deepseek": {"api_key": FULL_KEY}}})
    status = api_config.api_status()
    assert len(status) == len(api_config.PROVIDERS)
    assert all(isinstance(row, dict) for row in status)
    assert FULL_KEY not in str(status)
    deepseek = next(row for row in status if row["provider"] == "deepseek")
    assert deepseek["configured"] is True
    assert deepseek["masked_key"].endswith("wxyz")


def test_setup_hint_points_to_secrets_files():
    hint = api_config.api_setup_hint("deepseek")
    assert api_config.SECRETS_EXAMPLE_FILE in hint
    assert api_config.SECRETS_FILE in hint
    assert "DEEPSEEK_API_KEY" in hint
    assert "Settings" in hint


def test_example_secrets_template_is_valid_toml():
    data = tomllib.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    assert data["api"]["provider"] == "deepseek"
    assert data["api"]["deepseek"]["api_key"].startswith("sk-")
    assert data["api"]["deepseek"]["model"] == "deepseek-flash"


def test_example_template_resolves_to_credentials(monkeypatch):
    data = tomllib.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    _secrets(monkeypatch, data)
    creds = api_config.get_api_credentials("deepseek")
    assert creds.configured is True
    assert creds.usable is True
    assert creds.model == "deepseek-flash"
    assert creds.base_url == "https://api.deepseek.com/v1"

