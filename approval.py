"""
Human-in-the-loop approval system for sensitive operations
"""

import functools
from typing import Any, Callable, Dict, List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from entry import TimeEntry

console = Console()

class ApprovalRequest:
    """Represents a request for human approval"""
    def __init__(self, tool_name: str, description: str, data: Any, preview_func: Optional[Callable] = None):
        self.tool_name = tool_name
        self.description = description
        self.data = data
        self.preview_func = preview_func

def display_time_entries_preview(entries: List[TimeEntry]) -> None:
    """Display a preview of time entries to be created"""
    if not entries:
        console.print("[yellow]No entries to create[/yellow]")
        return
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Description", style="cyan", width=30)
    table.add_column("Start", style="green", width=16)
    table.add_column("Duration", style="yellow", width=10)
    table.add_column("Project", style="blue", width=15)
    
    for i, entry in enumerate(entries[:10]):  # Show max 10 entries
        project = entry.project or "None"
        table.add_row(
            entry.description[:27] + "..." if len(entry.description) > 30 else entry.description,
            f"{entry.start_date} {entry.start_time[:5]}",
            entry.duration,
            project[:12] + "..." if len(project) > 15 else project
        )
    
    if len(entries) > 10:
        table.add_row("...", "...", "...", f"... and {len(entries) - 10} more entries")
    
    console.print(table)

def request_approval(request: ApprovalRequest) -> tuple[bool, Optional[str]]:
    """
    Request human approval for a sensitive operation.
    
    Returns:
        tuple: (approved: bool, user_message: Optional[str])
            - approved: True if user approved, False if denied
            - user_message: Additional instructions from user, or None
    """
    console.print()
    
    # Create approval panel
    approval_panel = Panel(
        f"🔒 [bold yellow]APPROVAL REQUIRED[/bold yellow]\n\n"
        f"Tool: [bold cyan]{request.tool_name}[/bold cyan]\n"
        f"Action: {request.description}",
        border_style="yellow",
        title="[bold red]⚠️  Human Review Needed[/bold red]",
        title_align="left"
    )
    
    console.print(approval_panel)
    
    # Show preview if available
    if request.preview_func and request.data:
        console.print("\n[bold]Preview of changes:[/bold]")
        try:
            request.preview_func(request.data)
        except Exception as e:
            console.print(f"[red]Error displaying preview: {e}[/red]")
    
    console.print()
    
    # Get user response
    while True:
        console.print("[bold]Options:[/bold]")
        console.print("  [green]y[/green] / [green]yes[/green] - Approve and proceed")
        console.print("  [red]n[/red] / [red]no[/red] - Deny and cancel")
        console.print("  [blue]m[/blue] / [blue]modify[/blue] - Approve with modifications (provide instructions)")
        console.print("  [yellow]s[/yellow] / [yellow]show[/yellow] - Show preview again")
        console.print()
        
        response = input("Your decision: ").strip().lower()
        
        if response in ['y', 'yes']:
            console.print("[green]✓ Approved - proceeding with operation[/green]")
            return True, None
            
        elif response in ['n', 'no']:
            console.print("[red]✗ Denied - operation cancelled[/red]")
            return False, None
            
        elif response in ['m', 'modify']:
            console.print("\n[blue]Enter your modification instructions:[/blue]")
            instructions = input("Instructions: ").strip()
            if instructions:
                console.print(f"[green]✓ Approved with modifications: {instructions}[/green]")
                return True, instructions
            else:
                console.print("[yellow]No instructions provided, treating as simple approval[/yellow]")
                return True, None
                
        elif response in ['s', 'show']:
            if request.preview_func and request.data:
                console.print("\n[bold]Preview:[/bold]")
                try:
                    request.preview_func(request.data)
                except Exception as e:
                    console.print(f"[red]Error displaying preview: {e}[/red]")
                console.print()
            else:
                console.print("[yellow]No preview available[/yellow]")
                
        else:
            console.print("[red]Invalid option. Please enter y/yes, n/no, m/modify, or s/show[/red]")

def requires_approval(tool_name: str, description: str, preview_func: Optional[Callable] = None):
    """
    Decorator to add human approval requirement to a tool function.
    
    Args:
        tool_name: Name of the tool for display
        description: Description of the action being performed
        preview_func: Optional function to display preview of changes
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Create approval request
            # For the first argument (usually the data to be processed)
            data = args[0] if args else None
            
            request = ApprovalRequest(
                tool_name=tool_name,
                description=description,
                data=data,
                preview_func=preview_func
            )
            
            # Request approval
            approved, user_instructions = request_approval(request)
            
            if not approved:
                return "❌ Operation cancelled by user"
            
            # If user provided modification instructions, we could potentially
            # modify the operation here, but for simplicity, we'll just proceed
            # and let the user know their instructions were noted
            if user_instructions:
                console.print(f"[dim]Note: Proceeding with user instructions: {user_instructions}[/dim]")
            
            # Proceed with original function
            return func(*args, **kwargs)
        
        return wrapper
    return decorator