"""
Confirmation Modal Widget

Provides a reusable confirmation dialog for destructive actions.
"""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Container, Vertical, Horizontal, Center
from textual.widgets import Static, Button
from textual import on


class ConfirmationModal(ModalScreen[bool]):
    """
    Modal dialog for confirming destructive actions.

    Returns True if confirmed, False if cancelled.

    Example:
        result = await self.app.push_screen(ConfirmationModal(
            title="Erase Flash?",
            message="This will permanently erase all data on the flash chip.\nThis cannot be undone.",
            confirm_text="Erase Flash Chip",
            confirm_variant="error"
        ))
        if result:
            # User confirmed, proceed with action
            await erase_flash()
    """

    DEFAULT_CSS = """
    ConfirmationModal {
        align: center middle;
    }

    #confirmation-dialog {
        width: 50;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #confirmation-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        padding-bottom: 1;
    }

    #confirmation-message {
        text-align: center;
        color: $text;
        padding: 1 0 2 0;
    }

    #confirmation-buttons {
        height: auto;
        align: center middle;
        padding-top: 1;
    }

    #confirmation-buttons Button {
        margin: 0 1;
        min-width: 12;
    }

    .btn-confirm-error {
        background: $error;
        color: $text;
    }

    .btn-confirm-error:hover {
        background: $error-darken-1;
    }

    .btn-confirm-warning {
        background: $warning;
        color: $text;
    }

    .btn-confirm-warning:hover {
        background: $warning-darken-1;
    }
    """

    def __init__(
        self,
        title: str,
        message: str,
        confirm_text: str = "Confirm",
        cancel_text: str = "Cancel",
        confirm_variant: str = "error",  # "error", "warning", or "primary"
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.title = title
        self.message = message
        self.confirm_text = confirm_text
        self.cancel_text = cancel_text
        self.confirm_variant = confirm_variant

    def compose(self) -> ComposeResult:
        with Container(id="confirmation-dialog"):
            with Vertical():
                yield Static(self.title, id="confirmation-title")
                yield Static(self.message, id="confirmation-message")

                with Horizontal(id="confirmation-buttons"):
                    # Cancel button always comes first (safer default)
                    yield Button(
                        self.cancel_text,
                        id="btn-cancel",
                        variant="default"
                    )

                    # Confirm button with appropriate styling
                    confirm_classes = ""
                    if self.confirm_variant == "error":
                        confirm_classes = "btn-confirm-error"
                    elif self.confirm_variant == "warning":
                        confirm_classes = "btn-confirm-warning"

                    yield Button(
                        self.confirm_text,
                        id="btn-confirm",
                        variant="primary" if self.confirm_variant == "primary" else "default",
                        classes=confirm_classes
                    )

    @on(Button.Pressed, "#btn-confirm")
    def handle_confirm(self) -> None:
        """User confirmed the action"""
        self.dismiss(True)

    @on(Button.Pressed, "#btn-cancel")
    def handle_cancel(self) -> None:
        """User cancelled the action"""
        self.dismiss(False)

    def on_key(self, event) -> None:
        """Handle keyboard shortcuts"""
        if event.key == "escape":
            self.dismiss(False)
        elif event.key == "enter":
            # Enter confirms (but be careful with destructive actions!)
            pass  # Don't auto-confirm destructive actions with Enter
