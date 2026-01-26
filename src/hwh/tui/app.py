"""
hwh TUI - Hardware Hacking Tool

Multi-device interface with device-based tabs.
Each connected device gets its own tab with all features.

Design:
- Main page shows detected devices
- Connect to device -> creates device tab
- Multiple devices can be connected simultaneously
- Split-screen layout for multi-device workflows (press 's')
"""

import asyncio
from typing import Dict, Optional, Type, List, Tuple

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widgets import Static, Button, Select, TabbedContent, TabPane, Footer, Header
from textual.binding import Binding

from ..detect import detect, DeviceInfo
from .. import __version__

# Lazy import coordination to avoid circular imports
# These will be imported in methods that use them

# Import all panel types
from .panels.base import DevicePanel, GenericPanel, PanelCapability
from .panels.buspirate import BusPiratePanel
from .panels.bolt import BoltPanel
from .panels.tigard import TigardPanel
from .panels.faultycat import FaultyCatPanel
from .panels.tilink import TILinkPanel
from .panels.blackmagic import BlackMagicPanel
from .panels.uart_monitor import UARTMonitorPanel
from .panels.firmware import FirmwarePanel
from .panels.calibration import CalibrationPanel
from .panels.base import DeviceOutputMessage


class SplitPanelMirror(Container):
    """
    A mirror view that displays output from an existing panel.

    This avoids creating duplicate serial connections when showing
    the same device in split view. Instead of opening a new connection,
    it subscribes to output messages from the source panel.

    The mirror shows the source panel's output log and provides basic
    information about the device. For full control, users should use
    the device's main tab.
    """

    def __init__(self, device_info: DeviceInfo, source_panel: "DevicePanel", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device_info = device_info
        self.source_panel = source_panel
        self._log_widget = None

    def compose(self) -> ComposeResult:
        from textual.widgets import Log

        with Vertical():
            # Header with device info
            with Horizontal(classes="panel-header"):
                yield Static(f"{self.device_info.name}", classes="device-title")
                yield Static(f"Port: {self.device_info.port}", classes="device-port")
                yield Static("(output mirror)", classes="connection-status")

            # Info about what this mirror shows
            yield Static("Showing output from connected device. Use device tab for full control.", classes="help-text")

            # Output log - mirrors the source panel
            self._log_widget = Log(id=f"mirror-log-{id(self)}", classes="uart-log")
            self._log_widget.border_title = "output"
            yield self._log_widget

    async def on_mount(self) -> None:
        """Subscribe to output from the source panel when mounted"""
        # Register callback on source panel
        self.source_panel.on_output(self._on_source_output)

        # Write initial message
        if self._log_widget:
            self._log_widget.write(f"[*] Mirroring output from {self.device_info.name}\n")
            self._log_widget.write(f"[*] Use the '{self.device_info.name}' tab for full device controls\n")

    def _on_source_output(self, text: str) -> None:
        """Handle output from the source panel"""
        if self._log_widget:
            try:
                self._log_widget.write(text)
            except Exception:
                pass

    async def disconnect(self) -> None:
        """Mirror doesn't own the connection, so nothing to disconnect"""
        pass


class SplitView(Container):
    """Split view container showing two device panels side by side"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.left_device_id: Optional[str] = None
        self.right_device_id: Optional[str] = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="split-container"):
            # Left pane
            with Vertical(id="split-left", classes="split-pane"):
                yield Static("Select device for left pane", id="left-placeholder", classes="split-placeholder")

            # Divider
            yield Static("│", id="split-divider", classes="split-divider")

            # Right pane
            with Vertical(id="split-right", classes="split-pane"):
                yield Static("Select device for right pane", id="right-placeholder", classes="split-placeholder")


# Device VID:PID to panel class mapping
DEVICE_PANELS: Dict[tuple, Type[DevicePanel]] = {
    # Bus Pirate 5/6
    (0x1209, 0x7331): BusPiratePanel,

    # Curious Bolt
    (0xcafe, 0x4002): BoltPanel,

    # Bolt CTF (treated as UART monitor)
    (0xcafe, 0x4004): UARTMonitorPanel,

    # Tigard
    (0x0403, 0x6010): TigardPanel,

    # FaultyCat
    (0x2341, 0x8037): FaultyCatPanel,  # Arduino Micro based

    # Black Magic Probe
    (0x1d50, 0x6018): BlackMagicPanel,

    # TI MSP-FET
    (0x0451, 0xbef3): TILinkPanel,

    # Generic FTDI (could be many things)
    (0x0403, 0x6001): UARTMonitorPanel,

    # CH340 UART adapter
    (0x1a86, 0x7523): UARTMonitorPanel,

    # CP2102 UART adapter
    (0x10c4, 0xea60): UARTMonitorPanel,
}


class HwhApp(App):
    """
    hwh TUI Application

    Architecture:
    - Devices tab shows all detected devices
    - Each connected device gets its own tab
    - Tabs contain device-specific panels with all features
    """

    CSS_PATH = "style.tcss"
    TITLE = "hwh - Hardware Hacking Toolkit"
    SUB_TITLE = f"v{__version__}"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("f5", "refresh_devices", "Refresh"),
        Binding("f1", "show_devices", "Devices"),
        Binding("f2", "show_firmware", "Firmware"),
        Binding("f3", "toggle_split", "Split"),
        Binding("f4", "show_coordination", "Coordination"),
        Binding("f6", "show_calibration", "Calibration"),
        Binding("escape", "show_devices", "Discovery"),
        Binding("f12", "show_help", "Help"),
    ]

    def __init__(self):
        super().__init__()
        self.available_devices: Dict[str, DeviceInfo] = {}
        self.connected_panels: Dict[str, DevicePanel] = {}
        self.split_panels: Dict[str, DevicePanel] = {}  # Panels created for split view
        self._tab_counter = 0
        self._split_view_active = False

    def compose(self) -> ComposeResult:
        yield Header()

        with TabbedContent(id="main-tabs"):
            # Devices tab - always present
            with TabPane("Devices", id="tab-devices"):
                yield from self._build_devices_page()

            # Firmware analysis tab - always present, no device needed
            with TabPane("Firmware", id="tab-firmware"):
                yield FirmwarePanel(id="firmware-panel")

            # Calibration tab - for glitch timing calibration
            with TabPane("Calibration", id="tab-calibration"):
                yield CalibrationPanel(app=self, id="calibration-panel")

        # Footer with version
        with Horizontal(id="app-footer"):
            yield Footer()
            yield Static(f"v{__version__}", id="version-display")

    def _build_devices_page(self) -> ComposeResult:
        """Build the device selection page"""
        with Vertical(id="devices-page"):
            yield Static("hwh - Hardware Hacking Toolkit", id="app-title")
            yield Static("Detected Devices:", classes="section-title")

            # Device list container
            yield ScrollableContainer(id="device-list")

            # Control buttons
            with Horizontal(classes="button-row"):
                yield Button("Refresh Devices", id="btn-refresh", classes="btn-action")
                yield Button("Add Manual Device", id="btn-add-manual", classes="btn-action")

    async def on_ready(self) -> None:
        """Initialize application"""
        await self.refresh_device_list()

    async def action_refresh_devices(self) -> None:
        """Refresh device list action"""
        await self.refresh_device_list()

    async def action_show_devices(self) -> None:
        """Switch to devices tab"""
        tabs = self.query_one("#main-tabs", TabbedContent)
        tabs.active = "tab-devices"

    async def action_show_help(self) -> None:
        """Show help"""
        self.notify("hwh - Hardware Hacking Toolkit\nPress 'q' to quit, 'r' to refresh, 'f' for firmware, 's' for split view")

    async def action_show_firmware(self) -> None:
        """Switch to firmware analysis tab"""
        tabs = self.query_one("#main-tabs", TabbedContent)
        tabs.active = "tab-firmware"

    async def action_show_calibration(self) -> None:
        """Switch to calibration tab"""
        tabs = self.query_one("#main-tabs", TabbedContent)
        tabs.active = "tab-calibration"

    async def action_show_coordination(self) -> None:
        """Show coordination panel for multi-device operations"""
        if len(self.connected_panels) < 2:
            self.notify("Connect at least 2 devices for coordination mode", severity="warning")
            return

        tabs = self.query_one("#main-tabs", TabbedContent)

        # Check if coordination tab already exists
        try:
            tabs.active = "tab-coordination"
            return
        except Exception:
            pass

        # Create coordination tab
        await self._create_coordination_tab()

    async def _create_coordination_tab(self) -> None:
        """Create a coordination tab for multi-device glitching operations

        Layout:
        ┌─────────────────────────────────────────────────────────────┐
        │ UART Monitor (CH340)      │  Glitcher (Bolt)                │
        │ ┌─────────────────────┐   │  ┌───────────────────────────┐  │
        │ │ target output...    │   │  │ Glitch controls          │  │
        │ └─────────────────────┘   │  └───────────────────────────┘  │
        ├─────────────────────────────────────────────────────────────┤
        │ Logic Analyzer (SUMP - Bolt or Bus Pirate)                  │
        │ ┌─────────────────────────────────────────────────────────┐ │
        │ │ CH0-7 waveforms                                         │ │
        │ └─────────────────────────────────────────────────────────┘ │
        └─────────────────────────────────────────────────────────────┘
        """
        from textual.widgets import Log, Input
        from .panels.logic_analyzer import LogicAnalyzerWidget

        tabs = self.query_one("#main-tabs", TabbedContent)

        pane = TabPane("Coordination", id="tab-coordination")
        await tabs.add_pane(pane)

        # Build coordination content - three sections vertically
        coord_content = Vertical(id="coordination-content")
        await pane.mount(coord_content)

        # === TOP SECTION: UART Monitor + Glitcher side by side ===
        top_section = Horizontal(id="coord-top-section", classes="coord-top")
        await coord_content.mount(top_section)

        # --- Left: UART Monitor ---
        uart_section = Vertical(id="coord-uart-section", classes="coord-panel")
        await top_section.mount(uart_section)

        # UART header with device selector
        uart_header = Horizontal(classes="coord-panel-header")
        await uart_section.mount(uart_header)
        await uart_header.mount(Static("UART Monitor", classes="coord-panel-title"))

        # Find UART-capable devices
        uart_devices = [(info.name, device_id) for device_id, info in self.available_devices.items()
                        if device_id in self.connected_panels and "uart" in info.capabilities]
        if not uart_devices:
            uart_devices = [("No UART devices", "none")]

        uart_select = Select(uart_devices, id="coord-uart-device", classes="coord-device-select")
        await uart_header.mount(uart_select)

        # UART log
        uart_log = Log(id="coord-uart-log", classes="coord-log")
        uart_log.border_title = "Target Output"
        await uart_section.mount(uart_log)
        uart_log.write("[*] Select a UART device to monitor target output\n")

        # UART input
        uart_input_row = Horizontal(classes="coord-input-row")
        await uart_section.mount(uart_input_row)
        await uart_input_row.mount(Input(placeholder="Send to target...", id="coord-uart-input", classes="coord-input"))
        await uart_input_row.mount(Button("Send", id="coord-uart-send", classes="btn-small"))

        # --- Right: Glitcher Controls ---
        glitch_section = Vertical(id="coord-glitch-section", classes="coord-panel")
        await top_section.mount(glitch_section)

        # Glitcher header with device selector
        glitch_header = Horizontal(classes="coord-panel-header")
        await glitch_section.mount(glitch_header)
        await glitch_header.mount(Static("Glitcher", classes="coord-panel-title"))

        # Find glitch-capable devices
        glitch_devices = [(info.name, device_id) for device_id, info in self.available_devices.items()
                          if device_id in self.connected_panels and
                          any(c in info.capabilities for c in ["voltage_glitch", "glitch", "emfi"])]
        if not glitch_devices:
            glitch_devices = [("No glitch devices", "none")]

        glitch_select = Select(glitch_devices, id="coord-glitch-device", classes="coord-device-select")
        await glitch_header.mount(glitch_select)

        # Glitch parameters
        params_grid = Vertical(classes="coord-params")
        await glitch_section.mount(params_grid)

        # Width parameter
        width_row = Horizontal(classes="coord-param-row")
        await params_grid.mount(width_row)
        await width_row.mount(Static("Width:", classes="coord-param-label"))
        await width_row.mount(Input(value="50", id="coord-glitch-width", classes="coord-param-input"))
        await width_row.mount(Static("cycles (8.3ns/cycle)", classes="coord-param-unit"))

        # Delay parameter
        delay_row = Horizontal(classes="coord-param-row")
        await params_grid.mount(delay_row)
        await delay_row.mount(Static("Delay:", classes="coord-param-label"))
        await delay_row.mount(Input(value="100", id="coord-glitch-delay", classes="coord-param-input"))
        await delay_row.mount(Static("cycles", classes="coord-param-unit"))

        # Repeat parameter
        repeat_row = Horizontal(classes="coord-param-row")
        await params_grid.mount(repeat_row)
        await repeat_row.mount(Static("Repeat:", classes="coord-param-label"))
        await repeat_row.mount(Input(value="1", id="coord-glitch-repeat", classes="coord-param-input"))
        await repeat_row.mount(Static("times", classes="coord-param-unit"))

        # Glitch status and buttons
        status_section = Vertical(classes="coord-status-section")
        await glitch_section.mount(status_section)

        status_row = Horizontal(classes="coord-status-row")
        await status_section.mount(status_row)
        await status_row.mount(Static("Status:", classes="coord-status-label"))
        await status_row.mount(Static("Ready", id="coord-glitch-status", classes="coord-status-value"))

        button_row = Horizontal(classes="coord-buttons")
        await status_section.mount(button_row)
        await button_row.mount(Button("ARM", id="coord-glitch-arm", classes="btn-coord btn-arm"))
        await button_row.mount(Button("TRIGGER", id="coord-glitch-trigger", classes="btn-coord btn-trigger"))
        await button_row.mount(Button("DISARM", id="coord-glitch-disarm", classes="btn-coord btn-disarm"))

        # === MIDDLE SECTION: Trigger Routes ===
        trigger_section = Vertical(id="coord-trigger-section", classes="coord-panel")
        await coord_content.mount(trigger_section)

        trigger_header = Horizontal(classes="coord-panel-header")
        await trigger_section.mount(trigger_header)
        await trigger_header.mount(Static("Trigger Routing", classes="coord-panel-title"))

        # Coordinator status
        coord_status = Static("READY", id="coord-status", classes="coord-status-badge")
        await trigger_header.mount(coord_status)

        # Route configuration row
        route_config = Horizontal(classes="coord-route-config")
        await trigger_section.mount(route_config)

        # Pattern input
        await route_config.mount(Static("Pattern:", classes="coord-label"))
        await route_config.mount(Input(placeholder="Password:|Login:", id="coord-trigger-pattern", classes="coord-input-wide"))

        # Route mode
        await route_config.mount(Static("Mode:", classes="coord-label"))
        route_mode = Select([("Software", "software"), ("Hardware GPIO", "hardware")],
                           value="software", id="coord-route-mode", classes="coord-select")
        await route_config.mount(route_mode)

        # Add route button
        await route_config.mount(Button("Add Route", id="coord-add-route", classes="btn-coord"))

        # Active routes display
        routes_row = Horizontal(classes="coord-routes-row")
        await trigger_section.mount(routes_row)

        await routes_row.mount(Static("Active Routes:", classes="coord-label"))
        routes_list = Static("None", id="coord-routes-list", classes="coord-routes-list")
        await routes_row.mount(routes_list)

        # Arm/Disarm coordinator
        coord_buttons = Horizontal(classes="coord-buttons")
        await trigger_section.mount(coord_buttons)
        await coord_buttons.mount(Button("ARM COORDINATOR", id="coord-arm", classes="btn-coord btn-arm"))
        await coord_buttons.mount(Button("DISARM", id="coord-disarm", classes="btn-coord btn-disarm"))
        await coord_buttons.mount(Button("Clear Routes", id="coord-clear-routes", classes="btn-coord"))

        # Trigger event log
        trigger_log = Log(id="coord-trigger-log", classes="coord-log-small")
        trigger_log.border_title = "Trigger Events"
        await trigger_section.mount(trigger_log)

        # === BOTTOM SECTION: Logic Analyzer ===
        la_section = Vertical(id="coord-la-section", classes="coord-panel coord-la")
        await coord_content.mount(la_section)

        # Logic analyzer header
        la_header = Horizontal(classes="coord-panel-header")
        await la_section.mount(la_header)
        await la_header.mount(Static("Logic Analyzer (SUMP)", classes="coord-panel-title"))

        # Find SUMP-capable devices (Bolt has logic analyzer, Bus Pirate has SUMP)
        la_devices = [(info.name, device_id) for device_id, info in self.available_devices.items()
                      if device_id in self.connected_panels and
                      any(c in info.capabilities for c in ["logic_analyzer", "logic"])]
        if not la_devices:
            la_devices = [("No LA devices", "none")]

        la_select = Select(la_devices, id="coord-la-device", classes="coord-device-select")
        await la_header.mount(la_select)

        # LA controls
        la_controls = Horizontal(classes="coord-la-controls")
        await la_header.mount(la_controls)
        await la_controls.mount(Select(
            [("31.25 MHz", "31250000"), ("10 MHz", "10000000"), ("1 MHz", "1000000"), ("100 kHz", "100000")],
            value="1000000", id="coord-la-rate", classes="coord-la-select"
        ))
        await la_controls.mount(Select(
            [("1K", "1024"), ("4K", "4096"), ("8K", "8192"), ("16K", "16384")],
            value="4096", id="coord-la-samples", classes="coord-la-select"
        ))
        await la_controls.mount(Button("Capture", id="coord-la-capture", classes="btn-coord"))
        await la_controls.mount(Button("Demo", id="coord-la-demo", classes="btn-coord"))

        # Logic analyzer widget
        la_widget = LogicAnalyzerWidget(channels=8, visible_samples=80, id="coord-la-widget")
        await la_section.mount(la_widget)

        # LA navigation
        la_nav = Horizontal(classes="coord-la-nav")
        await la_section.mount(la_nav)
        await la_nav.mount(Button("◀◀", id="coord-la-left-fast", classes="btn-nav"))
        await la_nav.mount(Button("◀", id="coord-la-left", classes="btn-nav"))
        await la_nav.mount(Button("Trigger", id="coord-la-trigger", classes="btn-nav"))
        await la_nav.mount(Button("▶", id="coord-la-right", classes="btn-nav"))
        await la_nav.mount(Button("▶▶", id="coord-la-right-fast", classes="btn-nav"))

        # Switch to coordination tab
        tabs.active = "tab-coordination"
        self.notify("Coordination mode - UART monitor, glitcher, and logic analyzer")

    async def action_toggle_split(self) -> None:
        """Toggle split view mode"""
        tabs = self.query_one("#main-tabs", TabbedContent)

        if self._split_view_active:
            # Remove split view tab
            try:
                await tabs.remove_pane("tab-split")
                self._split_view_active = False
                # Clean up split panels
                for panel in self.split_panels.values():
                    await panel.disconnect()
                self.split_panels.clear()
                self.notify("Split view closed")
            except Exception:
                pass
        else:
            # Check if we have at least 2 connected devices
            if len(self.connected_panels) < 2:
                self.notify("Connect at least 2 devices for split view", severity="warning")
                return

            # Create split view tab
            await self._create_split_view()
            self._split_view_active = True

    async def _create_split_view(self) -> None:
        """Create a split view with device selectors"""
        tabs = self.query_one("#main-tabs", TabbedContent)

        # Create the split view pane
        pane = TabPane("Split View", id="tab-split")
        await tabs.add_pane(pane)

        # Build split view content - create widgets directly, no context manager
        split_content = Vertical(id="split-content")
        await pane.mount(split_content)

        # Device selector row
        selector_row = Horizontal(id="split-selectors", classes="split-selector-row")
        await split_content.mount(selector_row)

        # Build device options from connected panels
        # Note: connected_panels keys should match available_devices keys (device_type or device_type_N)
        device_options: List[Tuple[str, str]] = []
        for device_id, info in self.available_devices.items():
            if device_id in self.connected_panels:
                device_options.append((info.name, device_id))

        # Debug: if no options found, show available info
        if not device_options:
            self.notify(f"No connected devices found. Connected: {list(self.connected_panels.keys())}, Available: {list(self.available_devices.keys())}", severity="warning")

        # Left pane selector
        await selector_row.mount(Static("Left:", classes="split-label"))
        left_select = Select(
            options=device_options if device_options else [("No devices", "none")],
            id="select-left",
            classes="split-select",
            prompt="Select device",
            allow_blank=True
        )
        await selector_row.mount(left_select)

        # Right pane selector
        await selector_row.mount(Static("Right:", classes="split-label"))
        right_select = Select(
            options=device_options if device_options else [("No devices", "none")],
            id="select-right",
            classes="split-select",
            prompt="Select device",
            allow_blank=True
        )
        await selector_row.mount(right_select)

        # Main split container
        split_container = Horizontal(id="split-container", classes="split-container")
        await split_content.mount(split_container)

        # Create left and right panes with divider
        left_pane = Vertical(id="split-left", classes="split-pane")
        divider = Static("│" * 50, classes="split-divider")  # Vertical line
        right_pane = Vertical(id="split-right", classes="split-pane")

        await split_container.mount(left_pane)
        await split_container.mount(divider)
        await split_container.mount(right_pane)

        # Add placeholders
        await left_pane.mount(Static("Select a device above", classes="split-placeholder"))
        await right_pane.mount(Static("Select a device above", classes="split-placeholder"))

        # Switch to split view
        tabs.active = "tab-split"
        self.notify("Split view opened - select devices above")

    async def _update_split_pane(self, pane_id: str, device_id: str) -> None:
        """Update a split pane with a device panel or mirror"""
        try:
            pane = self.query_one(f"#{pane_id}", Vertical)
            await pane.remove_children()

            device_info = self.available_devices.get(device_id)
            if not device_info:
                await pane.mount(Static(f"Device '{device_id}' not found", classes="split-placeholder"))
                return

            # Clean up old panel/mirror in this pane
            old_panel = self.split_panels.get(pane_id)
            if old_panel:
                await old_panel.disconnect()
                del self.split_panels[pane_id]

            # Check if this device already has a connected panel
            existing_panel = self.connected_panels.get(device_id)

            if existing_panel:
                # Device is already connected - create a mirror view instead
                # This avoids creating duplicate serial connections
                mirror = SplitPanelMirror(
                    device_info=device_info,
                    source_panel=existing_panel,
                    id=f"mirror-{pane_id}-{device_id.replace('/', '_').replace(':', '_')}"
                )
                self.split_panels[pane_id] = mirror
                await pane.mount(mirror)
                self.notify(f"Showing {device_info.name} output")

            else:
                # No existing panel - this shouldn't happen in split view
                # since we only show connected devices in the selector
                await pane.mount(Static(f"Device '{device_info.name}' not connected", classes="split-placeholder"))
                self.notify(f"Device {device_info.name} is not connected", severity="warning")

        except Exception as e:
            import traceback
            self.notify(f"Error updating split pane: {e}", severity="error")
            # Log traceback to help debug
            traceback.print_exc()

    async def on_select_changed(self, event: Select.Changed) -> None:
        """Handle device selection in split view (app-level handler)"""
        select_id = event.select.id
        if not select_id:
            return

        # Only handle split view selectors
        # Ignore events from other Select widgets (e.g., in device panels)
        if select_id not in ("select-left", "select-right"):
            return

        device_id = str(event.value) if event.value else None
        if not device_id or device_id == "none":
            return

        if select_id == "select-left":
            await self._update_split_pane("split-left", device_id)
        elif select_id == "select-right":
            await self._update_split_pane("split-right", device_id)

    async def refresh_device_list(self) -> None:
        """Detect devices and update the list"""
        # Detect devices
        detected = detect()

        # Convert to our format
        self.available_devices = {}
        for device_id, device_info in detected.items():
            self.available_devices[device_id] = device_info

        # Update UI
        await self._update_device_list_ui()

        self.notify(f"Found {len(self.available_devices)} device(s)")

    async def _update_device_list_ui(self) -> None:
        """Update the device list in the UI"""
        try:
            device_list = self.query_one("#device-list", ScrollableContainer)
            await device_list.remove_children()

            if not self.available_devices:
                await device_list.mount(
                    Static("No devices detected. Connect a device and click Refresh.", classes="no-devices")
                )
                return

            # Add device entries - compact single-line format
            for device_id, device_info in self.available_devices.items():
                is_connected = device_id in self.connected_panels

                # Create compact device entry
                entry = Horizontal(classes="device-entry")
                await device_list.mount(entry)

                # Status indicator (● connected, ○ disconnected)
                status_symbol = "●" if is_connected else "○"
                status_class = "status-connected" if is_connected else "status-disconnected"
                await entry.mount(Static(status_symbol, classes=f"status-indicator {status_class}"))

                # Device name
                await entry.mount(Static(device_info.name, classes="device-name"))

                # Port path
                await entry.mount(Static(device_info.port or "N/A", classes="device-port"))

                # Capabilities (abbreviated)
                caps = ", ".join(device_info.capabilities[:4]) if device_info.capabilities else "-"
                if len(device_info.capabilities) > 4:
                    caps += "..."
                await entry.mount(Static(f"[{caps}]", classes="device-caps"))

                # Connect/Disconnect button
                if is_connected:
                    btn = Button("Disconnect", id=f"disconnect-{device_id}", classes="btn-disconnect")
                else:
                    btn = Button("Connect", id=f"connect-{device_id}", classes="btn-connect")
                await entry.mount(btn)

        except Exception as e:
            self.notify(f"Error updating device list: {e}", severity="error")

    def _get_panel_class(self, device_info: DeviceInfo) -> Type[DevicePanel]:
        """Get the appropriate panel class for a device"""
        key = (device_info.vid, device_info.pid)

        if key in DEVICE_PANELS:
            return DEVICE_PANELS[key]

        # Check capabilities for generic panel selection
        if device_info.capabilities:
            caps = [c.lower() for c in device_info.capabilities]
            if "glitch" in caps:
                return BoltPanel
            if "swd" in caps or "jtag" in caps:
                return TigardPanel
            if "spi" in caps or "i2c" in caps:
                return BusPiratePanel

        # Default to UART monitor for unknown serial devices
        return UARTMonitorPanel

    async def connect_device(self, device_id: str) -> None:
        """Connect to a device and create its tab"""
        if device_id in self.connected_panels:
            self.notify(f"Already connected to {device_id}")
            return

        device_info = self.available_devices.get(device_id)
        if not device_info:
            self.notify(f"Device not found: {device_id}", severity="error")
            return

        try:
            # Get appropriate panel class
            panel_class = self._get_panel_class(device_info)

            # Create panel instance
            self._tab_counter += 1
            tab_id = f"tab-device-{self._tab_counter}"

            panel = panel_class(device_info, self, id=f"panel-{device_id}")

            # Store panel reference
            self.connected_panels[device_id] = panel

            # Add tab to tabbed content
            tabs = self.query_one("#main-tabs", TabbedContent)

            # Create tab pane with panel
            pane = TabPane(device_info.name, id=tab_id)
            await tabs.add_pane(pane)
            await pane.mount(panel)

            # Connect to device
            success = await panel.connect()

            if success:
                # Switch to new tab
                tabs.active = tab_id
                self.notify(f"Connected to {device_info.name}")
            else:
                # Remove tab on failure
                await tabs.remove_pane(tab_id)
                del self.connected_panels[device_id]
                self.notify(f"Failed to connect to {device_info.name}", severity="error")

            # Update device list
            await self._update_device_list_ui()

        except Exception as e:
            self.notify(f"Connection error: {e}", severity="error")

    async def disconnect_device(self, device_id: str) -> None:
        """Disconnect from a device and remove its tab"""
        panel = self.connected_panels.get(device_id)
        if not panel:
            return

        try:
            # Disconnect panel
            await panel.disconnect()

            # Find and remove tab
            tabs = self.query_one("#main-tabs", TabbedContent)
            for pane in tabs.query(TabPane):
                if panel in pane.query("*"):
                    await tabs.remove_pane(pane.id)
                    break

            # Remove from connected panels
            del self.connected_panels[device_id]

            # Update device list
            await self._update_device_list_ui()

            self.notify(f"Disconnected from {panel.device_info.name}")

        except Exception as e:
            self.notify(f"Disconnect error: {e}", severity="error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id
        if not button_id:
            return

        if button_id == "btn-refresh":
            await self.refresh_device_list()

        elif button_id == "btn-add-manual":
            self.notify("Manual device addition not yet implemented")

        elif button_id.startswith("connect-"):
            device_id = button_id.replace("connect-", "")
            await self.connect_device(device_id)

        elif button_id.startswith("disconnect-"):
            device_id = button_id.replace("disconnect-", "")
            await self.disconnect_device(device_id)

        # Coordination tab - UART
        elif button_id == "coord-uart-send":
            await self._coord_uart_send()

        # Coordination tab - Glitcher
        elif button_id == "coord-glitch-arm":
            await self._coord_glitch_arm()
        elif button_id == "coord-glitch-trigger":
            await self._coord_glitch_trigger()
        elif button_id == "coord-glitch-disarm":
            await self._coord_glitch_disarm()

        # Coordination tab - Trigger Routes
        elif button_id == "coord-add-route":
            await self._coord_add_route()
        elif button_id == "coord-arm":
            await self._coord_arm_coordinator()
        elif button_id == "coord-disarm":
            await self._coord_disarm_coordinator()
        elif button_id == "coord-clear-routes":
            await self._coord_clear_routes()

        # Coordination tab - Logic Analyzer
        elif button_id == "coord-la-capture":
            await self._coord_la_capture()
        elif button_id == "coord-la-demo":
            await self._coord_la_demo()
        elif button_id in ("coord-la-left", "coord-la-left-fast", "coord-la-right", "coord-la-right-fast", "coord-la-trigger"):
            await self._coord_la_navigate(button_id)

    # -------------------------------------------------------------------------
    # Coordination Tab Handlers
    # -------------------------------------------------------------------------

    async def _coord_uart_send(self) -> None:
        """Send data to selected UART device"""
        from textual.widgets import Input, Log
        try:
            # Get selected device
            device_select = self.query_one("#coord-uart-device", Select)
            device_id = device_select.value
            if device_id == "none" or device_id not in self.connected_panels:
                self.notify("No UART device selected", severity="warning")
                return

            # Get input text
            uart_input = self.query_one("#coord-uart-input", Input)
            text = uart_input.value
            if not text:
                return

            # Get the panel and send data
            panel = self.connected_panels[device_id]
            if hasattr(panel, 'backend') and panel.backend:
                # Use backend's UART write if available
                if hasattr(panel.backend, 'uart_write'):
                    await panel.backend.uart_write(text.encode() + b'\n')
                elif hasattr(panel.backend, 'write'):
                    panel.backend.write(text.encode() + b'\n')

            # Log what we sent
            uart_log = self.query_one("#coord-uart-log", Log)
            uart_log.write(f"> {text}\n")
            uart_input.value = ""

        except Exception as e:
            self.notify(f"UART send failed: {e}", severity="error")

    async def _coord_glitch_arm(self) -> None:
        """Arm the glitcher"""
        from textual.widgets import Input
        try:
            device_select = self.query_one("#coord-glitch-device", Select)
            device_id = device_select.value
            if device_id == "none" or device_id not in self.connected_panels:
                self.notify("No glitch device selected", severity="warning")
                return

            panel = self.connected_panels[device_id]
            if hasattr(panel, 'backend') and panel.backend:
                # Get parameters
                width = int(self.query_one("#coord-glitch-width", Input).value or "50")
                delay = int(self.query_one("#coord-glitch-delay", Input).value or "100")
                repeat = int(self.query_one("#coord-glitch-repeat", Input).value or "1")

                # Configure and arm
                if hasattr(panel.backend, 'glitch_configure'):
                    await panel.backend.glitch_configure(width=width, delay=delay, repeat=repeat)
                if hasattr(panel.backend, 'glitch_arm'):
                    await panel.backend.glitch_arm()

                # Update status
                status = self.query_one("#coord-glitch-status", Static)
                status.update("ARMED")
                status.styles.color = "#F5A623"
                self.notify("Glitcher armed")
        except Exception as e:
            self.notify(f"Arm failed: {e}", severity="error")

    async def _coord_glitch_trigger(self) -> None:
        """Manually trigger the glitcher"""
        try:
            device_select = self.query_one("#coord-glitch-device", Select)
            device_id = device_select.value
            if device_id == "none" or device_id not in self.connected_panels:
                self.notify("No glitch device selected", severity="warning")
                return

            panel = self.connected_panels[device_id]
            if hasattr(panel, 'backend') and panel.backend:
                if hasattr(panel.backend, 'glitch_trigger'):
                    await panel.backend.glitch_trigger()
                    self.notify("Glitch triggered!")

        except Exception as e:
            self.notify(f"Trigger failed: {e}", severity="error")

    async def _coord_glitch_disarm(self) -> None:
        """Disarm the glitcher"""
        try:
            device_select = self.query_one("#coord-glitch-device", Select)
            device_id = device_select.value
            if device_id == "none" or device_id not in self.connected_panels:
                self.notify("No glitch device selected", severity="warning")
                return

            panel = self.connected_panels[device_id]
            if hasattr(panel, 'backend') and panel.backend:
                if hasattr(panel.backend, 'glitch_disarm'):
                    await panel.backend.glitch_disarm()

            # Update status
            status = self.query_one("#coord-glitch-status", Static)
            status.update("Ready")
            status.styles.color = "#7FD962"
            self.notify("Glitcher disarmed")

        except Exception as e:
            self.notify(f"Disarm failed: {e}", severity="error")

    async def _coord_la_capture(self) -> None:
        """Start logic analyzer capture"""
        from .panels.logic_analyzer import LogicAnalyzerWidget
        try:
            device_select = self.query_one("#coord-la-device", Select)
            device_id = device_select.value
            if device_id == "none" or device_id not in self.connected_panels:
                self.notify("No logic analyzer device selected", severity="warning")
                return

            panel = self.connected_panels[device_id]

            # Get capture parameters
            rate = int(self.query_one("#coord-la-rate", Select).value or "1000000")
            samples = int(self.query_one("#coord-la-samples", Select).value or "4096")

            if hasattr(panel, 'backend') and panel.backend:
                # Check for SUMP support
                if hasattr(panel.backend, 'sump_capture'):
                    self.notify(f"Capturing {samples} samples at {rate/1e6:.2f} MHz...")
                    data = await panel.backend.sump_capture(rate=rate, samples=samples)

                    # Update the LA widget
                    la_widget = self.query_one("#coord-la-widget", LogicAnalyzerWidget)
                    la_widget.set_capture(data)
                    self.notify("Capture complete")
                else:
                    self.notify("Device doesn't support SUMP capture", severity="warning")

        except Exception as e:
            self.notify(f"Capture failed: {e}", severity="error")

    async def _coord_la_demo(self) -> None:
        """Load demo data into the logic analyzer"""
        from .panels.logic_analyzer import LogicAnalyzerWidget
        try:
            la_widget = self.query_one("#coord-la-widget", LogicAnalyzerWidget)
            la_widget.load_demo_data()
            self.notify("Demo data loaded")
        except Exception as e:
            self.notify(f"Demo failed: {e}", severity="error")

    async def _coord_la_navigate(self, button_id: str) -> None:
        """Handle logic analyzer navigation buttons"""
        from .panels.logic_analyzer import LogicAnalyzerWidget
        try:
            la_widget = self.query_one("#coord-la-widget", LogicAnalyzerWidget)

            if button_id == "coord-la-left":
                la_widget.scroll_left(10)
            elif button_id == "coord-la-left-fast":
                la_widget.scroll_left(50)
            elif button_id == "coord-la-right":
                la_widget.scroll_right(10)
            elif button_id == "coord-la-right-fast":
                la_widget.scroll_right(50)
            elif button_id == "coord-la-trigger":
                la_widget.scroll_to_trigger()

        except Exception as e:
            self.notify(f"Navigation failed: {e}", severity="error")

    # -------------------------------------------------------------------------
    # Coordinator Integration
    # -------------------------------------------------------------------------

    async def _coord_add_route(self) -> None:
        """Add a trigger route from UART to glitcher"""
        from textual.widgets import Input, Log
        from ..coordination import RoutingMode
        try:
            # Get pattern
            pattern_input = self.query_one("#coord-trigger-pattern", Input)
            pattern = pattern_input.value.strip()
            if not pattern:
                self.notify("Enter a pattern (regex)", severity="warning")
                return

            # Get source device (UART monitor)
            uart_select = self.query_one("#coord-uart-device", Select)
            uart_device = uart_select.value
            if uart_device == "none":
                self.notify("Select a UART device", severity="warning")
                return

            # Get target device (glitcher)
            glitch_select = self.query_one("#coord-glitch-device", Select)
            glitch_device = glitch_select.value
            if glitch_device == "none":
                self.notify("Select a glitch device", severity="warning")
                return

            # Get glitch parameters
            width = int(self.query_one("#coord-glitch-width", Input).value or "50")
            delay = int(self.query_one("#coord-glitch-delay", Input).value or "100")

            # Get routing mode
            mode_select = self.query_one("#coord-route-mode", Select)
            mode_str = mode_select.value
            mode = RoutingMode.HARDWARE if mode_str == "hardware" else RoutingMode.SOFTWARE

            # Create route name
            route_name = f"uart_glitch_{len(self._coordinator.routes) + 1}"

            # Add route via coordinator
            self._coordinator.add_uart_glitch_route(
                name=route_name,
                uart_device=uart_device,
                glitch_device=glitch_device,
                pattern=pattern,
                width_ns=width * 8,  # Convert cycles to ns (8.3ns/cycle)
                offset_ns=delay * 8
            )

            # Update routes display
            self._update_routes_display()

            # Log
            trigger_log = self.query_one("#coord-trigger-log", Log)
            trigger_log.write(f"[+] Added route: {route_name}\n")
            trigger_log.write(f"    Pattern: {pattern}\n")
            trigger_log.write(f"    {uart_device} → {glitch_device}\n")

            # Clear pattern input
            pattern_input.value = ""

            self.notify(f"Route added: {route_name}")

        except Exception as e:
            self.notify(f"Failed to add route: {e}", severity="error")

    async def _coord_arm_coordinator(self) -> None:
        """Arm the coordinator to start monitoring"""
        from textual.widgets import Log
        from .device_pool import DeviceState
        try:
            # Initialize device pool with connected panels
            for device_id, panel in self.connected_panels.items():
                if device_id not in self._coordinator.pool.devices:
                    device_info = self.available_devices.get(device_id)
                    if device_info:
                        state = DeviceState(
                            device_info=device_info,
                            backend=getattr(panel, 'backend', None),
                            connected=True
                        )
                        self._coordinator.pool.devices[device_id] = state

            # Set up callbacks
            def on_trigger(event):
                try:
                    trigger_log = self.query_one("#coord-trigger-log", Log)
                    status = "✓" if event.success else "✗"
                    trigger_log.write(f"[{status}] {event.route_name}: {event.details}\n")
                except Exception:
                    pass

            def on_status(status):
                try:
                    status_widget = self.query_one("#coord-status", Static)
                    status_widget.update(status)
                    if status == "ARMED":
                        status_widget.styles.color = "#F5A623"
                    else:
                        status_widget.styles.color = "#7FD962"
                except Exception:
                    pass

            self._coordinator.set_callbacks(
                on_trigger=on_trigger,
                on_status_change=on_status,
                log_callback=lambda msg: self.query_one("#coord-trigger-log", Log).write(f"{msg}\n")
            )

            # Arm
            if await self._coordinator.arm():
                self.notify("Coordinator armed - monitoring for triggers")
                trigger_log = self.query_one("#coord-trigger-log", Log)
                trigger_log.write(f"[*] Coordinator armed with {len(self._coordinator.routes)} routes\n")
            else:
                self.notify("Failed to arm coordinator", severity="error")

        except Exception as e:
            self.notify(f"Arm failed: {e}", severity="error")

    async def _coord_disarm_coordinator(self) -> None:
        """Disarm the coordinator"""
        from textual.widgets import Log
        try:
            await self._coordinator.disarm()
            self.notify("Coordinator disarmed")

            trigger_log = self.query_one("#coord-trigger-log", Log)
            trigger_log.write("[*] Coordinator disarmed\n")

            # Update status
            status_widget = self.query_one("#coord-status", Static)
            status_widget.update("READY")
            status_widget.styles.color = "#7FD962"

        except Exception as e:
            self.notify(f"Disarm failed: {e}", severity="error")

    async def _coord_clear_routes(self) -> None:
        """Clear all trigger routes"""
        from textual.widgets import Log
        try:
            # Disarm first if armed
            if self._coordinator.is_armed:
                await self._coordinator.disarm()

            # Clear routes
            self._coordinator.routes.clear()

            # Update display
            self._update_routes_display()

            trigger_log = self.query_one("#coord-trigger-log", Log)
            trigger_log.write("[*] All routes cleared\n")

            self.notify("All routes cleared")

        except Exception as e:
            self.notify(f"Clear failed: {e}", severity="error")

    def _update_routes_display(self) -> None:
        """Update the active routes display"""
        try:
            routes_list = self.query_one("#coord-routes-list", Static)
            if not self._coordinator.routes:
                routes_list.update("None")
            else:
                route_strs = []
                for name, route in self._coordinator.routes.items():
                    status = "●" if route.enabled else "○"
                    route_strs.append(f"{status} {name}")
                routes_list.update(" | ".join(route_strs))
        except Exception:
            pass

    @property
    def _coordinator(self):
        """Get or create coordinator instance"""
        if not hasattr(self, '_coord_instance'):
            from ..coordination import get_coordinator
            self._coord_instance = get_coordinator()
        return self._coord_instance


def run_tui():
    """Launch the TUI"""
    app = HwhApp()
    app.run()


if __name__ == "__main__":
    run_tui()
