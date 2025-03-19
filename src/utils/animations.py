import time
import sys
import random
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.live import Live
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.align import Align
from rich.style import Style
from rich.layout import Layout
from rich.rule import Rule
from constants.constants import BANNER_TEXT

def display_banner():
    """Display ASCII art banner at startup."""
    console = Console()
    console.clear()
    
    # Create panel with the banner
    banner_panel = Panel(
        Align.center(BANNER_TEXT, vertical="middle"),
        border_style="bright_blue",
        padding=(1, 2),
        title="T3RN Bridge Bot",
        title_align="center"
    )
    
    # Print banner with shadow effect
    console.print("")
    console.print(banner_panel)
    console.print("")

def display_processing_animation(message="Processing"):
    """
    Create a context manager for displaying a processing animation.
    
    Args:
        message (str): Message to display
        
    Returns:
        Live: Rich Live context manager
    """
    console = Console()
    
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        TextColumn("[bold]{task.fields[status]}"),
        TimeElapsedColumn(),
        console=console,
        expand=True
    )
    
    class ProcessingAnimation:
        def __init__(self, message):
            self.message = message
            self.live = None
            self.task_id = None
        
        def __enter__(self):
            self.live = Live(console=console, refresh_per_second=10)
            self.live.__enter__()
            self.task_id = progress.add_task(self.message, status="Running")
            
            # Update the display
            self.live.update(progress)
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            # Mark task as completed
            if exc_type is None:
                progress.update(self.task_id, status="Completed")
                self.live.update(progress)
                time.sleep(0.5)  # Short pause to show completion
            else:
                progress.update(self.task_id, status="Failed")
                self.live.update(progress)
                time.sleep(0.5)  # Short pause to show failure
            
            # Clean up
            self.live.__exit__(exc_type, exc_val, exc_tb)
    
    return ProcessingAnimation(message)

def display_retry_animation(wait_time, attempt, max_attempts):
    """
    Display animation during retry wait.
    
    Args:
        wait_time (float): Wait time in seconds
        attempt (int): Current attempt number
        max_attempts (int): Maximum number of attempts
    """
    console = Console()
    
    # Create a progress bar for the retry wait
    with Progress(
        SpinnerColumn(),
        TextColumn(f"[yellow]Retry attempt {attempt}/{max_attempts}[/yellow]"),
        BarColumn(),
        TextColumn("[bold]{task.percentage:.0f}%"),
        console=console,
        expand=True
    ) as progress:
        # Add task for retry wait
        task = progress.add_task("Waiting to retry...", total=wait_time)
        
        # Update progress bar
        while not progress.finished:
            progress.update(task, advance=0.1)
            time.sleep(0.1)

def display_countdown(total_seconds):
    """
    Display countdown animation.
    
    Args:
        total_seconds (int): Total seconds to countdown
    """
    console = Console()
    
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    # Prepare time messages
    time_messages = [
        "Taking a break...",
        "Waiting for next cycle...",
        "Countdown to next run...",
        "Time until next bridge session..."
    ]
    
    # Create a layout for the countdown display
    layout = Layout()
    layout.split_column(
        Layout(name="header"),
        Layout(name="countdown")
    )
    
    with Live(layout, console=console, refresh_per_second=1) as live:
        for remaining_seconds in range(total_seconds, -1, -1):
            hours = remaining_seconds // 3600
            minutes = (remaining_seconds % 3600) // 60
            seconds = remaining_seconds % 60
            
            # Create countdown display
            time_message = random.choice(time_messages) if remaining_seconds % 30 == 0 else time_messages[remaining_seconds % len(time_messages)]
            
            header = Panel(
                Align.center(time_message),
                title="T3RN Bridge Bot",
                border_style="blue",
                padding=(0, 2)
            )
            
            countdown_text = Text()
            countdown_text.append("  Next run in: ", style="dim")
            countdown_text.append(f"{hours:02}:{minutes:02}:{seconds:02}", style="bold white on blue")
            countdown_text.append("  ", style="dim")
            
            progress_value = 1 - (remaining_seconds / total_seconds)
            progress_bar = "█" * int(50 * progress_value) + "░" * (50 - int(50 * progress_value))
            
            countdown_panel = Panel(
                Align.center(countdown_text) + "\n\n" + Align.center(f"[blue]{progress_bar}[/blue]"),
                border_style="blue",
                padding=(1, 2)
            )
            
            # Update the layout
            layout["header"].update(header)
            layout["countdown"].update(countdown_panel)
            
            # Sleep for a second
            time.sleep(1)