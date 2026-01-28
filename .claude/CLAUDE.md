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
pytest tests/test_tui.py -v  # TUI tests

# Code quality
black src/
ruff check src/

# Type checking
mypy src/

# CLI Commands
hwh devices                    # List connected devices
hwh devices --json             # JSON output for scripting
hwh devices --all              # Include unknown devices
hwh spi dump -d "Bus Pirate 5" -o dump.bin  # Dump SPI flash
hwh glitch sweep --device "Curious Bolt" --width 100-500  # Glitch sweep
hwh firmware extract firmware.bin           # Extract filesystems
hwh firmware analyze extracted_dir/         # Analyze for vulnerabilities

# Debug Scripts (for development/troubleshooting)
python scripts/test_bpio2_status.py /dev/cu.usbmodem6buspirate3  # Test BPIO2 connection
python scripts/test_bp_sump.py /dev/cu.usbmodem6buspirate3       # Test logic analyzer
python scripts/test_bpio2_uart.py /dev/cu.usbmodem6buspirate3    # Test UART functionality
python scripts/debug_startup.py                                   # Debug TUI startup

# Docker (for isolated testing)
docker build -t hwh .
docker run -it --privileged -v /dev:/dev hwh
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
│   ├── backend_tilink.py  # TI-Link backend (MSP-FET, XDS)
│   ├── backend_faultycat.py # FaultyCat EMFI glitcher backend
│   ├── sump.py            # SUMP protocol for logic analyzers
│   └── BACKEND_TODO.md    # Backend implementation status and roadmap
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
│   ├── extractor.py       # Filesystem extraction engine
│   ├── analyzer.py        # Basic security scanning
│   ├── analyzer_advanced.py # LinPEAS-style privilege escalation checks
│   ├── patterns.py        # Regex patterns for vulnerability detection
│   └── types.py           # Shared types and dataclasses
├── automation/            # High-level automation utilities (UART interaction, etc.)
├── coordination/          # Multi-device trigger routing
│   ├── coordinator.py     # Coordinator class for device orchestration
│   └── triggers.py        # Trigger conditions and actions
├── tui/
│   ├── app.py             # Main Textual TUI application
│   ├── device_pool.py     # Manages connected device instances
│   ├── config.py          # User configuration (~/.config/hwh/config.toml)
│   ├── campaign.py        # Glitch campaign management
│   ├── conditions.py      # Response classification (SUC/RST/HNG/NRM)
│   ├── style.tcss         # Metagross-inspired color scheme
│   ├── REDESIGN.md        # TUI redesign documentation
│   └── panels/            # Device-specific UI panels
│       ├── base.py        # DevicePanel base class + PanelCapability enum
│       ├── buspirate.py   # Bus Pirate panel (SPI, I2C, UART, Protocol modes)
│       ├── bolt.py        # Curious Bolt panel (glitching, power analysis)
│       ├── tigard.py      # Tigard panel
│       ├── stlink.py      # ST-Link panel
│       ├── blackmagic.py  # Black Magic Probe panel
│       ├── tilink.py      # TI-Link panel
│       ├── faultycat.py   # FaultyCat panel
│       ├── firmware.py    # Firmware analysis panel (F2)
│       ├── calibration.py # Glitch calibration panel (F6)
│       ├── logic_analyzer.py # Logic analyzer widget (SUMP waveforms)
│       ├── protocol_decoders.py # SPI/I2C/UART protocol decoders
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

**Implementation Status**: See `backends/BACKEND_TODO.md` for detailed completion status of each backend. Key points:
- BusPirateBackend: ~70% complete (SPI/I2C/UART working, flash operations are stubs)
- BoltBackend: ~60% complete (native library required, serial fallback incomplete)
- TigardBackend: ~40% complete (basic protocols working, OpenOCD integration needed)
- FaultyCatBackend, TILinkBackend, BlackMagicBackend: Need creation

### Device Detection

`detect.py` contains:
- **`KNOWN_USB_DEVICES`**: Dictionary mapping `(VID, PID)` tuples to `(name, device_type, capabilities)`
- **`detect()`**: Uses pyusb + pyserial to enumerate devices and match against known devices
- **Runtime identification**: RP2040 devices (Bolt/FaultyCat) share VID:PID and require serial probing to differentiate

### TUI Architecture

**Device Tabs**: Each connected device gets a dedicated tab with a device-specific panel (`tui/panels/`). Panels inherit from `DevicePanel` and declare capabilities via `PanelCapability` enum (SPI, I2C, UART, GLITCH, etc.).

**Multi-Device Support**: The TUI was completely redesigned to support multiple simultaneous device connections. See `tui/REDESIGN.md` for details on:
- Device list sidebar with status indicators (● connected, ○ disconnected)
- Per-device connection management
- Adaptive controls based on device capabilities
- glitch-o-bolt inspired styling

**Split View**: `SplitView` container shows two device panels side-by-side. Uses `SplitPanelMirror` to avoid duplicate connections - mirrors subscribe to output events from the source panel.

**Worker Pattern**: Critical for non-blocking hardware I/O. Use `@work(thread=True)` for all serial/USB operations:

```python
@work(exclusive=True, thread=True)
def serial_reader(self, port: str) -> None:
    worker = get_current_worker()
    ser = serial.Serial(port, 115200, timeout=0.1)
    try:
        while not worker.is_cancelled:
            data = ser.read(1024)
            if data:
                self.call_from_thread(self.handle_rx, data)
    finally:
        ser.close()
```

**Device Pool**: `DevicePool` manages active backend instances, ensuring only one connection per device. Panels request backends from the pool.

**Coordination View**: F4 opens a multi-device coordination tab for synchronized operations:
- Left panel: UART monitor for target output
- Right panel: Glitcher controls (arm/trigger/disarm)
- Bottom panel: Logic analyzer waveform display
- Note: Hardware integration still in progress, UI complete

### BPIO2 Protocol (Bus Pirate 5/6)

- **Bundled Library**: `src/hwh/pybpio/` contains the official BPIO2 FlatBuffers library
- **Serial Interface**: Uses COBS encoding over serial (`bpio_client.py`)
- **Ports**: Bus Pirate exposes two CDC interfaces:
  - `buspirate1`: Terminal/console (115200 baud)
  - `buspirate3`: BPIO2 binary interface (3000000 baud)
- **Protocol Handlers**: `bpio_spi.py`, `bpio_i2c.py`, `bpio_uart.py` wrap FlatBuffers operations
- **Limitation**: UART mode not implemented in BPIO2 firmware - backend falls back to terminal commands
- **Testing**: Use `scripts/test_bpio2_status.py` to verify BPIO2 connectivity

### SUMP Logic Analyzer

The SUMP protocol (`backends/sump.py`) provides logic analyzer functionality for compatible devices:

- **Protocol**: Open Logic Sniffer / SUMP compatible
- **Devices**: Bus Pirate 5/6, Curious Bolt (when in logic analyzer mode)
- **Features**: 8-channel capture, configurable sample rate, trigger support
- **Widget**: `tui/panels/logic_analyzer.py` provides waveform visualization
- **Decoders**: `tui/panels/protocol_decoders.py` implements SPI, I2C, UART protocol decoding
- **Testing**: Use `scripts/test_bp_sump.py` to test logic analyzer functionality

### Workflows System

Multi-device workflows (`workflows/`) coordinate operations across devices:

- **`Workflow`**: Abstract base with status tracking, progress reporting, cancellation
- **`adaptive_glitch.py`**: Intelligent parameter sweeping with success detection
- **`glitch_monitor.py`**: Coordinates glitcher + monitor device (e.g., Bolt + Bus Pirate)

Example: Glitch STM32 while monitoring UART for success condition.

### Firmware Analysis

Pipeline in `firmware/`:
- **`extractor.py`**: Binwalk integration for filesystem extraction (SquashFS, JFFS2, UBIFS, CPIO, TAR, ZIP, uImage)
- **`analyzer.py`**: Basic security scanning (credentials, hardcoded keys, unsafe functions in ELF binaries)
- **`analyzer_advanced.py`**: Advanced LinPEAS-style checks:
  - SUID/SGID binaries
  - Writable system paths
  - Sudo configuration analysis
  - Cron jobs and scheduled tasks
  - Init scripts and services
  - Software inventory (opkg, dpkg, rpm)
  - Weak file permissions
- **`patterns.py`**: Regex patterns for vulnerability detection

**Firmware Panel (F2)** provides:
- Load firmware files (.bin, .img) or extracted directories
- Automatic filesystem detection and extraction
- Nested archive handling (archives within archives, including uImage)
- Lazy-loading file browser for large filesystems
- Security pattern search (credentials, API keys, private keys, backdoors)
- Binary analysis (unsafe functions, buffer overflows, custom binaries)
- Service detection (systemd, init.d, xinetd)
- Software inventory with version information
- Privilege escalation vector detection
- Scheduled task analysis
- Export findings to TXT, JSON, CSV, or Markdown

**Commands** (in Firmware panel):
```
load <path>     - Load firmware file or directory
browse          - Open file browser
scan            - Scan for filesystems
extract         - Extract all filesystems
analyze         - Run full security scan (basic + advanced)
creds           - Scan for credentials only
search <regex>  - Custom pattern search
export [format] - Export findings (txt/json/csv/md)
debug           - Toggle debug logging
```

**Dependencies** (optional but recommended):
```bash
# Core extraction tools
brew install binwalk sasquatch squashfs-tools

# Additional format support
pip install jefferson ubi_reader

# Vulnerability scanning (optional)
brew install nuclei
```

## TUI Key Bindings

| Key | Action |
|-----|--------|
| `F1` | Devices tab (discovery) |
| `F2` | Firmware analysis tab |
| `F3` | Toggle split view |
| `F4` | Coordination view (multi-device) |
| `F5` | Refresh devices |
| `F6` | Glitch calibration tab (experimental) |
| `F12` | Show help |
| `Ctrl+Q` / `q` | Quit |
| `Tab` | Switch between panels |
| `Escape` | Return to discovery tab |

### Coordination Mode (F4)

Multi-device trigger routing for coordinated attacks:

**Trigger Sources**:
- UART pattern detection (e.g., "Password:" detected → trigger glitch)
- ADC threshold crossing (power spike → trigger action)
- GPIO hardware triggers (sub-microsecond latency via physical wiring)

**Workflow Example**:
1. Connect Bus Pirate (UART monitor) + Curious Bolt (glitcher)
2. Press F4 to open Coordination view
3. Configure trigger: UART pattern "login:" → Bolt glitch
4. Click "ARM COORDINATOR" to start monitoring
5. Glitch triggers automatically when pattern detected in UART stream

**Note**: UI complete, hardware integration in progress.

### Calibration Mode (F6)

**Status**: Experimental - UI complete, hardware integration in progress

**Purpose**: Measure and compensate for timing latency differences between hardware setups, enabling sharing of glitch parameters.

**Workflow**:
1. Connect glitch device (e.g., Curious Bolt)
2. Wire glitch output to logic analyzer input (loopback)
3. Press F6, select device, enter profile name
4. Click "Start Calibration" to measure timing characteristics
5. Save profile for future use

**Future Goal**: Share glitch configs with calibration profiles:
```python
from hwh.automation import PortableGlitchConfig, CalibrationManager
config = PortableGlitchConfig.load("stm32_rdp_bypass.json")
manager = CalibrationManager()
width, offset = manager.apply_calibration(config, "my_bolt_profile")
```

## CLI Usage

The `hwh` command provides both TUI and CLI interfaces:

### Launching TUI
```bash
hwh              # Launch TUI (default)
hwh tui          # Explicit TUI launch
```

### Device Detection
```bash
hwh devices      # List connected devices (human-readable)
hwh devices --json  # JSON output for scripting
hwh devices --all   # Include unknown devices
```

### SPI Flash Operations
```bash
# Dump SPI flash
hwh spi dump -d "Bus Pirate 5" -o dump.bin -a 0x0 -s 0x100000

# Auto-select first SPI-capable device
hwh spi dump -o dump.bin

# Custom speed
hwh spi dump -o dump.bin --speed 8000000
```

### Glitching Operations
```bash
# Run glitch parameter sweep
hwh glitch sweep --device "Curious Bolt" \
  --width 100-500 --offset 0-1000 --step 10

# Single glitch test
hwh glitch test --device "Curious Bolt" \
  --width 350 --offset 500
```

### Firmware Analysis
```bash
# Extract firmware
hwh firmware extract router.bin
# Output: router_extracted/

# Analyze extracted filesystem
hwh firmware analyze router_extracted/squashfs-root/

# Generate comprehensive markdown report
hwh firmware analyze router_extracted/squashfs-root/ \
  --export md -o security-report.md

# Verbose output for debugging
hwh firmware analyze path/ -v

# Export as JSON for automation
hwh firmware analyze path/ --export json -o findings.json
```

### Automation Python API

```python
# UART Baud Scanner
from hwh.automation import scan_uart_baud
report = await scan_uart_baud(port="/dev/ttyUSB0")
print(f"Detected: {report.best_baud} baud")

# Smart Glitch Campaign
from hwh.automation import SmartGlitchCampaign
campaign = SmartGlitchCampaign(glitch_backend=bolt, monitor_backend=buspirate)
campaign.classifier.add_success_pattern("flag{")
stats = await campaign.run(strategy="adaptive", max_attempts=1000)

# Firmware Analysis
from hwh.automation import analyze_firmware
report = await analyze_firmware("router.bin")
print(report.summary())
```

## Bus Pirate 5/6 Critical Notes

- **Only BP5 and BP6 supported** - older versions (v3, v4) are NOT supported
- **Use BPIO2 interface** - binary CDC interface (`buspirate3` port), NOT the terminal interface
- **UART limitation**: UART BPIO2 not implemented in firmware - use terminal fallback
- **Testing**: Debug scripts available in `scripts/` directory for troubleshooting
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

### General Guidelines
- Type hints everywhere (Python 3.10+)
- Dataclasses for configuration
- Rich logging for debug output
- Wrap all hardware operations in try/except with `serial.SerialException`, `usb.core.USBError`
- Implement retry logic with exponential backoff
- Always release hardware resources in finally blocks

### Textual TUI Patterns

**Worker Pattern for Hardware I/O**: CRITICAL - all serial/USB operations MUST run in workers to avoid blocking the UI:

```python
from textual.worker import work, get_current_worker

@work(exclusive=True, thread=True)
def serial_reader(self, port: str) -> None:
    """Read from serial port in background thread."""
    worker = get_current_worker()
    ser = serial.Serial(port, 115200, timeout=0.1)
    try:
        while not worker.is_cancelled:
            data = ser.read(1024)
            if data:
                # Use call_from_thread to safely update UI from worker
                self.call_from_thread(self.handle_rx, data)
    finally:
        ser.close()
```

**Device Panel Pattern**: All device panels inherit from `DevicePanel` and declare capabilities:

```python
from .base import DevicePanel, PanelCapability

class BusPiratePanel(DevicePanel):
    CAPABILITIES = [
        PanelCapability.SPI,
        PanelCapability.I2C,
        PanelCapability.UART,
    ]

    async def on_mount(self) -> None:
        """Called when panel is added to DOM."""
        backend = self.app.device_pool.get_backend(self.device_info)
        if backend and backend.connect():
            self._backend = backend
```

**Split View Pattern**: Use `SplitPanelMirror` to avoid duplicate connections:

```python
# SplitPanelMirror subscribes to DeviceOutputMessage events
# from the source panel instead of opening a new serial connection
mirror = SplitPanelMirror(device_info, source_panel=original_panel)
```

**Output Events**: Panels post `DeviceOutputMessage` for output mirroring:

```python
from .base import DeviceOutputMessage

def handle_rx(self, data: bytes) -> None:
    text = data.decode('utf-8', errors='replace')
    self.log_widget.write(text)
    # Notify any mirrors
    self.post_message(DeviceOutputMessage(text=text))
```

### Backend Implementation Patterns

**Backend Registration**: Use decorator to register backends:

```python
from ..backends import register_backend

@register_backend("buspirate")
class BusPirateBackend(BusBackend):
    def connect(self) -> bool:
        # Connection logic
        pass
```

**Protocol Fallback**: Bus Pirate backend uses BPIO2 with terminal fallback:

```python
def configure_uart(self, config: UARTConfig) -> bool:
    if self.bpio_client:
        # Try BPIO2 first
        try:
            return self._configure_uart_bpio(config)
        except NotImplementedError:
            pass
    # Fall back to terminal commands
    return self._configure_uart_terminal(config)
```

**RP2040 Device Identification**: Bolt and FaultyCat share VID:PID, require runtime probing:

```python
# In detect.py
if device.vid == 0x2E8A and device.pid == 0x000A:
    # Probe serial to differentiate
    device_type = _probe_rp2040_device(port)
    if device_type == "bolt":
        return DeviceInfo(name="Curious Bolt", device_type="bolt", ...)
    elif device_type == "faultycat":
        return DeviceInfo(name="FaultyCat", device_type="faultycat", ...)
```

### Testing

**Unit Tests**: Located in `tests/` directory
- `test_cli.py`: CLI command tests
- `test_tui.py`: TUI application tests
- Backend tests should mock hardware dependencies

**Integration Tests**: Require actual hardware
- Use debug scripts in `scripts/` for manual hardware testing
- Mock backends available for testing without hardware

**Running Tests**:
```bash
pytest                    # Run all tests
pytest tests/test_cli.py -v  # Single test file with verbose output
pytest -k "test_name"     # Run specific test
```

## Configuration

- User config: `~/.config/hwh/config.toml`
- Never hardcode paths, regex patterns, or magic values
- Use config file for all configurable parameters

Example configuration:
```toml
[devices]
auto_connect = ["Bus Pirate 5", "Curious Bolt"]

[glitch]
default_width = 350
default_repeat = 1000

[ui]
theme = "dark"
```

## Git Workflow

- Always use feature branches (e.g., `feature/bp-status-tab`)
- Commit frequently - small, incremental commits
- Never use `git checkout HEAD --` to restore files - destroys uncommitted work
- Use `git stash` before risky operations

## Reference Code

The `temp/` directory (if present) contains reference implementations (not shipped with package):

| Directory | Description |
|-----------|-------------|
| `temp/bpio2-reference/` | Official BPIO2 FlatBuffers library and Python bindings |
| `temp/bolt/` | Curious Bolt firmware and hardware reference |
| `temp/faultycat/` | FaultyCat EMFI glitcher reference |
| `temp/bp5-firmware/` | Bus Pirate 5 firmware source (PIO, pin definitions) |
| `temp/glitch-o-bolt/` | Glitch-o-Bolt TUI reference (design inspiration) |

## Development Priorities

When adding new features or backends, refer to `backends/BACKEND_TODO.md` for:
- Backend completion status
- Implementation priorities
- Required dependencies
- Testing requirements

**Recommended Priority Order**:
1. Complete BoltBackend serial fallback (most users won't have native library)
2. Complete BusPirateBackend flash operations (common use case)
3. Create FaultyCatBackend (relatively simple serial protocol)
4. Create BlackMagicBackend (pygdbmi makes this straightforward)
5. Complete TigardBackend OpenOCD integration
6. Create TILinkBackend (niche but useful)
7. Add protocol decoders for logic analyzer
8. Build flash chip database

## External Documentation

**Black Magic Probe**: https://black-magic.org/getting-started.html
**Bus Pirate 5/6**: https://docs.buspirate.com/docs/command-reference/
**Curious Bolt**: https://bolt.curious.supplies/docs/getting-started/
**Tigard**: https://github.com/tigard-tools/tigard
**STM32 Debug**: https://stm32-base.org/guides/connecting-your-debugger.html
**Textual Framework**: https://textual.textualize.io/
