"""
Alfred V3 - CLI Entry Point.

Usage:
    alfred chat              Start interactive chat
    alfred chat --mode quick Start in quick mode
    alfred health            Check system health
    alfred --help            Show help

V3 Changes:
    --mode flag for mode selection (quick/cook/plan/create)
"""

import asyncio

import typer
from rich.console import Console
from rich.panel import Panel
from rich.spinner import Spinner
from rich.live import Live

from alfred.core.modes import Mode, ModeContext

app = typer.Typer(
    name="alfred",
    help="Alfred - Your intelligent kitchen, fitness, and wine assistant.",
    add_completion=False,
)
console = Console()


@app.command()
def chat(
    log_prompts: bool = typer.Option(False, "--log-prompts", "-l", help="Log all LLM prompts to prompt_logs/"),
    log_session: bool = typer.Option(False, "--log", help="Enable session logging to session_logs/"),
    mode: str = typer.Option("plan", "--mode", "-m", help="Mode: quick, cook, plan, create"),
) -> None:
    """Start an interactive chat session with Alfred."""
    from alfred_kitchen.config import settings
    from alfred.graph import run_alfred
    from alfred.memory.conversation import initialize_conversation
    from alfred.llm.prompt_logger import enable_prompt_logging, get_session_log_dir
    from alfred.observability.session_logger import init_session_logger, close_session_logger
    from alfred.observability.langsmith import get_session_tracker

    if log_prompts:
        enable_prompt_logging(True)
        console.print("[dim]Prompt logging enabled. Check prompt_logs/ after the session.[/dim]")
    
    # V3: Session logging (lightweight observability)
    session_logger = None
    if log_session:
        session_logger = init_session_logger()
        console.print(f"[dim]Session logging enabled: {session_logger.log_path}[/dim]")

    # V3: Parse and validate mode
    try:
        selected_mode = Mode(mode.lower())
    except ValueError:
        console.print(f"[red]Invalid mode: {mode}. Using 'plan' mode.[/red]")
        selected_mode = Mode.PLAN
    
    mode_context = ModeContext(selected_mode=selected_mode)

    console.print(
        Panel.fit(
            f"[bold green]Alfred V3[/bold green]\n"
            f"Your intelligent assistant for kitchen, fitness, and wine.\n\n"
            f"[dim]Mode: [bold]{selected_mode.value}[/bold] (--mode to change)[/dim]\n"
            "[dim]Type 'exit' or 'quit' to end the session.[/dim]\n"
            "[dim]Type 'context' to see current conversation state.[/dim]\n"
            "[dim]Type 'mode <quick|plan|create>' to switch modes.[/dim]",
            title="Welcome",
            border_style="green",
        )
    )

    user_id = settings.dev_user_id
    
    # Initialize conversation context (persists across turns)
    conversation = initialize_conversation()
    turn_count = 0

    while True:
        try:
            # Show mode in prompt
            mode_badge = f"[dim][{selected_mode.value}][/dim] "
            user_input = console.input(f"\n{mode_badge}[bold blue]You:[/bold blue] ").strip()

            if user_input.lower() in ("exit", "quit", "q"):
                console.print("\n[dim]Goodbye![/dim]")
                break

            if not user_input:
                continue
            
            # Debug command to show conversation state
            if user_input.lower() == "context":
                _show_conversation_context(conversation, turn_count)
                continue
            
            # V3: Mode switching command
            if user_input.lower().startswith("mode "):
                new_mode_str = user_input.split(" ", 1)[1].strip().lower()
                try:
                    selected_mode = Mode(new_mode_str)
                    mode_context = ModeContext(selected_mode=selected_mode)
                    console.print(f"[green]Mode switched to: {selected_mode.value}[/green]")
                except ValueError:
                    valid = ", ".join(m.value for m in Mode)
                    console.print(f"[red]Invalid mode: {new_mode_str}. Options: {valid}[/red]")
                continue

            # Run through the graph with conversation context
            # V3: Pass mode context to conversation for workflow
            conversation["mode_context"] = mode_context.to_dict()
            
            # V3: Log turn start
            if session_logger:
                session_logger.turn_start(user_input, selected_mode.value)
            
            with Live(Spinner("dots", text="Thinking..."), console=console, transient=True):
                response, conversation = asyncio.run(run_alfred(
                    user_message=user_input,
                    user_id=user_id,
                    conversation=conversation,
                ))

            turn_count += 1
            
            # V3: Log turn end with entities from conversation
            if session_logger:
                # Extract any new entities from the conversation context
                active_entities = conversation.get("active_entities", {})
                entities_created = []
                for entity_type, entities in active_entities.items():
                    if isinstance(entities, list):
                        for e in entities:
                            if isinstance(e, dict):
                                entities_created.append({"type": entity_type, **e})
                    elif isinstance(entities, dict):
                        entities_created.append({"type": entity_type, **entities})
                
                session_logger.turn_end(
                    response, 
                    entities_created=entities_created if entities_created else None
                )
            
            console.print(f"\n[bold green]Alfred:[/bold green] {response}")

        except KeyboardInterrupt:
            console.print("\n\n[dim]Session interrupted. Goodbye![/dim]")
            break
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            if session_logger:
                session_logger.log("error", error=str(e))
    
    # V3: Close session logger
    if session_logger:
        log_path = close_session_logger()
        console.print(f"[dim]Session log saved: {log_path}[/dim]")
    
    # Show cost summary
    tracker = get_session_tracker()
    if tracker.calls:
        summary = tracker.summary()
        console.print(f"\n[dim]Session Cost: ${summary['total_cost_usd']:.4f} ({summary['total_input_tokens']:,} in / {summary['total_output_tokens']:,} out tokens)[/dim]")


def _show_conversation_context(conversation: dict, turn_count: int) -> None:
    """Show current conversation context for debugging."""
    console.print("\n[bold yellow]Conversation Context[/bold yellow]")
    console.print(f"[dim]Turns: {turn_count}[/dim]")
    
    # Engagement summary
    engagement = conversation.get("engagement_summary", "")
    if engagement:
        console.print(f"\n[bold]Session:[/bold] {engagement}")
    
    # Active entities
    active = conversation.get("active_entities", {})
    if active:
        console.print("\n[bold]Active Entities:[/bold]")
        for entity_type, entity_data in active.items():
            label = entity_data.get("label", "?")
            console.print(f"  • {entity_type}: {label}")
    
    # Recent turns
    recent = conversation.get("recent_turns", [])
    if recent:
        console.print(f"\n[bold]Recent Turns ({len(recent)}):[/bold]")
        for turn in recent[-3:]:
            user = turn.get("user", "")[:50]
            asst = turn.get("assistant", "")[:50]
            console.print(f"  [blue]You:[/blue] {user}...")
            console.print(f"  [green]Alfred:[/green] {asst}...")
    
    # History summary
    history = conversation.get("history_summary", "")
    if history:
        console.print(f"\n[bold]History Summary:[/bold] {history[:200]}...")
    
    console.print("")


@app.command()
def ask(
    message: str = typer.Argument(..., help="Message to send to Alfred"),
    log_prompts: bool = typer.Option(False, "--log-prompts", "-l", help="Log all LLM prompts to prompt_logs/"),
) -> None:
    """Send a single message to Alfred (useful for testing)."""
    from alfred_kitchen.config import settings
    from alfred.graph import run_alfred_simple
    from alfred.llm.prompt_logger import enable_prompt_logging, get_session_log_dir

    if log_prompts:
        enable_prompt_logging(True)

    user_id = settings.dev_user_id

    with Live(Spinner("dots", text="Thinking..."), console=console, transient=True):
        response = asyncio.run(run_alfred_simple(
            user_message=message,
            user_id=user_id,
        ))

    console.print(f"\n[bold green]Alfred:[/bold green] {response}")

    if log_prompts:
        log_dir = get_session_log_dir()
        if log_dir:
            console.print(f"\n[dim]Prompts logged to: {log_dir}[/dim]")


@app.command()
def health() -> None:
    """Check system health and configuration."""
    from alfred_kitchen.config import get_settings

    console.print("\n[bold]Alfred V3 Health Check[/bold]\n")

    try:
        settings = get_settings()
        console.print("[green]OK[/green] Configuration loaded")
        console.print(f"   Environment: {settings.alfred_env}")
        console.print(f"   Log level: {settings.log_level}")

        # Check OpenAI
        if settings.openai_api_key.startswith("sk-"):
            console.print("[green]OK[/green] OpenAI API key configured")
        else:
            console.print("[yellow]WARN[/yellow] OpenAI API key may be invalid")

        # Check Supabase
        if settings.supabase_url.startswith("https://"):
            console.print("[green]OK[/green] Supabase URL configured")
        else:
            console.print("[red]FAIL[/red] Supabase URL missing or invalid")

        # Check LangSmith
        if settings.langchain_tracing_v2 and settings.langchain_api_key:
            console.print("[green]OK[/green] LangSmith tracing enabled")
        else:
            console.print("[dim]INFO[/dim] LangSmith tracing disabled")

        console.print("\n[green]All checks passed![/green]")

    except Exception as e:
        console.print(f"\n[red]FAIL Configuration error: {e}[/red]")
        console.print("[dim]Make sure you have a .env file with required variables.[/dim]")
        raise typer.Exit(1)


@app.command()
def version() -> None:
    """Show version information."""
    from alfred import __version__

    console.print(f"Alfred V3 version {__version__}")


@app.command()
def serve(
    port: int = typer.Option(8000, "--port", "-p", help="Port to run on"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload for development"),
) -> None:
    """Start the web UI server."""
    import uvicorn
    import os
    
    # Railway sets PORT env var
    actual_port = int(os.environ.get("PORT", port))
    
    console.print(f"\n[bold green]Alfred Web UI[/bold green]")
    console.print(f"Starting server on http://localhost:{actual_port}")
    console.print(f"[dim]Press Ctrl+C to stop[/dim]\n")
    
    uvicorn.run(
        "alfred_kitchen.web.app:app",
        host="0.0.0.0",
        port=actual_port,
        reload=reload,
    )


@app.command()
def db() -> None:
    """Check database connection and schema."""
    from alfred_kitchen.db.client import get_client

    console.print("\n[bold]Database Connection Check[/bold]\n")

    try:
        client = get_client()
        console.print("[green]OK[/green] Connected to Supabase")

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
                console.print(f"  [green]OK[/green] {table}: {count} rows")
            except Exception as e:
                console.print(f"  [red]FAIL[/red] {table}: {e}")

        console.print("\n[green]Database check complete![/green]")

    except Exception as e:
        console.print(f"\n[red]FAIL Database connection failed: {e}[/red]")
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

