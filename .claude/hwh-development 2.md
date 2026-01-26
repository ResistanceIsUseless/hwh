# HWH Tool Development Skill

> SKILL.md for developing the hwh (Hardware Hacking Toolkit) project

## Overview

This skill provides specialized knowledge for extending the `hwh` hardware hacking toolkit - a multi-device TUI for hardware security research built with Python and Textual.

## When to Use This Skill

- Adding new device backends (Bus Pirate, Tigard, ST-Link, etc.)
- Implementing protocol handlers (SPI, I2C, UART, JTAG, SWD)
- Building TUI panels and widgets
- Implementing fault injection campaigns
- Adding firmware analysis features
- Fixing hardware communication bugs

## Project Structure

```
hwh/
├── cli.py                  # Typer CLI entry point
├── detect.py               # Device auto-detection
├── glitch_profiles.py      # Target-specific glitch parameters
├── backends/
│   ├── base.py             # Abstract DeviceBackend class
│   ├── buspirate.py        # Bus Pirate 5/6 (pyBusPirateLite)
│   ├── bolt.py             # Curious Bolt glitcher
│   ├── tigard.py           # Tigard (pyftdi)
│   ├── stlink.py           # ST-Link (pyocd)
│   ├── bmp.py              # Black Magic Probe (GDB)
│   ├── faultycat.py        # Faulty Cat EMFI
│   └── sump.py             # SUMP logic analyzer protocol
├── firmware/
│   ├── extractor.py        # Firmware extraction (binwalk)
│   ├── analyzer.py         # Security analysis engine
│   └── patterns.py         # Vulnerability regex patterns
└── tui/
    ├── app.py              # Main Textual app
    ├── style.tcss          # Global styling
    └── panels/
        ├── device.py       # Device selection panel
        ├── serial.py       # UART terminal panel
        ├── spi.py          # SPI flash panel
        ├── glitch.py       # Glitching campaign panel
        ├── firmware.py     # Firmware analysis panel
        └── logic.py        # Logic analyzer panel
```

## Backend Implementation Pattern

```python
# backends/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable

class Protocol(Enum):
    UART = auto()
    SPI = auto()
    I2C = auto()
    JTAG = auto()
    SWD = auto()

@dataclass
class DeviceInfo:
    name: str
    port: str
    vid: int
    pid: int
    serial: str | None = None
    protocols: list[Protocol] = None

class DeviceBackend(ABC):
    """Abstract base class for hardware backends."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Device display name."""
    
    @property
    @abstractmethod
    def supported_protocols(self) -> list[Protocol]:
        """List of supported protocols."""
    
    @abstractmethod
    def connect(self, port: str) -> bool:
        """Establish connection to device."""
    
    @abstractmethod
    def disconnect(self) -> None:
        """Release device resources."""
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Check connection status."""
    
    # Optional protocol methods (implement if supported)
    def uart_write(self, data: bytes) -> None:
        raise NotImplementedError
    
    def uart_read(self, size: int, timeout: float = 1.0) -> bytes:
        raise NotImplementedError
    
    def spi_transfer(self, data: bytes) -> bytes:
        raise NotImplementedError
    
    def i2c_write(self, addr: int, data: bytes) -> None:
        raise NotImplementedError
    
    def i2c_read(self, addr: int, size: int) -> bytes:
        raise NotImplementedError
    
    def i2c_scan(self) -> list[int]:
        raise NotImplementedError
```

### Bus Pirate Backend Example

```python
# backends/buspirate.py
from .base import DeviceBackend, Protocol, DeviceInfo
import serial

class BusPirateBackend(DeviceBackend):
    """Bus Pirate 5/6 backend using pyBusPirateLite."""
    
    name = "Bus Pirate"
    supported_protocols = [Protocol.UART, Protocol.SPI, Protocol.I2C]
    
    VID_PID = [(0x1209, 0x7331)]  # Bus Pirate 5
    
    def __init__(self):
        self._port: str | None = None
        self._serial: serial.Serial | None = None
        self._mode: str | None = None
    
    def connect(self, port: str) -> bool:
        try:
            self._serial = serial.Serial(port, 115200, timeout=0.5)
            self._port = port
            # Enter binary mode
            for _ in range(20):
                self._serial.write(b'\x00')
            response = self._serial.read(5)
            return response == b'BBIO1'
        except serial.SerialException:
            return False
    
    def disconnect(self) -> None:
        if self._serial:
            # Reset to terminal mode
            self._serial.write(b'\x0F')
            self._serial.close()
            self._serial = None
    
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open
    
    def enter_spi_mode(self) -> bool:
        if not self.is_connected():
            return False
        self._serial.write(b'\x01')  # Enter SPI mode
        response = self._serial.read(4)
        self._mode = "spi" if response == b'SPI1' else None
        return self._mode == "spi"
    
    def spi_transfer(self, data: bytes) -> bytes:
        if self._mode != "spi":
            self.enter_spi_mode()
        
        # Bulk transfer command
        length = len(data)
        if length > 16:
            raise ValueError("Bulk transfer limited to 16 bytes")
        
        self._serial.write(bytes([0x10 | (length - 1)]))
        self._serial.write(data)
        
        response = self._serial.read(1)  # ACK
        if response != b'\x01':
            raise IOError("SPI transfer failed")
        
        return self._serial.read(length)
    
    def spi_cs(self, active: bool) -> None:
        """Control chip select."""
        cmd = 0x02 if active else 0x03
        self._serial.write(bytes([cmd]))
        self._serial.read(1)  # ACK
```

### Tigard Backend Example

```python
# backends/tigard.py
from .base import DeviceBackend, Protocol
from pyftdi.spi import SpiController
from pyftdi.i2c import I2cController
from pyftdi.ftdi import Ftdi

class TigardBackend(DeviceBackend):
    """Tigard multi-protocol tool using pyftdi."""
    
    name = "Tigard"
    supported_protocols = [Protocol.SPI, Protocol.I2C, Protocol.UART, Protocol.JTAG]
    
    VID_PID = [(0x0403, 0x6010)]  # FTDI FT2232H
    
    def __init__(self):
        self._url: str | None = None
        self._spi: SpiController | None = None
        self._i2c: I2cController | None = None
    
    @classmethod
    def enumerate(cls) -> list[str]:
        """List available Tigard devices."""
        devices = []
        for dev in Ftdi.list_devices():
            if (dev[0].vid, dev[0].pid) in cls.VID_PID:
                serial = dev[0].sn
                if serial and serial.startswith("TG"):
                    devices.append(f"ftdi://ftdi:2232:{serial}/2")
        return devices
    
    def connect(self, url: str) -> bool:
        try:
            self._url = url
            return True
        except Exception:
            return False
    
    def disconnect(self) -> None:
        if self._spi:
            self._spi.terminate()
            self._spi = None
        if self._i2c:
            self._i2c.terminate()
            self._i2c = None
    
    def _get_spi(self) -> SpiController:
        if not self._spi:
            self._spi = SpiController()
            self._spi.configure(self._url)
        return self._spi
    
    def spi_transfer(self, data: bytes, freq: float = 1e6) -> bytes:
        spi = self._get_spi()
        port = spi.get_port(cs=0, freq=freq, mode=0)
        return port.exchange(data)
    
    def spi_read_flash(self, address: int, size: int) -> bytes:
        """Read from SPI flash using standard READ command."""
        spi = self._get_spi()
        port = spi.get_port(cs=0, freq=12e6, mode=0)
        
        cmd = bytes([0x03,  # READ command
                     (address >> 16) & 0xFF,
                     (address >> 8) & 0xFF,
                     address & 0xFF])
        
        return port.exchange(cmd, size)
    
    def spi_read_jedec_id(self) -> tuple[int, int, int]:
        """Read JEDEC manufacturer/device ID."""
        data = self.spi_transfer(bytes([0x9F, 0, 0, 0]))
        return data[0], data[1], data[2]
```

## TUI Panel Pattern

```python
# tui/panels/spi.py
from textual.app import ComposeResult
from textual.widgets import Static, Button, Input, DataTable, ProgressBar, RichLog
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual import work, on
from textual.worker import get_current_worker

class SPIFlashPanel(Static):
    """SPI flash read/write panel."""
    
    DEFAULT_CSS = """
    SPIFlashPanel {
        layout: grid;
        grid-size: 2;
        grid-columns: 1fr 2fr;
        height: 100%;
    }
    
    #controls {
        border: solid $primary;
        padding: 1;
    }
    
    #output {
        border: solid $secondary;
    }
    """
    
    jedec_id: reactive[tuple | None] = reactive(None)
    flash_size: reactive[int] = reactive(0)
    progress: reactive[float] = reactive(0.0)
    
    def compose(self) -> ComposeResult:
        with Vertical(id="controls"):
            yield Static("SPI Flash", classes="title")
            yield Static("JEDEC ID: --", id="jedec-label")
            yield Static("Size: --", id="size-label")
            yield Horizontal(
                Button("Detect", id="detect"),
                Button("Dump", id="dump"),
                Button("Verify", id="verify"),
            )
            yield Input(placeholder="Output file", id="output-path")
            yield ProgressBar(total=100, id="progress")
        
        with Vertical(id="output"):
            yield RichLog(id="log", highlight=True)
    
    def watch_jedec_id(self, value: tuple | None) -> None:
        if value:
            mfr, typ, cap = value
            text = f"JEDEC ID: {mfr:02X} {typ:02X} {cap:02X}"
            self.query_one("#jedec-label").update(text)
    
    def watch_flash_size(self, value: int) -> None:
        if value:
            mb = value / (1024 * 1024)
            self.query_one("#size-label").update(f"Size: {mb:.1f} MB")
    
    def watch_progress(self, value: float) -> None:
        self.query_one("#progress", ProgressBar).update(progress=value)
    
    @on(Button.Pressed, "#detect")
    def detect_flash(self) -> None:
        self.run_detect()
    
    @work(thread=True, exclusive=True)
    def run_detect(self) -> None:
        """Detect flash chip in background."""
        log = self.query_one("#log", RichLog)
        self.call_from_thread(log.write, "[cyan]Detecting flash...[/]")
        
        try:
            backend = self.app.get_active_backend()
            mfr, typ, cap = backend.spi_read_jedec_id()
            
            self.call_from_thread(setattr, self, "jedec_id", (mfr, typ, cap))
            
            # Calculate size from capacity code
            size = 1 << cap if cap < 32 else 0
            self.call_from_thread(setattr, self, "flash_size", size)
            
            self.call_from_thread(
                log.write,
                f"[green]Flash detected: {self.get_chip_name(mfr, typ)}[/]"
            )
        except Exception as e:
            self.call_from_thread(
                log.write,
                f"[red]Detection failed: {e}[/]"
            )
    
    @on(Button.Pressed, "#dump")
    def dump_flash(self) -> None:
        output_path = self.query_one("#output-path", Input).value
        if not output_path:
            self.notify("Enter output file path", severity="warning")
            return
        self.run_dump(output_path)
    
    @work(thread=True, exclusive=True)
    def run_dump(self, output_path: str) -> None:
        """Dump flash to file in background."""
        worker = get_current_worker()
        log = self.query_one("#log", RichLog)
        
        if not self.flash_size:
            self.call_from_thread(log.write, "[red]Detect flash first[/]")
            return
        
        try:
            backend = self.app.get_active_backend()
            chunk_size = 4096
            
            with open(output_path, 'wb') as f:
                for offset in range(0, self.flash_size, chunk_size):
                    if worker.is_cancelled:
                        self.call_from_thread(log.write, "[yellow]Dump cancelled[/]")
                        return
                    
                    chunk = backend.spi_read_flash(offset, chunk_size)
                    f.write(chunk)
                    
                    progress = (offset + chunk_size) / self.flash_size * 100
                    self.call_from_thread(setattr, self, "progress", progress)
            
            self.call_from_thread(
                log.write,
                f"[green]Dump complete: {output_path}[/]"
            )
        except Exception as e:
            self.call_from_thread(log.write, f"[red]Dump failed: {e}[/]")
    
    @staticmethod
    def get_chip_name(mfr: int, typ: int) -> str:
        """Lookup chip name from JEDEC ID."""
        chips = {
            (0xEF, 0x40): "Winbond W25Qxx",
            (0xC2, 0x20): "Macronix MX25Lxx",
            (0x1F, 0x86): "Atmel/Microchip AT25SFxxx",
            (0xBF, 0x25): "SST SST25VFxxx",
        }
        return chips.get((mfr, typ), f"Unknown ({mfr:02X}:{typ:02X})")
```

## Glitch Campaign Implementation

```python
# tui/panels/glitch.py
from textual.widgets import Static, Button, Input, DataTable, RichLog
from textual.reactive import reactive
from textual import work
from textual.worker import get_current_worker
from dataclasses import dataclass
from enum import Enum
import json

class GlitchResult(Enum):
    SUCCESS = "SUC"   # Security bypassed
    NORMAL = "NRM"    # Normal operation
    RESET = "RST"     # Target reset
    HANG = "HNG"      # No response

@dataclass
class GlitchPoint:
    delay: int
    width: int
    result: GlitchResult
    response: bytes = b""

class GlitchCampaignPanel(Static):
    """Voltage glitching campaign panel."""
    
    results: reactive[list[GlitchPoint]] = reactive([])
    running: reactive[bool] = reactive(False)
    
    def compose(self) -> ComposeResult:
        with Vertical(id="params"):
            yield Static("Glitch Parameters")
            yield Input(placeholder="Delay min", id="delay-min", value="1000")
            yield Input(placeholder="Delay max", id="delay-max", value="5000")
            yield Input(placeholder="Delay step", id="delay-step", value="10")
            yield Input(placeholder="Width min", id="width-min", value="10")
            yield Input(placeholder="Width max", id="width-max", value="100")
            yield Input(placeholder="Width step", id="width-step", value="5")
            yield Button("Start Campaign", id="start", variant="primary")
            yield Button("Stop", id="stop", variant="error")
        
        with Vertical(id="results"):
            yield DataTable(id="results-table")
            yield Static(id="heatmap")
            yield RichLog(id="log")
    
    def on_mount(self) -> None:
        table = self.query_one("#results-table", DataTable)
        table.add_columns("Delay", "Width", "Result", "Details")
    
    @on(Button.Pressed, "#start")
    def start_campaign(self) -> None:
        params = {
            "delay_min": int(self.query_one("#delay-min", Input).value),
            "delay_max": int(self.query_one("#delay-max", Input).value),
            "delay_step": int(self.query_one("#delay-step", Input).value),
            "width_min": int(self.query_one("#width-min", Input).value),
            "width_max": int(self.query_one("#width-max", Input).value),
            "width_step": int(self.query_one("#width-step", Input).value),
        }
        self.running = True
        self.run_campaign(params)
    
    @on(Button.Pressed, "#stop")
    def stop_campaign(self) -> None:
        self.running = False
        for worker in self.workers:
            worker.cancel()
    
    @work(thread=True, exclusive=True)
    def run_campaign(self, params: dict) -> None:
        """Execute glitch parameter sweep."""
        worker = get_current_worker()
        log = self.query_one("#log", RichLog)
        
        backend = self.app.get_active_backend()
        
        for delay in range(params["delay_min"], params["delay_max"], params["delay_step"]):
            for width in range(params["width_min"], params["width_max"], params["width_step"]):
                if worker.is_cancelled or not self.running:
                    self.call_from_thread(log.write, "[yellow]Campaign stopped[/]")
                    return
                
                # Execute glitch
                backend.set_glitch_params(delay=delay, width=width)
                backend.power_cycle_target()
                backend.arm_glitch()
                backend.trigger_glitch()
                
                response = backend.read_target_response(timeout=1.0)
                result = self.classify_response(response)
                
                point = GlitchPoint(delay, width, result, response)
                self.call_from_thread(self.add_result, point)
                
                if result == GlitchResult.SUCCESS:
                    self.call_from_thread(
                        log.write,
                        f"[bold green]SUCCESS at delay={delay}, width={width}[/]"
                    )
                    # Optionally stop on first success
                    # return
    
    def add_result(self, point: GlitchPoint) -> None:
        """Add result to table and update heatmap."""
        table = self.query_one("#results-table", DataTable)
        
        colors = {
            GlitchResult.SUCCESS: "green",
            GlitchResult.RESET: "yellow",
            GlitchResult.HANG: "red",
            GlitchResult.NORMAL: "dim",
        }
        
        table.add_row(
            str(point.delay),
            str(point.width),
            f"[{colors[point.result]}]{point.result.value}[/]",
            point.response[:20].hex() if point.response else "--"
        )
        
        self.results = self.results + [point]
    
    def classify_response(self, response: bytes | None) -> GlitchResult:
        """Classify glitch outcome from target response."""
        if response is None or len(response) == 0:
            return GlitchResult.HANG
        
        # Customize based on target
        if b"ACCESS GRANTED" in response or b"UNLOCKED" in response:
            return GlitchResult.SUCCESS
        elif b"RESET" in response or b"\x00" * 10 in response:
            return GlitchResult.RESET
        else:
            return GlitchResult.NORMAL
    
    def export_results(self, path: str) -> None:
        """Export campaign results to JSON."""
        data = [
            {
                "delay": p.delay,
                "width": p.width,
                "result": p.result.value,
                "response": p.response.hex()
            }
            for p in self.results
        ]
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
```

## Protocol Reference

### SPI Flash Commands
| Command | Opcode | Description |
|---------|--------|-------------|
| RDID | 0x9F | Read JEDEC ID |
| READ | 0x03 | Read data |
| FAST_READ | 0x0B | Fast read (with dummy byte) |
| WREN | 0x06 | Write enable |
| WRDI | 0x04 | Write disable |
| PP | 0x02 | Page program (256 bytes) |
| SE | 0x20 | Sector erase (4KB) |
| BE | 0xD8 | Block erase (64KB) |
| CE | 0xC7 | Chip erase |
| RDSR | 0x05 | Read status register |

### I2C EEPROM Addressing
- 24C01-24C16: 7-bit device address + internal address
- 24C32+: 7-bit device address + 16-bit internal address
- Common addresses: 0x50-0x57 (A0-A2 pins select)

### JTAG Standard Instructions
| Instruction | Description |
|-------------|-------------|
| BYPASS | Pass through (0xFF typically) |
| IDCODE | Read device ID |
| EXTEST | External boundary scan test |
| SAMPLE | Sample boundary scan register |
| INTEST | Internal test |

## Testing Without Hardware

```python
# backends/mock.py
class MockBackend(DeviceBackend):
    """Mock backend for testing without hardware."""
    
    name = "Mock Device"
    supported_protocols = [Protocol.SPI, Protocol.I2C, Protocol.UART]
    
    def __init__(self):
        self._connected = False
        self._flash_data = bytes([0xFF] * 0x100000)  # 1MB fake flash
    
    def connect(self, port: str) -> bool:
        self._connected = True
        return True
    
    def disconnect(self) -> None:
        self._connected = False
    
    def is_connected(self) -> bool:
        return self._connected
    
    def spi_read_jedec_id(self) -> tuple:
        return (0xEF, 0x40, 0x17)  # Fake W25Q64
    
    def spi_read_flash(self, address: int, size: int) -> bytes:
        return self._flash_data[address:address + size]
```

## Dependencies

```toml
# pyproject.toml
[project]
dependencies = [
    "textual>=0.50.0",
    "pyserial>=3.5",
    "pyftdi>=0.55.0",
    "pyocd>=0.36.0",
    "typer>=0.12.0",
    "rich>=13.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "black>=24.0",
    "ruff>=0.3.0",
]
```

## References

- Bus Pirate: https://buspirate.com/
- pyftdi: https://eblot.github.io/pyftdi/
- pyOCD: https://pyocd.io/
- Textual: https://textual.textualize.io/
