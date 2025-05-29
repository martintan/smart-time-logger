#!/usr/bin/env python3
"""
ActivityWatch Timeline Processor
A CLI tool to fetch timeline data from ActivityWatch API and process it with LLM
"""

import os
from typing import Optional

import click
from dotenv import load_dotenv
from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from smolagents import CodeAgent, LiteLLMModel

from entry import TimeEntryList
from tools import (
    create_time_entries,
    fetch_timeline_data,
    fetch_time_entries,
    run_full_workflow,
)

load_dotenv()

console = Console()


def styled_input() -> str:
    """Custom input function that renders the prompt inside a styled text box."""
    import sys

    # Create an empty input box that fills the full width
    input_box = Panel(
        " ",  # Empty space for the input area
        border_style="bright_black",
        box=ROUNDED,
        padding=(0, 1),
        expand=True,  # This makes it fill the available width
        title="[dim white]💬 Input[/dim white]",
        title_align="left",
    )

    console.print("")
    console.print(input_box)

    # Move cursor up to position it inside the box
    # ANSI escape sequence to move cursor up 2 lines and right 4 characters
    sys.stdout.write("\033[2A")  # Move up 2 lines
    sys.stdout.write("\033[2C")  # Move right 4 characters
    sys.stdout.write("\033[36m>\033[0m ")  # Print cyan ">" and reset color
    sys.stdout.flush()

    # Get user input
    user_input = input().strip()

    # Move cursor down to continue normal output
    console.print("")

    return user_input


def run_full_timeline_processing(
    model: Optional[str] = None,
    aw_url: Optional[str] = None,
    output: Optional[str] = None,
    min_duration: Optional[int] = None,
) -> Optional[TimeEntryList]:
    """Run the complete timeline processing workflow"""
    console.print("[bold green]ActivityWatch Timeline Processor[/bold green]")
    console.print("=" * 50)

    # Use the tools workflow
    result = run_full_workflow(model, aw_url, output, min_duration)

    # Return None for now since the tools manage their own state
    return None


def create_agent() -> CodeAgent:
    """Create the smolagents agent with all tools"""
    # Get LLM model from environment or use default
    model_name = os.getenv("LLM_MODEL", "gpt-4o")

    # Create LiteLLM model instance
    model = LiteLLMModel(model_id=model_name)

    # Define core tools only
    tools = [
        fetch_timeline_data,
        fetch_time_entries,
        create_time_entries,
    ]

    # Create agent with tools
    agent = CodeAgent(tools=tools, model=model, add_base_tools=False, max_steps=10)

    return agent


def chat_interface():
    """Simple chat interface for the agent"""
    console.print(
        "[bold green]ActivityWatch Timeline Processor - Agent Mode[/bold green]"
    )
    console.print("=" * 60)
    console.print("[cyan]Available tools:[/cyan]")
    console.print(
        "• [bold]fetch_timeline_data[/bold] - Fetch timeline data from ActivityWatch"
    )
    console.print(
        "• [bold]fetch_time_entries[/bold] - Fetch Toggl time entries for specific time range"
    )
    console.print(
        "• [bold]create_time_entries[/bold] - Create time entries in Toggl workspace"
    )
    console.print()
    console.print(
        "[dim]You can ask the agent to use these tools or combine them in natural language.[/dim]"
    )
    console.print(
        "[dim]Example: 'fetch timeline data for today and show me time entries'[/dim]"
    )
    console.print("• 'exit' - Exit the application")
    console.print()

    # Create agent
    agent = create_agent()

    while True:
        try:
            # Get user input using styled input box
            user_input = styled_input()

            if user_input.lower() in ["exit", "quit", "q"]:
                console.print("[yellow]Goodbye![/yellow]")
                break

            if not user_input:
                continue

            # Run agent with user input
            console.print(f"[dim]Processing: {user_input}[/dim]")
            try:
                result = agent.run(user_input)
                console.print(f"\n[green]Agent result:[/green] {result}")
            except Exception as e:
                console.print(f"[red]Agent error: {e}[/red]")

        except KeyboardInterrupt:
            console.print("\n[yellow]Goodbye![/yellow]")
            break
        except Exception as e:
            console.print(f"[red]Unexpected error: {e}[/red]")


@click.command()
@click.option(
    "--model", default=None, help="LLM model to use (default: from env or gpt-4)"
)
@click.option(
    "--aw-url",
    default=None,
    help="ActivityWatch server URL (default: from env or localhost:5600)",
)
@click.option("--output", "-o", help="Output file to save results (optional)")
@click.option(
    "--min-duration",
    default=None,
    type=int,
    help="Minimum activity duration in minutes to consider (default: 5)",
)
def main(model: str, aw_url: str, output: Optional[str], min_duration: Optional[int]):
    """ActivityWatch Timeline Processor CLI"""
    # Check if we should run in chat mode (no CLI args provided)
    if not any([model, aw_url, output, min_duration]):
        chat_interface()
    else:
        # Run original CLI mode
        run_full_timeline_processing(model, aw_url, output, min_duration)


if __name__ == "__main__":
    main()
