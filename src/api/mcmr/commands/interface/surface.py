from cyclopts import App
from rich import box
from rich.console import Console
from rich.table import Table

app = App(name="mcmr", help="Define and enforce the engineering rules that make your code yours.")
console = Console(emoji=False)


def readable_table(title: str) -> Table:
    """Return the consistent terminal table every human-facing command uses."""
    return Table(
        title=title,
        box=box.SIMPLE_HEAD,
        header_style="bold cyan",
        row_styles=("", "dim"),
        show_lines=False,
    )
