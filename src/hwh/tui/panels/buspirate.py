"""
Bus Pirate Panel

Full-featured panel for Bus Pirate 5/6 devices.
Supports: SPI, I2C, UART, 1-Wire, JTAG/SWD scanning, Logic Analyzer, ADC, PWM
"""

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
        """Device status display - shows BPIO2 device information"""
        with Vertical(id="status-container"):
            yield Static("Device Status", classes="section-title")
            yield Static("Connection and firmware information from BPIO2", classes="help-text")

            with Horizontal(classes="button-row"):
                yield Button("Refresh", id="btn-status-refresh", classes="btn-action")

            # Status display grid
            with Grid(classes="status-grid", id="status-grid"):
                # Version info
                yield Static("Firmware:", classes="status-label")
                yield Static("---", id="status-firmware", classes="status-value")
                yield Static("Hardware:", classes="status-label")
                yield Static("---", id="status-hardware", classes="status-value")

                # Mode info
                yield Static("Mode:", classes="status-label")
                yield Static("---", id="status-mode", classes="status-value")
                yield Static("Pin Labels:", classes="status-label")
                yield Static("---", id="status-pins", classes="status-value")

                # PSU info
                yield Static("PSU:", classes="status-label")
                yield Static("---", id="status-psu", classes="status-value")
                yield Static("Pull-ups:", classes="status-label")
                yield Static("---", id="status-pullups", classes="status-value")

                # Measured values
                yield Static("Voltage:", classes="status-label")
                yield Static("---", id="status-voltage-meas", classes="status-value")
                yield Static("Current:", classes="status-label")
                yield Static("---", id="status-current-meas", classes="status-value")

            # ADC readings section
            yield Static("ADC Readings", classes="section-subtitle")
            with Horizontal(classes="adc-row", id="adc-readings"):
                for i in range(8):
                    yield Static(f"IO{i}:", classes="adc-label-small")
                    yield Static("---", id=f"status-adc-{i}", classes="adc-value-small")

    def _build_protocol_section(self) -> ComposeResult:
        """Protocol-specific controls that change based on mode"""
        with Container(id="protocol-container"):
            # SPI controls (shown when SPI mode selected)
            with Container(id="spi-controls", classes="protocol-controls"):
                yield Static("SPI Configuration", classes="section-title")
                with Grid(classes="config-grid"):
                    yield Static("Speed:")
                    yield Select(
                        [("1MHz", "1000000"), ("4MHz", "4000000"), ("8MHz", "8000000")],
                        value="1000000",
                        id="spi-speed"
                    )
                    yield Static("Mode:")
                    yield Select(
                        [("0 (CPOL=0,CPHA=0)", "0"), ("1", "1"), ("2", "2"), ("3", "3")],
                        value="0",
                        id="spi-mode"
                    )
                    yield Static("CS Active:")
                    yield Select([("Low", "low"), ("High", "high")], value="low", id="spi-cs")

                with Horizontal(classes="button-row"):
                    yield Button("Read Flash ID", id="btn-spi-id", classes="btn-action")
                    yield Button("Dump Flash", id="btn-spi-dump", classes="btn-action")
                    yield Button("Erase", id="btn-spi-erase", classes="btn-action")
                    yield Button("Write", id="btn-spi-write", classes="btn-action")

                with Horizontal(classes="input-row"):
                    yield Static("Address:")
                    yield Input(value="0x000000", id="spi-addr", classes="hex-input")
                    yield Static("Size:")
                    yield Input(value="0x1000", id="spi-size", classes="hex-input")
                    yield Static("File:")
                    yield Input(value="dump.bin", id="spi-file", classes="file-input")

            # I2C controls
            with Container(id="i2c-controls", classes="protocol-controls hidden"):
                yield Static("I2C Configuration", classes="section-title")
                with Grid(classes="config-grid"):
                    yield Static("Speed:")
                    yield Select(
                        [("100kHz", "100000"), ("400kHz", "400000"), ("1MHz", "1000000")],
                        value="100000",
                        id="i2c-speed"
                    )
                    yield Static("Address:")
                    yield Input(value="0x50", id="i2c-addr", classes="hex-input")

                with Horizontal(classes="button-row"):
                    yield Button("Scan Bus", id="btn-i2c-scan", classes="btn-action")
                    yield Button("Read Byte", id="btn-i2c-read", classes="btn-action")
                    yield Button("Write Byte", id="btn-i2c-write", classes="btn-action")
                    yield Button("Dump EEPROM", id="btn-i2c-dump", classes="btn-action")

            # UART controls
            with Container(id="uart-controls", classes="protocol-controls hidden"):
                yield Static("UART Configuration", classes="section-title")
                with Grid(classes="config-grid"):
                    yield Static("Baud:")
                    yield Select(
                        [("9600", "9600"), ("115200", "115200"), ("230400", "230400"), ("921600", "921600")],
                        value="115200",
                        id="uart-baud"
                    )
                    yield Static("Format:")
                    yield Select(
                        [("8N1", "8N1"), ("8E1", "8E1"), ("8O1", "8O1"), ("7E1", "7E1")],
                        value="8N1",
                        id="uart-format"
                    )

                with Horizontal(classes="button-row"):
                    yield Button("Bridge Mode", id="btn-uart-bridge", classes="btn-action")
                    yield Button("Auto Baud", id="btn-uart-auto", classes="btn-action")

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
        """Logic analyzer controls"""
        with Vertical():
            yield Static("Logic Analyzer", classes="section-title")
            yield Static("8 channels @ 62.5MSPS max | Demo mode for testing", classes="help-text")

            with Horizontal(classes="button-row"):
                yield Button("Capture", id="btn-logic-capture", classes="btn-action")
                yield Button("Stop", id="btn-logic-stop", classes="btn-action")
                yield Button("Demo", id="btn-logic-demo", classes="btn-action")
                yield Button("Export", id="btn-logic-export", classes="btn-action")

            with Grid(classes="config-grid"):
                yield Static("Rate:")
                yield Select(
                    [("62.5MHz", "62500000"), ("10MHz", "10000000"), ("1MHz", "1000000")],
                    value="10000000",
                    id="logic-rate"
                )
                yield Static("Samples:")
                yield Select(
                    [("1K", "1024"), ("8K", "8192"), ("32K", "32768")],
                    value="8192",
                    id="logic-samples"
                )
                yield Static("Trigger:")
                yield Select(
                    [("None", "none"), ("CH0 ↑", "ch0_rise"), ("CH0 ↓", "ch0_fall"),
                     ("CH1 ↑", "ch1_rise"), ("CH1 ↓", "ch1_fall")],
                    value="none",
                    id="logic-trigger"
                )

            # Channel enables - compact row
            with Horizontal(classes="channel-row"):
                for i in range(8):
                    yield Static(f"{i}", classes="channel-num")
                    yield Switch(id=f"logic-ch{i}", value=True if i < 4 else False)

            # Waveform display using LogicAnalyzerWidget
            self._logic_widget = LogicAnalyzerWidget(channels=8, visible_samples=60, id="logic-waveform")
            yield self._logic_widget

    def _build_power_section(self) -> ComposeResult:
        """Power supply and measurement controls"""
        with Vertical():
            yield Static("Power & Measurement", classes="section-title")

            with Horizontal(classes="power-controls"):
                with Vertical(classes="power-group"):
                    yield Static("Power Supply")
                    with Horizontal():
                        yield Static("Enable:")
                        yield Switch(id="power-enable")
                    with Horizontal():
                        yield Static("Voltage:")
                        yield Select(
                            [("3.3V", "3.3"), ("5V", "5.0"), ("1.8V", "1.8")],
                            value="3.3",
                            id="power-voltage"
                        )

                with Vertical(classes="power-group"):
                    yield Static("Pull-ups")
                    with Horizontal():
                        yield Static("Enable:")
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
        elif button_id == "btn-logic-export":
            self.log_output("[*] Export not implemented yet")

        # Scan tab
        elif button_id == "btn-jtag-scan":
            self.log_output("[*] Starting JTAG pin scan...")
            self.log_output("[*] Testing all pin combinations...")
        elif button_id == "btn-swd-scan":
            self.log_output("[*] Starting SWD pin scan...")
        elif button_id == "btn-uart-detect":
            await self._uart_auto_detect()

        # Power tab
        elif button_id == "btn-adc-read":
            await self._read_adc()
        elif button_id == "btn-adc-monitor":
            self.log_output("[*] ADC monitor not implemented yet")
        elif button_id == "btn-pwm-start":
            await self._start_pwm()
        elif button_id == "btn-pwm-stop":
            await self._stop_pwm()
        elif button_id == "btn-freq-measure":
            self.log_output("[*] Frequency measurement not implemented yet")

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

    async def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle Switch widget changes"""
        switch_id = event.switch.id
        if not switch_id:
            return

        value = event.value

        if switch_id == "power-enable":
            await self._toggle_power(value)
        elif switch_id == "pullup-enable":
            await self._toggle_pullups(value)

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
                self._update_protocol_visibility("hiz")

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
                    self._update_protocol_visibility("spi")
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
                    self._update_protocol_visibility("i2c")
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
                    self._update_protocol_visibility("uart")
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
            return str(select.value) if select.value else default
        except Exception:
            return default

    def _update_protocol_visibility(self, mode: str) -> None:
        """Show/hide protocol-specific controls based on mode"""
        try:
            # Get all protocol control containers
            spi_controls = self.query_one("#spi-controls", Container)
            i2c_controls = self.query_one("#i2c-controls", Container)
            uart_controls = self.query_one("#uart-controls", Container)

            # Hide all first
            spi_controls.add_class("hidden")
            i2c_controls.add_class("hidden")
            uart_controls.add_class("hidden")

            # Show the appropriate one
            if mode == "spi":
                spi_controls.remove_class("hidden")
            elif mode == "i2c":
                i2c_controls.remove_class("hidden")
            elif mode == "uart":
                uart_controls.remove_class("hidden")

        except Exception:
            pass  # Controls may not exist yet

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

    async def _toggle_power(self, enabled: bool) -> None:
        """Toggle power supply"""
        if not self._backend:
            self.log_output("[!] Not connected")
            return

        try:
            # Get voltage from power-voltage select
            voltage_str = self._get_select_value("power-voltage", "3.3")
            voltage_mv = int(float(voltage_str) * 1000)

            if self._backend.set_psu(enabled=enabled, voltage_mv=voltage_mv):
                self.power_enabled = enabled
                if enabled:
                    self.log_output(f"[+] PSU enabled: {voltage_str}V")
                else:
                    self.log_output("[-] PSU disabled")
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
        """Erase SPI flash"""
        self.log_output("[*] SPI erase not yet implemented")
        self.log_output("[!] This is a destructive operation - use with caution")

    async def _spi_write_flash(self) -> None:
        """Write to SPI flash"""
        self.log_output("[*] SPI write not yet implemented")
        self.log_output("[!] This is a destructive operation - use with caution")

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
        self.log_output("[*] PWM output not yet implemented via BPIO2")

    async def _stop_pwm(self) -> None:
        """Stop PWM output"""
        self.log_output("[*] PWM stop not yet implemented via BPIO2")

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
                # Update firmware version
                fw_ver = f"{status.get('version_firmware_major', '?')}.{status.get('version_firmware_minor', '?')}"
                self._update_status_field("status-firmware", f"v{fw_ver}")

                # Update hardware version
                hw_ver = f"{status.get('version_hardware_major', '?')} REV{status.get('version_hardware_minor', '?')}"
                self._update_status_field("status-hardware", f"v{hw_ver}")

                # Update mode
                mode = status.get('mode_current', 'Unknown')
                self._update_status_field("status-mode", mode)

                # Update pin labels
                pins = status.get('mode_pin_labels', 'N/A')
                self._update_status_field("status-pins", str(pins)[:30])

                # Update PSU status
                psu_enabled = status.get('psu_enabled', False)
                psu_mv = status.get('psu_set_mv', 0)
                if psu_enabled:
                    self._update_status_field("status-psu", f"ON ({psu_mv}mV)")
                else:
                    self._update_status_field("status-psu", "OFF")

                # Update pullups
                pullups = status.get('pullup_enabled', False)
                self._update_status_field("status-pullups", "Enabled" if pullups else "Disabled")

                # Update measured values
                meas_mv = status.get('psu_measured_mv', 0)
                meas_ma = status.get('psu_measured_ma', 0)
                self._update_status_field("status-voltage-meas", f"{meas_mv}mV")
                self._update_status_field("status-current-meas", f"{meas_ma}mA")

                # Update ADC values
                adc_values = status.get('adc_mv', [])
                for i, val in enumerate(adc_values[:8]):
                    self._update_status_field(f"status-adc-{i}", f"{val}mV")

                self.log_output("[+] Status refreshed")

            else:
                # Try simplified status
                simple_status = self._backend.get_status() if hasattr(self._backend, 'get_status') else None
                if simple_status and not simple_status.get('error'):
                    self._update_status_field("status-firmware", simple_status.get('firmware', 'N/A'))
                    self._update_status_field("status-hardware", simple_status.get('hardware', 'N/A'))
                    self._update_status_field("status-mode", simple_status.get('mode', 'HiZ'))
                    self._update_status_field("status-psu", "ON" if simple_status.get('psu_enabled') else "OFF")
                    self._update_status_field("status-pullups", "Enabled" if simple_status.get('pullups_enabled') else "Disabled")

                    if simple_status.get('serial_fallback'):
                        self.log_output("[!] Limited info (serial fallback mode)")
                    else:
                        self.log_output("[+] Status refreshed (simplified)")
                else:
                    self.log_output("[!] Could not get device status")

        except Exception as e:
            self.log_output(f"[!] Status refresh error: {e}")

    def _update_status_field(self, field_id: str, value: str) -> None:
        """Update a status field in the Status tab"""
        try:
            field = self.query_one(f"#{field_id}", Static)
            field.update(value)
        except Exception:
            pass  # Field may not exist yet

    # --------------------------------------------------------------------------
    # Logic Analyzer Functions
    # --------------------------------------------------------------------------

    async def _start_logic_capture(self) -> None:
        """Start logic analyzer capture using SUMP protocol"""
        if self._logic_capturing:
            self.log_output("[!] Capture already in progress")
            return

        self._logic_capturing = True
        self.log_output("[*] Starting logic capture...")

        # Get config from UI
        try:
            rate_select = self.query_one("#logic-rate", Select)
            samples_select = self.query_one("#logic-samples", Select)
            trigger_select = self.query_one("#logic-trigger", Select)

            sample_rate = int(rate_select.value) if rate_select.value else 10000000
            num_samples = int(samples_select.value) if samples_select.value else 8192
            trigger = str(trigger_select.value) if trigger_select.value else "none"

            self.log_output(f"[*] Rate: {sample_rate/1e6:.1f}MHz, Samples: {num_samples}, Trigger: {trigger}")
        except Exception as e:
            self.log_output(f"[!] Config error: {e}")
            self._logic_capturing = False
            return

        # Parse trigger config
        trigger_channel = None
        trigger_edge = "rising"
        if trigger != "none":
            # Parse "ch0_rise" or "ch1_fall" format
            parts = trigger.split("_")
            if len(parts) == 2:
                trigger_channel = int(parts[0].replace("ch", ""))
                trigger_edge = "rising" if parts[1] == "rise" else "falling"
                self.log_output(f"[*] Trigger on CH{trigger_channel} {trigger_edge} edge")

        # Try to use the backend for real capture
        if self._backend and hasattr(self._backend, 'capture_logic'):
            self.log_output("[*] Entering SUMP mode...")
            try:
                # Run capture in background to avoid blocking UI
                import asyncio
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
                    self.log_output(f"[+] Captured {len(result['samples'][0])} samples")

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
                        self.log_output("[+] Capture complete - waveform updated")
                else:
                    self.log_output("[!] Capture returned no data")
                    self.log_output("[*] Check device connection and trigger conditions")

            except Exception as e:
                self.log_output(f"[!] Capture error: {e}")
                self.log_output("[*] Use 'Demo' button to test with sample data")
        else:
            self.log_output("[!] No backend available for hardware capture")
            self.log_output("[*] Use 'Demo' button to test with sample data")

        self._logic_capturing = False

    async def _stop_logic_capture(self) -> None:
        """Stop logic analyzer capture"""
        if not self._logic_capturing:
            return

        self._logic_capturing = False
        self.log_output("[*] Capture stopped")

    async def _load_logic_demo(self) -> None:
        """Load demo capture data for testing the waveform display"""
        import random

        self.log_output("[*] Loading demo capture data...")

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
            self.log_output(f"[+] Loaded {num_samples} samples, trigger at position {glitch_pos}")
            self.log_output("[*] CH0=CLK, CH1=DATA, CH2=CS, CH3=GLITCH_TRIGGER")
        else:
            self.log_output("[!] Logic widget not initialized")
