# hwh - Hardware Hacking Toolkit

<p align="center">
  <img src="hwh.png" alt="hwh mascot" width="400">
</p>

A multi-device TUI (Terminal User Interface) for hardware security research. Control multiple hardware hacking tools simultaneously from a single interface.

## Features

- **Multi-Device Support** - Connect and control multiple devices at once
- **Device-Based Tabs** - Each device gets its own tab with all capabilities
- **Split View** - Monitor multiple devices side-by-side (F3)
- **Coordination Mode** - Multi-device trigger routing for coordinated attacks (F4)
- **Logic Analyzer** - SUMP protocol with protocol decoders (SPI, I2C, UART)
- **Smart Glitch Campaigns** - Adaptive parameter search with result classification
- **Firmware Analysis** - Extract, navigate, and search firmware for vulnerabilities
- **Automation Tools** - UART baud scanner, protocol replay, firmware secrets scanning

## Supported Devices

| Device | Capabilities |
|--------|-------------|
| Bus Pirate 5/6 | SPI, I2C, UART, JTAG Scan, Logic Analyzer |
| Curious Bolt | Voltage Glitching, Logic Analyzer, Power Analysis |
| Tigard | SPI, I2C, UART, JTAG, SWD |
| FaultyCat | EMFI, Pin Detection |
| TI-Link/MSP-FET | JTAG, SWD, EnergyTrace, BSL |
| Black Magic Probe | SWD, JTAG, GDB Server |

## Installation

### pip (Recommended)

```bash
pip install hwh
```

### Homebrew (macOS)

```bash
brew tap ResistanceIsUseless/hwh
brew install hwh
```

### Docker

```bash
docker run -it --privileged -v /dev:/dev resistanceisuseless/hwh
```

### From Source

```bash
git clone https://github.com/ResistanceIsUseless/hwh.git
cd hwh
pip install -e .
```

## Usage

### Launch TUI

```bash
hwh
```

Or explicitly:

```bash
hwh tui
```

### CLI Commands

```bash
# List connected devices
hwh devices

# Connect to specific device
hwh connect "Bus Pirate 5"

# Read SPI flash
hwh spi read --device "Bus Pirate 5" --output dump.bin

# Run glitch sweep
hwh glitch sweep --device "Curious Bolt" --width 100-500 --offset 0-1000
```

### Keyboard Shortcuts (TUI)

| Key | Action |
|-----|--------|
| `F1` | Go to Devices tab |
| `F2` | Go to Firmware tab |
| `F3` | Toggle split view |
| `F4` | Coordination mode (multi-device) |
| `F6` | Calibration (glitch timing) |
| `F12` | Show help |
| `Escape` | Back to device discovery |
| `q` | Quit |
| `Tab` | Switch between panels |

## Firmware Analysis

The Firmware tab (F2) provides tools for analyzing firmware images without requiring hardware:

### Features
- **Extraction** - Scan and extract SquashFS, JFFS2, UBIFS, CPIO, TAR, ZIP filesystems
- **Nested Archives** - Automatically extract archives within archives
- **File Browser** - Navigate extracted filesystem with lazy-loading tree view
- **Raw Image Support** - Load .img files directly (auto-detects filesystem type)
- **Security Search** - Find hardcoded credentials, API keys, private keys
- **Binary Analysis** - Detect unsafe functions in ELF binaries
- **Pattern Search** - Custom regex search across all files
- **Findings Export** - Export results to TXT, JSON, or CSV

### Dependencies
```bash
# Required
brew install binwalk

# Recommended for better extraction
brew install sasquatch squashfs-tools
pip install jefferson ubi_reader

# For archive support
# tar and unzip are usually pre-installed
```

### Commands
```
load <path>     - Load firmware file or directory
browse          - Open file browser for extracted files
scan            - Scan for filesystems
extract         - Extract all filesystems
analyze         - Run full security scan
creds           - Scan for credentials only
search <regex>  - Search with custom pattern
export [format] - Export findings (txt/json/csv)
debug           - Toggle debug logging
```

## Coordination Mode

Press `F4` with 2+ devices connected to enter Coordination Mode for multi-device attack workflows.

### Trigger Routing
Route events from one device to actions on another:
- **UART Pattern → Glitch**: Bus Pirate detects "Password:" → Bolt triggers glitch
- **Power Threshold → Glitch**: Bolt ADC crosses threshold → trigger fault injection
- **GPIO Hardware Triggers**: Sub-microsecond latency via physical wiring

### Example Workflow
1. Connect Bus Pirate (UART monitor) and Bolt (glitcher)
2. Press F4 for Coordination mode
3. Enter pattern: `Password:`
4. Click "Add Route" to create UART→glitch route
5. Click "ARM COORDINATOR" to start monitoring
6. Glitch triggers automatically when pattern detected

## Glitch Calibration (Proof of Concept)

> **Note**: This feature is experimental and under active development. The calibration workflow and API may change.

Press `F6` to access the Calibration tab for measuring and compensating glitch timing latency.

### Concept

The idea is to measure the timing characteristics of your specific hardware setup so that glitch parameters can be shared between users. Different setups have different latencies due to:
- Wire length between devices
- Hardware response time variations
- Connection quality and routing

By calibrating your setup, you create a profile that can be used to adjust shared glitch parameters to work on your hardware.

### Current Status
- ✅ TUI interface with device-specific wiring instructions
- ✅ Profile save/load infrastructure
- ✅ Simulation mode for UI testing
- ⚠️ Hardware calibration integration (in progress)
- ⚠️ Cross-setup parameter sharing (planned)

### Calibration Workflow
1. Connect your glitch device (e.g., Curious Bolt)
2. Wire the glitch output to a logic analyzer input (loopback)
3. Select your device in the Calibration tab
4. Enter a profile name (e.g., "bolt_10cm_wire")
5. Click "Start Calibration"
6. Save the profile for future use

### Wiring Example (Curious Bolt)
```
    GLITCH OUT ──────┐
                     │ (short wire)
    LA CH0     ◄─────┘
```

### Future: Portable Glitch Configs
The goal is to enable sharing glitch parameters like this:
```python
from hwh.automation import PortableGlitchConfig, CalibrationManager

# Load a shared config (e.g., from a writeup or community database)
config = PortableGlitchConfig.load("stm32_rdp_bypass.json")

# Apply your local calibration to compensate for setup differences
manager = CalibrationManager()
width, offset = manager.apply_calibration(config, "my_bolt_10cm_wire")
print(f"Adjusted for your setup: width={width}ns, offset={offset}ns")
```

## Automation Tools

### UART Baud Scanner
```python
from hwh.automation import scan_uart_baud
report = await scan_uart_baud(port="/dev/ttyUSB0")
print(f"Detected: {report.best_baud} baud")
```

### Smart Glitch Campaign
```python
from hwh.automation import SmartGlitchCampaign
campaign = SmartGlitchCampaign(glitch_backend=bolt, monitor_backend=buspirate)
campaign.classifier.add_success_pattern("flag{")
stats = await campaign.run(strategy="adaptive", max_attempts=1000)
```

### Logic Analyzer Triggered Glitch
```python
from hwh.automation import LATriggeredGlitcher, TriggerPattern
glitcher = LATriggeredGlitcher(la_backend=bolt, glitch_backend=bolt)
# Detect idle periods (e.g., end of boot sequence)
await glitcher.learn_patterns(TriggerPattern.IDLE_HIGH, min_duration_us=1000)
glitcher.configure(glitch_delay_us=500, glitch_width_ns=100)
await glitcher.arm_and_wait()
```

### Firmware Analysis
```python
from hwh.automation import analyze_firmware
report = await analyze_firmware("router.bin")
print(report.summary())  # Shows credentials, keys, interesting files
```

## Configuration

Configuration is stored in `~/.config/hwh/config.toml`:

```toml
[devices]
# Auto-connect to these devices on startup
auto_connect = ["Bus Pirate 5", "Curious Bolt"]

[glitch]
# Default glitch parameters
default_width = 350
default_repeat = 1000

[ui]
# Theme: "dark" or "light"
theme = "dark"
```

## Development

```bash
# Clone and install in development mode
git clone https://github.com/ResistanceIsUseless/hwh.git
cd hwh
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black src/
ruff check src/
```

## Architecture

```
hwh/
├── cli.py              # CLI entry point
├── detect.py           # Device detection
├── glitch_profiles.py  # Pre-configured glitch parameters
├── backends/
│   ├── base.py         # Backend base classes (Bus, Debug, Glitch, GPIO)
│   ├── backend_buspirate.py   # Bus Pirate 5/6 with BPIO2
│   ├── backend_bolt.py        # Curious Bolt glitcher
│   ├── backend_tigard.py      # Tigard with OpenOCD
│   └── sump.py         # SUMP protocol for logic analyzers
├── coordination/
│   ├── coordinator.py  # Multi-device trigger routing
│   └── triggers.py     # Trigger conditions and actions
├── automation/
│   ├── uart_scanner.py     # UART baud rate detection
│   ├── smart_glitch.py     # Adaptive glitch campaigns
│   ├── la_glitch.py        # Logic analyzer triggered glitching
│   ├── protocol_replay.py  # SPI/I2C/UART capture and replay
│   └── firmware_analysis.py # Automated secret scanning
├── firmware/
│   └── extractor.py    # Firmware extraction engine
├── pybpio/             # Bundled Bus Pirate BPIO2 library
└── tui/
    ├── app.py          # Main TUI application
    ├── device_pool.py  # Multi-device management
    └── panels/         # Device-specific UI panels
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Credits

- TUI framework: [Textual](https://textual.textualize.io/)
- Design inspiration: [glitch-o-bolt](https://rossmarks.uk/git/0xRoM/glitch-o-bolt)
- Color scheme: Metagross Pokemon colors
