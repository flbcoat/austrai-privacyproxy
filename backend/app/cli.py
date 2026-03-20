"""AUSTR.AI PrivacyProxy CLI — Click-based command-line interface.

Provides commands for setup, configuration, custom terms management,
anonymization, analysis, and running the API server.
"""

import json
import os
import sys
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.text import Text

console = Console()
error_console = Console(stderr=True)

CONFIG_DIR = Path.home() / ".privacyproxy"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

VERSION = "2.0.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    """Load config from ~/.privacyproxy/config.yaml."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_config(config: dict) -> None:
    """Save config to ~/.privacyproxy/config.yaml."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)


def _apply_config_to_env(config: dict) -> None:
    """Push config values into environment variables so app.config.Settings picks them up."""
    if config.get("mistral_api_key"):
        os.environ.setdefault("MISTRAL_API_KEY", config["mistral_api_key"])
    if config.get("model"):
        os.environ.setdefault("MISTRAL_MODEL", config["model"])
    if config.get("confidence_threshold") is not None:
        os.environ.setdefault(
            "CONFIDENCE_THRESHOLD", str(config["confidence_threshold"])
        )


def _ensure_config_or_env() -> dict:
    """Load config and apply to env. Warn if no API key is available."""
    config = _load_config()
    _apply_config_to_env(config)
    return config


def _check_spacy_model() -> bool:
    """Check if the required SpaCy model is installed."""
    try:
        import spacy
        spacy.load("de_core_news_lg")
        return True
    except OSError:
        return False
    except ImportError:
        return False


def _ensure_spacy_model() -> None:
    """Check for SpaCy model and offer to download if missing."""
    if _check_spacy_model():
        return

    console.print(
        "[yellow]SpaCy model 'de_core_news_lg' is not installed.[/yellow]"
    )
    if click.confirm("Download it now (~560 MB)?", default=True):
        import subprocess
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Downloading de_core_news_lg...", total=None)
            result = subprocess.run(
                [sys.executable, "-m", "spacy", "download", "de_core_news_lg"],
                capture_output=True,
                text=True,
            )
        if result.returncode == 0:
            console.print("[green]SpaCy model installed successfully.[/green]")
        else:
            error_console.print(f"[red]Failed to download SpaCy model:[/red]\n{result.stderr}")
            raise click.Abort()
    else:
        error_console.print(
            "[red]SpaCy model is required. Install manually:[/red]\n"
            "  python -m spacy download de_core_news_lg"
        )
        raise click.Abort()


def _init_detector() -> None:
    """Initialize the Presidio analyzer (lazy, with SpaCy check)."""
    _ensure_spacy_model()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Loading NLP model and PII detector...", total=None)
        from app.services.detector import init_analyzer
        init_analyzer()


def _read_input(input_arg: str) -> tuple[str, str]:
    """Read input from a file path or treat as literal text.

    Args:
        input_arg: A file path or a text string.

    Returns:
        Tuple of (text_content, source_label).
    """
    path = Path(input_arg)
    if path.is_file():
        # Check for supported file formats that need extraction
        ext = path.suffix.lower()
        binary_formats = {".pdf", ".docx", ".xlsx", ".png", ".jpg", ".jpeg",
                          ".tiff", ".tif", ".bmp", ".webp"}
        if ext in binary_formats:
            from app.services.extractor import extract_text
            file_bytes = path.read_bytes()
            result = extract_text(file_bytes, path.name)
            if result.warnings:
                for w in result.warnings:
                    console.print(f"[yellow]Warning: {w}[/yellow]")
            return result.text, f"file: {path.name} ({result.format}, {result.pages} page(s))"
        else:
            text = path.read_text(encoding="utf-8")
            return text, f"file: {path.name}"
    else:
        return input_arg, "text input"


# ---------------------------------------------------------------------------
# CLI Group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(VERSION, prog_name="privacyproxy")
def main() -> None:
    """AUSTR.AI PrivacyProxy -- Open-source anonymization proxy for LLM requests."""
    pass


# ---------------------------------------------------------------------------
# privacyproxy init
# ---------------------------------------------------------------------------

@main.command()
def init() -> None:
    """Interactive setup: configure API key, model, and preferences."""
    console.print(
        Panel(
            "[bold]AUSTR.AI PrivacyProxy Setup[/bold]\n\n"
            "This will create a configuration file at:\n"
            f"  [cyan]{CONFIG_FILE}[/cyan]",
            title="Init",
            border_style="blue",
        )
    )

    config = _load_config()

    # API Key
    current_key = config.get("mistral_api_key", "")
    masked = f"{current_key[:8]}...{current_key[-4:]}" if len(current_key) > 12 else "(not set)"
    api_key = click.prompt(
        f"Mistral API key [{masked}]",
        default=current_key or "",
        show_default=False,
    )
    if api_key:
        config["mistral_api_key"] = api_key

    # Model
    current_model = config.get("model", "mistral/mistral-small-latest")
    model = click.prompt("Model", default=current_model)
    config["model"] = model

    # Confidence threshold
    current_threshold = config.get("confidence_threshold", 0.6)
    threshold = click.prompt(
        "Confidence threshold (0.0-1.0)",
        default=current_threshold,
        type=float,
    )
    config["confidence_threshold"] = threshold

    # Local LLM
    use_local = click.confirm("Enable local LLM (requires llama-cpp-python)?", default=False)
    if use_local:
        local_config = config.get("local_llm", {})
        local_config["enabled"] = True
        default_path = str(CONFIG_DIR / "models" / "qwen2.5-0.5b-instruct-q4_k_m.gguf")
        model_path = click.prompt(
            "Local model path",
            default=local_config.get("model_path", default_path),
        )
        local_config["model_path"] = model_path
        config["local_llm"] = local_config
    else:
        config.setdefault("local_llm", {"enabled": False, "model_path": ""})

    # Preserve existing custom terms
    config.setdefault("custom_terms", [])

    _save_config(config)

    console.print(f"\n[green]Configuration saved to {CONFIG_FILE}[/green]")

    # Check SpaCy model
    if not _check_spacy_model():
        console.print()
        _ensure_spacy_model()

    console.print("\n[bold green]Setup complete.[/bold green] Run [cyan]privacyproxy info[/cyan] to verify.")


# ---------------------------------------------------------------------------
# privacyproxy config
# ---------------------------------------------------------------------------

@main.group()
def config() -> None:
    """Show or modify configuration."""
    pass


@config.command("show")
def config_show() -> None:
    """Display the current configuration."""
    cfg = _load_config()
    if not cfg:
        console.print(
            "[yellow]No configuration found.[/yellow] Run [cyan]privacyproxy init[/cyan] to create one."
        )
        return

    # Mask API key for display
    display = dict(cfg)
    key = display.get("mistral_api_key", "")
    if key and len(key) > 12:
        display["mistral_api_key"] = f"{key[:8]}...{key[-4:]}"
    elif key:
        display["mistral_api_key"] = "***"

    yaml_str = yaml.dump(display, default_flow_style=False, allow_unicode=True)
    console.print(Panel(
        Syntax(yaml_str, "yaml", theme="monokai"),
        title=f"Config: {CONFIG_FILE}",
        border_style="blue",
    ))


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set a configuration value. KEY VALUE pairs like: model mistral/mistral-large-latest."""
    cfg = _load_config()

    # Type conversion for known keys
    if key == "confidence_threshold":
        try:
            cfg[key] = float(value)
        except ValueError:
            error_console.print(f"[red]Invalid float value: {value}[/red]")
            raise click.Abort()
    elif key in ("local_llm.enabled",):
        parts = key.split(".")
        sub = cfg.setdefault(parts[0], {})
        sub[parts[1]] = value.lower() in ("true", "1", "yes")
    elif key in ("local_llm.model_path",):
        parts = key.split(".")
        sub = cfg.setdefault(parts[0], {})
        sub[parts[1]] = value
    else:
        cfg[key] = value

    _save_config(cfg)
    console.print(f"[green]Set {key} = {value}[/green]")


# ---------------------------------------------------------------------------
# privacyproxy terms
# ---------------------------------------------------------------------------

@main.group()
def terms() -> None:
    """Manage custom deny-list terms for PII detection."""
    pass


@terms.command("add")
@click.argument("term", nargs=-1, required=True)
def terms_add(term: tuple[str, ...]) -> None:
    """Add one or more terms to the custom deny list."""
    from app.custom_terms import add_terms
    updated = add_terms(list(term))
    console.print(f"[green]Added {len(term)} term(s). Total custom terms: {len(updated)}[/green]")
    for t in term:
        console.print(f"  + {t}")


@terms.command("remove")
@click.argument("term")
def terms_remove(term: str) -> None:
    """Remove a term from the custom deny list."""
    from app.custom_terms import remove_term
    if remove_term(term):
        console.print(f"[green]Removed: {term}[/green]")
    else:
        error_console.print(f"[yellow]Term not found: {term}[/yellow]")


@terms.command("list")
def terms_list() -> None:
    """List all custom deny-list terms."""
    from app.custom_terms import get_custom_terms
    current_terms = get_custom_terms()
    if not current_terms:
        console.print("[dim]No custom terms configured.[/dim]")
        return

    table = Table(title="Custom Deny-List Terms", show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Term", style="cyan")
    for i, t in enumerate(current_terms, 1):
        table.add_row(str(i), t)
    console.print(table)


@terms.command("clear")
def terms_clear() -> None:
    """Clear all custom deny-list terms."""
    from app.custom_terms import clear_terms
    if click.confirm("Remove all custom terms?", default=False):
        count = clear_terms()
        console.print(f"[green]Cleared {count} term(s).[/green]")
    else:
        console.print("[dim]Cancelled.[/dim]")


# ---------------------------------------------------------------------------
# privacyproxy analyze
# ---------------------------------------------------------------------------

@main.command()
@click.argument("input_arg", metavar="INPUT")
def analyze(input_arg: str) -> None:
    """Detect PII entities in a file or text (no LLM call).

    INPUT can be a file path or a text string.
    """
    _ensure_config_or_env()
    text, source = _read_input(input_arg)

    if not text.strip():
        error_console.print("[red]No text to analyze.[/red]")
        raise click.Abort()

    _init_detector()

    from app.services.detector import detect
    from app.custom_terms import get_custom_terms

    custom = get_custom_terms()
    entities = detect(text, deny_list=custom if custom else None)

    if not entities:
        console.print(Panel(
            "[green]No PII entities detected.[/green]",
            title=f"Analysis: {source}",
            border_style="green",
        ))
        return

    table = Table(title=f"Detected PII Entities ({source})")
    table.add_column("Type", style="cyan", no_wrap=True)
    table.add_column("Text", style="white")
    table.add_column("Score", justify="right", style="green")
    table.add_column("Position", style="dim")

    for entity in entities:
        table.add_row(
            entity.entity_type,
            entity.text,
            f"{entity.score:.0%}",
            f"{entity.start}-{entity.end}",
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(entities)} entities detected[/dim]")


# ---------------------------------------------------------------------------
# privacyproxy anonymize
# ---------------------------------------------------------------------------

@main.command()
@click.argument("input_arg", metavar="INPUT")
@click.option("-o", "--output", "output_path", default=None, help="Output file path.")
@click.option("--format", "output_format", type=click.Choice(["json", "text"]), default="text", help="Output format.")
@click.option("--local", is_flag=True, default=False, help="Anonymize only, no LLM call.")
def anonymize(input_arg: str, output_path: str | None, output_format: str, local: bool) -> None:
    """Anonymize a file or text, optionally sending to LLM.

    INPUT can be a file path or a text string.
    Use --local to skip the LLM call and only perform anonymization.
    """
    config = _ensure_config_or_env()
    text, source = _read_input(input_arg)

    if not text.strip():
        error_console.print("[red]No text to anonymize.[/red]")
        raise click.Abort()

    _init_detector()

    from app.services.detector import detect
    from app.services.anonymizer import anonymize as do_anonymize
    from app.custom_terms import get_custom_terms

    # Detect entities
    custom = get_custom_terms()
    entities = detect(text, deny_list=custom if custom else None)

    # Anonymize
    anonymized_text, mappings = do_anonymize(text, entities)

    result: dict = {
        "source": source,
        "anonymized_text": anonymized_text,
        "mappings": mappings,
        "entities_count": len(entities),
    }

    # Optionally call LLM
    if not local:
        api_key = os.environ.get("MISTRAL_API_KEY", config.get("mistral_api_key", ""))
        if not api_key:
            console.print(
                "[yellow]No API key configured. Use --local for offline anonymization "
                "or run 'privacyproxy init' to set up.[/yellow]"
            )
            local = True

    if not local:
        import asyncio
        from app.services.llm_client import call_llm
        from app.services.rehydrator import rehydrate

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Sending anonymized text to LLM...", total=None)
            llm_response = asyncio.run(
                call_llm(anonymized_text, "Respond professionally and helpfully.")
            )

        rehydrated = rehydrate(llm_response, mappings)
        result["llm_response_anonymized"] = llm_response
        result["llm_response_rehydrated"] = rehydrated

    # Output
    if output_format == "json" or (output_path and output_path.endswith(".json")):
        output_str = json.dumps(result, indent=2, ensure_ascii=False)
    else:
        parts = [
            f"--- Anonymized Text ---\n{anonymized_text}",
            f"\n--- Mappings ({len(mappings)} replacements) ---",
        ]
        for placeholder, original in mappings.items():
            parts.append(f"  {placeholder} -> {original}")
        if "llm_response_anonymized" in result:
            parts.append(f"\n--- LLM Response (anonymized) ---\n{result['llm_response_anonymized']}")
            parts.append(f"\n--- LLM Response (rehydrated) ---\n{result['llm_response_rehydrated']}")
        output_str = "\n".join(parts)

    if output_path:
        Path(output_path).write_text(output_str, encoding="utf-8")
        console.print(f"[green]Output written to {output_path}[/green]")
    else:
        console.print(Panel(output_str, title=f"Anonymization: {source}", border_style="blue"))


# ---------------------------------------------------------------------------
# privacyproxy serve
# ---------------------------------------------------------------------------

@main.command()
@click.option("--port", default=8000, type=int, help="Port to listen on.")
@click.option("--host", default="0.0.0.0", help="Host to bind to.")
def serve(port: int, host: str) -> None:
    """Start the FastAPI server."""
    config = _ensure_config_or_env()

    api_key = os.environ.get("MISTRAL_API_KEY", config.get("mistral_api_key", ""))
    if not api_key:
        error_console.print(
            "[red]No API key configured.[/red] Run [cyan]privacyproxy init[/cyan] first "
            "or set the MISTRAL_API_KEY environment variable."
        )
        raise click.Abort()

    _ensure_spacy_model()

    console.print(Panel(
        f"[bold]Starting AUSTR.AI PrivacyProxy[/bold]\n\n"
        f"  Host:  [cyan]{host}[/cyan]\n"
        f"  Port:  [cyan]{port}[/cyan]\n"
        f"  Docs:  [cyan]http://{host}:{port}/docs[/cyan]\n"
        f"  Model: [cyan]{config.get('model', os.environ.get('MISTRAL_MODEL', 'mistral/mistral-small-latest'))}[/cyan]",
        title="Server",
        border_style="green",
    ))

    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        log_level="info",
    )


# ---------------------------------------------------------------------------
# privacyproxy info
# ---------------------------------------------------------------------------

@main.command()
def info() -> None:
    """Show version, model info, and supported formats."""
    config = _load_config()

    # Version panel
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("Version", VERSION)
    table.add_row("Config", str(CONFIG_FILE))
    table.add_row("Config exists", "[green]yes[/green]" if CONFIG_FILE.exists() else "[red]no[/red]")

    # Model info
    model = config.get("model", os.environ.get("MISTRAL_MODEL", "mistral/mistral-small-latest"))
    table.add_row("LLM model", model)

    api_key = config.get("mistral_api_key", os.environ.get("MISTRAL_API_KEY", ""))
    if api_key:
        masked = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
        table.add_row("API key", f"[green]{masked}[/green]")
    else:
        table.add_row("API key", "[red]not set[/red]")

    threshold = config.get("confidence_threshold", 0.6)
    table.add_row("Confidence threshold", str(threshold))

    # Local LLM
    local_cfg = config.get("local_llm", {})
    local_enabled = local_cfg.get("enabled", False)
    table.add_row("Local LLM", "[green]enabled[/green]" if local_enabled else "[dim]disabled[/dim]")
    if local_enabled:
        table.add_row("Local model path", local_cfg.get("model_path", "(not set)"))

    # Custom terms
    terms = config.get("custom_terms", [])
    table.add_row("Custom terms", str(len(terms)))

    # SpaCy model
    spacy_ok = _check_spacy_model()
    table.add_row("SpaCy de_core_news_lg", "[green]installed[/green]" if spacy_ok else "[red]not installed[/red]")

    console.print(Panel(table, title="AUSTR.AI PrivacyProxy", border_style="blue"))

    # Supported formats
    fmt_table = Table(title="Supported File Formats")
    fmt_table.add_column("Format", style="cyan", no_wrap=True)
    fmt_table.add_column("Extensions", style="white")
    fmt_table.add_column("Description")

    formats = [
        ("PDF", ".pdf", "Text extraction from all pages"),
        ("DOCX", ".docx", "Paragraphs and tables"),
        ("XLSX", ".xlsx", "Cell contents from all sheets"),
        ("TEXT", ".txt, .csv, .md, .json, .xml, .html", "Direct UTF-8/Latin-1 decoding"),
        ("IMAGE", ".png, .jpg, .jpeg, .tiff, .tif, .bmp, .webp", "OCR (German + English), EXIF stripping"),
    ]
    for fmt, ext, desc in formats:
        fmt_table.add_row(fmt, ext, desc)

    console.print(fmt_table)


if __name__ == "__main__":
    main()
