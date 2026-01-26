# Textual TUI Development Guide

Reference guide for building the hwh TUI with the Textual framework.

## Current TUI Key Bindings (app.py)

| Key | Action | Binding |
|-----|--------|---------|
| F1 | Devices tab | `action_show_devices` |
| F2 | Firmware tab | `action_show_firmware` |
| F3 | Toggle split view | `action_toggle_split` |
| F4 | Coordination mode | `action_show_coordination` |
| F5 | Refresh devices | `action_refresh_devices` |
| F12 | Show help | `action_show_help` |
| Ctrl+Q | Quit | `action_quit` |
| Escape | Device discovery | `action_show_devices` |

## Textual Framework Mastery

### Core Architecture

```python
from textual.app import App, ComposeResult
from textual.screen import Screen, ModalScreen
from textual.widgets import (
    Header, Footer, Static, Button, Input, Label,
    DataTable, Tree, RichLog, TabbedContent, TabPane,
    ProgressBar, Switch, Select, TextArea, Markdown,
    LoadingIndicator, Sparkline, Digits
)
from textual.containers import (
    Container, Horizontal, Vertical, Grid,
    ScrollableContainer, Center, Middle
)
from textual.reactive import reactive, var
from textual.message import Message
from textual.binding import Binding
from textual import work, on
from textual.worker import Worker, get_current_worker
```

### Application Structure

```python
class HwhApp(App):
    """Hardware hacking toolkit main application."""

    CSS_PATH = "style.tcss"
    TITLE = "hwh - Hardware Hacking Toolkit"

    # Current key bindings (see app.py for authoritative source)
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("f5", "refresh_devices", "Refresh"),
        Binding("f1", "show_devices", "Devices"),
        Binding("f2", "show_firmware", "Firmware"),
        Binding("f3", "toggle_split", "Split"),
        Binding("f4", "show_coordination", "Coordination"),
        Binding("escape", "show_devices", "Discovery"),
        Binding("f12", "show_help", "Help"),
    ]

    # Reactive state
    available_devices: Dict[str, DeviceInfo] = {}
    connected_panels: Dict[str, DevicePanel] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(id="main-tabs"):
            with TabPane("Devices", id="tab-devices"):
                yield from self._build_devices_page()
            with TabPane("Firmware", id="tab-firmware"):
                yield FirmwarePanel(id="firmware-panel")
        yield Footer()

    async def on_ready(self) -> None:
        """Initialize application."""
        await self.refresh_device_list()
```

### Worker Pattern for Hardware I/O

**CRITICAL**: Never block the event loop. Use workers for all hardware operations.

```python
# Thread worker for synchronous I/O (serial, USB)
@work(exclusive=True, thread=True)
def read_spi_flash(self, device: str, size: int) -> bytes:
    """Read flash in background thread."""
    worker = get_current_worker()
    
    spi = self.get_spi_interface(device)
    data = bytearray()
    chunk_size = 4096
    
    for offset in range(0, size, chunk_size):
        if worker.is_cancelled:
            return bytes(data)  # Partial result
        
        chunk = spi.read(offset, min(chunk_size, size - offset))
        data.extend(chunk)
        
        # Update UI from thread
        self.call_from_thread(
            self.update_progress, offset + len(chunk), size
        )
    
    return bytes(data)

# Async worker for async-compatible operations
@work(exclusive=True)
async def analyze_firmware(self, path: str) -> dict:
    """Run analysis with async subprocess."""
    import asyncio
    
    proc = await asyncio.create_subprocess_exec(
        'binwalk', '--quiet', '--csv', path,
        stdout=asyncio.subprocess.PIPE
    )
    stdout, _ = await proc.communicate()
    return self.parse_binwalk_output(stdout)

# Handling worker results
def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
    if event.state == WorkerState.SUCCESS:
        result = event.worker.result
        self.process_result(result)
    elif event.state == WorkerState.ERROR:
        self.notify(f"Error: {event.worker.error}", severity="error")
```

### Custom Widgets

**Hex Viewer** (high-performance with Line API):
```python
from textual.widget import Widget
from textual.strip import Strip
from rich.segment import Segment
from rich.style import Style

class HexViewer(Widget):
    """Scrollable hex viewer for binary data."""
    
    DEFAULT_CSS = """
    HexViewer {
        height: 100%;
        overflow-y: auto;
    }
    """
    
    data: reactive[bytes] = reactive(b"")
    bytes_per_line: int = 16
    offset: int = 0  # For highlighting
    
    def __init__(self, data: bytes = b"", **kwargs):
        super().__init__(**kwargs)
        self.data = data
    
    @property
    def line_count(self) -> int:
        return (len(self.data) + self.bytes_per_line - 1) // self.bytes_per_line
    
    def render_line(self, y: int) -> Strip:
        start = y * self.bytes_per_line
        if start >= len(self.data):
            return Strip.blank(self.size.width)
        
        line_data = self.data[start:start + self.bytes_per_line]
        segments = []
        
        # Address
        segments.append(Segment(f"{start:08X}  ", Style(color="cyan", bold=True)))
        
        # Hex bytes with spacing
        hex_parts = []
        for i, b in enumerate(line_data):
            style = Style(color="green" if b != 0xFF else "bright_black")
            hex_parts.append(Segment(f"{b:02X}", style))
            hex_parts.append(Segment(" "))
            if i == 7:
                hex_parts.append(Segment(" "))
        
        # Pad if short line
        padding = " " * (3 * (self.bytes_per_line - len(line_data)))
        if len(line_data) <= 8:
            padding += " "
        segments.extend(hex_parts)
        segments.append(Segment(padding + " "))
        
        # ASCII
        ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in line_data)
        segments.append(Segment(ascii_str, Style(color="yellow")))
        
        return Strip(segments)
    
    def scroll_to_offset(self, offset: int) -> None:
        line = offset // self.bytes_per_line
        self.scroll_to(y=line, animate=True)
```

**Status Indicator** (reactive badge):
```python
class StatusIndicator(Static):
    """Connection status with reactive updates."""
    
    DEFAULT_CSS = """
    StatusIndicator {
        padding: 0 1;
    }
    StatusIndicator.connected {
        background: $success;
        color: $text;
    }
    StatusIndicator.disconnected {
        background: $error;
        color: $text;
    }
    """
    
    connected: reactive[bool] = reactive(False)
    
    def watch_connected(self, connected: bool) -> None:
        self.remove_class("connected", "disconnected")
        self.add_class("connected" if connected else "disconnected")
        self.update("● Connected" if connected else "○ Disconnected")
```

**Protocol Decoder Panel**:
```python
class ProtocolDecoder(Static):
    """Decode and display protocol frames."""
    
    class FrameDecoded(Message):
        def __init__(self, protocol: str, fields: dict, raw: bytes):
            super().__init__()
            self.protocol = protocol
            self.fields = fields
            self.raw = raw
    
    DECODERS = {
        "spi_flash": {
            0x9F: ("RDID", lambda d: {"mfr": d[1], "type": d[2], "cap": d[3]}),
            0x03: ("READ", lambda d: {"addr": int.from_bytes(d[1:4], 'big')}),
            0x02: ("PAGE_PROGRAM", lambda d: {"addr": int.from_bytes(d[1:4], 'big'), "len": len(d)-4}),
        }
    }
    
    def decode(self, protocol: str, data: bytes) -> dict | None:
        if protocol not in self.DECODERS:
            return None
        
        cmd = data[0] if data else 0
        if cmd in self.DECODERS[protocol]:
            name, parser = self.DECODERS[protocol][cmd]
            return {"command": name, **parser(data)}
        
        return {"command": f"UNKNOWN (0x{cmd:02X})"}
```

### TCSS Styling

```css
/* style.tcss */
Screen {
    background: $surface;
}

Header {
    dock: top;
    background: $primary;
}

Footer {
    dock: bottom;
}

/* Device panel */
#device-list {
    width: 30;
    border: solid $primary;
    height: 100%;
}

#device-detail {
    width: 1fr;
    padding: 1;
}

/* Split view */
.split-horizontal {
    layout: horizontal;
}

.split-vertical {
    layout: vertical;
}

.panel {
    border: solid $secondary;
    margin: 1;
    padding: 1;
}

/* Hex viewer */
HexViewer {
    background: $surface-darken-1;
    color: $text;
    scrollbar-gutter: stable;
}

/* Progress indicator */
ProgressBar > .bar--complete {
    color: $success;
}

ProgressBar > .bar--indeterminate {
    color: $primary;
}

/* Log styling */
RichLog {
    background: $surface-darken-2;
    border: solid $accent;
    scrollbar-size: 1 1;
}

/* Data table */
DataTable {
    height: auto;
    max-height: 20;
}

DataTable > .datatable--header {
    background: $primary;
    color: $text;
}

DataTable > .datatable--cursor {
    background: $secondary;
}

/* Modal dialogs */
ModalScreen {
    align: center middle;
}

#dialog {
    width: 60;
    height: auto;
    border: thick $primary;
    background: $surface;
    padding: 1 2;
}
```

### Message Passing

```python
# Define custom messages
class DeviceConnected(Message):
    def __init__(self, device_id: str, device_type: str):
        super().__init__()
        self.device_id = device_id
        self.device_type = device_type

class DataReceived(Message):
    def __init__(self, device_id: str, data: bytes):
        super().__init__()
        self.device_id = device_id
        self.data = data

# Post messages from workers
self.post_message(DeviceConnected("bp5", "Bus Pirate 5"))

# Handle with decorators
@on(DeviceConnected)
def handle_device_connected(self, event: DeviceConnected) -> None:
    self.query_one("#status").update(f"Connected: {event.device_type}")

# Or with explicit handler
def on_data_received(self, event: DataReceived) -> None:
    log = self.query_one(f"#log-{event.device_id}", RichLog)
    log.write(f"RX: {event.data.hex(' ')}")
```

### Screens and Navigation

```python
class SettingsScreen(Screen):
    """Settings modal screen."""
    
    BINDINGS = [
        Binding("escape", "pop_screen", "Back"),
    ]
    
    def compose(self) -> ComposeResult:
        with Container(id="settings-dialog"):
            yield Static("Settings", classes="title")
            yield Input(placeholder="Serial port", id="port")
            yield Select(
                [(b, b) for b in ["9600", "115200", "921600"]],
                prompt="Baud rate",
                id="baudrate"
            )
            with Horizontal():
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", id="cancel")
    
    @on(Button.Pressed, "#save")
    def save_settings(self) -> None:
        port = self.query_one("#port", Input).value
        # Save and return
        self.dismiss({"port": port})
    
    @on(Button.Pressed, "#cancel")
    def cancel(self) -> None:
        self.dismiss(None)

# Push screen and handle result
async def action_settings(self) -> None:
    result = await self.push_screen(SettingsScreen())
    if result:
        self.apply_settings(result)
```

### Real-time Data Display

```python
class LiveDataPanel(Static):
    """Real-time data visualization."""
    
    samples: reactive[list] = reactive([])
    
    def compose(self) -> ComposeResult:
        yield Sparkline([], id="sparkline")
        yield Static(id="current-value")
        yield DataTable(id="stats")
    
    def watch_samples(self, samples: list) -> None:
        if not samples:
            return
        
        # Update sparkline
        self.query_one("#sparkline", Sparkline).data = samples[-100:]
        
        # Update current value
        self.query_one("#current-value").update(f"Current: {samples[-1]:.2f}")
        
        # Update stats table
        table = self.query_one("#stats", DataTable)
        if not table.columns:
            table.add_columns("Stat", "Value")
        table.clear()
        table.add_row("Min", f"{min(samples):.2f}")
        table.add_row("Max", f"{max(samples):.2f}")
        table.add_row("Avg", f"{sum(samples)/len(samples):.2f}")
```

### Error Handling Patterns

```python
class RobustSerialWidget(Static):
    """Widget with graceful hardware error handling."""
    
    def __init__(self):
        super().__init__()
        self._serial: serial.Serial | None = None
        self._reconnect_attempts = 0
        self._max_reconnects = 3
    
    @work(thread=True)
    def connect(self, port: str) -> None:
        worker = get_current_worker()
        
        while self._reconnect_attempts < self._max_reconnects:
            if worker.is_cancelled:
                return
            
            try:
                self._serial = serial.Serial(port, 115200, timeout=0.5)
                self._reconnect_attempts = 0
                self.call_from_thread(self.on_connected)
                self._read_loop(worker)
                return
            except serial.SerialException as e:
                self._reconnect_attempts += 1
                self.call_from_thread(
                    self.notify,
                    f"Connection failed ({self._reconnect_attempts}/{self._max_reconnects}): {e}",
                    severity="warning"
                )
                time.sleep(1.0 * self._reconnect_attempts)  # Backoff
        
        self.call_from_thread(
            self.notify, "Max reconnection attempts reached", severity="error"
        )
    
    def _read_loop(self, worker: Worker) -> None:
        while not worker.is_cancelled and self._serial:
            try:
                data = self._serial.read(1024)
                if data:
                    self.call_from_thread(self.on_data, data)
            except serial.SerialException:
                self.call_from_thread(self.on_disconnected)
                break
    
    def on_unmount(self) -> None:
        """Clean up hardware resources."""
        if self._serial:
            try:
                self._serial.close()
            except:
                pass
```

## Best Practices

1. **Never block the event loop** - Use `@work(thread=True)` for serial/USB
2. **Use `call_from_thread`** - To safely update UI from workers
3. **Reactive over manual updates** - Let `watch_*` methods handle state changes
4. **TCSS over inline styles** - Maintainable, themeable
5. **Message passing over direct coupling** - Decoupled components
6. **Graceful degradation** - Handle hardware disconnection
7. **Progressive disclosure** - Start simple, reveal complexity on demand

## Performance Tips

- Use `Line API` (render_line) for large data sets
- Limit RichLog buffer size with `max_lines`
- Batch UI updates when possible
- Use `refresh(repaint=False)` when only layout changed
- Profile with `textual run --dev` for devtools
