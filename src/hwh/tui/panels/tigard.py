"""
Tigard Panel

Panel for Tigard multi-protocol debug adapter.
Supports: SPI, I2C, UART, JTAG, SWD

Features:
- Fast SPI flash operations
- JTAG debugging via OpenOCD
- SWD debugging via OpenOCD
- UART bridging
"""

from typing import List, Optional
from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal, Grid
from textual.widgets import Static, Button, Input, Select, Switch, Log, TabbedContent, TabPane

from .base import DevicePanel, DeviceInfo, PanelCapability, CommandSuggestion


@dataclass
class SPIFlashInfo:
    """SPI Flash identification"""
    manufacturer: str = ""
    device_id: int = 0
    size_bytes: int = 0
    name: str = ""


class TigardPanel(DevicePanel):
    """
    Panel for Tigard debug adapter.

    Features:
    - Protocol selection (SPI, I2C, UART, JTAG, SWD)
    - Fast SPI flash operations
    - OpenOCD integration for JTAG/SWD
    """

    DEVICE_NAME = "Tigard"
    CAPABILITIES = [
        PanelCapability.SPI,
        PanelCapability.I2C,
        PanelCapability.UART,
        PanelCapability.JTAG,
        PanelCapability.SWD,
        PanelCapability.FLASH,
    ]

    def __init__(self, device_info: DeviceInfo, app, *args, **kwargs):
        super().__init__(device_info, app, *args, **kwargs)
        self.current_mode = "SPI"
        self.flash_info: Optional[SPIFlashInfo] = None
        self._backend = None

    def compose(self) -> ComposeResult:
        with Vertical(id="tigard-panel"):
            # Header
            with Horizontal(classes="panel-header"):
                yield Static(f"{self.device_info.name}", classes="device-title")
                yield Static(f"Port: {self.device_info.port}", classes="device-port")
                yield Static("Mode:", classes="mode-label")
                yield Select(
                    [(m, m) for m in ["SPI", "I2C", "UART", "JTAG", "SWD"]],
                    value="SPI",
                    id="tigard-mode",
                    classes="mode-select"
                )

            # Feature tabs
            with TabbedContent(id="tigard-features"):
                # SPI Tab
                with TabPane("SPI Flash", id="tab-spi"):
                    yield from self._build_spi_section()

                # Debug Tab (JTAG/SWD)
                with TabPane("Debug", id="tab-debug"):
                    yield from self._build_debug_section()

                # UART Tab
                with TabPane("UART", id="tab-uart"):
                    yield from self._build_uart_section()

            # Console
            yield from self._build_console_section()

    def _build_spi_section(self) -> ComposeResult:
        """SPI Flash operations"""
        with Vertical():
            yield Static("SPI Flash Operations", classes="section-title")
            yield Static("High-speed flash reading/writing", classes="help-text")

            with Grid(classes="config-grid"):
                yield Static("Speed:")
                yield Select(
                    [("1MHz", "1000000"), ("4MHz", "4000000"), ("8MHz", "8000000"), ("24MHz", "24000000")],
                    value="8000000",
                    id="spi-speed"
                )
                yield Static("Mode:")
                yield Select(
                    [("0", "0"), ("1", "1"), ("2", "2"), ("3", "3")],
                    value="0",
                    id="spi-mode"
                )

            with Horizontal(classes="button-row"):
                yield Button("Detect Flash", id="btn-detect", classes="btn-action")
                yield Button("Read ID", id="btn-read-id", classes="btn-action")
                yield Button("Dump", id="btn-dump", classes="btn-action")
                yield Button("Erase", id="btn-erase", classes="btn-action")
                yield Button("Write", id="btn-write", classes="btn-action")

            # Flash info display
            with Container(classes="flash-info") as info:
                info.border_title = "flash info"
                yield Static("Manufacturer: ---", id="flash-manufacturer")
                yield Static("Device ID: ---", id="flash-device-id")
                yield Static("Size: ---", id="flash-size")
                yield Static("Name: ---", id="flash-name")

            # Dump/Write parameters
            with Grid(classes="config-grid"):
                yield Static("Address:")
                yield Input(value="0x000000", id="flash-addr", classes="hex-input")
                yield Static("Size:")
                yield Input(value="0x100000", id="flash-size-input", classes="hex-input")
                yield Static("File:")
                yield Input(value="dump.bin", id="flash-file", classes="file-input")

    def _build_debug_section(self) -> ComposeResult:
        """JTAG/SWD debugging via OpenOCD"""
        with Vertical():
            yield Static("Debug Interface", classes="section-title")
            yield Static("JTAG/SWD debugging via OpenOCD", classes="help-text")

            with Grid(classes="config-grid"):
                yield Static("Interface:")
                yield Select(
                    [("SWD", "swd"), ("JTAG", "jtag")],
                    value="swd",
                    id="debug-interface"
                )
                yield Static("Target:")
                yield Select(
                    [("Auto", "auto"), ("STM32F1", "stm32f1x"), ("STM32F4", "stm32f4x"),
                     ("nRF52", "nrf52"), ("ESP32", "esp32"), ("RP2040", "rp2040")],
                    value="auto",
                    id="debug-target"
                )
                yield Static("Speed:")
                yield Select(
                    [("1MHz", "1000"), ("2MHz", "2000"), ("4MHz", "4000")],
                    value="1000",
                    id="debug-speed"
                )

            with Horizontal(classes="button-row"):
                yield Button("Connect", id="btn-debug-connect", classes="btn-action")
                yield Button("Halt", id="btn-debug-halt", classes="btn-action")
                yield Button("Reset", id="btn-debug-reset", classes="btn-action")
                yield Button("Resume", id="btn-debug-resume", classes="btn-action")

            with Horizontal(classes="button-row"):
                yield Button("Read Memory", id="btn-read-mem", classes="btn-action")
                yield Button("Dump Firmware", id="btn-dump-fw", classes="btn-action")
                yield Button("Flash Firmware", id="btn-flash-fw", classes="btn-action")

            # OpenOCD status
            with Container(classes="openocd-status") as status:
                status.border_title = "openocd"
                yield Static("Status: Not connected", id="openocd-status")
                yield Static("Target: ---", id="openocd-target")
                yield Static("Core: ---", id="openocd-core")

            # Memory read parameters
            with Grid(classes="config-grid"):
                yield Static("Address:")
                yield Input(value="0x08000000", id="mem-addr", classes="hex-input")
                yield Static("Size:")
                yield Input(value="0x1000", id="mem-size", classes="hex-input")

    def _build_uart_section(self) -> ComposeResult:
        """UART bridging"""
        with Vertical():
            yield Static("UART Bridge", classes="section-title")

            with Grid(classes="config-grid"):
                yield Static("Baud:")
                yield Select(
                    [("9600", "9600"), ("115200", "115200"), ("921600", "921600")],
                    value="115200",
                    id="uart-baud"
                )
                yield Static("Format:")
                yield Select(
                    [("8N1", "8N1"), ("8E1", "8E1"), ("8O1", "8O1")],
                    value="8N1",
                    id="uart-format"
                )

            with Horizontal(classes="button-row"):
                yield Button("Start Bridge", id="btn-uart-start", classes="btn-action")
                yield Button("Stop", id="btn-uart-stop", classes="btn-action")

    async def connect(self) -> bool:
        """Connect to Tigard"""
        try:
            from ...backends import get_backend
            self._backend = get_backend(self.device_info)

            if self._backend:
                self._backend.connect()
                self.connected = True
                self.log_output(f"[+] Connected to {self.device_info.name}")
                self.log_output("[*] Tigard ready - select mode to begin")
                return True
            else:
                self.log_output(f"[!] No backend for {self.device_info.name}")
                self.connected = True
                return True

        except Exception as e:
            self.log_output(f"[!] Connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from Tigard"""
        if self._backend:
            try:
                self._backend.disconnect()
            except Exception:
                pass
            self._backend = None

        self.connected = False
        self.log_output(f"[-] Disconnected from {self.device_info.name}")

    async def send_command(self, command: str) -> None:
        """Handle commands"""
        await super().send_command(command)

        parts = command.strip().split()
        if not parts:
            return

        cmd = parts[0].lower()

        if cmd == "help":
            self._show_help()
        elif cmd == "spi":
            await self._handle_spi_command(parts[1:])
        elif cmd == "debug":
            await self._handle_debug_command(parts[1:])
        elif cmd == "openocd":
            await self._handle_openocd_command(parts[1:])
        else:
            self.log_output(f"Unknown command: {cmd}")

    def get_command_suggestions(self, partial: str) -> List[CommandSuggestion]:
        """Get suggestions"""
        suggestions = [
            CommandSuggestion("help", "Show available commands"),
            CommandSuggestion("spi id", "Read SPI flash ID", "spi"),
            CommandSuggestion("spi dump", "Dump SPI flash", "spi"),
            CommandSuggestion("debug connect", "Connect via OpenOCD", "debug"),
            CommandSuggestion("debug halt", "Halt target", "debug"),
            CommandSuggestion("debug reset", "Reset target", "debug"),
            CommandSuggestion("openocd start", "Start OpenOCD server", "openocd"),
        ]

        if partial:
            partial_lower = partial.lower()
            suggestions = [s for s in suggestions if s.command.lower().startswith(partial_lower)]

        return suggestions

    def _show_help(self) -> None:
        """Display help"""
        help_text = """
Tigard Commands:
  help              - Show this help
  spi id            - Read SPI flash ID
  spi dump <file>   - Dump flash to file
  spi write <file>  - Write file to flash
  spi erase         - Erase flash
  debug connect     - Connect to target via OpenOCD
  debug halt        - Halt target CPU
  debug reset       - Reset target
  debug dump <file> - Dump firmware
  openocd start     - Start OpenOCD server
"""
        self.log_output(help_text)

    async def _handle_spi_command(self, args: List[str]) -> None:
        """Handle SPI commands"""
        if not args:
            self.log_output("[!] SPI command required")
            return

        # Ensure SPI is configured
        if not await self._ensure_spi_configured():
            return

        subcmd = args[0].lower()
        if subcmd == "id":
            await self._spi_read_id()
        elif subcmd == "dump":
            filename = args[1] if len(args) > 1 else "dump.bin"
            address = int(args[2], 16) if len(args) > 2 else 0
            size = int(args[3], 16) if len(args) > 3 else 0x100000
            await self._spi_dump(filename, address, size)
        elif subcmd == "erase":
            erase_type = args[1] if len(args) > 1 else "chip"
            address = int(args[2], 16) if len(args) > 2 else 0
            await self._spi_erase(erase_type, address)
        elif subcmd == "write":
            filename = args[1] if len(args) > 1 else "firmware.bin"
            address = int(args[2], 16) if len(args) > 2 else 0
            await self._spi_write(filename, address)
        elif subcmd == "status":
            await self._spi_read_status()

    async def _ensure_spi_configured(self) -> bool:
        """Ensure SPI is configured before operations"""
        if not self._backend:
            self.log_output("[!] Not connected to Tigard")
            return False

        try:
            # Get speed and mode from UI
            speed_select = self.query_one("#spi-speed", Select)
            mode_select = self.query_one("#spi-mode", Select)

            speed = int(speed_select.value) if speed_select.value else 8000000
            mode = int(mode_select.value) if mode_select.value else 0

            from ...backends import SPIConfig
            config = SPIConfig(speed_hz=speed, mode=mode)

            if self._backend.configure_spi(config):
                self.log_output(f"[*] SPI configured: {speed/1e6:.1f}MHz, mode {mode}")
                return True
            else:
                self.log_output("[!] Failed to configure SPI")
                return False
        except Exception as e:
            self.log_output(f"[!] SPI config error: {e}")
            return False

    async def _spi_read_id(self) -> None:
        """Read SPI flash JEDEC ID"""
        self.log_output("[*] Reading SPI flash ID...")

        try:
            jedec_id = self._backend.spi_flash_read_id()
            if jedec_id and len(jedec_id) >= 3:
                mfr = jedec_id[0]
                dev_type = jedec_id[1]
                capacity = jedec_id[2]

                # Decode manufacturer
                mfr_names = {
                    0xEF: "Winbond",
                    0xC2: "Macronix",
                    0x20: "Micron",
                    0x01: "Spansion",
                    0xBF: "SST",
                    0x1F: "Atmel",
                    0x9D: "ISSI",
                }
                mfr_name = mfr_names.get(mfr, "Unknown")

                # Calculate size (2^capacity bytes)
                size_bytes = 1 << capacity if capacity < 32 else 0
                size_str = f"{size_bytes // (1024*1024)}MB" if size_bytes >= 1024*1024 else f"{size_bytes // 1024}KB"

                self.log_output(f"[+] Manufacturer: {mfr_name} (0x{mfr:02X})")
                self.log_output(f"[+] Device Type: 0x{dev_type:02X}")
                self.log_output(f"[+] Capacity: 0x{capacity:02X} ({size_str})")

                # Update UI
                self._update_flash_info(mfr_name, mfr, dev_type, capacity, size_bytes)

                # Store flash info
                self.flash_info = SPIFlashInfo(
                    manufacturer=mfr_name,
                    device_id=(dev_type << 8) | capacity,
                    size_bytes=size_bytes,
                    name=f"{mfr_name} {size_str}"
                )
            else:
                self.log_output("[!] Failed to read flash ID - check connections")
        except Exception as e:
            self.log_output(f"[!] Error reading ID: {e}")

    def _update_flash_info(self, mfr: str, mfr_id: int, dev_type: int, capacity: int, size: int) -> None:
        """Update flash info display in UI"""
        try:
            self.query_one("#flash-manufacturer", Static).update(f"Manufacturer: {mfr} (0x{mfr_id:02X})")
            self.query_one("#flash-device-id", Static).update(f"Device ID: 0x{dev_type:02X}{capacity:02X}")
            size_str = f"{size // (1024*1024)}MB" if size >= 1024*1024 else f"{size // 1024}KB"
            self.query_one("#flash-size", Static).update(f"Size: {size_str}")
            self.query_one("#flash-name", Static).update(f"Name: {mfr} Flash")
        except Exception:
            pass

    async def _spi_dump(self, filename: str, address: int, size: int) -> None:
        """Dump SPI flash to file"""
        self.log_output(f"[*] Dumping {size:,} bytes from 0x{address:06X} to {filename}...")

        try:
            import asyncio
            from pathlib import Path

            data = bytearray()
            chunk_size = 4096
            read_bytes = 0

            while read_bytes < size:
                remaining = size - read_bytes
                to_read = min(chunk_size, remaining)

                chunk = self._backend.spi_flash_read(address + read_bytes, to_read)
                if not chunk:
                    self.log_output(f"[!] Read failed at 0x{address + read_bytes:06X}")
                    break

                data.extend(chunk)
                read_bytes += len(chunk)

                # Progress update every 64KB
                if read_bytes % (64 * 1024) == 0:
                    pct = (read_bytes * 100) // size
                    self.log_output(f"[*] Progress: {pct}% ({read_bytes:,} / {size:,} bytes)")

                # Yield to UI
                await asyncio.sleep(0)

            # Write to file
            Path(filename).write_bytes(data)
            self.log_output(f"[+] Dump complete: {len(data):,} bytes written to {filename}")

        except Exception as e:
            self.log_output(f"[!] Dump failed: {e}")

    async def _spi_erase(self, erase_type: str, address: int = 0) -> None:
        """Erase SPI flash"""
        self.log_output(f"[*] Erasing flash ({erase_type})...")

        try:
            if self._backend.spi_flash_erase(address, erase_type):
                self.log_output("[+] Erase complete")
            else:
                self.log_output("[!] Erase failed")
        except Exception as e:
            self.log_output(f"[!] Erase error: {e}")

    async def _spi_write(self, filename: str, address: int = 0) -> None:
        """Write file to SPI flash"""
        from pathlib import Path
        import asyncio

        path = Path(filename)
        if not path.exists():
            self.log_output(f"[!] File not found: {filename}")
            return

        data = path.read_bytes()
        self.log_output(f"[*] Writing {len(data):,} bytes to 0x{address:06X}...")

        try:
            # Write in chunks with progress
            chunk_size = 4096
            written = 0

            while written < len(data):
                chunk = data[written:written + chunk_size]
                if not self._backend.spi_flash_write(address + written, chunk):
                    self.log_output(f"[!] Write failed at 0x{address + written:06X}")
                    return

                written += len(chunk)

                # Progress update every 64KB
                if written % (64 * 1024) == 0:
                    pct = (written * 100) // len(data)
                    self.log_output(f"[*] Progress: {pct}% ({written:,} / {len(data):,} bytes)")

                await asyncio.sleep(0)

            self.log_output(f"[+] Write complete: {written:,} bytes")

        except Exception as e:
            self.log_output(f"[!] Write error: {e}")

    async def _spi_read_status(self) -> None:
        """Read SPI flash status register"""
        try:
            status = self._backend.spi_flash_read_status()
            self.log_output(f"[*] Status register: 0x{status:02X}")
            self.log_output(f"    BUSY: {bool(status & 0x01)}")
            self.log_output(f"    WEL:  {bool(status & 0x02)}")
        except Exception as e:
            self.log_output(f"[!] Error: {e}")

    async def _handle_debug_command(self, args: List[str]) -> None:
        """Handle debug commands"""
        if not args:
            self.log_output("[!] Debug command required")
            return

        subcmd = args[0].lower()
        if subcmd == "connect":
            await self._debug_connect()
        elif subcmd == "halt":
            await self._debug_halt()
        elif subcmd == "reset":
            halt = len(args) > 1 and args[1].lower() == "halt"
            await self._debug_reset(halt)
        elif subcmd == "resume":
            await self._debug_resume()
        elif subcmd == "dump":
            filename = args[1] if len(args) > 1 else "firmware.bin"
            address = int(args[2], 16) if len(args) > 2 else 0x08000000
            size = int(args[3], 16) if len(args) > 3 else 0x10000
            await self._debug_dump(filename, address, size)
        elif subcmd == "regs":
            await self._debug_read_registers()
        elif subcmd == "read":
            if len(args) >= 3:
                address = int(args[1], 16)
                size = int(args[2], 16)
                await self._debug_read_memory(address, size)
            else:
                self.log_output("[!] Usage: debug read <address> <size>")

    async def _debug_connect(self) -> None:
        """Connect to target via OpenOCD"""
        from ...backends.backend_tigard import TigardDebugBackend

        self.log_output("[*] Starting OpenOCD...")

        try:
            # Get interface and target from UI
            interface_select = self.query_one("#debug-interface", Select)
            target_select = self.query_one("#debug-target", Select)

            interface = str(interface_select.value) if interface_select.value else "swd"
            target = str(target_select.value) if target_select.value else "auto"

            self.log_output(f"[*] Interface: {interface.upper()}")
            self.log_output(f"[*] Target: {target}")

            # Create debug backend
            self._debug_backend = TigardDebugBackend(self.device_info)
            self._debug_backend.set_interface(interface)
            self._debug_backend.set_target(target)

            if self._debug_backend.connect():
                self.log_output("[+] OpenOCD connected")
                self._update_debug_status("Connected", target)
            else:
                self.log_output("[!] OpenOCD connection failed")
                self.log_output("[*] Check that OpenOCD is installed and target is connected")
                self._debug_backend = None

        except Exception as e:
            self.log_output(f"[!] Debug connect error: {e}")

    def _update_debug_status(self, status: str, target: str = "---") -> None:
        """Update debug status display"""
        try:
            self.query_one("#openocd-status", Static).update(f"Status: {status}")
            self.query_one("#openocd-target", Static).update(f"Target: {target}")
        except Exception:
            pass

    async def _debug_halt(self) -> None:
        """Halt target CPU"""
        if not hasattr(self, '_debug_backend') or not self._debug_backend:
            self.log_output("[!] Not connected - run 'debug connect' first")
            return

        self.log_output("[*] Halting target...")
        if self._debug_backend.halt():
            self.log_output("[+] Target halted")
            # Try to read PC
            regs = self._debug_backend.read_registers()
            if 'pc' in regs:
                self.log_output(f"[*] PC: 0x{regs['pc']:08X}")
        else:
            self.log_output("[!] Halt failed")

    async def _debug_resume(self) -> None:
        """Resume target execution"""
        if not hasattr(self, '_debug_backend') or not self._debug_backend:
            self.log_output("[!] Not connected")
            return

        self.log_output("[*] Resuming target...")
        if self._debug_backend.resume():
            self.log_output("[+] Target running")
        else:
            self.log_output("[!] Resume failed")

    async def _debug_reset(self, halt: bool = False) -> None:
        """Reset target"""
        if not hasattr(self, '_debug_backend') or not self._debug_backend:
            self.log_output("[!] Not connected")
            return

        self.log_output(f"[*] Resetting target {'(halt)' if halt else ''}...")
        if self._debug_backend.reset(halt):
            self.log_output("[+] Target reset complete")
        else:
            self.log_output("[!] Reset failed")

    async def _debug_read_registers(self) -> None:
        """Read and display CPU registers"""
        if not hasattr(self, '_debug_backend') or not self._debug_backend:
            self.log_output("[!] Not connected")
            return

        self.log_output("[*] Reading registers...")
        regs = self._debug_backend.read_registers()

        if regs:
            for name, value in regs.items():
                self.log_output(f"  {name:6s}: 0x{value:08X}")
        else:
            self.log_output("[!] Failed to read registers")

    async def _debug_read_memory(self, address: int, size: int) -> None:
        """Read memory from target"""
        if not hasattr(self, '_debug_backend') or not self._debug_backend:
            self.log_output("[!] Not connected")
            return

        self.log_output(f"[*] Reading {size} bytes from 0x{address:08X}...")
        data = self._debug_backend.read_memory(address, size)

        if data:
            # Display as hex dump
            for i in range(0, min(len(data), 256), 16):
                hex_part = ' '.join(f'{b:02X}' for b in data[i:i+16])
                ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[i:i+16])
                self.log_output(f"  {address+i:08X}: {hex_part:<48} {ascii_part}")

            if len(data) > 256:
                self.log_output(f"  ... ({len(data)} bytes total)")
        else:
            self.log_output("[!] Memory read failed")

    async def _debug_dump(self, filename: str, address: int, size: int) -> None:
        """Dump firmware from target"""
        if not hasattr(self, '_debug_backend') or not self._debug_backend:
            self.log_output("[!] Not connected")
            return

        self.log_output(f"[*] Dumping {size:,} bytes from 0x{address:08X} to {filename}...")

        data = self._debug_backend.dump_firmware(address, size)
        if data:
            from pathlib import Path
            Path(filename).write_bytes(data)
            self.log_output(f"[+] Dump complete: {len(data):,} bytes written")
        else:
            self.log_output("[!] Dump failed")

    async def _handle_openocd_command(self, args: List[str]) -> None:
        """Handle OpenOCD commands"""
        if not args:
            self.log_output("[!] OpenOCD command required")
            return

        subcmd = args[0].lower()
        if subcmd == "start":
            self.log_output("[*] Starting OpenOCD server...")
            self.log_output("[*] Listening on localhost:3333 (GDB)")
            self.log_output("[*] Listening on localhost:4444 (telnet)")
        elif subcmd == "stop":
            self.log_output("[*] Stopping OpenOCD server...")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id
        if not button_id:
            return

        # SPI Flash buttons
        if button_id == "btn-detect":
            self.log_output("[*] Auto-detecting flash...")
            await self._handle_spi_command(["id"])
        elif button_id == "btn-read-id":
            await self._handle_spi_command(["id"])
        elif button_id == "btn-dump":
            # Get parameters from UI
            try:
                addr = self.query_one("#flash-addr", Input).value
                size = self.query_one("#flash-size-input", Input).value
                filename = self.query_one("#flash-file", Input).value
                await self._handle_spi_command(["dump", filename, addr, size])
            except Exception:
                await self._handle_spi_command(["dump"])
        elif button_id == "btn-erase":
            await self._handle_spi_command(["erase", "chip"])
        elif button_id == "btn-write":
            try:
                addr = self.query_one("#flash-addr", Input).value
                filename = self.query_one("#flash-file", Input).value
                await self._handle_spi_command(["write", filename, addr])
            except Exception:
                await self._handle_spi_command(["write"])

        # Debug buttons
        elif button_id == "btn-debug-connect":
            await self._debug_connect()
        elif button_id == "btn-debug-halt":
            await self._debug_halt()
        elif button_id == "btn-debug-reset":
            await self._debug_reset(halt=True)
        elif button_id == "btn-debug-resume":
            await self._debug_resume()
        elif button_id == "btn-read-mem":
            try:
                addr = int(self.query_one("#mem-addr", Input).value, 16)
                size = int(self.query_one("#mem-size", Input).value, 16)
                await self._debug_read_memory(addr, size)
            except Exception as e:
                self.log_output(f"[!] Invalid address/size: {e}")
        elif button_id == "btn-dump-fw":
            try:
                addr = int(self.query_one("#mem-addr", Input).value, 16)
                size = int(self.query_one("#mem-size", Input).value, 16)
                await self._debug_dump("firmware.bin", addr, size)
            except Exception as e:
                self.log_output(f"[!] Invalid parameters: {e}")
        elif button_id == "btn-flash-fw":
            self.log_output("[*] Flash firmware - use: debug flash <filename>")

        # UART buttons
        elif button_id == "btn-uart-start":
            await self._start_uart_bridge()
        elif button_id == "btn-uart-stop":
            await self._stop_uart_bridge()

    async def _start_uart_bridge(self) -> None:
        """Start UART bridge"""
        if not self._backend:
            self.log_output("[!] Not connected")
            return

        try:
            baud_select = self.query_one("#uart-baud", Select)
            baud = int(baud_select.value) if baud_select.value else 115200

            from ...backends import UARTConfig
            config = UARTConfig(baudrate=baud)

            if self._backend.configure_uart(config):
                self.log_output(f"[+] UART bridge started at {baud} baud")
                self.log_output("[*] Type in console to send data")
            else:
                self.log_output("[!] Failed to start UART bridge")
        except Exception as e:
            self.log_output(f"[!] UART error: {e}")

    async def _stop_uart_bridge(self) -> None:
        """Stop UART bridge"""
        self.log_output("[*] UART bridge stopped")
