# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

hwh is a multi-device TUI for hardware security research built with Python and Textual. It provides a unified interface to control hardware hacking tools: Bus Pirate 5/6, Curious Bolt, Tigard, ST-Link, Black Magic Probe, FaultyCat, and TI-Link.

## Development Commands

```bash
# Install in development mode
pip install -e ".[dev]"

# Run the TUI
hwh              # or: python -m hwh tui

# Run tests
pytest
pytest tests/test_cli.py -v  # single test file

# Code quality
black src/
ruff check src/

# Type checking
mypy src/

# Test BPIO2 connection (Bus Pirate 5/6)
python scripts/test_bpio2_status.py /dev/cu.usbmodem6buspirate3
```

## Architecture

### High-Level Structure

```
src/hwh/
├── cli.py                 # Click CLI entry point (hwh command)
├── detect.py              # USB/serial device detection (KNOWN_USB_DEVICES map)
├── backends/              # Device abstraction layer
│   ├── base.py            # Abstract base classes: Backend, BusBackend, DebugBackend, GlitchBackend
│   ├── backend_buspirate.py  # Bus Pirate 5/6 backend (uses pybpio)
│   ├── backend_bolt.py    # Curious Bolt backend
│   ├── backend_tigard.py  # Tigard backend
│   ├── backend_stlink.py  # ST-Link backend
│   ├── backend_blackmagic.py # Black Magic Probe backend
│   └── sump.py            # SUMP protocol for logic analyzers
├── pybpio/                # Bundled BPIO2 FlatBuffers library for Bus Pirate 5/6
│   ├── bpio_client.py     # BPIOClient class (serial + COBS + FlatBuffers)
│   ├── bpio_spi.py        # SPI protocol handler
│   ├── bpio_i2c.py        # I2C protocol handler
│   ├── bpio_uart.py       # UART protocol handler (firmware support limited)
│   ├── bpio_1wire.py      # 1-Wire protocol handler
│   └── tooling/bpio/      # Generated FlatBuffers Python code
├── tooling/               # Device-specific tooling
│   └── bolt/              # Curious Bolt scope utilities
├── firmware/              # Firmware extraction and analysis (binwalk integration)
├── automation/            # High-level automation utilities (UART interaction, etc.)
├── tui/
│   ├── app.py             # Main Textual TUI application
│   ├── device_pool.py     # Manages connected device instances
│   ├── config.py          # User configuration (~/.config/hwh/config.toml)
│   ├── campaign.py        # Glitch campaign management
│   ├── conditions.py      # Response classification (SUC/RST/HNG/NRM)
│   ├── style.tcss         # Metagross-inspired color scheme
│   └── panels/            # Device-specific UI panels
│       ├── base.py        # DevicePanel base class + PanelCapability enum
│       ├── buspirate.py   # Bus Pirate panel (SPI, I2C, UART, Protocol modes)
│       ├── bolt.py        # Curious Bolt panel (glitching, power analysis)
│       ├── tigard.py      # Tigard panel
│       ├── firmware.py    # Firmware analysis panel
│       ├── logic_analyzer.py # Logic analyzer widget (SUMP waveforms)
│       └── uart_monitor.py   # Generic UART monitor panel
└── workflows/             # Multi-device coordinated workflows
    ├── base.py            # Workflow, WorkflowStatus, WorkflowResult
    ├── adaptive_glitch.py # Adaptive glitch parameter search
    └── glitch_monitor.py  # Coordinated glitch+monitor workflows
```

### Backend System

All device backends inherit from abstract base classes in `backends/base.py`:

- **`Backend`**: Base connection management, status, capabilities
- **`BusBackend`**: SPI/I2C/UART protocol operations
- **`DebugBackend`**: SWD/JTAG debug operations
- **`GlitchBackend`**: Voltage/clock glitch fault injection

**Registration**: Backends register using `@register_backend(device_type)` decorator. The TUI retrieves backends via `get_backend(device: DeviceInfo)`.

**Example**: `BusPirateBackend` inherits from `BusBackend` and implements SPI/I2C/UART using the bundled `pybpio` library, with fallback to serial terminal commands when BPIO2 is unavailable.

### Device Detection

`detect.py` contains:
- **`KNOWN_USB_DEVICES`**: Dictionary mapping `(VID, PID)` tuples to `(name, device_type, capabilities)`
- **`detect()`**: Uses pyusb + pyserial to enumerate devices and match against known devices
- **Runtime identification**: RP2040 devices (Bolt/FaultyCat) share VID:PID and require serial probing to differentiate

### TUI Architecture

**Device Tabs**: Each connected device gets a dedicated tab with a device-specific panel (`tui/panels/`). Panels inherit from `DevicePanel` and declare capabilities via `PanelCapability` enum (SPI, I2C, UART, GLITCH, etc.).

**Split View**: `SplitView` container shows two device panels side-by-side. Uses `SplitPanelMirror` to avoid duplicate connections - mirrors subscribe to output events from the source panel.

**Worker Pattern**: Critical for non-blocking hardware I/O. Use `@work(thread=True)` for all serial/USB operations:

```python
@work(exclusive=True, thread=True)
def serial_reader(self, port: str) -> None:
    worker = get_current_worker()
    ser = serial.Serial(port, 115200, timeout=0.1)
    while not worker.is_cancelled:
        data = ser.read(1024)
        if data:
            self.call_from_thread(self.handle_rx, data)
    ser.close()
```

**Device Pool**: `DevicePool` manages active backend instances, ensuring only one connection per device. Panels request backends from the pool.

**Coordination View**: F4 opens a multi-device coordination tab for synchronized operations:
- Left panel: UART monitor for target output
- Right panel: Glitcher controls (arm/trigger/disarm)
- Bottom panel: Logic analyzer waveform display

### BPIO2 Protocol (Bus Pirate 5/6)

- **Bundled Library**: `src/hwh/pybpio/` contains the official BPIO2 FlatBuffers library
- **Serial Interface**: Uses COBS encoding over serial (`bpio_client.py`)
- **Ports**: Bus Pirate exposes two CDC interfaces:
  - `buspirate1`: Terminal/console (115200 baud)
  - `buspirate3`: BPIO2 binary interface (3000000 baud)
- **Protocol Handlers**: `bpio_spi.py`, `bpio_i2c.py`, `bpio_uart.py` wrap FlatBuffers operations
- **Limitation**: UART mode not implemented in BPIO2 firmware - backend falls back to terminal commands

### SUMP Logic Analyzer

The SUMP protocol (`backends/sump.py`) provides logic analyzer functionality for compatible devices:

- **Protocol**: Open Logic Sniffer / SUMP compatible
- **Devices**: Bus Pirate 5/6, Curious Bolt (when in logic analyzer mode)
- **Features**: 8-channel capture, configurable sample rate, trigger support
- **Widget**: `tui/panels/logic_analyzer.py` provides waveform visualization

### Workflows System

Multi-device workflows (`workflows/`) coordinate operations across devices:

- **`Workflow`**: Abstract base with status tracking, progress reporting, cancellation
- **`adaptive_glitch.py`**: Intelligent parameter sweeping with success detection
- **`glitch_monitor.py`**: Coordinates glitcher + monitor device (e.g., Bolt + Bus Pirate)

Example: Glitch STM32 while monitoring UART for success condition.

### Firmware Analysis

Pipeline in `firmware/`:
- **`extractor.py`**: Binwalk integration for filesystem extraction (SquashFS, JFFS2, UBIFS, CPIO)
- **`analyzer.py`**: Security scanning (credentials, hardcoded keys, unsafe functions in ELF binaries)
- **`patterns.py`**: Regex patterns for vulnerability detection

## TUI Key Bindings

| Key | Action |
|-----|--------|
| `F1` | Devices tab (discovery) |
| `F2` | Firmware analysis tab |
| `F3` | Toggle split view |
| `F4` | Coordination view (multi-device) |
| `F5` | Refresh devices |
| `F12` | Show help |
| `Ctrl+Q` | Quit |
| `Escape` | Return to discovery tab |

## Bus Pirate 5/6 Critical Notes

- **Only BP5 and BP6 supported** - older versions (v3, v4) are NOT supported
- **Use BPIO2 interface** - binary CDC interface (`buspirate3` port), NOT the terminal interface
- **UART limitation**: UART BPIO2 not implemented in firmware - use terminal fallback
- **Documentation**: https://docs.buspirate.com/docs/binmode-reference/protocol-bpio2/

## Hardware Protocol Quick Reference

### UART
- Common baud rates: 9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600
- Frame: Start bit, 5-9 data bits, parity (N/O/E), 1-2 stop bits
- Security targets: Debug consoles, U-Boot, root shells

### SPI Flash Commands
- RDID (0x9F): Read JEDEC ID
- READ (0x03): Read data
- WREN (0x06): Write enable
- PP (0x02): Page program
- SE (0x20): Sector erase
- BE (0xD8): Block erase
- CE (0xC7): Chip erase

### I2C
- 2-wire: SDA, SCL with pull-ups (4.7kΩ typical)
- 7-bit addressing (0x00-0x77), 10-bit extended
- Common targets: EEPROMs (24Cxx), sensors, authentication ICs

### JTAG
- 5-wire: TDI, TDO, TCK, TMS, TRST (optional)
- Standard instructions: BYPASS (0xFF), IDCODE, EXTEST, SAMPLE

### SWD (ARM)
- 2-wire alternative to JTAG: SWDIO, SWCLK
- ARM CoreSight debug architecture
- Debug registers: DHCSR, DCRSR, DCRDR, DEMCR

## Voltage Glitching Quick Reference

**Theory**: Brief voltage drops cause timing violations, leading to instruction skips, branch corruption, or register corruption.

**Parameters**:
- **Delay**: Trigger → glitch offset (ns/μs)
- **Width**: Glitch pulse duration (10-500ns typical)
- **Voltage**: VCC drop amount

**Common Targets**:
- RDP/ROP bypass (STM32, nRF52, LPC)
- Secure boot signature verification
- AES key schedule corruption
- Bootloader authentication

**Search Pattern**:
```python
for delay in range(delay_min, delay_max, delay_step):
    for width in range(width_min, width_max, width_step):
        glitcher.set_delay(delay)
        glitcher.set_length(width)
        glitcher.power_cycle_target()
        glitcher.arm()
        result = classify_response(glitcher.read())
        # SUC=success, RST=reset, HNG=hang, NRM=normal
```

## Memory Maps (Common MCUs)

**STM32F4**:
- Flash: 0x08000000 (up to 2MB)
- SRAM: 0x20000000 (up to 256KB)
- Option bytes: 0x1FFFC000

**nRF52840**:
- Flash: 0x00000000 (1MB)
- SRAM: 0x20000000 (256KB)
- FICR: 0x10000000, UICR: 0x10001000

## Code Practices

- Type hints everywhere (Python 3.10+)
- Async patterns for hardware I/O (Textual workers)
- Dataclasses for configuration
- Rich logging for debug output
- Wrap all hardware operations in try/except with `serial.SerialException`, `usb.core.USBError`
- Implement retry logic with exponential backoff
- Always release hardware resources in finally blocks

## Configuration

- User config: `~/.config/hwh/config.toml`
- Never hardcode paths, regex patterns, or magic values
- Use config file for all configurable parameters

## Git Workflow

- Always use feature branches (e.g., `feature/bp-status-tab`)
- Commit frequently - small, incremental commits
- Never use `git checkout HEAD --` to restore files - destroys uncommitted work
- Use `git stash` before risky operations

## Reference Code

The `temp/` directory contains reference implementations (not shipped with package):

| Directory | Description |
|-----------|-------------|
| `temp/bpio2-reference/` | Official BPIO2 FlatBuffers library and Python bindings |
| `temp/bolt/` | Curious Bolt firmware and hardware reference |
| `temp/faultycat/` | FaultyCat EMFI glitcher reference |
| `temp/bp5-firmware/` | Bus Pirate 5 firmware source (PIO, pin definitions) |
| `temp/glitch-o-bolt/` | Glitch-o-Bolt TUI reference (design inspiration) |

## External Documentation

**Black Magic Probe**: https://black-magic.org/getting-started.html
**Bus Pirate 5/6**: https://docs.buspirate.com/docs/command-reference/
**Curious Bolt**: https://bolt.curious.supplies/docs/getting-started/
**Tigard**: https://github.com/tigard-tools/tigard
**STM32 Debug**: https://stm32-base.org/guides/connecting-your-debugger.html
