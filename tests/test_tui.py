"""Tests for hwh TUI."""

import pytest
import asyncio
from hwh.tui.app import HwhApp


class TestTUIImports:
    """Test that TUI modules import correctly."""

    def test_import_app(self):
        """Test HwhApp imports."""
        from hwh.tui.app import HwhApp
        assert HwhApp is not None

    def test_import_panels(self):
        """Test panel imports."""
        from hwh.tui.panels import (
            DevicePanel,
            BusPiratePanel,
            BoltPanel,
            TigardPanel,
            FirmwarePanel,
            CalibrationPanel,
        )
        assert DevicePanel is not None
        assert BusPiratePanel is not None
        assert BoltPanel is not None
        assert TigardPanel is not None
        assert FirmwarePanel is not None
        assert CalibrationPanel is not None

    def test_import_calibration_configs(self):
        """Test calibration configurations import."""
        from hwh.tui.panels.calibration import CALIBRATION_CONFIGS
        assert 'Curious Bolt' in CALIBRATION_CONFIGS
        assert 'Bus Pirate' in CALIBRATION_CONFIGS


class TestTUIApp:
    """Test TUI application."""

    @pytest.fixture
    def app(self):
        """Create app instance."""
        return HwhApp()

    @pytest.mark.asyncio
    async def test_app_creates(self, app):
        """Test app can be created."""
        assert app is not None
        assert app.title == "hwh - Hardware Hacking Toolkit"

    @pytest.mark.asyncio
    async def test_app_has_tabs(self, app):
        """Test app has main tabs."""
        async with app.run_test() as pilot:
            from textual.widgets import TabbedContent
            tabs = app.query_one('#main-tabs', TabbedContent)
            assert tabs is not None

    @pytest.mark.asyncio
    async def test_devices_tab_exists(self, app):
        """Test devices tab exists."""
        async with app.run_test() as pilot:
            from textual.widgets import TabPane
            # Devices tab should be active by default
            devices_tab = app.query_one('#tab-devices', TabPane)
            assert devices_tab is not None

    @pytest.mark.asyncio
    async def test_firmware_tab_exists(self, app):
        """Test firmware tab exists."""
        async with app.run_test() as pilot:
            from textual.widgets import TabPane
            firmware_tab = app.query_one('#tab-firmware', TabPane)
            assert firmware_tab is not None

    @pytest.mark.asyncio
    async def test_calibration_tab_exists(self, app):
        """Test calibration tab exists."""
        async with app.run_test() as pilot:
            from textual.widgets import TabPane
            calibration_tab = app.query_one('#tab-calibration', TabPane)
            assert calibration_tab is not None


class TestTUINavigation:
    """Test TUI keyboard navigation."""

    @pytest.fixture
    def app(self):
        """Create app instance."""
        return HwhApp()

    @pytest.mark.asyncio
    async def test_f1_goes_to_devices(self, app):
        """Test F1 switches to devices tab."""
        async with app.run_test() as pilot:
            await pilot.press('f1')
            from textual.widgets import TabbedContent
            tabs = app.query_one('#main-tabs', TabbedContent)
            assert tabs.active == 'tab-devices'

    @pytest.mark.asyncio
    async def test_f2_goes_to_firmware(self, app):
        """Test F2 switches to firmware tab."""
        async with app.run_test() as pilot:
            await pilot.press('f2')
            from textual.widgets import TabbedContent
            tabs = app.query_one('#main-tabs', TabbedContent)
            assert tabs.active == 'tab-firmware'

    @pytest.mark.asyncio
    async def test_f6_goes_to_calibration(self, app):
        """Test F6 switches to calibration tab."""
        async with app.run_test() as pilot:
            await pilot.press('f6')
            from textual.widgets import TabbedContent
            tabs = app.query_one('#main-tabs', TabbedContent)
            assert tabs.active == 'tab-calibration'


class TestCalibrationPanel:
    """Test calibration panel functionality."""

    @pytest.fixture
    def app(self):
        """Create app instance."""
        return HwhApp()

    @pytest.mark.asyncio
    async def test_calibration_panel_renders(self, app):
        """Test calibration panel renders correctly."""
        async with app.run_test() as pilot:
            await pilot.press('f6')
            await asyncio.sleep(0.1)

            from hwh.tui.panels.calibration import CalibrationPanel
            cal_panel = app.query_one('#calibration-panel', CalibrationPanel)
            assert cal_panel is not None

    @pytest.mark.asyncio
    async def test_calibration_device_selector(self, app):
        """Test device selector exists."""
        async with app.run_test() as pilot:
            await pilot.press('f6')
            await asyncio.sleep(0.1)

            from textual.widgets import Select
            device_select = app.query_one('#calibration-device-select', Select)
            assert device_select is not None

    @pytest.mark.asyncio
    async def test_calibration_profile_input(self, app):
        """Test profile name input exists."""
        async with app.run_test() as pilot:
            await pilot.press('f6')
            await asyncio.sleep(0.1)

            from textual.widgets import Input
            profile_input = app.query_one('#profile-name-input', Input)
            assert profile_input is not None

    @pytest.mark.asyncio
    async def test_calibration_results_table(self, app):
        """Test results table exists and has correct rows."""
        async with app.run_test() as pilot:
            await pilot.press('f6')
            await asyncio.sleep(0.1)

            from textual.widgets import DataTable
            results_table = app.query_one('#results-table', DataTable)
            assert results_table is not None
            # Check that expected rows exist
            assert results_table.row_count >= 6  # status, latency, jitter, min, max, p95, p99

    @pytest.mark.asyncio
    async def test_calibration_buttons_exist(self, app):
        """Test calibration buttons exist."""
        async with app.run_test() as pilot:
            await pilot.press('f6')
            await asyncio.sleep(0.1)

            from textual.widgets import Button
            start_btn = app.query_one('#btn-start-calibration', Button)
            stop_btn = app.query_one('#btn-stop-calibration', Button)
            assert start_btn is not None
            assert stop_btn is not None

    @pytest.mark.asyncio
    async def test_calibration_wiring_display(self, app):
        """Test wiring diagram and instructions exist."""
        async with app.run_test() as pilot:
            await pilot.press('f6')
            await asyncio.sleep(0.1)

            from textual.widgets import Static
            wiring_instructions = app.query_one('#wiring-instructions', Static)
            wiring_diagram = app.query_one('#wiring-diagram', Static)
            assert wiring_instructions is not None
            assert wiring_diagram is not None

    @pytest.mark.asyncio
    async def test_device_selection_updates_instructions(self, app):
        """Test that selecting a device updates wiring instructions."""
        async with app.run_test() as pilot:
            await pilot.press('f6')
            await asyncio.sleep(0.1)

            from hwh.tui.panels.calibration import CalibrationPanel
            cal_panel = app.query_one('#calibration-panel', CalibrationPanel)

            # Set device directly and trigger update
            cal_panel.current_device = 'Curious Bolt'
            await cal_panel._show_device_instructions('Curious Bolt')
            await asyncio.sleep(0.1)

            assert cal_panel.current_device == 'Curious Bolt'

    @pytest.mark.asyncio
    async def test_simulated_calibration(self, app):
        """Test simulated calibration creates profile."""
        async with app.run_test() as pilot:
            await pilot.press('f6')
            await asyncio.sleep(0.1)

            from hwh.tui.panels.calibration import CalibrationPanel
            cal_panel = app.query_one('#calibration-panel', CalibrationPanel)

            # Setup for calibration
            cal_panel.current_device = 'Curious Bolt'
            cal_panel.calibration_running = True

            # Run simulated calibration
            await cal_panel._run_simulated_calibration('test_profile', 10)

            # Verify profile was created
            assert cal_panel._current_profile is not None
            assert cal_panel._current_profile.profile_name == 'test_profile'
            assert cal_panel._current_profile.trigger_latency_ns > 0


class TestFirmwarePanel:
    """Test firmware panel functionality."""

    @pytest.fixture
    def app(self):
        """Create app instance."""
        return HwhApp()

    @pytest.mark.asyncio
    async def test_firmware_panel_renders(self, app):
        """Test firmware panel renders."""
        async with app.run_test() as pilot:
            await pilot.press('f2')
            await asyncio.sleep(0.1)

            from hwh.tui.panels.firmware import FirmwarePanel
            firmware_panel = app.query_one('#firmware-panel', FirmwarePanel)
            assert firmware_panel is not None


class TestAutomationImports:
    """Test automation module imports."""

    def test_import_uart_scanner(self):
        """Test UART scanner imports."""
        from hwh.automation import UARTScanner, scan_uart_baud
        assert UARTScanner is not None
        assert scan_uart_baud is not None

    def test_import_smart_glitch(self):
        """Test smart glitch imports."""
        from hwh.automation import SmartGlitchCampaign, GlitchResult
        assert SmartGlitchCampaign is not None
        assert GlitchResult is not None

    def test_import_la_glitch(self):
        """Test LA glitch imports."""
        from hwh.automation import LATriggeredGlitcher, TriggerPattern
        assert LATriggeredGlitcher is not None
        assert TriggerPattern is not None

    def test_import_protocol_replay(self):
        """Test protocol replay imports."""
        from hwh.automation import Protocol, ProtocolCapture, ProtocolReplay
        assert Protocol is not None
        assert ProtocolCapture is not None
        assert ProtocolReplay is not None

    def test_import_firmware_analysis(self):
        """Test firmware analysis imports."""
        from hwh.automation import FirmwareAnalyzer, analyze_firmware
        assert FirmwareAnalyzer is not None
        assert analyze_firmware is not None

    def test_import_calibration(self):
        """Test calibration imports."""
        from hwh.automation import (
            GlitchCalibrator,
            CalibrationProfile,
            CalibrationManager,
            PortableGlitchConfig,
            JitterStats,
            calibrate_setup,
        )
        assert GlitchCalibrator is not None
        assert CalibrationProfile is not None
        assert CalibrationManager is not None
        assert PortableGlitchConfig is not None
        assert JitterStats is not None
        assert calibrate_setup is not None


class TestCalibrationModule:
    """Test calibration module functionality."""

    def test_jitter_stats_creation(self):
        """Test JitterStats creation."""
        from hwh.automation.calibration import JitterStats

        stats = JitterStats(
            mean_ns=150.0,
            std_dev_ns=5.0,
            min_ns=140.0,
            max_ns=165.0,
            p95_ns=158.0,
            p99_ns=162.0,
            sample_count=100
        )

        assert stats.mean_ns == 150.0
        assert stats.std_dev_ns == 5.0
        assert stats.min_ns == 140.0
        assert stats.max_ns == 165.0
        assert stats.p95_ns == 158.0
        assert stats.p99_ns == 162.0
        assert stats.sample_count == 100

    def test_calibration_profile_creation(self):
        """Test CalibrationProfile creation."""
        from hwh.automation.calibration import CalibrationProfile, JitterStats

        jitter = JitterStats(
            mean_ns=150.0,
            std_dev_ns=5.0,
            min_ns=140.0,
            max_ns=165.0,
            p95_ns=158.0,
            p99_ns=162.0,
            sample_count=100
        )

        profile = CalibrationProfile(
            profile_name='test_profile',
            device_type='Curious Bolt',
            device_id='bolt_123',
            setup_description='Test setup',
            wire_length_cm=10.0,
            trigger_latency_ns=150.0,
            trigger_jitter=jitter,
            width_accuracy=0.95,
            reference_latency_ns=175.0,
            calibration_date='2024-01-01',
            sample_count=100,
            notes='Test notes'
        )

        assert profile.profile_name == 'test_profile'
        assert profile.device_type == 'Curious Bolt'
        assert profile.trigger_latency_ns == 150.0
        assert profile.trigger_jitter.std_dev_ns == 5.0

    def test_portable_glitch_config(self):
        """Test PortableGlitchConfig creation."""
        from hwh.automation.calibration import PortableGlitchConfig

        config = PortableGlitchConfig(
            target_name='stm32_rdp_bypass',
            target_chip='STM32F4',
            logical_width_ns=100,
            logical_offset_ns=5000,
            repeat=1,
            calibrated_on='reference_bolt',
            reference_latency_ns=175.0,
            success_pattern='flag{',
            author='test',
            notes='Works on F4 series'
        )

        assert config.target_name == 'stm32_rdp_bypass'
        assert config.logical_width_ns == 100
        assert config.logical_offset_ns == 5000
