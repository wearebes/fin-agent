"""CLI entrypoints for the fin-agent scaffold runtime."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import typer
import uvicorn

from fin_agent.bootstrap.container import Container, RuntimeSettingsError, build_container
from fin_agent.bootstrap.settings import (
    AppSettings,
    collect_runtime_validation_errors,
    export_env_example,
    load_settings,
    render_settings_schema,
)
from fin_agent.domain.constants import RunStatus
from fin_agent.domain.types import ResearchRequest

app = typer.Typer(no_args_is_help=True, help='fin-agent command line interface.')
research_app = typer.Typer(help='Research workflow commands.')
app.add_typer(research_app, name='research')


def _load_runtime(env: str | None) -> tuple[AppSettings, Container]:
    """Load application settings and build the runtime container."""
    settings = load_settings(env)
    return settings, build_container(settings)


@app.command()
def api(
    env: str | None = typer.Option(default=None, help='Configuration environment override.'),
    host: str = typer.Option(default='127.0.0.1', help='Bind host.'),
    port: int = typer.Option(default=8000, min=1, max=65535, help='Bind port.'),
    reload: bool = typer.Option(default=False, help='Enable autoreload for development.'),
) -> None:
    """Start the FastAPI app for the scaffold service."""
    if env is not None:
        os.environ['FIN_AGENT__APP__ENVIRONMENT'] = env
    uvicorn.run(
        'fin_agent.bootstrap.app:create_default_app',
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )


@research_app.command('run')
def research_run(
    question: str = typer.Option(..., help='Research question to answer.'),
    ticker: str | None = typer.Option(default=None, help='Optional ticker symbol.'),
    template: str = typer.Option(default='open_research', help='Research template name.'),
    env: str | None = typer.Option(default=None, help='Configuration environment override.'),
) -> None:
    """Execute a scaffold research run and print the planned result."""
    try:
        _settings, container = _load_runtime(env)
    except RuntimeSettingsError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    result = asyncio.run(
        container.research_service.run(
            ResearchRequest(question=question, ticker=ticker, template=template)
        )
    )
    typer.echo(result.model_dump_json(indent=2))
    if result.status == RunStatus.FAILED:
        raise typer.Exit(code=1)


@app.command()
def doctor(
    env: str | None = typer.Option(default=None, help='Configuration environment override.'),
    write_env_example: Path | None = typer.Option(
        default=None,
        help='Write the generated .env.example content to the given path.',
    ),
    print_schema: bool = typer.Option(default=False, help='Print the AppSettings JSON schema.'),
) -> None:
    """Inspect configuration state or regenerate the env example file."""
    if write_env_example is not None:
        write_env_example.write_text(export_env_example(), encoding='utf-8')
        typer.echo(str(write_env_example))
        return
    if print_schema:
        typer.echo(json.dumps(render_settings_schema(), indent=2))
        return

    settings = load_settings(env)
    errors = collect_runtime_validation_errors(settings)
    report = {
        'python_executable': sys.executable,
        'conda_env': os.environ.get('CONDA_DEFAULT_ENV'),
        'conda_prefix': os.environ.get('CONDA_PREFIX'),
        'python_from_conda': bool(
            os.environ.get('CONDA_PREFIX')
            and sys.executable.startswith(os.environ['CONDA_PREFIX'])
        ),
        'environment': settings.app.environment.value,
        'source_files': [str(path) for path in settings.source_files],
        'providers': settings.providers.default_selection.model_dump(mode='json'),
        'validation_errors': errors,
    }
    typer.echo(json.dumps(report, indent=2))
    if errors:
        raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == '__main__':
    main()
