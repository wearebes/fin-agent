"""Centralized configuration loading for the fin-agent scaffold."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, get_args, get_origin

import yaml
from pydantic import BaseModel, Field, PrivateAttr, SecretStr
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from fin_agent.adapters.llm.openai.config import OpenAIConfig
from fin_agent.adapters.market_data.akshare.config import AKShareConfig
from fin_agent.adapters.market_data.yfinance.config import YFinanceConfig
from fin_agent.adapters.search.exa.config import ExaSearchConfig
from fin_agent.domain.constants import (
    EnvironmentName,
    LLMProviderName,
    MarketDataProviderName,
    SearchProviderName,
    WorkflowName,
)
from fin_agent.workflows.research.config import ResearchWorkflowConfig

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_ROOT = PROJECT_ROOT / "configs"


class AppConfig(BaseModel):
    name: str = Field(default="fin-agent", description="Application name used by the API and CLI.")
    environment: EnvironmentName = Field(
        default=EnvironmentName.LOCAL,
        description="Active configuration environment.",
    )


class LoggingConfig(BaseModel):
    level: str = Field(default="INFO", description="Logging level for API and CLI commands.")
    json: bool = Field(
        default=False,
        description="Emit newline-delimited JSON logs instead of plain text.",
    )


class DatabaseConfig(BaseModel):
    url: str = Field(default="sqlite:///./var/fin_agent.db", description="Database connection string.")
    echo: bool = Field(default=False, description="Echo SQL statements to logs.")


class RuntimeConfig(BaseModel):
    request_timeout_seconds: int = Field(
        default=30,
        ge=1,
        description="Default request timeout used by adapters and services.",
    )
    data_dir: str = Field(default="./var", description="Directory for local runtime artifacts.")
    validate_runtime_secrets: bool = Field(
        default=True,
        description="Validate required provider secrets during runtime bootstrap.",
    )


class ProviderSelectionConfig(BaseModel):
    llm: LLMProviderName = Field(default=LLMProviderName.OPENAI, description="Default LLM provider name.")
    market_data: MarketDataProviderName = Field(
        default=MarketDataProviderName.YFINANCE,
        description="Default market data provider name.",
    )
    search: SearchProviderName = Field(
        default=SearchProviderName.EXA,
        description="Default search provider name.",
    )


class ProvidersConfig(BaseModel):
    default_selection: ProviderSelectionConfig = Field(default_factory=ProviderSelectionConfig)


class WorkflowSelectionConfig(BaseModel):
    research: WorkflowName = Field(
        default=WorkflowName.RESEARCH,
        description="Default workflow registered for research tasks.",
    )


class WorkflowsConfig(BaseModel):
    default_selection: WorkflowSelectionConfig = Field(default_factory=WorkflowSelectionConfig)


class FeatureFlagsConfig(BaseModel):
    enable_api_docs: bool = Field(default=True, description="Enable public API docs endpoints.")
    enable_trace_storage: bool = Field(
        default=True,
        description="Persist workflow traces in the runtime store.",
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Configuration file '{path}' does not exist.")
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise TypeError(f"Configuration file '{path}' must contain a mapping at the top level.")
    return data


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        base_value = merged.get(key)
        if isinstance(base_value, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(base_value, value)
        else:
            merged[key] = value
    return merged


def _resolve_environment_from_init(init_kwargs: Mapping[str, Any]) -> EnvironmentName:
    app_value = init_kwargs.get('app')
    if isinstance(app_value, AppConfig):
        return app_value.environment
    if isinstance(app_value, Mapping) and 'environment' in app_value:
        return EnvironmentName(str(app_value['environment']))
    env_value = os.environ.get('FIN_AGENT__APP__ENVIRONMENT')
    if env_value:
        return EnvironmentName(env_value)
    return EnvironmentName.LOCAL


def _config_files_for(environment: EnvironmentName) -> tuple[Path, Path]:
    return (
        CONFIG_ROOT / 'base.yaml',
        CONFIG_ROOT / 'environments' / f'{environment.value}.yaml',
    )


class LayeredYamlSettingsSource(PydanticBaseSettingsSource):
    def __init__(
        self,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
    ) -> None:
        super().__init__(settings_cls)
        self._init_settings = init_settings

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        environment = _resolve_environment_from_init(getattr(self._init_settings, 'init_kwargs', {}))
        base_path, env_path = _config_files_for(environment)
        return _deep_merge(_read_yaml(base_path), _read_yaml(env_path))


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix='FIN_AGENT__',
        env_nested_delimiter='__',
        env_file=str(PROJECT_ROOT / '.env'),
        env_file_encoding='utf-8',
        env_ignore_empty=True,
        extra='forbid',
        validate_default=True,
    )

    app: AppConfig = Field(default_factory=AppConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    workflows: WorkflowsConfig = Field(default_factory=WorkflowsConfig)
    feature_flags: FeatureFlagsConfig = Field(default_factory=FeatureFlagsConfig)
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    market_data: YFinanceConfig = Field(default_factory=YFinanceConfig)
    akshare: AKShareConfig = Field(default_factory=AKShareConfig)
    search: ExaSearchConfig = Field(default_factory=ExaSearchConfig)
    research_workflow: ResearchWorkflowConfig = Field(default_factory=ResearchWorkflowConfig)

    _source_files: tuple[Path, Path] = PrivateAttr(default_factory=tuple)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            LayeredYamlSettingsSource(settings_cls, init_settings),
            file_secret_settings,
        )

    @property
    def source_files(self) -> tuple[Path, Path]:
        return self._source_files


def load_settings(env: str | None = None) -> AppSettings:
    """Resolve settings from init args, env, .env, layered YAML, and defaults."""
    init_kwargs: dict[str, Any] = {}
    if env is not None:
        init_kwargs['app'] = {'environment': EnvironmentName(env)}
    settings = AppSettings(**init_kwargs)
    settings._source_files = _config_files_for(settings.app.environment)
    return settings


def render_settings_schema() -> dict[str, Any]:
    """Return the JSON schema for the full application settings tree."""
    return AppSettings.model_json_schema()


def _resolve_nested_model(field: FieldInfo) -> type[BaseModel] | None:
    annotation = field.annotation
    if annotation is None:
        return None
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    origin = get_origin(annotation)
    if origin is None:
        return None
    for candidate in get_args(annotation):
        if isinstance(candidate, type) and issubclass(candidate, BaseModel):
            return candidate
    return None


def _format_env_value(field: FieldInfo) -> str:
    if field.default is PydanticUndefined or field.default is None:
        return '<set-me>' if 'api key' in (field.description or '').lower() else ''
    value = field.default
    if isinstance(value, SecretStr):
        return '<set-me>'
    if isinstance(value, bool):
        return str(value).lower()
    if hasattr(value, 'value'):
        return str(value.value)
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return str(value)


def _iter_env_lines(model: type[BaseModel], path: tuple[str, ...]) -> list[str]:
    lines: list[str] = []
    for field_name, field in model.model_fields.items():
        nested_model = _resolve_nested_model(field)
        if nested_model is not None:
            lines.extend(_iter_env_lines(nested_model, (*path, field_name)))
            continue
        env_name = 'FIN_AGENT__' + '__'.join((*path, field_name)).upper()
        if field.description:
            lines.append(f'# {field.description}')
        lines.append(f'{env_name}={_format_env_value(field)}')
        lines.append('')
    return lines


def export_env_example() -> str:
    """Generate a repo-local .env.example from the authoritative settings tree."""
    lines = [
        '# Generated from fin_agent.bootstrap.settings.AppSettings.',
        '# Regenerate with: fin-agent doctor --write-env-example .env.example',
        '',
    ]
    lines.extend(_iter_env_lines(AppSettings, ()))
    return '\n'.join(lines).strip() + '\n'


def _secret_is_set(secret: SecretStr | None) -> bool:
    return secret is not None and bool(secret.get_secret_value().strip())


def collect_runtime_validation_errors(settings: AppSettings) -> list[str]:
    """Check scaffold runtime prerequisites that must be present at startup."""
    errors: list[str] = []
    if settings.runtime.validate_runtime_secrets:
        if settings.providers.default_selection.llm == LLMProviderName.OPENAI and not _secret_is_set(
            settings.openai.api_key
        ):
            errors.append('FIN_AGENT__OPENAI__API_KEY is required for the default OpenAI provider.')
        if (
            settings.providers.default_selection.search == SearchProviderName.EXA
            and settings.search.enabled
            and not _secret_is_set(settings.search.api_key)
        ):
            errors.append('FIN_AGENT__SEARCH__API_KEY is required for the default Exa search provider.')
    if not settings.database.url.strip():
        errors.append('database.url must not be empty.')
    return errors
