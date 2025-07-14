"""Main CLI entry point for Quality Forge."""

import asyncio
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler

from .crew import run_quality_forge
from .exceptions import QualityForgeError

app = typer.Typer(
    name="qualityforge",
    help="Production-ready quality-automation bot powered by CrewAI and Groq",
    add_completion=False,
)

console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration."""
    log_level = logging.DEBUG if verbose else logging.INFO
    
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)]
    )


@app.command()
def run(
    repo_path: Path = typer.Argument(
        ...,
        help="Path to the repository to analyze",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    max_files: int = typer.Option(
        10,
        "--max-files",
        "-m",
        help="Maximum number of Python files to analyze",
        min=1,
        max=50,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-d",
        help="Run analysis without creating PR or making changes",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
    config_file: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to custom configuration file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
) -> None:
    """Run Quality Forge analysis on a repository.
    
    This command will:
    1. Scan Python files in the repository
    2. Analyze code quality issues using AI agents
    3. Generate refactoring suggestions
    4. Create pull request with proposed changes (unless --dry-run)
    
    Args:
        repo_path: Path to the repository to analyze
        max_files: Maximum number of Python files to analyze (default: 10)
        dry_run: Run analysis without creating PR or making changes
        verbose: Enable verbose logging
        config_file: Path to custom configuration file
    """
    setup_logging(verbose)
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Starting Quality Forge analysis on {repo_path}")
        logger.info(f"Max files: {max_files}, Dry run: {dry_run}")
        
        # Run the main Quality Forge workflow
        asyncio.run(run_quality_forge(
            repo_path=repo_path,
            max_files=max_files,
            dry_run=dry_run,
            config_file=config_file,
        ))
        
        logger.info("Quality Forge analysis completed successfully")
        
    except QualityForgeError as e:
        logger.error(f"Quality Forge error: {e}")
        raise typer.Exit(code=1)
    except KeyboardInterrupt:
        logger.info("Analysis interrupted by user")
        raise typer.Exit(code=130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(code=1)


@app.command()
def version() -> None:
    """Display Quality Forge version information."""
    from . import __version__
    console.print(f"Quality Forge version: {__version__}")


@app.command()
def check_config() -> None:
    """Check configuration and dependencies."""
    from .config.settings import Settings
    
    try:
        settings = Settings()
        console.print("[green]✓[/green] Configuration loaded successfully")
        console.print(f"[blue]Model:[/blue] {settings.groq_model}")
        console.print(f"[blue]Max tokens:[/blue] {settings.max_tokens}")
        console.print(f"[blue]Rate limit:[/blue] {settings.rate_limit_per_minute}")
        
        # Check required environment variables
        required_vars = ["GROQ_API_KEY"]
        missing_vars = []
        
        for var in required_vars:
            if not getattr(settings, var.lower(), None):
                missing_vars.append(var)
        
        if missing_vars:
            console.print(f"[red]✗[/red] Missing environment variables: {', '.join(missing_vars)}")
            raise typer.Exit(code=1)
        else:
            console.print("[green]✓[/green] All required environment variables are set")
            
    except Exception as e:
        console.print(f"[red]✗[/red] Configuration error: {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()