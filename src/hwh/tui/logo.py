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


# ASCII art logo - Crash Override style (compact 3-line)
LOGO_ART = r"""
░█   █░ ░█   █░ ░█   █░
░█▀▀▀█░ ░█▄█▄█░ ░█▀▀▀█░
░▀   ▀░ ░▀░ ░▀░ ░▀   ▀░
"""

# Subtitle line
LOGO_SUBTITLE = "Hardware Hacking Toolkit"

# Compact logo for smaller screens
LOGO_COMPACT = r"""
█ █  █   █  █ █
█▀█  █▄█▄█  █▀█
▀ ▀  ▀   ▀  ▀ ▀
"""

# Minimal logo
LOGO_MINI = r"""
╦ ╦╦ ╦╦ ╦
╠═╣║║║╠═╣
╩ ╩╚╩╝╩ ╩
"""

# Gradient colors for 3-line logo (Metagross Pokemon colors)
GRADIENT_COLORS = [
    "#9DC3CF",  # Pastel Blue (top)
    "#5E99AE",  # Crystal Blue (middle)
    "#2F596D",  # Police Blue (bottom)
]

# Alternative cyber gradient (green hacker style)
CYBER_GRADIENT = [
    "#00ff00",  # Bright green (top)
    "#00bb00",  # Medium green (middle)
    "#007700",  # Dark green (bottom)
]

# Blue/cyan hacker gradient
HACKER_GRADIENT = [
    "#00ffff",  # Cyan (top)
    "#0099ff",  # Blue (middle)
    "#0055ff",  # Deep blue (bottom)
]


def create_gradient_logo(use_cyber: bool = False) -> Text:
    """Create the logo with gradient coloring and inline subtitle."""
    colors = CYBER_GRADIENT if use_cyber else GRADIENT_COLORS
    lines = LOGO_ART.strip().split('\n')

    # Subtitle parts to show on each line
    subtitles = [
        f"  Hardware Hacking Toolkit",
        f"  ━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  v{__version__}",
    ]

    text = Text()

    for i, line in enumerate(lines):
        # Pick color based on line position
        color_idx = min(i, len(colors) - 1)
        color = colors[color_idx]

        # Add the logo part
        text.append(line, style=Style(color=color, bold=True))

        # Add subtitle on same line
        if i < len(subtitles):
            subtitle_color = "#9DC3CF" if i == 0 else ("#2F596D" if i == 1 else "#5E99AE")
            text.append(subtitles[i], style=Style(color=subtitle_color))

        if i < len(lines) - 1:
            text.append('\n')

    return text


def create_subtitle() -> Text:
    """Create standalone subtitle (for alternative layouts)."""
    text = Text()
    text.append("━" * 26, style="#2F596D")
    text.append("\n")
    text.append("Hardware Hacking Toolkit", style=Style(color="#9DC3CF", bold=True))
    text.append(f" v{__version__}", style=Style(color="#5E99AE"))
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
    """Full header banner with logo (subtitle is inline with logo)."""

    DEFAULT_CSS = """
    HeaderBanner {
        width: 100%;
        height: auto;
        align: center middle;
        padding: 1 1 0 1;
        background: #141618;
    }

    HeaderBanner .logo-text {
        text-align: center;
        width: 100%;
    }
    """

    def __init__(self, cyber: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.cyber = cyber

    def compose(self) -> ComposeResult:
        # Logo now includes inline subtitle
        yield Static(create_gradient_logo(self.cyber), classes="logo-text")


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
