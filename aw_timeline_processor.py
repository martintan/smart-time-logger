#!/usr/bin/env python3
"""
ActivityWatch Timeline Processor
A CLI tool to fetch timeline data from ActivityWatch API and process it with LLM
"""

import os
from typing import Optional

import click
from dotenv import load_dotenv
from rich.console import Console
from smolagents import CodeAgent, LiteLLMModel

from entry import TimeEntryList
from tools import (
    create_time_entries,
    display_results,
    display_time_range,
    fetch_timeline_data,
    fetch_time_entries,
    get_and_display_buckets,
    initialize_clients,
    process_timeline_with_llm,
    run_full_workflow,
    save_results,
    test_connection,
)

load_dotenv()

console = Console()


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

    # Define all tools
    tools = [
        initialize_clients,
        test_connection,
        get_and_display_buckets,
        display_time_range,
        fetch_timeline_data,
        fetch_time_entries,
        create_time_entries,
        process_timeline_with_llm,
        display_results,
        save_results,
        run_full_workflow,
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
    console.print("[cyan]Available commands:[/cyan]")
    console.print(
        "• 'process timeline' or 'run full workflow' - Complete timeline processing"
    )
    console.print("• 'initialize' - Initialize clients")
    console.print("• 'test connection' - Test ActivityWatch connection")
    console.print("• 'get buckets' - Show available buckets")
    console.print("• 'show time range' - Display time range")
    console.print("• 'fetch data' - Fetch timeline data")
    console.print(
        "• 'fetch time entries [date] [start_time] [end_time]' - Fetch Toggl entries for specific time range"
    )
    console.print(
        "• 'create time entries [entries_list]' - Create time entries in Toggl workspace from TimeEntry objects"
    )
    console.print("• 'process with llm' - Process with LLM")
    console.print("• 'display results' - Show processed results")
    console.print("• 'save results filename.json' - Save results to file")
    console.print("• 'exit' - Exit the application")
    console.print()

    # Create agent
    agent = create_agent()

    while True:
        try:
            # Get user input
            user_input = input("\n🤖 Enter command: ").strip()

            if user_input.lower() in ["exit", "quit", "q"]:
                console.print("[yellow]Goodbye![/yellow]")
                break

            if not user_input:
                continue

            # Run agent with user input
            console.print(f"\n[dim]Processing: {user_input}[/dim]")
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
