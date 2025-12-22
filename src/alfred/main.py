"""
Alfred V2 - CLI Entry Point.

Usage:
    alfred chat              Start interactive chat
    alfred health            Check system health
    alfred --help            Show help
"""

import asyncio

import typer
from rich.console import Console
from rich.panel import Panel
from rich.spinner import Spinner
from rich.live import Live

app = typer.Typer(
    name="alfred",
    help="Alfred - Your intelligent kitchen, fitness, and wine assistant.",
    add_completion=False,
)
console = Console()


@app.command()
def chat() -> None:
    """Start an interactive chat session with Alfred."""
    from alfred.config import settings
    from alfred.graph import run_alfred

    console.print(
        Panel.fit(
            "[bold green]Alfred V2[/bold green]\n"
            "Your intelligent assistant for kitchen, fitness, and wine.\n\n"
            "[dim]Type 'exit' or 'quit' to end the session.[/dim]",
            title="Welcome",
            border_style="green",
        )
    )

    user_id = settings.DEV_USER_ID

    while True:
        try:
            user_input = console.input("\n[bold blue]You:[/bold blue] ").strip()

            if user_input.lower() in ("exit", "quit", "q"):
                console.print("\n[dim]Goodbye! 👋[/dim]")
                break

            if not user_input:
                continue

            # Run through the graph
            with Live(Spinner("dots", text="Thinking..."), console=console, transient=True):
                response = asyncio.run(run_alfred(
                    user_message=user_input,
                    user_id=user_id,
                ))

            console.print(f"\n[bold green]Alfred:[/bold green] {response}")

        except KeyboardInterrupt:
            console.print("\n\n[dim]Session interrupted. Goodbye! 👋[/dim]")
            break
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")


@app.command()
def ask(message: str = typer.Argument(..., help="Message to send to Alfred")) -> None:
    """Send a single message to Alfred (useful for testing)."""
    from alfred.config import settings
    from alfred.graph import run_alfred

    user_id = settings.DEV_USER_ID

    with Live(Spinner("dots", text="Thinking..."), console=console, transient=True):
        response = asyncio.run(run_alfred(
            user_message=message,
            user_id=user_id,
        ))

    console.print(f"\n[bold green]Alfred:[/bold green] {response}")


@app.command()
def health() -> None:
    """Check system health and configuration."""
    from alfred.config import get_settings

    console.print("\n[bold]Alfred V2 Health Check[/bold]\n")

    try:
        settings = get_settings()
        console.print("✅ Configuration loaded")
        console.print(f"   Environment: {settings.alfred_env}")
        console.print(f"   Log level: {settings.log_level}")

        # Check OpenAI
        if settings.openai_api_key.startswith("sk-"):
            console.print("✅ OpenAI API key configured")
        else:
            console.print("⚠️  OpenAI API key may be invalid")

        # Check Supabase
        if settings.supabase_url.startswith("https://"):
            console.print("✅ Supabase URL configured")
        else:
            console.print("❌ Supabase URL missing or invalid")

        # Check LangSmith
        if settings.langchain_tracing_v2 and settings.langchain_api_key:
            console.print("✅ LangSmith tracing enabled")
        else:
            console.print("ℹ️  LangSmith tracing disabled")

        console.print("\n[green]All checks passed![/green]")

    except Exception as e:
        console.print(f"\n[red]❌ Configuration error: {e}[/red]")
        console.print("[dim]Make sure you have a .env file with required variables.[/dim]")
        raise typer.Exit(1)


@app.command()
def version() -> None:
    """Show version information."""
    from alfred import __version__

    console.print(f"Alfred V2 version {__version__}")


if __name__ == "__main__":
    app()

