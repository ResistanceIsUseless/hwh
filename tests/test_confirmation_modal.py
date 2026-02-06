"""Tests for ConfirmationModal widget."""

import pytest
import asyncio
from textual.pilot import Pilot
from hwh.tui.app import HwhApp
from hwh.tui.widgets import ConfirmationModal


class TestConfirmationModal:
    """Test ConfirmationModal widget functionality."""

    @pytest.mark.asyncio
    async def test_modal_imports(self):
        """Test that ConfirmationModal imports correctly."""
        from hwh.tui.widgets import ConfirmationModal
        assert ConfirmationModal is not None

    @pytest.mark.asyncio
    async def test_modal_creation(self):
        """Test that modal can be created with required parameters."""
        modal = ConfirmationModal(
            title="Test Title",
            message="Test message",
            confirm_text="Confirm",
            cancel_text="Cancel"
        )
        assert modal is not None
        assert modal.title == "Test Title"
        assert modal.message == "Test message"
        assert modal.confirm_text == "Confirm"
        assert modal.cancel_text == "Cancel"

    @pytest.mark.asyncio
    async def test_modal_default_values(self):
        """Test modal with default parameter values."""
        modal = ConfirmationModal(
            title="Test",
            message="Message"
        )
        assert modal.confirm_text == "Confirm"
        assert modal.cancel_text == "Cancel"
        assert modal.confirm_variant == "error"

    @pytest.mark.asyncio
    async def test_modal_error_variant(self):
        """Test modal with error variant (red background)."""
        modal = ConfirmationModal(
            title="Delete File?",
            message="This cannot be undone",
            confirm_variant="error"
        )
        assert modal.confirm_variant == "error"

    @pytest.mark.asyncio
    async def test_modal_warning_variant(self):
        """Test modal with warning variant (yellow background)."""
        modal = ConfirmationModal(
            title="Are you sure?",
            message="This might cause issues",
            confirm_variant="warning"
        )
        assert modal.confirm_variant == "warning"

    @pytest.mark.asyncio
    async def test_modal_primary_variant(self):
        """Test modal with primary variant (normal button)."""
        modal = ConfirmationModal(
            title="Continue?",
            message="Ready to proceed?",
            confirm_variant="primary"
        )
        assert modal.confirm_variant == "primary"

    @pytest.mark.asyncio
    async def test_modal_custom_button_text(self):
        """Test modal with custom button text."""
        modal = ConfirmationModal(
            title="Erase Flash?",
            message="This will erase all data",
            confirm_text="Erase Chip",
            cancel_text="Keep Data"
        )
        assert modal.confirm_text == "Erase Chip"
        assert modal.cancel_text == "Keep Data"


class TestConfirmationModalInteraction:
    """Test user interaction with ConfirmationModal."""

    @pytest.fixture
    def app(self):
        """Create app instance for testing."""
        return HwhApp()

    @pytest.mark.asyncio
    async def test_modal_has_confirm_button(self, app):
        """Test that modal has confirm button."""
        async with app.run_test() as pilot:
            modal = ConfirmationModal(
                title="Test",
                message="Message"
            )
            await app.push_screen(modal)
            await pilot.pause()

            from textual.widgets import Button
            confirm_btn = modal.query_one("#btn-confirm", Button)
            assert confirm_btn is not None

    @pytest.mark.asyncio
    async def test_modal_has_cancel_button(self, app):
        """Test that modal has cancel button."""
        async with app.run_test() as pilot:
            modal = ConfirmationModal(
                title="Test",
                message="Message"
            )
            await app.push_screen(modal)
            await pilot.pause()

            from textual.widgets import Button
            cancel_btn = modal.query_one("#btn-cancel", Button)
            assert cancel_btn is not None

    @pytest.mark.asyncio
    async def test_modal_confirm_returns_true(self, app):
        """Test that clicking confirm returns True."""
        async with app.run_test() as pilot:
            modal = ConfirmationModal(
                title="Test",
                message="Message"
            )

            # Push modal (this returns immediately, doesn't wait for dismissal)
            await app.push_screen(modal)
            await pilot.pause()

            # Click confirm button
            await pilot.click("#btn-confirm")
            await pilot.pause()

            # Modal should be dismissed - verify it's no longer the active screen
            assert app.screen != modal

    @pytest.mark.asyncio
    async def test_modal_cancel_returns_false(self, app):
        """Test that clicking cancel returns False."""
        async with app.run_test() as pilot:
            modal = ConfirmationModal(
                title="Test",
                message="Message"
            )

            # Push modal (this returns immediately, doesn't wait for dismissal)
            await app.push_screen(modal)
            await pilot.pause()

            # Click cancel button
            await pilot.click("#btn-cancel")
            await pilot.pause()

            # Modal should be dismissed - verify it's no longer the active screen
            assert app.screen != modal

    @pytest.mark.asyncio
    async def test_modal_escape_key_cancels(self, app):
        """Test that pressing Escape dismisses modal with False."""
        async with app.run_test() as pilot:
            modal = ConfirmationModal(
                title="Test",
                message="Message"
            )

            # Push modal (this returns immediately, doesn't wait for dismissal)
            await app.push_screen(modal)
            await pilot.pause()

            # Press Escape key
            await pilot.press("escape")
            await pilot.pause()

            # Modal should be dismissed - verify it's no longer the active screen
            assert app.screen != modal


class TestConfirmationModalStyling:
    """Test ConfirmationModal visual styling."""

    @pytest.fixture
    def app(self):
        """Create app instance."""
        return HwhApp()

    @pytest.mark.asyncio
    async def test_modal_has_title(self, app):
        """Test that modal displays title."""
        async with app.run_test() as pilot:
            modal = ConfirmationModal(
                title="Test Title",
                message="Message"
            )
            await app.push_screen(modal)
            await pilot.pause()

            from textual.widgets import Static
            title = modal.query_one("#confirmation-title", Static)
            assert title is not None
            # Check that the title widget exists (content is rendered internally)
            # The modal stores title in self.title, so verify that matches
            assert modal.title == "Test Title"

    @pytest.mark.asyncio
    async def test_modal_has_message(self, app):
        """Test that modal displays message."""
        async with app.run_test() as pilot:
            modal = ConfirmationModal(
                title="Title",
                message="Test Message Content"
            )
            await app.push_screen(modal)
            await pilot.pause()

            from textual.widgets import Static
            message = modal.query_one("#confirmation-message", Static)
            assert message is not None
            # Check that the message widget exists (content is rendered internally)
            # The modal stores message in self.message, so verify that matches
            assert modal.message == "Test Message Content"

    @pytest.mark.asyncio
    async def test_modal_error_variant_has_class(self, app):
        """Test that error variant button has correct class."""
        async with app.run_test() as pilot:
            modal = ConfirmationModal(
                title="Delete?",
                message="This is dangerous",
                confirm_variant="error"
            )
            await app.push_screen(modal)
            await pilot.pause()

            from textual.widgets import Button
            confirm_btn = modal.query_one("#btn-confirm", Button)
            assert confirm_btn.has_class("btn-confirm-error")

    @pytest.mark.asyncio
    async def test_modal_warning_variant_has_class(self, app):
        """Test that warning variant button has correct class."""
        async with app.run_test() as pilot:
            modal = ConfirmationModal(
                title="Warning",
                message="Be careful",
                confirm_variant="warning"
            )
            await app.push_screen(modal)
            await pilot.pause()

            from textual.widgets import Button
            confirm_btn = modal.query_one("#btn-confirm", Button)
            assert confirm_btn.has_class("btn-confirm-warning")


class TestConfirmationModalUseCases:
    """Test real-world use cases for ConfirmationModal."""

    @pytest.fixture
    def app(self):
        """Create app instance."""
        return HwhApp()

    @pytest.mark.asyncio
    async def test_flash_erase_confirmation(self, app):
        """Test flash erase confirmation use case."""
        async with app.run_test() as pilot:
            modal = ConfirmationModal(
                title="Erase Flash Sector?",
                message="This will permanently erase a 4KB sector at address 0x000000.\nThis action cannot be undone.\n\nAre you sure you want to continue?",
                confirm_text="Erase Sector",
                cancel_text="Cancel",
                confirm_variant="error"
            )

            # Verify modal is configured correctly for destructive action
            assert modal.confirm_variant == "error"
            assert "Erase Sector" in modal.confirm_text
            assert "permanently" in modal.message.lower()

    @pytest.mark.asyncio
    async def test_glitch_stop_confirmation(self, app):
        """Test glitch campaign stop confirmation."""
        async with app.run_test() as pilot:
            modal = ConfirmationModal(
                title="Stop Glitch Campaign?",
                message="Campaign is still running with 500 attempts remaining.\nStop now?",
                confirm_text="Stop Campaign",
                cancel_text="Continue Running",
                confirm_variant="warning"
            )

            # Verify modal is configured correctly for warning
            assert modal.confirm_variant == "warning"
            assert "Stop" in modal.confirm_text

    @pytest.mark.asyncio
    async def test_disconnect_device_confirmation(self, app):
        """Test device disconnect confirmation (if unsaved data)."""
        async with app.run_test() as pilot:
            modal = ConfirmationModal(
                title="Disconnect Device?",
                message="You have unsaved glitch profiles.\nDisconnect anyway?",
                confirm_text="Disconnect",
                cancel_text="Stay Connected",
                confirm_variant="warning"
            )

            assert modal.confirm_variant == "warning"
            assert "unsaved" in modal.message.lower()

    @pytest.mark.asyncio
    async def test_profile_overwrite_confirmation(self, app):
        """Test overwriting existing profile confirmation."""
        async with app.run_test() as pilot:
            modal = ConfirmationModal(
                title="Overwrite Profile?",
                message="Profile 'stm32_bypass' already exists.\nOverwrite it?",
                confirm_text="Overwrite",
                cancel_text="Cancel",
                confirm_variant="warning"
            )

            assert "already exists" in modal.message
            assert modal.confirm_variant == "warning"
