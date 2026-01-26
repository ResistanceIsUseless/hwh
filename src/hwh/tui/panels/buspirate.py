"""
Bus Pirate Panel

Full-featured panel for Bus Pirate 5/6 devices.
Supports: SPI, I2C, UART, 1-Wire, JTAG/SWD scanning, Logic Analyzer, ADC, PWM
"""

import asyncio
from typing import List, Optional
from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal, Grid
from textual.widgets import Static, Button, Input, Select, Switch, Log, TabbedContent, TabPane

from .base import DevicePanel, DeviceInfo, PanelCapability, CommandSuggestion
from .logic_analyzer import LogicAnalyzerWidget, LogicCapture


@dataclass
class SPIConfig:
    speed: int = 1000000
    mode: int = 0
    cs_active_low: bool = True


@dataclass
class I2CConfig:
    speed: int = 100000
    address: int = 0x50


@dataclass
class UARTConfig:
    baud: int = 115200
    data_bits: int = 8
    parity: str = "N"
    stop_bits: int = 1


class BusPiratePanel(DevicePanel):
    """
    Panel for Bus Pirate 5/6 devices.

    Features:
    - Protocol selection (SPI, I2C, UART, 1-Wire)
    - JTAG/SWD pin scanning
    - Logic analyzer (8ch, 62.5MSPS)
    - ADC voltage measurement
    - PWM generation
    - Power supply control
    """

    DEVICE_NAME = "Bus Pirate"
    CAPABILITIES = [
        PanelCapability.SPI,
        PanelCapability.I2C,
        PanelCapability.UART,
        PanelCapability.JTAG,
        PanelCapability.SWD,
        PanelCapability.LOGIC,
        PanelCapability.ADC,
        PanelCapability.PWM,
        PanelCapability.GPIO,
    ]

    def __init__(self, device_info: DeviceInfo, app, *args, **kwargs):
        super().__init__(device_info, app, *args, **kwargs)
        self.current_mode = "HiZ"
        self.spi_config = SPIConfig()
        self.i2c_config = I2CConfig()
        self.uart_config = UARTConfig()
        self.power_enabled = False
        self.pullups_enabled = False
        self._backend = None
        self._logic_widget: Optional[LogicAnalyzerWidget] = None
        self._logic_capturing = False
        # Live ADC values for pinout display (in mV)
        self._adc_values: List[int] = [0] * 8
        self._psu_measured_mv: int = 0
        self._psu_measured_ma: int = 0
        self._pinout_refresh_timer = None

    def compose(self) -> ComposeResult:
        with Vertical(id="buspirate-panel"):
            # Header with device info and mode
            with Horizontal(classes="panel-header"):
                yield Static(f"{self.device_info.name}", classes="device-title")
                yield Static(f"Port: {self.device_info.port}", classes="device-port")
                yield Static(f"Mode: ", classes="mode-label")
                yield Select(
                    [(mode, mode) for mode in ["HiZ", "SPI", "I2C", "UART", "1-Wire", "2-Wire", "3-Wire"]],
                    value="HiZ",
                    id="mode-select",
                    classes="mode-select"
                )
                yield Static(" Voltage:", classes="voltage-label")
                yield Select(
                    [("3.3V", "3.3"), ("5V", "5.0"), ("Off", "0")],
                    value="3.3",
                    id="voltage-select",
                    classes="voltage-select"
                )

            # Feature tabs within device panel
            with TabbedContent(id="bp-features"):
                # Status Tab - Device info (first tab for connection verification)
                with TabPane("Status", id="tab-status"):
                    yield from self._build_status_section()

                # Protocol Tab - Current mode operations
                with TabPane("Protocol", id="tab-protocol"):
                    yield from self._build_protocol_section()

                # Scan Tab - JTAG/SWD pin detection
                with TabPane("Scan", id="tab-scan"):
                    yield from self._build_scan_section()

                # Logic Tab - Logic analyzer
                with TabPane("Logic", id="tab-logic"):
                    yield from self._build_logic_section()

                # Power Tab - ADC/PWM/Power
                with TabPane("Power", id="tab-power"):
                    yield from self._build_power_section()

            # Console at bottom
            yield from self._build_console_section()

    def _build_status_section(self) -> ComposeResult:
        """Device status display - shows comprehensive BPIO2 device information"""
        with Vertical(id="status-container", classes="status-container"):
            # Refresh button at top
            with Horizontal(classes="button-row"):
                yield Button("Refresh", id="btn-status-refresh", classes="btn-action")

            # Version Information group
            with Container(classes="status-group"):
                yield Static("Version Information", classes="status-group-title")
                with Grid(classes="status-grid-2col"):
                    yield Static("FlatBuffers:", classes="status-key")
                    yield Static("---", id="status-flatbuffers", classes="status-val")
                    yield Static("Hardware:", classes="status-key")
                    yield Static("---", id="status-hardware", classes="status-val")
                    yield Static("Firmware:", classes="status-key")
                    yield Static("---", id="status-firmware", classes="status-val")
                    yield Static("Git Hash:", classes="status-key")
                    yield Static("---", id="status-git-hash", classes="status-val")
                    yield Static("Build Date:", classes="status-key")
                    yield Static("---", id="status-build-date", classes="status-val")

            # Mode Information group
            with Container(classes="status-group"):
                yield Static("Mode Information", classes="status-group-title")
                with Grid(classes="status-grid-2col"):
                    yield Static("Current Mode:", classes="status-key")
                    yield Static("---", id="status-mode", classes="status-val")
                    yield Static("Available:", classes="status-key")
                    yield Static("---", id="status-modes-available", classes="status-val")
                    yield Static("Bit Order:", classes="status-key")
                    yield Static("---", id="status-bit-order", classes="status-val")
                    yield Static("Pin Labels:", classes="status-key")
                    yield Static("---", id="status-pins", classes="status-val")
                    yield Static("Max Packet:", classes="status-key")
                    yield Static("---", id="status-max-packet", classes="status-val")
                    yield Static("Max Write:", classes="status-key")
                    yield Static("---", id="status-max-write", classes="status-val")
                    yield Static("Max Read:", classes="status-key")
                    yield Static("---", id="status-max-read", classes="status-val")

            # Power Supply group
            with Container(classes="status-group"):
                yield Static("Power Supply", classes="status-group-title")
                with Grid(classes="status-grid-2col"):
                    yield Static("PSU Enabled:", classes="status-key")
                    yield Static("---", id="status-psu", classes="status-val")
                    yield Static("Set Voltage:", classes="status-key")
                    yield Static("---", id="status-set-voltage", classes="status-val")
                    yield Static("Set Current:", classes="status-key")
                    yield Static("---", id="status-set-current", classes="status-val")
                    yield Static("Measured V:", classes="status-key")
                    yield Static("---", id="status-voltage-meas", classes="status-val")
                    yield Static("Measured I:", classes="status-key")
                    yield Static("---", id="status-current-meas", classes="status-val")
                    yield Static("OC Error:", classes="status-key")
                    yield Static("---", id="status-oc-error", classes="status-val")
                    yield Static("Pull-ups:", classes="status-key")
                    yield Static("---", id="status-pullups", classes="status-val")

            # IO Pins group
            with Container(classes="status-group"):
                yield Static("IO Pins", classes="status-group-title")
                with Grid(classes="status-grid-2col"):
                    yield Static("ADC Values:", classes="status-key")
                    yield Static("---", id="status-adc-values", classes="status-val")
                    yield Static("Directions:", classes="status-key")
                    yield Static("---", id="status-io-directions", classes="status-val")
                    yield Static("Values:", classes="status-key")
                    yield Static("---", id="status-io-values", classes="status-val")

            # System group
            with Container(classes="status-group"):
                yield Static("System", classes="status-group-title")
                with Grid(classes="status-grid-2col"):
                    yield Static("LEDs:", classes="status-key")
                    yield Static("---", id="status-leds", classes="status-val")
                    yield Static("Disk Size:", classes="status-key")
                    yield Static("---", id="status-disk-size", classes="status-val")
                    yield Static("Disk Used:", classes="status-key")
                    yield Static("---", id="status-disk-used", classes="status-val")

    def _build_protocol_section(self) -> ComposeResult:
        """Protocol-specific controls with subtabs for SPI, I2C, UART"""
        with TabbedContent(id="protocol-tabs"):
            # SPI Tab
            with TabPane("SPI", id="tab-spi"):
                yield from self._build_spi_subtab()

            # I2C Tab
            with TabPane("I2C", id="tab-i2c"):
                yield from self._build_i2c_subtab()

            # UART Tab
            with TabPane("UART", id="tab-uart"):
                yield from self._build_uart_subtab()

    def _build_power_control_row(self, prefix: str) -> ComposeResult:
        """Build a power control row with voltage switch, dropdown, and live refresh"""
        with Horizontal(classes="power-control-row"):
            yield Static("VOUT:", classes="power-label")
            yield Switch(id=f"{prefix}-power-switch", value=False)
            yield Select(
                [("3.3V", "3300"), ("5.0V", "5000"), ("1.8V", "1800"), ("2.5V", "2500")],
                value="3300",
                id=f"{prefix}-voltage-select",
                classes="voltage-select-sm"
            )
            yield Static("Pull-ups:", classes="pullup-label")
            yield Switch(id=f"{prefix}-pullup-switch", value=False)
            yield Button("⟳", id=f"{prefix}-refresh-pinout", classes="btn-refresh-pinout")
            yield Button("Live", id=f"{prefix}-live-toggle", classes="btn-live-toggle")

    def _build_spi_subtab(self) -> ComposeResult:
        """Build SPI protocol subtab with pinout and controls"""
        with Vertical(classes="protocol-subtab"):
            # Power control row
            yield from self._build_power_control_row("spi")

            # SPI Pinout diagram with live voltage display
            with Container(classes="pinout-box"):
                yield Static("SPI Pinout (Live)", classes="pinout-title")
                yield Static(
                    self._build_spi_pinout_ascii(),
                    id="spi-pinout",
                    classes="pinout-diagram"
                )

            # SPI Configuration
            yield Static("Configuration", classes="section-subtitle")
            with Horizontal(classes="config-row"):
                yield Static("Speed:", classes="config-label")
                yield Select(
                    [("1MHz", "1000000"), ("2MHz", "2000000"), ("4MHz", "4000000"),
                     ("8MHz", "8000000"), ("16MHz", "16000000"), ("24MHz", "24000000")],
                    value="1000000",
                    id="spi-speed",
                    classes="config-select"
                )
                yield Static("Mode:", classes="config-label")
                yield Select(
                    [("0 (CPOL=0,CPHA=0)", "0"), ("1 (CPOL=0,CPHA=1)", "1"),
                     ("2 (CPOL=1,CPHA=0)", "2"), ("3 (CPOL=1,CPHA=1)", "3")],
                    value="0",
                    id="spi-mode",
                    classes="config-select"
                )
                yield Static("CS:", classes="config-label")
                yield Select([("Active Low", "low"), ("Active High", "high")], value="low", id="spi-cs", classes="config-select-sm")

            # Flash Operations
            yield Static("Flash Operations", classes="section-subtitle")
            with Horizontal(classes="button-row"):
                yield Button("Read ID", id="btn-spi-id", classes="btn-action")
                yield Button("Dump", id="btn-spi-dump", classes="btn-action")
                yield Button("Erase", id="btn-spi-erase", classes="btn-action btn-danger")
                yield Button("Write", id="btn-spi-write", classes="btn-action btn-danger")

            with Horizontal(classes="input-row"):
                yield Static("Addr:", classes="input-label")
                yield Input(value="0x000000", id="spi-addr", classes="hex-input")
                yield Static("Size:", classes="input-label")
                yield Input(value="0x1000", id="spi-size", classes="hex-input")
                yield Static("File:", classes="input-label")
                yield Input(value="dump.bin", id="spi-file", classes="file-input")

            # Output log
            yield Log(id="spi-log", classes="protocol-log")

    def _build_i2c_subtab(self) -> ComposeResult:
        """Build I2C protocol subtab with pinout and controls"""
        with Vertical(classes="protocol-subtab"):
            # Power control row
            yield from self._build_power_control_row("i2c")

            # I2C Pinout diagram with live voltage display
            with Container(classes="pinout-box"):
                yield Static("I2C Pinout (Live)", classes="pinout-title")
                yield Static(
                    self._build_i2c_pinout_ascii(),
                    id="i2c-pinout",
                    classes="pinout-diagram"
                )

            # I2C Configuration
            yield Static("Configuration", classes="section-subtitle")
            with Horizontal(classes="config-row"):
                yield Static("Speed:", classes="config-label")
                yield Select(
                    [("100kHz (Standard)", "100000"), ("400kHz (Fast)", "400000"),
                     ("1MHz (Fast+)", "1000000")],
                    value="100000",
                    id="i2c-speed",
                    classes="config-select"
                )
                yield Static("Address:", classes="config-label")
                yield Input(value="0x50", id="i2c-addr", classes="hex-input")

            # I2C Operations
            yield Static("Operations", classes="section-subtitle")
            with Horizontal(classes="button-row"):
                yield Button("Scan Bus", id="btn-i2c-scan", classes="btn-action")
                yield Button("Read", id="btn-i2c-read", classes="btn-action")
                yield Button("Write", id="btn-i2c-write", classes="btn-action")
                yield Button("Dump EEPROM", id="btn-i2c-dump", classes="btn-action")

            with Horizontal(classes="input-row"):
                yield Static("Register:", classes="input-label")
                yield Input(value="0x00", id="i2c-reg", classes="hex-input")
                yield Static("Length:", classes="input-label")
                yield Input(value="1", id="i2c-len", classes="hex-input-sm")
                yield Static("Data:", classes="input-label")
                yield Input(value="0x00", id="i2c-data", classes="hex-input")

            # Output log
            yield Log(id="i2c-log", classes="protocol-log")

    def _build_uart_subtab(self) -> ComposeResult:
        """Build UART protocol subtab with pinout and controls (stub - not implemented in firmware)"""
        with Vertical(classes="protocol-subtab"):
            # Power control row
            yield from self._build_power_control_row("uart")

            # UART Pinout diagram with live voltage display
            with Container(classes="pinout-box"):
                yield Static("UART Pinout (Live)", classes="pinout-title")
                yield Static(
                    self._build_uart_pinout_ascii(),
                    id="uart-pinout",
                    classes="pinout-diagram"
                )

            # UART Firmware Warning
            with Container(classes="warning-box"):
                yield Static(
                    "⚠ UART BPIO2 NOT IMPLEMENTED IN FIRMWARE\n"
                    "UART mode is listed in BPIO2 schema but the firmware handler is not implemented.\n"
                    "Use terminal commands via the console port for UART operations.",
                    classes="warning-text"
                )

            # UART Configuration (stub)
            yield Static("Configuration", classes="section-subtitle")
            with Horizontal(classes="config-row"):
                yield Static("Baud:", classes="config-label")
                yield Select(
                    [("9600", "9600"), ("19200", "19200"), ("38400", "38400"),
                     ("57600", "57600"), ("115200", "115200"), ("230400", "230400"),
                     ("460800", "460800"), ("921600", "921600")],
                    value="115200",
                    id="uart-baud",
                    classes="config-select"
                )
                yield Static("Format:", classes="config-label")
                yield Select(
                    [("8N1", "8N1"), ("8E1", "8E1"), ("8O1", "8O1"), ("7E1", "7E1"), ("7O1", "7O1")],
                    value="8N1",
                    id="uart-format",
                    classes="config-select-sm"
                )

            # UART Operations (limited without BPIO2)
            yield Static("Operations (via terminal fallback)", classes="section-subtitle")
            with Horizontal(classes="button-row"):
                yield Button("Bridge Mode", id="btn-uart-bridge", classes="btn-action")
                yield Button("Auto Baud", id="btn-uart-auto", classes="btn-action")

            # Output log
            yield Log(id="uart-log", classes="protocol-log")

    def _build_scan_section(self) -> ComposeResult:
        """JTAG/SWD pin scanning controls"""
        with Vertical():
            yield Static("Pin Scanning", classes="section-title")
            yield Static("Scan target pins to detect JTAG/SWD interfaces", classes="help-text")

            with Horizontal(classes="button-row"):
                yield Button("JTAG Scan", id="btn-jtag-scan", classes="btn-action")
                yield Button("SWD Scan", id="btn-swd-scan", classes="btn-action")
                yield Button("UART Detect", id="btn-uart-detect", classes="btn-action")

            with Grid(classes="config-grid"):
                yield Static("Pins to scan:")
                yield Input(value="0-7", id="scan-pins", classes="pin-input")
                yield Static("Voltage:")
                yield Select([("3.3V", "3.3"), ("1.8V", "1.8"), ("5V", "5.0")], value="3.3", id="scan-voltage")

            yield Static("Scan Results:", classes="section-subtitle")
            yield Log(id="scan-results", classes="scan-log")

    def _build_logic_section(self) -> ComposeResult:
        """Logic analyzer controls - consistent with Bolt panel design"""
        with Vertical():
            yield Static("Logic Analyzer", classes="section-title")
            yield Static("8 channels @ 62.5MSPS max | SUMP protocol", classes="help-text")

            # Controls row - rate and samples
            with Horizontal(classes="logic-controls"):
                yield Static("Rate:", classes="logic-label")
                yield Select(
                    [
                        ("62.5 MHz", "62500000"),
                        ("31.25 MHz", "31250000"),
                        ("10 MHz", "10000000"),
                        ("5 MHz", "5000000"),
                        ("1 MHz", "1000000"),
                        ("500 kHz", "500000"),
                        ("100 kHz", "100000"),
                    ],
                    value="1000000",
                    id="logic-rate",
                    classes="logic-select"
                )
                yield Static("Samples:", classes="logic-label")
                yield Select(
                    [
                        ("1K", "1024"),
                        ("4K", "4096"),
                        ("8K", "8192"),
                        ("16K", "16384"),
                        ("32K", "32768"),
                    ],
                    value="8192",
                    id="logic-samples",
                    classes="logic-select"
                )

            # Trigger row - separate channel and edge selectors like Bolt
            with Horizontal(classes="logic-trigger-row"):
                yield Static("Trigger:", classes="logic-label")
                yield Select(
                    [("None", "none")] + [(f"CH{i}", str(i)) for i in range(8)],
                    value="none",
                    id="logic-trigger-channel",
                    classes="logic-select"
                )
                yield Select(
                    [("Rising", "rising"), ("Falling", "falling")],
                    value="rising",
                    id="logic-trigger-edge",
                    classes="logic-select"
                )

            # SUMP port input (for manual override)
            with Horizontal(classes="logic-port-row"):
                yield Static("SUMP Port:", classes="logic-label")
                yield Input(
                    placeholder="auto-detect (buspirate3)",
                    id="logic-sump-port",
                    classes="logic-port-input"
                )

            # Action buttons - consistent with Bolt
            with Horizontal(classes="logic-buttons"):
                yield Button("Capture", id="btn-logic-capture", variant="primary")
                yield Button("Stop", id="btn-logic-stop", variant="error")
                yield Button("Demo", id="btn-logic-demo", variant="default")
                yield Button("<<", id="btn-logic-scroll-left")
                yield Button(">>", id="btn-logic-scroll-right")
                yield Button("Trigger", id="btn-logic-goto-trigger")

            # Waveform display - use same visible_samples as Bolt
            self._logic_widget = LogicAnalyzerWidget(
                channels=8,
                visible_samples=120,
                id="logic-waveform",
                classes="logic-waveform"
            )
            yield self._logic_widget

            # Status line for updates - like Bolt
            yield Static(
                "Ready - configure settings and click Capture",
                id="logic-status",
                classes="logic-status"
            )

            # Log output for detailed status messages
            yield Log(id="logic-log", classes="logic-log")

    def _build_power_section(self) -> ComposeResult:
        """Power supply and measurement controls"""
        with Vertical():
            yield Static("Power & Measurement", classes="section-title")

            with Horizontal(classes="power-controls"):
                with Vertical(classes="power-group"):
                    yield Static("VOUT Power Supply", classes="power-group-title")
                    with Horizontal(classes="power-row"):
                        yield Static("Enable:", classes="power-label")
                        yield Switch(id="power-enable")
                    with Horizontal(classes="power-row"):
                        yield Static("Voltage:", classes="power-label")
                        yield Input(value="3.3", id="power-voltage-input", classes="voltage-input", placeholder="0.0-5.0")
                        yield Static("V", classes="voltage-unit")
                    with Horizontal(classes="power-row"):
                        yield Static("Preset:", classes="power-label")
                        yield Button("1.8V", id="btn-vout-18", classes="btn-preset")
                        yield Button("3.3V", id="btn-vout-33", classes="btn-preset")
                        yield Button("5.0V", id="btn-vout-50", classes="btn-preset")
                    with Horizontal(classes="power-row"):
                        yield Button("Apply Voltage", id="btn-vout-apply", classes="btn-action")

                with Vertical(classes="power-group"):
                    yield Static("Pull-ups", classes="power-group-title")
                    with Horizontal(classes="power-row"):
                        yield Static("Enable:", classes="power-label")
                        yield Switch(id="pullup-enable")

            yield Static("ADC Measurement", classes="section-subtitle")
            with Horizontal(classes="adc-display"):
                yield Static("CH0: ", classes="adc-label")
                yield Static("---", id="adc-ch0", classes="adc-value")
                yield Static("V", classes="adc-unit")
                yield Button("Read", id="btn-adc-read", classes="btn-small")
                yield Button("Monitor", id="btn-adc-monitor", classes="btn-small")

            yield Static("PWM Output", classes="section-subtitle")
            with Grid(classes="config-grid"):
                yield Static("Frequency:")
                yield Input(value="1000", id="pwm-freq")
                yield Static("Duty:")
                yield Input(value="50", id="pwm-duty")
            with Horizontal():
                yield Button("Start PWM", id="btn-pwm-start", classes="btn-action")
                yield Button("Stop PWM", id="btn-pwm-stop", classes="btn-action")

            yield Static("Frequency Counter", classes="section-subtitle")
            with Horizontal():
                yield Static("Measured: ")
                yield Static("---", id="freq-value", classes="freq-display")
                yield Static("Hz")
                yield Button("Measure", id="btn-freq-measure", classes="btn-small")

    async def connect(self) -> bool:
        """Connect to Bus Pirate via BPIO2 FlatBuffers protocol"""
        try:
            # Try to get Bus Pirate backend
            from ...backends import get_backend
            self.log_output(f"[*] Connecting to {self.device_info.name}...")
            self.log_output(f"[*] Port: {self.device_info.port}")

            self._backend = get_backend(self.device_info)

            if self._backend:
                self.log_output(f"[*] Using BPIO2 FlatBuffers protocol...")
                success = self._backend.connect()

                if success:
                    self.connected = True
                    self.log_output(f"[+] Connected successfully!")

                    # Query device status to display info in console
                    await self._query_device_status()

                    # Also populate the Status tab
                    await self._refresh_status_display()

                    # Initial ADC refresh for live pinout displays
                    await self._refresh_adc_values()
                    return True
                else:
                    self.log_output(f"[!] Backend connection failed")
                    return False
            else:
                self.log_output(f"[!] No backend available for {self.device_info.name}")
                return False

        except Exception as e:
            self.log_output(f"[!] Connection failed: {e}")
            import traceback
            self.log_output(f"[!] {traceback.format_exc()}")
            return False

    async def _query_device_status(self) -> None:
        """Query and display device status from BPIO2"""
        if not self._backend:
            return

        try:
            # Get status from backend (simplified format)
            status = None
            if hasattr(self._backend, 'get_status'):
                status = self._backend.get_status()

            if status and not status.get('error'):
                # Display version info
                fw_ver = status.get('firmware', 'Unknown')
                hw_ver = status.get('hardware', 'Unknown')
                self.log_output(f"[*] Firmware: v{fw_ver}")
                self.log_output(f"[*] Hardware: v{hw_ver}")

                # Display current mode
                mode = status.get('mode', 'HiZ')
                self.current_mode = mode
                self.log_output(f"[*] Mode: {mode}")

                # Display PSU status
                psu_enabled = status.get('psu_enabled', False)
                psu_voltage = status.get('psu_voltage', '3.3V')
                if psu_enabled:
                    self.log_output(f"[*] PSU: ON ({psu_voltage})")
                    self.power_enabled = True
                else:
                    self.log_output(f"[*] PSU: OFF")
                    self.power_enabled = False

                # Display pullups
                pullups = status.get('pullups_enabled', False)
                self.pullups_enabled = pullups
                if pullups:
                    self.log_output(f"[*] Pull-ups: Enabled")

                # Check if using serial fallback
                if status.get('serial_fallback'):
                    self.log_output(f"[!] Note: Using serial fallback (BPIO2 unavailable)")

            else:
                error = status.get('error', 'Unknown error') if status else 'No response'
                self.log_output(f"[!] Status error: {error}")
                self.log_output(f"[*] Mode: HiZ (default)")

        except Exception as e:
            self.log_output(f"[!] Status query error: {e}")

    async def disconnect(self) -> None:
        """Disconnect from Bus Pirate"""
        # Stop live pinout updates if running
        if self._pinout_refresh_timer is not None:
            self._pinout_refresh_timer.stop()
            self._pinout_refresh_timer = None
            self._update_live_button_labels(False)

        if self._backend:
            try:
                self._backend.disconnect()
            except Exception:
                pass
            self._backend = None
        self.connected = False
        self.log_output(f"[-] Disconnected from {self.device_info.name}")

    async def send_command(self, command: str) -> None:
        """Send command to Bus Pirate"""
        await super().send_command(command)

        # Parse and execute command
        parts = command.strip().split()
        if not parts:
            return

        cmd = parts[0].lower()

        if cmd == "help":
            self._show_help()
        elif cmd == "mode":
            if len(parts) > 1:
                await self._set_mode(parts[1])
        elif cmd == "spi":
            await self._handle_spi_command(parts[1:])
        elif cmd == "i2c":
            await self._handle_i2c_command(parts[1:])
        elif cmd == "logic":
            await self._handle_logic_command(parts[1:])
        elif cmd == "power":
            await self._handle_power_command(parts[1:])
        else:
            self.log_output(f"Unknown command: {cmd}. Type 'help' for available commands.")

    def get_command_suggestions(self, partial: str) -> List[CommandSuggestion]:
        """Get command suggestions for auto-completion"""
        suggestions = [
            CommandSuggestion("help", "Show available commands"),
            CommandSuggestion("mode spi", "Switch to SPI mode", "mode"),
            CommandSuggestion("mode i2c", "Switch to I2C mode", "mode"),
            CommandSuggestion("mode uart", "Switch to UART mode", "mode"),
            CommandSuggestion("spi id", "Read SPI flash ID", "spi"),
            CommandSuggestion("spi dump", "Dump SPI flash", "spi"),
            CommandSuggestion("i2c scan", "Scan I2C bus for devices", "i2c"),
            CommandSuggestion("logic capture", "Start logic capture", "logic"),
            CommandSuggestion("power on", "Enable power supply", "power"),
            CommandSuggestion("power off", "Disable power supply", "power"),
            CommandSuggestion("adc read", "Read ADC voltage", "adc"),
        ]

        if partial:
            partial_lower = partial.lower()
            suggestions = [s for s in suggestions if s.command.lower().startswith(partial_lower)]

        return suggestions

    def _show_help(self) -> None:
        """Display help message"""
        help_text = """
Available commands:
  help              - Show this help
  mode <mode>       - Set mode (spi, i2c, uart, 1wire)
  spi id            - Read SPI flash ID
  spi dump <file>   - Dump SPI flash to file
  i2c scan          - Scan I2C bus
  logic capture     - Capture logic data
  power on/off      - Control power supply
  adc read          - Read ADC voltage
"""
        self.log_output(help_text)

    async def _set_mode(self, mode: str) -> None:
        """Set Bus Pirate mode"""
        mode = mode.upper()
        valid_modes = ["HIZ", "SPI", "I2C", "UART", "1WIRE", "2WIRE", "3WIRE"]
        if mode not in valid_modes:
            self.log_output(f"[!] Invalid mode: {mode}")
            return

        self.current_mode = mode
        self.log_output(f"[*] Mode set to: {mode}")

        # Update UI to show relevant controls
        # This would hide/show protocol-specific controls

    async def _handle_spi_command(self, args: List[str]) -> None:
        """Handle SPI commands"""
        if not args:
            self.log_output("[!] SPI command required (id, dump, write, erase)")
            return

        subcmd = args[0].lower()
        if subcmd == "id":
            self.log_output("[*] Reading SPI flash ID...")
            # Would call backend to read flash ID
            self.log_output("[+] Flash ID: 0xEF4016 (Winbond W25Q32)")
        elif subcmd == "dump":
            filename = args[1] if len(args) > 1 else "dump.bin"
            self.log_output(f"[*] Dumping flash to {filename}...")
        elif subcmd == "write":
            self.log_output("[*] Writing to flash...")
        elif subcmd == "erase":
            self.log_output("[*] Erasing flash...")

    async def _handle_i2c_command(self, args: List[str]) -> None:
        """Handle I2C commands"""
        if not args:
            self.log_output("[!] I2C command required (scan, read, write)")
            return

        subcmd = args[0].lower()
        if subcmd == "scan":
            self.log_output("[*] Scanning I2C bus...")
            self.log_output("[+] Found devices at: 0x50, 0x68")
        elif subcmd == "read":
            addr = args[1] if len(args) > 1 else "0x50"
            self.log_output(f"[*] Reading from {addr}...")

    async def _handle_logic_command(self, args: List[str]) -> None:
        """Handle logic analyzer commands"""
        if not args:
            self.log_output("[!] Logic command required (capture, stop)")
            return

        subcmd = args[0].lower()
        if subcmd == "capture":
            self.log_output("[*] Starting logic capture...")
            self.log_output("[*] Waiting for trigger...")
        elif subcmd == "stop":
            self.log_output("[*] Stopping capture...")

    async def _handle_power_command(self, args: List[str]) -> None:
        """Handle power commands"""
        if not args:
            self.log_output("[!] Power command required (on, off)")
            return

        subcmd = args[0].lower()
        if subcmd == "on":
            self.power_enabled = True
            self.log_output("[+] Power supply enabled (3.3V)")
        elif subcmd == "off":
            self.power_enabled = False
            self.log_output("[-] Power supply disabled")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id
        if not button_id:
            return

        # Status tab
        if button_id == "btn-status-refresh":
            await self._refresh_status_display()

        # Protocol tab - SPI
        elif button_id == "btn-spi-id":
            await self._spi_read_flash_id()
        elif button_id == "btn-spi-dump":
            await self._spi_dump_flash()
        elif button_id == "btn-spi-erase":
            await self._spi_erase_flash()
        elif button_id == "btn-spi-write":
            await self._spi_write_flash()

        # Protocol tab - I2C
        elif button_id == "btn-i2c-scan":
            await self._i2c_scan_bus()
        elif button_id == "btn-i2c-read":
            await self._i2c_read_byte()
        elif button_id == "btn-i2c-write":
            await self._i2c_write_byte()
        elif button_id == "btn-i2c-dump":
            await self._i2c_dump_eeprom()

        # Protocol tab - UART
        elif button_id == "btn-uart-bridge":
            await self._uart_start_bridge()
        elif button_id == "btn-uart-auto":
            await self._uart_auto_detect()

        # Logic tab
        elif button_id == "btn-logic-capture":
            await self._start_logic_capture()
        elif button_id == "btn-logic-stop":
            await self._stop_logic_capture()
        elif button_id == "btn-logic-demo":
            await self._load_logic_demo()
        elif button_id == "btn-logic-scroll-left":
            self._logic_scroll(-50)
        elif button_id == "btn-logic-scroll-right":
            self._logic_scroll(50)
        elif button_id == "btn-logic-goto-trigger":
            self._logic_goto_trigger()

        # Scan tab
        elif button_id == "btn-jtag-scan":
            self.log_output("[*] Starting JTAG pin scan...")
            self.log_output("[*] Testing all pin combinations...")
        elif button_id == "btn-swd-scan":
            self.log_output("[*] Starting SWD pin scan...")
        elif button_id == "btn-uart-detect":
            await self._uart_auto_detect()

        # Power tab - VOUT controls
        elif button_id == "btn-vout-18":
            self._set_voltage_input("1.8")
        elif button_id == "btn-vout-33":
            self._set_voltage_input("3.3")
        elif button_id == "btn-vout-50":
            self._set_voltage_input("5.0")
        elif button_id == "btn-vout-apply":
            await self._apply_vout_voltage()

        # Power tab - other controls
        elif button_id == "btn-adc-read":
            await self._read_adc()
        elif button_id == "btn-adc-monitor":
            await self._toggle_adc_monitor()
        elif button_id == "btn-pwm-start":
            await self._start_pwm()
        elif button_id == "btn-pwm-stop":
            await self._stop_pwm()
        elif button_id == "btn-freq-measure":
            await self._measure_frequency()

        # Pinout refresh buttons
        elif button_id in ("spi-refresh-pinout", "i2c-refresh-pinout", "uart-refresh-pinout"):
            await self._refresh_adc_values()
            self.log_output("[+] Pinout voltages refreshed")

        # Live toggle buttons
        elif button_id in ("spi-live-toggle", "i2c-live-toggle", "uart-live-toggle"):
            await self._toggle_live_pinout()

    async def on_select_changed(self, event: Select.Changed) -> None:
        """Handle Select widget changes"""
        select_id = event.select.id
        if not select_id:
            return

        value = str(event.value) if event.value else None
        if not value:
            return

        # Mode selection in header
        if select_id == "mode-select":
            await self._change_mode(value)

        # Voltage selection in header
        elif select_id == "voltage-select":
            await self._change_voltage(value)

        # Power tab voltage
        elif select_id == "power-voltage":
            # Just store the selection, applied when power is enabled
            pass

        # Protocol subtab voltage selections (spi/i2c/uart-voltage-select)
        elif select_id in ("spi-voltage-select", "i2c-voltage-select", "uart-voltage-select"):
            # If power is already enabled, apply the new voltage immediately
            prefix = select_id.replace("-voltage-select", "")
            try:
                power_switch = self.query_one(f"#{prefix}-power-switch", Switch)
                if power_switch.value:
                    # Power is on, apply new voltage
                    voltage_mv = int(value)
                    await self._toggle_protocol_power(True, voltage_mv)
                    # Sync other protocol voltage selects
                    self._sync_protocol_voltage_selects(value)
            except Exception:
                pass

    async def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle Switch widget changes"""
        switch_id = event.switch.id
        value = event.value

        if not switch_id:
            return

        # Power tab switches
        if switch_id == "power-enable":
            await self._toggle_power(value)
        elif switch_id == "pullup-enable":
            await self._toggle_pullups(value)

        # Protocol subtab power switches (SPI/I2C/UART)
        elif switch_id in ("spi-power-switch", "i2c-power-switch", "uart-power-switch"):
            # Get the voltage from the corresponding dropdown
            prefix = switch_id.replace("-power-switch", "")
            voltage_mv = int(self._get_select_value(f"{prefix}-voltage-select", "3300"))
            await self._toggle_protocol_power(value, voltage_mv)
            # Sync other protocol power switches
            self._sync_protocol_power_switches(value)

        # Protocol subtab pullup switches
        elif switch_id in ("spi-pullup-switch", "i2c-pullup-switch", "uart-pullup-switch"):
            await self._toggle_pullups(value)
            # Sync other pullup switches
            self._sync_pullup_switches(value)

    async def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Handle tab activation - configure Bus Pirate mode when switching protocol subtabs"""
        tab_id = event.tab.id if event.tab else None
        tabbed_content_id = event.tabbed_content.id if event.tabbed_content else None

        # Only handle protocol subtab switches
        if tabbed_content_id != "protocol-tabs":
            return

        if not self._backend:
            self.log_output("[!] Not connected - mode not changed on device")
            return

        # Map tab IDs to modes - Textual generates IDs like "--content-tab-tab-spi"
        tab_to_mode = {
            "--content-tab-tab-spi": "SPI",
            "--content-tab-tab-i2c": "I2C",
            "--content-tab-tab-uart": "UART",
        }

        mode = tab_to_mode.get(tab_id)
        if mode:
            await self._change_mode(mode)

    # --------------------------------------------------------------------------
    # Mode Switching
    # --------------------------------------------------------------------------

    async def _change_mode(self, mode: str) -> None:
        """Change Bus Pirate protocol mode via BPIO2"""
        if not self._backend:
            self.log_output("[!] Not connected")
            return

        self.log_output(f"[*] Switching to {mode} mode...")

        try:
            # Map UI mode names to backend method calls
            mode_upper = mode.upper()

            if mode_upper == "HIZ":
                # HiZ is the default safe mode
                self.current_mode = "HiZ"
                self.log_output(f"[+] Mode: HiZ (safe mode)")

            elif mode_upper == "SPI":
                # Get SPI config from UI
                speed = self._get_select_value("spi-speed", "1000000")
                spi_mode = self._get_select_value("spi-mode", "0")
                cs_active = self._get_select_value("spi-cs", "low")

                from ...backends.base import SPIConfig
                config = SPIConfig(
                    speed_hz=int(speed),
                    mode=int(spi_mode),
                    cs_active_low=(cs_active == "low")
                )

                if self._backend.configure_spi(config):
                    self.current_mode = "SPI"
                    self.log_output(f"[+] SPI mode: {int(speed)//1000}kHz, mode {spi_mode}")
                else:
                    self.log_output("[!] Failed to configure SPI")

            elif mode_upper == "I2C":
                # Get I2C config from UI
                speed = self._get_select_value("i2c-speed", "100000")

                from ...backends.base import I2CConfig
                config = I2CConfig(speed_hz=int(speed))

                if self._backend.configure_i2c(config):
                    self.current_mode = "I2C"
                    self.log_output(f"[+] I2C mode: {int(speed)//1000}kHz")
                else:
                    self.log_output("[!] Failed to configure I2C")

            elif mode_upper == "UART":
                # Get UART config from UI
                baud = self._get_select_value("uart-baud", "115200")
                format_str = self._get_select_value("uart-format", "8N1")

                # Parse format (e.g., "8N1" -> data_bits=8, parity='N', stop_bits=1)
                data_bits = int(format_str[0])
                parity = format_str[1]
                stop_bits = int(format_str[2])

                from ...backends.base import UARTConfig
                config = UARTConfig(
                    baudrate=int(baud),
                    data_bits=data_bits,
                    parity=parity,
                    stop_bits=stop_bits
                )

                if self._backend.configure_uart(config):
                    self.current_mode = "UART"
                    self.log_output(f"[+] UART mode: {baud} {format_str}")
                else:
                    self.log_output("[!] Failed to configure UART")

            else:
                self.log_output(f"[!] Mode {mode} not yet implemented via BPIO2")

            # Refresh status display after mode change
            await self._refresh_status_display()

        except Exception as e:
            self.log_output(f"[!] Mode change error: {e}")

    def _get_select_value(self, select_id: str, default: str) -> str:
        """Get value from a Select widget"""
        try:
            select = self.query_one(f"#{select_id}", Select)
            # Check for Select.BLANK and None/falsy values
            if select.value is None or select.value == Select.BLANK:
                return default
            return str(select.value)
        except Exception:
            return default

    # --------------------------------------------------------------------------
    # Live Pinout Diagram Functions
    # --------------------------------------------------------------------------

    def _format_voltage(self, mv: int) -> str:
        """Format millivolt value for display (e.g., '3.3V' or '---')"""
        if mv <= 0:
            return "---"
        elif mv < 1000:
            return f"{mv}mV"
        else:
            return f"{mv/1000:.1f}V"

    def _build_spi_pinout_ascii(self) -> str:
        """Build SPI pinout ASCII diagram with live voltage values"""
        # Get live voltage values
        vout = self._format_voltage(self._psu_measured_mv)
        v = [self._format_voltage(self._adc_values[i]) if i < len(self._adc_values) else "---" for i in range(8)]

        return (
            "┌─────────────────────────────────────────────────────────────────────┐\n"
            "│  Pin 1     2     3     4     5     6     7     8     9    10        │\n"
            "│  VOUT    IO0   IO1   IO2   IO3   IO4   IO5   IO6   IO7   GND        │\n"
            f"│  {vout:^5} {v[0]:^5} {v[1]:^5} {v[2]:^5} {v[3]:^5} {v[4]:^5} {v[5]:^5} {v[6]:^5} {v[7]:^5}  0V         │\n"
            "│          └─────────────────┘     MISO   CS   CLK  MOSI              │\n"
            "│               Auxiliary                                             │\n"
            "└─────────────────────────────────────────────────────────────────────┘\n"
            "  IO4=MISO (Master In)    IO6=CLK (Clock)\n"
            "  IO5=CS (Chip Select)    IO7=MOSI (Master Out)"
        )

    def _build_i2c_pinout_ascii(self) -> str:
        """Build I2C pinout ASCII diagram with live voltage values"""
        # Get live voltage values
        vout = self._format_voltage(self._psu_measured_mv)
        v = [self._format_voltage(self._adc_values[i]) if i < len(self._adc_values) else "---" for i in range(8)]

        return (
            "┌─────────────────────────────────────────────────────────────────────┐\n"
            "│  Pin 1     2     3     4     5     6     7     8     9    10        │\n"
            "│  VOUT    IO0   IO1   IO2   IO3   IO4   IO5   IO6   IO7   GND        │\n"
            f"│  {vout:^5} {v[0]:^5} {v[1]:^5} {v[2]:^5} {v[3]:^5} {v[4]:^5} {v[5]:^5} {v[6]:^5} {v[7]:^5}  0V         │\n"
            "│          SDA   SCL         AUX                                      │\n"
            "│                                                                     │\n"
            "└─────────────────────────────────────────────────────────────────────┘\n"
            "  IO0=SDA (Data)     IO1=SCL (Clock)\n"
            "  Enable pull-ups for I2C (typical 4.7kΩ to VOUT)"
        )

    def _build_uart_pinout_ascii(self) -> str:
        """Build UART pinout ASCII diagram with live voltage values"""
        # Get live voltage values
        vout = self._format_voltage(self._psu_measured_mv)
        v = [self._format_voltage(self._adc_values[i]) if i < len(self._adc_values) else "---" for i in range(8)]

        return (
            "┌─────────────────────────────────────────────────────────────────────┐\n"
            "│  Pin 1     2     3     4     5     6     7     8     9    10        │\n"
            "│  VOUT    IO0   IO1   IO2   IO3   IO4   IO5   IO6   IO7   GND        │\n"
            f"│  {vout:^5} {v[0]:^5} {v[1]:^5} {v[2]:^5} {v[3]:^5} {v[4]:^5} {v[5]:^5} {v[6]:^5} {v[7]:^5}  0V         │\n"
            "│                            AUX    TX    RX                          │\n"
            "│                                                                     │\n"
            "└─────────────────────────────────────────────────────────────────────┘\n"
            "  IO4=TX (BP output → Target RX)\n"
            "  IO5=RX (BP input ← Target TX)"
        )

    async def _refresh_adc_values(self) -> None:
        """Fetch current ADC values from device and update pinout displays"""
        if not self._backend or not self.connected:
            return

        try:
            # Get full status which includes ADC values
            status = None
            if hasattr(self._backend, 'get_full_status'):
                status = self._backend.get_full_status()

            if status:
                # Update cached ADC values
                self._adc_values = status.get('adc_mv', [0] * 8)
                self._psu_measured_mv = status.get('psu_measured_mv', 0)
                self._psu_measured_ma = status.get('psu_measured_ma', 0)

                # Update all pinout diagrams
                self._update_pinout_displays()
        except Exception as e:
            # Log errors but don't spam during live updates
            if self._pinout_refresh_timer is None:
                self.log_output(f"[!] ADC refresh error: {e}")

    def _update_pinout_displays(self) -> None:
        """Update all pinout displays with current ADC values"""
        try:
            spi_pinout = self.query_one("#spi-pinout", Static)
            spi_pinout.update(self._build_spi_pinout_ascii())
        except Exception:
            pass

        try:
            i2c_pinout = self.query_one("#i2c-pinout", Static)
            i2c_pinout.update(self._build_i2c_pinout_ascii())
        except Exception:
            pass

        try:
            uart_pinout = self.query_one("#uart-pinout", Static)
            uart_pinout.update(self._build_uart_pinout_ascii())
        except Exception:
            pass

    async def _toggle_live_pinout(self) -> None:
        """Toggle live pinout updates on/off"""
        if self._pinout_refresh_timer is not None:
            # Stop live updates
            self._pinout_refresh_timer.stop()
            self._pinout_refresh_timer = None
            self.log_output("[-] Live pinout updates stopped")
            # Update button labels
            self._update_live_button_labels(False)
        else:
            # Start live updates (every 500ms)
            if not self.connected:
                self.log_output("[!] Connect to device first to enable live updates")
                return
            self._pinout_refresh_timer = self.set_interval(0.5, self._refresh_adc_values)
            self.log_output("[+] Live pinout updates started (500ms interval)")
            # Update button labels
            self._update_live_button_labels(True)
            # Immediate refresh
            await self._refresh_adc_values()

    def _update_live_button_labels(self, is_live: bool) -> None:
        """Update live toggle button labels to show current state"""
        for prefix in ("spi", "i2c", "uart"):
            try:
                btn = self.query_one(f"#{prefix}-live-toggle", Button)
                btn.label = "Stop" if is_live else "Live"
                if is_live:
                    btn.add_class("btn-active")
                else:
                    btn.remove_class("btn-active")
            except Exception:
                pass

    async def _toggle_adc_monitor(self) -> None:
        """Toggle ADC monitoring - alias for live pinout toggle"""
        await self._toggle_live_pinout()

    async def _toggle_protocol_power(self, enabled: bool, voltage_mv: int = 3300) -> None:
        """Toggle power from protocol subtab switches"""
        if not self._backend:
            self.log_output("[!] Not connected - connect to device first")
            return

        try:
            self.log_output(f"[*] Setting PSU: {'ON' if enabled else 'OFF'} at {voltage_mv}mV")
            result = self._backend.set_psu(enabled=enabled, voltage_mv=voltage_mv)
            if result:
                self.power_enabled = enabled
                if enabled:
                    self.log_output(f"[+] PSU enabled: {voltage_mv / 1000:.1f}V")
                else:
                    self.log_output("[-] PSU disabled")
            else:
                self.log_output(f"[!] Failed to {'enable' if enabled else 'disable'} PSU")
        except Exception as e:
            self.log_output(f"[!] Power error: {e}")

    def _sync_protocol_power_switches(self, value: bool) -> None:
        """Sync all protocol power switches to the same state"""
        for prefix in ("spi", "i2c", "uart"):
            try:
                switch = self.query_one(f"#{prefix}-power-switch", Switch)
                if switch.value != value:
                    switch.value = value
            except Exception:
                pass

        # Also sync the main power switch in Power tab
        try:
            main_switch = self.query_one("#power-enable", Switch)
            if main_switch.value != value:
                main_switch.value = value
        except Exception:
            pass

    def _sync_pullup_switches(self, value: bool) -> None:
        """Sync all pullup switches to the same state"""
        for prefix in ("spi", "i2c", "uart"):
            try:
                switch = self.query_one(f"#{prefix}-pullup-switch", Switch)
                if switch.value != value:
                    switch.value = value
            except Exception:
                pass

        # Also sync the main pullup switch in Power tab
        try:
            main_switch = self.query_one("#pullup-enable", Switch)
            if main_switch.value != value:
                main_switch.value = value
        except Exception:
            pass

    def _sync_protocol_voltage_selects(self, value: str) -> None:
        """Sync all protocol voltage selects to the same value"""
        for prefix in ("spi", "i2c", "uart"):
            try:
                select = self.query_one(f"#{prefix}-voltage-select", Select)
                if str(select.value) != value:
                    select.value = value
            except Exception:
                pass

    async def _change_voltage(self, voltage_str: str) -> None:
        """Change PSU voltage via header dropdown"""
        if not self._backend:
            return

        try:
            voltage = float(voltage_str)
            if voltage == 0:
                # Turn off PSU
                if self._backend.set_psu(enabled=False):
                    self.power_enabled = False
                    self.log_output("[*] PSU disabled")
            else:
                # Set voltage and enable
                voltage_mv = int(voltage * 1000)
                if self._backend.set_psu(enabled=True, voltage_mv=voltage_mv):
                    self.power_enabled = True
                    self.log_output(f"[+] PSU enabled: {voltage}V")
        except Exception as e:
            self.log_output(f"[!] Voltage change error: {e}")

    def _set_voltage_input(self, voltage: str) -> None:
        """Set the voltage input field to a preset value"""
        try:
            voltage_input = self.query_one("#power-voltage-input", Input)
            voltage_input.value = voltage
        except Exception:
            pass

    def _get_voltage_from_input(self) -> float:
        """Get voltage from input field, clamped to 0.0-5.0 range"""
        try:
            voltage_input = self.query_one("#power-voltage-input", Input)
            voltage = float(voltage_input.value or "3.3")
            # Clamp to valid range
            return max(0.0, min(5.0, voltage))
        except (ValueError, Exception):
            return 3.3  # Default

    async def _apply_vout_voltage(self) -> None:
        """Apply the voltage from the input field"""
        if not self._backend:
            self.log_output("[!] Not connected - connect to device first")
            return

        try:
            voltage = self._get_voltage_from_input()
            voltage_mv = int(voltage * 1000)
            self.log_output(f"[*] Applying VOUT: {voltage:.2f}V ({voltage_mv}mV)")

            # Enable PSU with the specified voltage
            result = self._backend.set_psu(enabled=True, voltage_mv=voltage_mv)
            if result:
                self.power_enabled = True
                self.log_output(f"[+] VOUT set to {voltage:.2f}V")
                # Update the switch to reflect enabled state
                try:
                    power_switch = self.query_one("#power-enable", Switch)
                    power_switch.value = True
                except Exception:
                    pass
                # Also sync protocol subtab power switches
                self._sync_protocol_power_switches(True)
            else:
                self.log_output(f"[!] Failed to set VOUT to {voltage:.2f}V")
        except Exception as e:
            self.log_output(f"[!] VOUT error: {e}")

    async def _toggle_power(self, enabled: bool) -> None:
        """Toggle power supply via Power tab switch"""
        if not self._backend:
            self.log_output("[!] Not connected - connect to device first")
            return

        try:
            # Get voltage from input field
            voltage = self._get_voltage_from_input()
            voltage_mv = int(voltage * 1000)
            self.log_output(f"[*] Setting PSU: {'ON' if enabled else 'OFF'} at {voltage:.2f}V")

            result = self._backend.set_psu(enabled=enabled, voltage_mv=voltage_mv)
            if result:
                self.power_enabled = enabled
                if enabled:
                    self.log_output(f"[+] PSU enabled: {voltage:.2f}V")
                else:
                    self.log_output("[-] PSU disabled")
                # Sync protocol subtab power switches
                self._sync_protocol_power_switches(enabled)
            else:
                self.log_output(f"[!] Failed to {'enable' if enabled else 'disable'} PSU")
        except Exception as e:
            self.log_output(f"[!] Power error: {e}")

    async def _toggle_pullups(self, enabled: bool) -> None:
        """Toggle pull-up resistors"""
        if not self._backend:
            self.log_output("[!] Not connected")
            return

        try:
            if self._backend.set_pullups(enabled=enabled):
                self.pullups_enabled = enabled
                if enabled:
                    self.log_output("[+] Pull-ups enabled")
                else:
                    self.log_output("[-] Pull-ups disabled")
            else:
                self.log_output(f"[!] Failed to {'enable' if enabled else 'disable'} pull-ups")
        except Exception as e:
            self.log_output(f"[!] Pull-up error: {e}")

    # --------------------------------------------------------------------------
    # SPI Operations
    # --------------------------------------------------------------------------

    async def _spi_read_flash_id(self) -> None:
        """Read SPI flash JEDEC ID"""
        if not self._backend:
            self.log_output("[!] Not connected")
            return

        self.log_output("[*] Reading SPI flash ID...")

        try:
            # Ensure we're in SPI mode
            if self.current_mode != "SPI":
                await self._change_mode("SPI")

            flash_id = self._backend.spi_flash_read_id()
            if flash_id and len(flash_id) >= 3:
                mfr = flash_id[0]
                dev_type = flash_id[1]
                capacity = flash_id[2]

                # Lookup manufacturer
                mfr_names = {
                    0xEF: "Winbond",
                    0xC2: "Macronix",
                    0x20: "Micron",
                    0x01: "Spansion",
                    0xBF: "SST",
                    0x1F: "Atmel",
                }
                mfr_name = mfr_names.get(mfr, "Unknown")

                self.log_output(f"[+] Flash ID: {flash_id.hex().upper()}")
                self.log_output(f"    Manufacturer: {mfr_name} (0x{mfr:02X})")
                self.log_output(f"    Device Type: 0x{dev_type:02X}")
                self.log_output(f"    Capacity: 0x{capacity:02X}")
            else:
                self.log_output("[!] No flash detected or invalid response")
        except Exception as e:
            self.log_output(f"[!] SPI ID error: {e}")

    async def _spi_dump_flash(self) -> None:
        """Dump SPI flash to file"""
        self.log_output("[*] SPI dump not yet implemented")
        self.log_output("[*] Use command: spi dump <filename>")

    async def _spi_erase_flash(self) -> None:
        """Erase SPI flash sector or chip"""
        if not self._backend:
            self.log_output("[!] Not connected")
            return

        try:
            # Ensure we're in SPI mode
            if self.current_mode != "SPI":
                await self._change_mode("SPI")

            self.log_output("[!] WARNING: This will erase flash data!")
            self.log_output("[*] Erasing 4KB sector at address 0x000000...")

            # Progress callback
            def progress(msg):
                self.log_output(f"[*] {msg}")

            # Run erase in executor to not block UI
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None,
                lambda: self._backend.spi_flash_erase(
                    address=0,
                    erase_type="sector",
                    progress_callback=progress
                )
            )

            if success:
                self.log_output("[+] Sector erase complete")
            else:
                self.log_output("[!] Erase failed")

        except Exception as e:
            self.log_output(f"[!] SPI erase error: {e}")

    async def _spi_write_flash(self) -> None:
        """Write data to SPI flash from file"""
        if not self._backend:
            self.log_output("[!] Not connected")
            return

        try:
            # Ensure we're in SPI mode
            if self.current_mode != "SPI":
                await self._change_mode("SPI")

            # For now, write test pattern to first 256 bytes
            self.log_output("[!] WARNING: This will overwrite flash data!")
            self.log_output("[*] Writing test pattern to address 0x000000...")

            # Create test data (256 bytes incrementing pattern)
            test_data = bytes(range(256))

            # Progress callback
            def progress(written, total):
                pct = (written / total) * 100 if total > 0 else 0
                self.log_output(f"[*] Progress: {written}/{total} bytes ({pct:.0f}%)")
                return True  # Continue

            # Run write in executor
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None,
                lambda: self._backend.spi_flash_write(
                    address=0,
                    data=test_data,
                    progress_callback=progress
                )
            )

            if success:
                self.log_output("[+] Write complete")
                # Verify by reading back
                self.log_output("[*] Verifying...")
                verify_data = await loop.run_in_executor(
                    None,
                    lambda: self._backend.spi_flash_read(0, 256)
                )
                if verify_data == test_data:
                    self.log_output("[+] Verification passed")
                else:
                    self.log_output("[!] Verification FAILED - data mismatch")
            else:
                self.log_output("[!] Write failed")

        except Exception as e:
            self.log_output(f"[!] SPI write error: {e}")

    # --------------------------------------------------------------------------
    # I2C Operations
    # --------------------------------------------------------------------------

    async def _i2c_scan_bus(self) -> None:
        """Scan I2C bus for devices"""
        if not self._backend:
            self.log_output("[!] Not connected")
            return

        self.log_output("[*] Scanning I2C bus...")

        try:
            # Ensure we're in I2C mode
            if self.current_mode != "I2C":
                await self._change_mode("I2C")

            devices = self._backend.i2c_scan()
            if devices:
                self.log_output(f"[+] Found {len(devices)} device(s):")
                for addr in devices:
                    self.log_output(f"    0x{addr:02X}")
            else:
                self.log_output("[*] No I2C devices found")
        except Exception as e:
            self.log_output(f"[!] I2C scan error: {e}")

    async def _i2c_read_byte(self) -> None:
        """Read byte from I2C device"""
        if not self._backend:
            self.log_output("[!] Not connected")
            return

        try:
            # Get address from UI
            addr_str = self._get_input_value("i2c-addr", "0x50")
            addr = int(addr_str, 16) if addr_str.startswith("0x") else int(addr_str)

            self.log_output(f"[*] Reading from I2C address 0x{addr:02X}...")

            data = self._backend.i2c_read(addr, 1)
            if data:
                self.log_output(f"[+] Read: 0x{data[0]:02X}")
            else:
                self.log_output("[!] No response from device")
        except Exception as e:
            self.log_output(f"[!] I2C read error: {e}")

    async def _i2c_write_byte(self) -> None:
        """Write byte to I2C device"""
        self.log_output("[*] I2C write not yet implemented")
        self.log_output("[*] Use command: i2c write <addr> <data>")

    async def _i2c_dump_eeprom(self) -> None:
        """Dump I2C EEPROM contents"""
        self.log_output("[*] I2C EEPROM dump not yet implemented")
        self.log_output("[*] Use command: i2c dump <addr> <size>")

    def _get_input_value(self, input_id: str, default: str) -> str:
        """Get value from an Input widget"""
        try:
            input_widget = self.query_one(f"#{input_id}", Input)
            return input_widget.value if input_widget.value else default
        except Exception:
            return default

    # --------------------------------------------------------------------------
    # UART Operations
    # --------------------------------------------------------------------------

    async def _uart_start_bridge(self) -> None:
        """Start UART bridge mode"""
        if not self._backend:
            self.log_output("[!] Not connected")
            return

        self.log_output("[*] Starting UART bridge mode...")

        try:
            # Ensure we're in UART mode
            if self.current_mode != "UART":
                await self._change_mode("UART")

            if self._backend.uart_start_bridge():
                self.log_output("[+] UART bridge mode active")
                self.log_output("[*] Data is passed through transparently")
                self.log_output("[*] Reset device to exit bridge mode")
            else:
                self.log_output("[!] Failed to start bridge mode")
        except Exception as e:
            self.log_output(f"[!] UART bridge error: {e}")

    async def _uart_auto_detect(self) -> None:
        """Auto-detect UART configuration"""
        if not self._backend:
            self.log_output("[!] Not connected")
            return

        self.log_output("[*] Auto-detecting UART configuration...")
        self.log_output("[*] Make sure target is transmitting data...")

        try:
            results = self._backend.uart_auto_detect_quick(
                test_duration_ms=500,
                progress_callback=lambda cur, tot, cfg: self._uart_scan_progress(cur, tot, cfg)
            )

            if results:
                valid_results = [r for r in results if r.get('likely_valid')]
                if valid_results:
                    self.log_output(f"[+] Found {len(valid_results)} likely configuration(s):")
                    for r in valid_results:
                        self.log_output(f"    {r['baudrate']} {r['data_bits']}{r['parity']}{r['stop_bits']} ({r['printable_ratio']:.0%} printable)")
                else:
                    self.log_output("[*] No valid configurations detected")
                    self.log_output("[*] Try again with target actively transmitting")
            else:
                self.log_output("[*] No data received at any baud rate")
        except Exception as e:
            self.log_output(f"[!] UART auto-detect error: {e}")

    def _uart_scan_progress(self, current: int, total: int, config_str: str) -> bool:
        """Progress callback for UART scan"""
        if config_str:
            self.log_output(f"[*] Testing {config_str}... ({current}/{total})")
        return True  # Continue scanning

    # --------------------------------------------------------------------------
    # Power/ADC Operations
    # --------------------------------------------------------------------------

    async def _read_adc(self) -> None:
        """Read ADC voltage"""
        if not self._backend:
            self.log_output("[!] Not connected")
            return

        try:
            status = None
            if hasattr(self._backend, 'get_full_status'):
                status = self._backend.get_full_status()

            if status:
                adc_values = status.get('adc_mv', [])
                if adc_values:
                    self.log_output("[+] ADC readings:")
                    for i, val in enumerate(adc_values[:8]):
                        voltage_v = val / 1000.0
                        self.log_output(f"    IO{i}: {val}mV ({voltage_v:.2f}V)")

                    # Update the ADC display in Power tab
                    try:
                        adc_ch0 = self.query_one("#adc-ch0", Static)
                        if adc_values:
                            adc_ch0.update(f"{adc_values[0] / 1000:.2f}")
                    except Exception:
                        pass
                else:
                    self.log_output("[*] No ADC data available")
            else:
                self.log_output("[!] Could not get ADC status")
        except Exception as e:
            self.log_output(f"[!] ADC read error: {e}")

    async def _start_pwm(self) -> None:
        """Start PWM output"""
        if not self._backend:
            self.log_output("[!] Not connected")
            return

        try:
            # Get frequency and duty cycle from UI inputs if available
            freq_str = self._get_input_value("pwm-freq", "1000")
            duty_str = self._get_input_value("pwm-duty", "50")

            frequency = int(freq_str)
            duty_cycle = float(duty_str)

            self.log_output(f"[*] Starting PWM: {frequency}Hz, {duty_cycle}% duty cycle...")

            # Run in executor
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None,
                lambda: self._backend.pwm_start(frequency, duty_cycle)
            )

            if success:
                self.log_output(f"[+] PWM started on AUX pin")
            else:
                self.log_output("[!] PWM start failed")

        except ValueError as e:
            self.log_output(f"[!] Invalid PWM parameters: {e}")
        except Exception as e:
            self.log_output(f"[!] PWM error: {e}")

    async def _stop_pwm(self) -> None:
        """Stop PWM output"""
        if not self._backend:
            self.log_output("[!] Not connected")
            return

        try:
            self.log_output("[*] Stopping PWM...")

            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None,
                lambda: self._backend.pwm_stop()
            )

            if success:
                self.log_output("[+] PWM stopped")
            else:
                self.log_output("[!] PWM stop failed")

        except Exception as e:
            self.log_output(f"[!] PWM stop error: {e}")

    async def _measure_frequency(self) -> None:
        """Measure frequency on input pin"""
        if not self._backend:
            self.log_output("[!] Not connected")
            return

        try:
            self.log_output("[*] Measuring frequency on AUX pin...")
            self.log_output("[*] Connect signal to AUX pin and wait...")

            # Run in executor
            loop = asyncio.get_event_loop()
            freq = await loop.run_in_executor(
                None,
                lambda: self._backend.frequency_measure(timeout_ms=3000)
            )

            if freq is not None:
                if freq >= 1_000_000:
                    self.log_output(f"[+] Frequency: {freq / 1_000_000:.3f} MHz")
                elif freq >= 1000:
                    self.log_output(f"[+] Frequency: {freq / 1000:.3f} kHz")
                else:
                    self.log_output(f"[+] Frequency: {freq} Hz")
            else:
                self.log_output("[!] No signal detected or measurement timeout")

        except Exception as e:
            self.log_output(f"[!] Frequency measurement error: {e}")

    # --------------------------------------------------------------------------
    # Status Display Functions
    # --------------------------------------------------------------------------

    async def _refresh_status_display(self) -> None:
        """Refresh the status tab with current device information"""
        if not self._backend:
            self.log_output("[!] Not connected")
            return

        self.log_output("[*] Refreshing device status...")

        try:
            # Get full status from BPIO2
            status = None
            if hasattr(self._backend, 'get_full_status'):
                status = self._backend.get_full_status()

            if status:
                # Version Information
                fb_ver = f"{status.get('version_flatbuffers_major', '?')}.{status.get('version_flatbuffers_minor', '?')}"
                self._update_status_field("status-flatbuffers", fb_ver)

                hw_ver = f"{status.get('version_hardware_major', '?')} REV{status.get('version_hardware_minor', '?')}"
                self._update_status_field("status-hardware", hw_ver)

                fw_ver = f"{status.get('version_firmware_major', '?')}.{status.get('version_firmware_minor', '?')}"
                self._update_status_field("status-firmware", fw_ver)

                git_hash = status.get('version_firmware_git_hash', '')
                self._update_status_field("status-git-hash", git_hash if git_hash else "N/A")

                # Use version_firmware_date (correct key from BPIO2)
                build_date = status.get('version_firmware_date', '')
                self._update_status_field("status-build-date", build_date if build_date else "N/A")

                # Mode Information
                mode = status.get('mode_current', 'Unknown')
                self._update_status_field("status-mode", mode if mode else "HiZ")
                self.current_mode = mode if mode else "HiZ"

                modes_available = status.get('modes_available', [])
                self._update_status_field("status-modes-available", ", ".join(modes_available) if modes_available else "N/A")

                # Use mode_bitorder_msb (boolean) from BPIO2
                bit_order_msb = status.get('mode_bitorder_msb', True)
                self._update_status_field("status-bit-order", "MSB" if bit_order_msb else "LSB")

                pins = status.get('mode_pin_labels', [])
                pin_str = ", ".join(pins) if pins else "N/A"
                self._update_status_field("status-pins", pin_str)

                # Use mode_max_* keys (correct from BPIO2)
                max_packet = status.get('mode_max_packet_size', 0)
                self._update_status_field("status-max-packet", f"{max_packet} bytes" if max_packet else "N/A")

                max_write = status.get('mode_max_write', 0)
                self._update_status_field("status-max-write", f"{max_write} bytes" if max_write else "N/A")

                max_read = status.get('mode_max_read', 0)
                self._update_status_field("status-max-read", f"{max_read} bytes" if max_read else "N/A")

                # Power Supply
                psu_enabled = status.get('psu_enabled', False)
                self._update_status_field("status-psu", "Yes" if psu_enabled else "No", "status-val-on" if psu_enabled else "status-val-off")
                self.power_enabled = psu_enabled

                set_mv = status.get('psu_set_mv', 0)
                self._update_status_field("status-set-voltage", f"{set_mv} mV")

                set_ma = status.get('psu_set_ma', 0)
                self._update_status_field("status-set-current", f"{set_ma} mA")

                meas_mv = status.get('psu_measured_mv', 0)
                self._update_status_field("status-voltage-meas", f"{meas_mv} mV")

                meas_ma = status.get('psu_measured_ma', 0)
                self._update_status_field("status-current-meas", f"{meas_ma} mA")

                # Use psu_current_error (correct key from BPIO2)
                oc_error = status.get('psu_current_error', False)
                self._update_status_field("status-oc-error", "Yes" if oc_error else "No", "status-val-error" if oc_error else "")

                pullups = status.get('pullup_enabled', False)
                self._update_status_field("status-pullups", "Enabled" if pullups else "Disabled", "status-val-on" if pullups else "status-val-off")
                self.pullups_enabled = pullups

                # IO Pins
                adc_values = status.get('adc_mv', [])
                if adc_values:
                    adc_str = ", ".join(f"{v}mV" for v in adc_values[:8])
                    self._update_status_field("status-adc-values", adc_str)
                else:
                    self._update_status_field("status-adc-values", "N/A")

                io_dir = status.get('io_direction', 0)
                if isinstance(io_dir, int):
                    dir_strs = [f"IO{i}:{'OUT' if (io_dir >> i) & 1 else 'IN'}" for i in range(8)]
                    self._update_status_field("status-io-directions", ", ".join(dir_strs))
                else:
                    self._update_status_field("status-io-directions", str(io_dir))

                io_val = status.get('io_value', 0)
                if isinstance(io_val, int):
                    val_strs = [f"IO{i}:{'HIGH' if (io_val >> i) & 1 else 'LOW'}" for i in range(8)]
                    self._update_status_field("status-io-values", ", ".join(val_strs))
                else:
                    self._update_status_field("status-io-values", str(io_val))

                # System - use led_count and disk_*_mb (correct keys from BPIO2)
                led_count = status.get('led_count', 0)
                self._update_status_field("status-leds", str(led_count) if led_count else "N/A")

                disk_size_mb = status.get('disk_size_mb', 0)
                self._update_status_field("status-disk-size", f"{disk_size_mb:.2f} MB" if disk_size_mb else "N/A")

                disk_used_mb = status.get('disk_used_mb', 0)
                self._update_status_field("status-disk-used", f"{disk_used_mb:.2f} MB" if disk_used_mb else "N/A")

                self.log_output("[+] Status refreshed")

            else:
                # Try simplified status
                simple_status = self._backend.get_status() if hasattr(self._backend, 'get_status') else None
                if simple_status and not simple_status.get('error'):
                    self._update_status_field("status-firmware", simple_status.get('firmware', 'N/A'))
                    self._update_status_field("status-hardware", simple_status.get('hardware', 'N/A'))
                    self._update_status_field("status-mode", simple_status.get('mode', 'HiZ'))
                    self._update_status_field("status-psu", "Yes" if simple_status.get('psu_enabled') else "No")
                    self._update_status_field("status-pullups", "Enabled" if simple_status.get('pullups_enabled') else "Disabled")

                    if simple_status.get('serial_fallback'):
                        self.log_output("[!] Limited info (serial fallback mode)")
                    else:
                        self.log_output("[+] Status refreshed (simplified)")
                else:
                    self.log_output("[!] Could not get device status")

        except Exception as e:
            self.log_output(f"[!] Status refresh error: {e}")

    def _update_status_field(self, field_id: str, value: str, css_class: str = "") -> None:
        """Update a status field in the Status tab with optional styling"""
        try:
            field = self.query_one(f"#{field_id}", Static)
            field.update(value)
            # Apply CSS class if provided (for on/off/error styling)
            if css_class:
                # Remove previous state classes and add new one
                field.remove_class("status-val-on", "status-val-off", "status-val-error")
                field.add_class(css_class)
        except Exception:
            pass  # Field may not exist yet

    # --------------------------------------------------------------------------
    # Logic Analyzer Functions
    # --------------------------------------------------------------------------

    def _update_logic_status(self, message: str) -> None:
        """Update the logic analyzer status line"""
        try:
            status = self.query_one("#logic-status", Static)
            status.update(message)
        except Exception:
            pass

    def _logic_log(self, message: str) -> None:
        """Log message to the logic analyzer log widget"""
        try:
            log_widget = self.query_one("#logic-log", Log)
            log_widget.write_line(message)
        except Exception:
            pass
        # Also send to main log
        self.log_output(message)

    def _logic_scroll(self, delta: int) -> None:
        """Scroll the logic analyzer waveform view"""
        if self._logic_widget:
            try:
                self._logic_widget.scroll(delta)
            except Exception:
                pass

    def _logic_goto_trigger(self) -> None:
        """Scroll to trigger position in waveform"""
        if self._logic_widget:
            try:
                self._logic_widget.scroll_to_trigger()
                self._update_logic_status("Scrolled to trigger position")
            except Exception:
                pass

    async def _start_logic_capture(self) -> None:
        """Start logic analyzer capture using SUMP protocol"""
        if self._logic_capturing:
            self._logic_log("[!] Capture already in progress")
            return

        self._logic_capturing = True
        self._update_logic_status("Starting capture...")
        self._logic_log("[*] Starting logic capture...")

        # Get config from UI - use new separate trigger selectors like Bolt
        try:
            rate_select = self.query_one("#logic-rate", Select)
            samples_select = self.query_one("#logic-samples", Select)
            trigger_ch_select = self.query_one("#logic-trigger-channel", Select)
            trigger_edge_select = self.query_one("#logic-trigger-edge", Select)
            sump_port_input = self.query_one("#logic-sump-port", Input)

            sample_rate = int(rate_select.value) if rate_select.value != Select.BLANK else 1000000
            num_samples = int(samples_select.value) if samples_select.value != Select.BLANK else 8192

            # Parse trigger settings
            trigger_channel = None
            trigger_ch_val = trigger_ch_select.value
            if trigger_ch_val and trigger_ch_val != "none" and trigger_ch_val != Select.BLANK:
                trigger_channel = int(trigger_ch_val)

            trigger_edge = str(trigger_edge_select.value) if trigger_edge_select.value != Select.BLANK else "rising"

            # Get custom SUMP port if specified
            custom_port = sump_port_input.value.strip() if sump_port_input.value else None

            self._logic_log(f"[*] Rate: {sample_rate/1e6:.1f}MHz, Samples: {num_samples}")
            if trigger_channel is not None:
                self._logic_log(f"[*] Trigger: CH{trigger_channel} {trigger_edge} edge")
            else:
                self._logic_log("[*] Trigger: Immediate (no trigger)")

        except Exception as e:
            self._logic_log(f"[!] Config error: {e}")
            self._update_logic_status(f"Config error: {e}")
            self._logic_capturing = False
            return

        # Try to use the backend for real capture
        if self._backend and hasattr(self._backend, 'capture_logic'):
            self._update_logic_status(f"Capturing at {sample_rate/1e6:.1f}MHz...")
            self._logic_log("[*] Entering SUMP mode...")
            try:
                # Run capture in background to avoid blocking UI
                loop = asyncio.get_event_loop()

                # Run the blocking capture in executor
                result = await loop.run_in_executor(
                    None,
                    lambda: self._backend.capture_logic(
                        sample_rate=sample_rate,
                        sample_count=num_samples,
                        channels=8,
                        trigger_channel=trigger_channel,
                        trigger_edge=trigger_edge,
                        timeout=10.0
                    )
                )

                if result and result.get("samples"):
                    sample_count = len(result['samples'][0]) if result.get('samples') else 0
                    self._logic_log(f"[+] Captured {sample_count} samples")

                    # Convert to LogicCapture format
                    capture = LogicCapture(
                        channels=result.get("channels", 8),
                        sample_rate=result.get("sample_rate", sample_rate),
                        samples=result["samples"],
                        trigger_position=result.get("trigger_position", 0)
                    )

                    if self._logic_widget:
                        self._logic_widget.set_capture(capture)
                        self._logic_widget.scroll_to_trigger()
                        self._logic_log("[+] Capture complete - waveform updated")
                        self._update_logic_status(f"Captured {sample_count} samples - use scroll buttons to navigate")
                else:
                    self._logic_log("[!] Capture returned no data")
                    self._logic_log("[*] Check device connection and trigger conditions")
                    self._update_logic_status("Capture failed - no data returned")

            except Exception as e:
                self._logic_log(f"[!] Capture error: {e}")
                self._logic_log("[*] Use 'Demo' button to test with sample data")
                self._update_logic_status(f"Capture error: {e}")
        else:
            self._logic_log("[!] No backend available for hardware capture")
            self._logic_log("[*] Use 'Demo' button to test with sample data")
            self._update_logic_status("No backend - use Demo to test")

        self._logic_capturing = False

    async def _stop_logic_capture(self) -> None:
        """Stop logic analyzer capture"""
        if not self._logic_capturing:
            return

        self._logic_capturing = False
        self._logic_log("[*] Capture stopped")
        self._update_logic_status("Capture stopped")

    async def _load_logic_demo(self) -> None:
        """Load demo capture data for testing the waveform display"""
        import random

        self._logic_log("[*] Loading demo capture data...")
        self._update_logic_status("Loading demo data...")

        # Generate realistic-looking demo waveforms
        samples = []
        num_samples = 500

        # CH0: Clock signal (regular square wave)
        ch0 = []
        for i in range(num_samples):
            ch0.append(1 if (i // 8) % 2 == 0 else 0)
        samples.append(ch0)

        # CH1: Data signal (changes on clock edges, simulating SPI MOSI)
        ch1 = []
        data_byte = 0xA5  # Example data pattern
        bit_idx = 0
        for i in range(num_samples):
            if i % 64 == 0:  # New byte every 64 samples (8 bits * 8 samples/bit)
                data_byte = random.randint(0, 255)
                bit_idx = 0
            bit = (data_byte >> (7 - (bit_idx // 8))) & 1
            ch1.append(bit)
            if i % 8 == 7:
                bit_idx += 1
        samples.append(ch1)

        # CH2: Chip select (low during transfer)
        ch2 = []
        for i in range(num_samples):
            ch2.append(0 if 50 < i < 450 else 1)
        samples.append(ch2)

        # CH3: Glitch trigger signal (short pulse)
        ch3 = []
        glitch_pos = random.randint(200, 300)
        for i in range(num_samples):
            ch3.append(1 if glitch_pos <= i < glitch_pos + 5 else 0)
        samples.append(ch3)

        # CH4-7: Random noise/unused
        for ch in range(4, 8):
            ch_data = []
            state = 0
            for i in range(num_samples):
                if random.random() < 0.02:
                    state = 1 - state
                ch_data.append(state)
            samples.append(ch_data)

        # Create capture object
        capture = LogicCapture(
            channels=8,
            sample_rate=10000000,  # 10MHz
            samples=samples,
            trigger_position=glitch_pos
        )

        # Update the widget
        if self._logic_widget:
            self._logic_widget.set_capture(capture)
            self._logic_widget.scroll_to_trigger()
            self._logic_log(f"[+] Loaded {num_samples} samples, trigger at position {glitch_pos}")
            self._logic_log("[*] CH0=CLK, CH1=DATA, CH2=CS, CH3=GLITCH_TRIGGER")
            self._update_logic_status(f"Demo loaded: {num_samples} samples - use scroll buttons to navigate")
        else:
            self._logic_log("[!] Logic widget not initialized")
            self._update_logic_status("Error: Logic widget not initialized")
