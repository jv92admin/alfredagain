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
def chat(
    log_prompts: bool = typer.Option(False, "--log-prompts", "-l", help="Log all LLM prompts to prompt_logs/"),
) -> None:
    """Start an interactive chat session with Alfred."""
    from alfred.config import settings
    from alfred.graph import run_alfred
    from alfred.llm.prompt_logger import enable_prompt_logging, get_session_log_dir

    if log_prompts:
        enable_prompt_logging(True)
        console.print("[dim]📝 Prompt logging enabled. Check prompt_logs/ after the session.[/dim]")

    console.print(
        Panel.fit(
            "[bold green]Alfred V2[/bold green]\n"
            "Your intelligent assistant for kitchen, fitness, and wine.\n\n"
            "[dim]Type 'exit' or 'quit' to end the session.[/dim]",
            title="Welcome",
            border_style="green",
        )
    )

    user_id = settings.dev_user_id

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
def ask(
    message: str = typer.Argument(..., help="Message to send to Alfred"),
    log_prompts: bool = typer.Option(False, "--log-prompts", "-l", help="Log all LLM prompts to prompt_logs/"),
) -> None:
    """Send a single message to Alfred (useful for testing)."""
    from alfred.config import settings
    from alfred.graph import run_alfred
    from alfred.llm.prompt_logger import enable_prompt_logging, get_session_log_dir

    if log_prompts:
        enable_prompt_logging(True)

    user_id = settings.dev_user_id

    with Live(Spinner("dots", text="Thinking..."), console=console, transient=True):
        response = asyncio.run(run_alfred(
            user_message=message,
            user_id=user_id,
        ))

    console.print(f"\n[bold green]Alfred:[/bold green] {response}")

    if log_prompts:
        log_dir = get_session_log_dir()
        if log_dir:
            console.print(f"\n[dim]📝 Prompts logged to: {log_dir}[/dim]")


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


@app.command()
def db() -> None:
    """Check database connection and schema."""
    from alfred.db.client import get_client

    console.print("\n[bold]Database Connection Check[/bold]\n")

    try:
        client = get_client()
        console.print("✅ Connected to Supabase")

        # Check each table
        tables = [
            "users",
            "ingredients",
            "inventory",
            "recipes",
            "recipe_ingredients",
            "meal_plans",
            "shopping_list",
            "preferences",
            "flavor_preferences",
            "conversation_memory",
        ]

        console.print("\n[bold]Table Status:[/bold]")
        for table in tables:
            try:
                result = client.table(table).select("*", count="exact").limit(0).execute()
                count = result.count if hasattr(result, "count") else "?"
                console.print(f"  ✅ {table}: {count} rows")
            except Exception as e:
                console.print(f"  ❌ {table}: {e}")

        console.print("\n[green]Database check complete![/green]")

    except Exception as e:
        console.print(f"\n[red]❌ Database connection failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def tools() -> None:
    """List all registered tools."""
    from alfred.tools.registry import registry
    import alfred.tools  # Ensure tools are registered

    console.print("\n[bold]Registered Tools[/bold]\n")

    # Get all tools
    all_tools = list(registry._tools.values())

    if not all_tools:
        console.print("[dim]No tools registered.[/dim]")
        return

    # Group by agent
    by_agent: dict[str, list] = {}
    for tool in all_tools:
        by_agent.setdefault(tool.agent, []).append(tool)

    for agent, agent_tools in sorted(by_agent.items()):
        console.print(f"\n[bold blue]{agent.upper()}[/bold blue]")
        for tool in sorted(agent_tools, key=lambda t: t.name):
            console.print(f"  • {tool.name}: {tool.summary}")

    console.print(f"\n[dim]Total: {len(all_tools)} tools[/dim]")


if __name__ == "__main__":
    app()

