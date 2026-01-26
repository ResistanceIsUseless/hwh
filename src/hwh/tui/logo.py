"""
hwh ASCII Logo with gradient colors.

Inspired by Crash Override from Hackers (1995).
"""

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static
from rich.text import Text
from rich.style import Style

from .. import __version__


# ASCII art logo - cyberpunk/hacker style
LOGO_ART = r"""
 ██░ ██  █     █░ ██░ ██
▓██░ ██▒▓█░ █ ░█░▓██░ ██▒
▒██▀▀██░▒█░ █ ░█ ▒██▀▀██░
░▓█ ░██ ░█░ █ ░█ ░▓█ ░██
░▓█▒░██▓░░██▒██▓ ░▓█▒░██▓
 ▒ ░░▒░▒░ ▓░▒ ▒   ▒ ░░▒░▒
 ▒ ░▒░ ░  ▒ ░ ░   ▒ ░▒░ ░
 ░  ░░ ░  ░   ░   ░  ░░ ░
 ░  ░  ░    ░     ░  ░  ░
"""

# Compact logo for smaller screens
LOGO_COMPACT = r"""
█ █ █ █ █ █ █   █ █ █ █ █ █ █
█ █ █ █ █ █ █   █ █ █ █ █ █ █
███████ █ █ █ █ ███████████████
█ █ █ █ █ █ █   █ █ █ █ █ █ █
█ █ █ █ █ █ █   █ █ █ █ █ █ █
"""

# Minimal logo
LOGO_MINI = r"""
╦ ╦╦ ╦╦ ╦
╠═╣║║║╠═╣
╩ ╩╚╩╝╩ ╩
"""

# Gradient colors (Metagross Pokemon colors - matches the theme)
GRADIENT_COLORS = [
    "#9DC3CF",  # Pastel Blue (top)
    "#5E99AE",  # Crystal Blue
    "#5E99AE",  # Crystal Blue
    "#2F596D",  # Police Blue
    "#2F596D",  # Police Blue
    "#5E99AE",  # Crystal Blue
    "#9DC3CF",  # Pastel Blue
    "#B3B8BB",  # Ash Gray
    "#B3B8BB",  # Ash Gray (bottom fade)
]

# Alternative cyber gradient
CYBER_GRADIENT = [
    "#00ff00",  # Bright green (top)
    "#00dd00",
    "#00bb00",
    "#009900",
    "#007700",
    "#005500",
    "#003300",
    "#002200",
    "#001100",
]

# Blue/cyan hacker gradient
HACKER_GRADIENT = [
    "#00ffff",  # Cyan
    "#00ddff",
    "#00bbff",
    "#0099ff",
    "#0077ff",
    "#0055ff",
    "#0033ff",
    "#0022dd",
    "#0011bb",
]


def create_gradient_logo(use_cyber: bool = False) -> Text:
    """Create the logo with gradient coloring."""
    colors = CYBER_GRADIENT if use_cyber else GRADIENT_COLORS
    lines = LOGO_ART.strip().split('\n')

    text = Text()

    for i, line in enumerate(lines):
        # Pick color based on line position
        color_idx = min(i, len(colors) - 1)
        color = colors[color_idx]

        text.append(line, style=Style(color=color, bold=True))
        if i < len(lines) - 1:
            text.append('\n')

    return text


def create_subtitle() -> Text:
    """Create the subtitle with version."""
    text = Text()
    text.append("═" * 32, style="#2F596D")
    text.append("\n")
    text.append("  Hardware Hacking Toolkit", style=Style(color="#9DC3CF", bold=True))
    text.append(f"  v{__version__}", style=Style(color="#5E99AE"))
    text.append("\n")
    text.append("═" * 32, style="#2F596D")
    return text


def create_full_header() -> Text:
    """Create the complete header with logo and subtitle."""
    text = Text()
    text.append_text(create_gradient_logo())
    text.append("\n")
    text.append_text(create_subtitle())
    return text


class LogoWidget(Static):
    """Widget displaying the hwh ASCII logo with gradient."""

    DEFAULT_CSS = """
    LogoWidget {
        width: 100%;
        height: auto;
        content-align: center middle;
        text-align: center;
        padding: 0;
        margin: 0;
    }
    """

    def __init__(self, compact: bool = False, cyber: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.compact = compact
        self.cyber = cyber

    def render(self) -> Text:
        """Render the logo."""
        return create_gradient_logo(use_cyber=self.cyber)


class HeaderBanner(Container):
    """Full header banner with logo and subtitle."""

    DEFAULT_CSS = """
    HeaderBanner {
        width: 100%;
        height: auto;
        align: center middle;
        padding: 0 1;
        background: #141618;
    }

    HeaderBanner .logo-text {
        text-align: center;
        width: 100%;
    }

    HeaderBanner .subtitle-text {
        text-align: center;
        width: 100%;
        margin-top: 0;
    }
    """

    def __init__(self, cyber: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.cyber = cyber

    def compose(self) -> ComposeResult:
        yield Static(create_gradient_logo(self.cyber), classes="logo-text")
        yield Static(create_subtitle(), classes="subtitle-text")


# Simpler inline header for space-constrained views
def get_inline_header() -> str:
    """Get a single-line header."""
    return f"[bold #5E99AE]╔═══ [#9DC3CF]hwh[/#9DC3CF] ═══╗[/] [#B3B8BB]Hardware Hacking Toolkit v{__version__}[/]"


def get_mini_header() -> Text:
    """Get minimal header for tight spaces."""
    text = Text()
    text.append("hwh", style=Style(color="#9DC3CF", bold=True))
    text.append(" │ ", style="#2F596D")
    text.append("Hardware Hacking Toolkit", style="#5E99AE")
    text.append(f" v{__version__}", style="#B3B8BB")
    return text
