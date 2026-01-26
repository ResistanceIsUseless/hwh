# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

hwh (Hardware Hacking Toolkit) is a multi-device TUI for hardware security research. It supports controlling multiple hardware hacking tools simultaneously from a single Textual-based interface.

## Commands

### Development
```bash
# Install in development mode
pip install -e ".[dev]"

# Run the TUI
hwh              # Launches TUI by default
hwh tui          # Explicit TUI launch

# CLI commands
hwh devices      # List detected devices
hwh detect       # Alias for devices
hwh spi dump -o output.bin     # Dump SPI flash
hwh i2c scan                   # Scan I2C bus
hwh glitch single -w 100       # Trigger glitch
```

### Testing
```bash
# Run all tests
pytest

# Run a single test file
pytest tests/test_cli.py

# Run a specific test
pytest tests/test_cli.py::test_cli_help
```

### Code Quality
```bash
black src/           # Format code
ruff check src/      # Lint
mypy src/            # Type checking
```

### Bus Pirate Testing
```bash
# Test BPIO2 connection (requires Bus Pirate 5/6 connected)
python scripts/test_bpio2_status.py [port]
# Default port: /dev/cu.usbmodem6buspirate3
```

## Architecture

### Core Layers

1. **CLI Layer** (`src/hwh/cli.py`) - Click-based CLI entry point. Running `hwh` without arguments launches TUI.

2. **Device Detection** (`src/hwh/detect.py`) - USB and serial enumeration with VID:PID matching. `detect()` returns `Dict[str, DeviceInfo]`.

3. **Backend Layer** (`src/hwh/backends/`) - Device communication abstraction:
   - `base.py` - Abstract base classes: `Backend`, `BusBackend`, `DebugBackend`, `GlitchBackend`
   - `backend_*.py` - Device-specific implementations
   - Registry pattern via `register_backend()` and `get_backend()`

4. **TUI Layer** (`src/hwh/tui/`) - Textual-based interface:
   - `app.py` - Main `HwhApp` class, tab management, device connection lifecycle
   - `panels/base.py` - `DevicePanel` base class all device panels inherit from
   - `panels/*.py` - Device-specific UI panels

### Key Patterns

**Device Panel Flow:**
```
HwhApp.connect_device(device_id)
  -> _get_panel_class(device_info)  # VID:PID lookup in DEVICE_PANELS dict
  -> panel_class(device_info, app)  # Instantiate panel
  -> tabs.add_pane(panel)           # Add as tab
  -> panel.connect()                # Establish device connection
```

**Backend Configuration:**
```python
backend = get_backend(device_info)
with backend:
    backend.configure_spi(SPIConfig(speed_hz=1000000))
    data = backend.spi_flash_read(0x0, 4096)
```

### BPIO2 Library (`src/hwh/pybpio/`)

Bundled FlatBuffers-based protocol client for Bus Pirate 5/6. Connects via binary CDC interface (`buspirate3` port), not terminal.

```python
from hwh.pybpio import BPIOClient

with BPIOClient('/dev/cu.usbmodem6buspirate3', baudrate=3000000) as client:
    status = client.status_request()
    client.configuration_request(mode='spi', psu_enable=True, psu_set_mv=3300)
    client.data_request(data_write=[0x9F], bytes_read=3)  # Read JEDEC ID
```

### TUI Panel Capabilities

Panels declare capabilities via `PanelCapability` enum. The split view and coordination mode use these to filter device selectors.

### Message Flow

Panels communicate via Textual messages:
- `DeviceOutputMessage` - Device produces output (logs, UART data)
- `DeviceStatusMessage` - Device status changes

## Git Workflow

- **Always use feature branches** for new work (e.g., `feature/bp-status-tab`)
- **Commit frequently** - small, incremental commits that can be rolled back
- **Never use `git checkout HEAD --`** to restore files - this destroys uncommitted work
- Use `git stash` before switching branches or making risky changes

## Bus Pirate 5/6 Development (BPIO2 Only)

- **Only support Bus Pirate 5 and Bus Pirate 6** - older versions (v3, v4) are NOT supported
- **Always use BPIO2 FlatBuffers library** (bundled in `src/hwh/pybpio/`)
- The BPIO2 library connects via the binary CDC interface (buspirate3), NOT the terminal interface
- BPIO2 Documentation: https://docs.buspirate.com/docs/binmode-reference/protocol-bpio2/
- Test connection with `BPIOClient` before adding UI features
- Reference working test scripts in `scripts/` directory
- **UART BPIO2 not implemented in firmware** - use terminal fallback for UART mode

## File Organization

- `src/hwh/` - Main package
- `src/hwh/pybpio/tooling/` - Generated FlatBuffers code (do not edit manually)
- `scripts/` - Test and utility scripts
- `temp/` - Reference materials, not part of the package
- `tests/` - pytest tests
