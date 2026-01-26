"""
Calibration Panel

Provides a guided calibration workflow for glitch timing measurement.
Shows device-specific wiring instructions and runs calibration procedures.
"""

import asyncio
from typing import Optional, Dict, List, Any
from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widgets import Static, Button, Input, Log, Select, ProgressBar, DataTable
from textual.reactive import reactive


# Device-specific calibration configurations
@dataclass
class CalibrationWiring:
    """Wiring instructions for calibration setup."""
    device_name: str
    glitch_output_pin: str
    la_input_channel: str
    wire_instructions: List[str]
    diagram: str
    notes: List[str]


# Wiring configurations for supported devices
CALIBRATION_CONFIGS: Dict[str, CalibrationWiring] = {
    "Curious Bolt": CalibrationWiring(
        device_name="Curious Bolt",
        glitch_output_pin="GLITCH OUT",
        la_input_channel="LA CH0",
        wire_instructions=[
            "1. Locate the GLITCH OUT pin on the Bolt header",
            "2. Locate the LA CH0 pin (Logic Analyzer Channel 0)",
            "3. Connect a short wire between GLITCH OUT and LA CH0",
            "4. Use the shortest wire possible for accurate measurement",
        ],
        diagram="""
    Curious Bolt Header
    ┌─────────────────────┐
    │  GND  GLITCH  TRIG  │
    │   ●     ●      ●    │
    │         │           │
    │         │  (wire)   │
    │         ▼           │
    │   ●     ●      ●    │
    │  VCC  LA_CH0  CH1   │
    └─────────────────────┘

    Connect GLITCH OUT → LA CH0 with a short jumper wire
""",
        notes=[
            "Use a wire similar to your actual glitch setup for realistic latency",
            "Shorter wires = lower latency, longer wires = higher latency",
            "Run multiple calibration iterations for stable jitter measurement",
            "Save your profile with a descriptive name (e.g., 'bolt_10cm_wire')",
        ],
    ),

    "Bus Pirate": CalibrationWiring(
        device_name="Bus Pirate 5/6",
        glitch_output_pin="AUX (IO0)",
        la_input_channel="LA CH0",
        wire_instructions=[
            "1. Enable Logic Analyzer mode on Bus Pirate",
            "2. Connect IO0 (AUX) to LA CH0",
            "3. The calibration will pulse IO0 and measure on LA",
            "Note: Bus Pirate is typically used as a monitor, not glitcher",
        ],
        diagram="""
    Bus Pirate 5/6 Header
    ┌──────────────────────────┐
    │  MOSI MISO CLK  CS  AUX  │
    │   ●    ●    ●   ●    ●   │
    │                      │   │
    │                (wire)│   │
    │                      ▼   │
    │   ●    ●    ●   ●    ●   │
    │  LA0  LA1  LA2 LA3  GND  │
    └──────────────────────────┘

    Connect AUX (IO0) → LA0 with a short jumper wire
""",
        notes=[
            "Bus Pirate is typically used as UART/protocol monitor",
            "For glitch timing, calibrate using Curious Bolt instead",
            "This calibration measures Bus Pirate IO response time only",
        ],
    ),
}


class CalibrationPanel(Container):
    """
    Panel for glitch timing calibration.

    Provides:
    - Device-specific wiring instructions
    - Guided calibration workflow
    - Profile saving and loading
    - Latency and jitter display
    """

    # Reactive state
    calibration_running = reactive(False)
    current_device = reactive("")

    def __init__(self, app, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hwh_app = app
        self._calibration_task: Optional[asyncio.Task] = None
        self._current_profile = None

    def compose(self) -> ComposeResult:
        with Vertical(id="calibration-panel"):
            # Header
            yield Static("Glitch Calibration", id="calibration-title", classes="panel-title")
            yield Static(
                "Measure trigger-to-glitch latency for accurate timing parameters",
                classes="panel-subtitle"
            )

            # Main content in two columns
            with Horizontal(classes="calibration-main"):
                # Left column: Instructions and wiring
                with Vertical(id="calibration-instructions", classes="calibration-column"):
                    yield Static("Setup Instructions", classes="section-title")

                    # Device selector
                    with Horizontal(classes="device-select-row"):
                        yield Static("Device:", classes="field-label")
                        yield Select(
                            [
                                ("Curious Bolt", "Curious Bolt"),
                                ("Bus Pirate", "Bus Pirate"),
                            ],
                            id="calibration-device-select",
                            prompt="Select device...",
                            classes="calibration-select"
                        )

                    # Wiring instructions container
                    with ScrollableContainer(id="wiring-container", classes="wiring-container"):
                        yield Static(
                            "Select a device to see wiring instructions",
                            id="wiring-instructions",
                            classes="wiring-text"
                        )

                    # Wiring diagram
                    yield Static(
                        "",
                        id="wiring-diagram",
                        classes="wiring-diagram"
                    )

                # Right column: Calibration controls and results
                with Vertical(id="calibration-controls", classes="calibration-column"):
                    yield Static("Calibration", classes="section-title")

                    # Profile name input
                    with Horizontal(classes="input-row"):
                        yield Static("Profile name:", classes="field-label")
                        yield Input(
                            placeholder="e.g., bolt_10cm_wire",
                            id="profile-name-input",
                            classes="profile-input"
                        )

                    # Iterations selector
                    with Horizontal(classes="input-row"):
                        yield Static("Iterations:", classes="field-label")
                        yield Select(
                            [
                                ("50 (quick)", "50"),
                                ("100 (recommended)", "100"),
                                ("200 (accurate)", "200"),
                                ("500 (precise)", "500"),
                            ],
                            value="100",
                            id="iterations-select",
                            classes="calibration-select"
                        )

                    # Action buttons
                    with Horizontal(classes="button-row"):
                        yield Button(
                            "Start Calibration",
                            id="btn-start-calibration",
                            variant="primary",
                            classes="calibration-btn"
                        )
                        yield Button(
                            "Stop",
                            id="btn-stop-calibration",
                            variant="error",
                            classes="calibration-btn",
                            disabled=True
                        )

                    # Progress
                    yield ProgressBar(
                        id="calibration-progress",
                        total=100,
                        show_percentage=True,
                        classes="calibration-progress"
                    )

                    # Results section
                    yield Static("Results", classes="section-title")
                    with Container(id="results-container", classes="results-container"):
                        yield DataTable(
                            id="results-table",
                            show_header=False,
                            classes="results-table"
                        )

                    # Profile management
                    yield Static("Saved Profiles", classes="section-title")
                    with Horizontal(classes="button-row"):
                        yield Button("Load Profile", id="btn-load-profile", classes="profile-btn")
                        yield Button("Save Profile", id="btn-save-profile", classes="profile-btn")
                        yield Button("Delete", id="btn-delete-profile", variant="error", classes="profile-btn")

                    # Profiles list
                    yield Select(
                        [],
                        id="profiles-list",
                        prompt="Select saved profile...",
                        classes="profiles-select"
                    )

            # Log output
            with Container(classes="log-container"):
                yield Log(id="calibration-log", classes="calibration-log")

    async def on_mount(self) -> None:
        """Initialize panel on mount."""
        # Set up results table
        table = self.query_one("#results-table", DataTable)
        table.add_columns("Metric", "Value")
        table.add_row("Status", "Ready", key="status")
        table.add_row("Latency", "-", key="latency")
        table.add_row("Jitter (σ)", "-", key="jitter")
        table.add_row("Min", "-", key="min")
        table.add_row("Max", "-", key="max")
        table.add_row("P95", "-", key="p95")
        table.add_row("P99", "-", key="p99")

        # Load saved profiles
        await self._refresh_profiles_list()

        self._log("Calibration panel ready")
        self._log("Select a device and connect wires as shown")

    async def on_select_changed(self, event: Select.Changed) -> None:
        """Handle device selection."""
        if event.select.id == "calibration-device-select":
            device_name = str(event.value) if event.value else None
            if device_name and device_name in CALIBRATION_CONFIGS:
                await self._show_device_instructions(device_name)
                self.current_device = device_name

        elif event.select.id == "profiles-list":
            # Profile selected - could auto-load details
            pass

    async def _show_device_instructions(self, device_name: str) -> None:
        """Display wiring instructions for the selected device."""
        config = CALIBRATION_CONFIGS.get(device_name)
        if not config:
            return

        # Update wiring instructions
        instructions_text = "\n".join(config.wire_instructions)
        instructions_text += "\n\nNotes:\n" + "\n".join(f"• {note}" for note in config.notes)

        try:
            instructions = self.query_one("#wiring-instructions", Static)
            instructions.update(instructions_text)

            diagram = self.query_one("#wiring-diagram", Static)
            diagram.update(config.diagram)
        except Exception:
            pass

        self._log(f"Selected device: {device_name}")
        self._log(f"Connect: {config.glitch_output_pin} → {config.la_input_channel}")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "btn-start-calibration":
            await self._start_calibration()
        elif button_id == "btn-stop-calibration":
            self._stop_calibration()
        elif button_id == "btn-save-profile":
            await self._save_profile()
        elif button_id == "btn-load-profile":
            await self._load_selected_profile()
        elif button_id == "btn-delete-profile":
            await self._delete_selected_profile()

    async def _start_calibration(self) -> None:
        """Start the calibration procedure."""
        if self.calibration_running:
            self._log("Calibration already running")
            return

        # Get profile name
        try:
            name_input = self.query_one("#profile-name-input", Input)
            profile_name = name_input.value.strip()
            if not profile_name:
                self._log("[!] Enter a profile name")
                return
        except Exception:
            return

        # Get iterations
        try:
            iter_select = self.query_one("#iterations-select", Select)
            iterations = int(iter_select.value) if iter_select.value else 100
        except Exception:
            iterations = 100

        # Check device selection
        if not self.current_device:
            self._log("[!] Select a device first")
            return

        # Find connected device
        device_panel = self._find_connected_device()
        if not device_panel:
            self._log("[!] No matching device connected")
            self._log(f"    Connect a {self.current_device} and try again")
            return

        # Update UI state
        self.calibration_running = True
        self._update_button_states()
        self._update_result("status", "Running...")

        self._log(f"Starting calibration: {profile_name}")
        self._log(f"Device: {self.current_device}")
        self._log(f"Iterations: {iterations}")

        # Run calibration in background
        self._calibration_task = asyncio.create_task(
            self._run_calibration(device_panel, profile_name, iterations)
        )

    def _find_connected_device(self) -> Optional[Any]:
        """Find a connected device matching the current selection."""
        if not self.hwh_app or not self.current_device:
            return None

        # Look for matching connected panel
        for device_id, panel in self.hwh_app.connected_panels.items():
            if self.current_device == "Curious Bolt" and "BoltPanel" in type(panel).__name__:
                return panel
            elif self.current_device == "Bus Pirate" and "BusPiratePanel" in type(panel).__name__:
                return panel

        return None

    async def _run_calibration(self, device_panel, profile_name: str, iterations: int) -> None:
        """Run the actual calibration procedure."""
        try:
            from ...automation.calibration import GlitchCalibrator, CalibrationProfile

            # Create calibrator
            # For Bolt, we need the scope object
            glitch_backend = None
            la_backend = None

            if hasattr(device_panel, '_scope') and device_panel._scope:
                # Bolt panel with scope library
                glitch_backend = device_panel._scope
                la_backend = device_panel._scope
                self._log("Using Bolt scope for calibration")
            else:
                # Simulation mode
                self._log("[*] Running in simulation mode (no hardware)")
                await self._run_simulated_calibration(profile_name, iterations)
                return

            # Create calibrator and run
            calibrator = GlitchCalibrator(
                glitch_backend=glitch_backend,
                la_backend=la_backend,
                la_channel=0,  # CH0 for loopback
                log_callback=self._log
            )

            # Run calibration with progress updates
            progress = self.query_one("#calibration-progress", ProgressBar)

            for i in range(iterations):
                if not self.calibration_running:
                    break

                # Update progress
                progress.progress = (i + 1) / iterations * 100

                # Small delay for UI updates
                await asyncio.sleep(0.01)

            # Get results
            profile = await calibrator.run_calibration(
                profile_name=profile_name,
                iterations=iterations
            )

            if profile:
                self._current_profile = profile
                self._display_results(profile)
                self._log(f"[+] Calibration complete!")
                self._log(f"    Latency: {profile.trigger_latency_ns:.1f}ns")
                if profile.trigger_jitter:
                    self._log(f"    Jitter: ±{profile.trigger_jitter.stddev:.1f}ns")
            else:
                self._log("[!] Calibration failed")

        except ImportError as e:
            self._log(f"[!] Calibration module not available: {e}")
            await self._run_simulated_calibration(profile_name, iterations)
        except Exception as e:
            self._log(f"[!] Calibration error: {e}")
        finally:
            self.calibration_running = False
            self._update_button_states()
            self._update_result("status", "Complete" if self._current_profile else "Failed")

    async def _run_simulated_calibration(self, profile_name: str, iterations: int) -> None:
        """Run a simulated calibration for testing."""
        import random

        self._log("[*] Running simulated calibration...")
        progress = self.query_one("#calibration-progress", ProgressBar)

        # Simulate measurements
        measurements = []
        base_latency = 150 + random.random() * 50  # 150-200ns base

        for i in range(iterations):
            if not self.calibration_running:
                break

            # Simulate measurement with jitter
            latency = base_latency + random.gauss(0, 5)  # ~5ns jitter
            measurements.append(latency)

            progress.progress = (i + 1) / iterations * 100
            await asyncio.sleep(0.02)

        if measurements:
            # Calculate statistics
            import statistics
            mean = statistics.mean(measurements)
            stddev = statistics.stdev(measurements) if len(measurements) > 1 else 0
            min_val = min(measurements)
            max_val = max(measurements)
            sorted_m = sorted(measurements)
            p95 = sorted_m[int(len(sorted_m) * 0.95)]
            p99 = sorted_m[int(len(sorted_m) * 0.99)]

            # Update results
            self._update_result("latency", f"{mean:.1f}ns")
            self._update_result("jitter", f"±{stddev:.1f}ns")
            self._update_result("min", f"{min_val:.1f}ns")
            self._update_result("max", f"{max_val:.1f}ns")
            self._update_result("p95", f"{p95:.1f}ns")
            self._update_result("p99", f"{p99:.1f}ns")

            self._log(f"[+] Simulated calibration complete")
            self._log(f"    Latency: {mean:.1f}ns ± {stddev:.1f}ns")
            self._log(f"    (This is simulated data - connect hardware for real results)")

            # Create a mock profile for testing
            from ...automation.calibration import CalibrationProfile, JitterStats
            self._current_profile = CalibrationProfile(
                profile_name=profile_name,
                trigger_latency_ns=mean,
                trigger_jitter=JitterStats(
                    mean=mean,
                    stddev=stddev,
                    min=min_val,
                    max=max_val,
                    p95=p95,
                    p99=p99
                ),
                width_accuracy=0.95,
                reference_latency_ns=175.0,
                device_info={"device": "Simulated", "note": "Test data"},
                created_at=""
            )

    def _stop_calibration(self) -> None:
        """Stop the running calibration."""
        self.calibration_running = False
        if self._calibration_task:
            self._calibration_task.cancel()
            self._calibration_task = None
        self._log("[*] Calibration stopped")
        self._update_button_states()
        self._update_result("status", "Stopped")

    def _display_results(self, profile) -> None:
        """Display calibration results in the table."""
        self._update_result("latency", f"{profile.trigger_latency_ns:.1f}ns")

        if profile.trigger_jitter:
            j = profile.trigger_jitter
            self._update_result("jitter", f"±{j.stddev:.1f}ns")
            self._update_result("min", f"{j.min:.1f}ns")
            self._update_result("max", f"{j.max:.1f}ns")
            self._update_result("p95", f"{j.p95:.1f}ns")
            self._update_result("p99", f"{j.p99:.1f}ns")

    def _update_result(self, key: str, value: str) -> None:
        """Update a result in the table."""
        try:
            table = self.query_one("#results-table", DataTable)
            table.update_cell(key, "Value", value)
        except Exception:
            pass

    def _update_button_states(self) -> None:
        """Update button enabled/disabled states."""
        try:
            start_btn = self.query_one("#btn-start-calibration", Button)
            stop_btn = self.query_one("#btn-stop-calibration", Button)

            start_btn.disabled = self.calibration_running
            stop_btn.disabled = not self.calibration_running
        except Exception:
            pass

    async def _save_profile(self) -> None:
        """Save the current calibration profile."""
        if not self._current_profile:
            self._log("[!] No calibration data to save")
            self._log("    Run a calibration first")
            return

        try:
            from ...automation.calibration import CalibrationManager
            manager = CalibrationManager()
            path = manager.save_profile(self._current_profile)
            self._log(f"[+] Profile saved: {path}")
            await self._refresh_profiles_list()
        except Exception as e:
            self._log(f"[!] Save failed: {e}")

    async def _load_selected_profile(self) -> None:
        """Load the selected profile from the list."""
        try:
            profiles_select = self.query_one("#profiles-list", Select)
            profile_name = str(profiles_select.value) if profiles_select.value else None

            if not profile_name:
                self._log("[!] Select a profile to load")
                return

            from ...automation.calibration import CalibrationManager
            manager = CalibrationManager()
            profile = manager.load_profile(profile_name)

            if profile:
                self._current_profile = profile
                self._display_results(profile)
                self._log(f"[+] Loaded profile: {profile_name}")
                self._log(f"    Latency: {profile.trigger_latency_ns:.1f}ns")
            else:
                self._log(f"[!] Profile not found: {profile_name}")

        except Exception as e:
            self._log(f"[!] Load failed: {e}")

    async def _delete_selected_profile(self) -> None:
        """Delete the selected profile."""
        try:
            profiles_select = self.query_one("#profiles-list", Select)
            profile_name = str(profiles_select.value) if profiles_select.value else None

            if not profile_name:
                self._log("[!] Select a profile to delete")
                return

            from ...automation.calibration import CalibrationManager
            manager = CalibrationManager()

            if manager.delete_profile(profile_name):
                self._log(f"[+] Deleted profile: {profile_name}")
                await self._refresh_profiles_list()
            else:
                self._log(f"[!] Delete failed: {profile_name}")

        except Exception as e:
            self._log(f"[!] Delete failed: {e}")

    async def _refresh_profiles_list(self) -> None:
        """Refresh the list of saved profiles."""
        try:
            from ...automation.calibration import CalibrationManager
            manager = CalibrationManager()
            profiles = manager.list_profiles()

            profiles_select = self.query_one("#profiles-list", Select)

            options = [(name, name) for name in profiles]
            # Can't directly set options, need to remove and re-add
            # For now, just log the available profiles
            if profiles:
                self._log(f"[*] Found {len(profiles)} saved profile(s)")
        except Exception:
            pass

    def _log(self, message: str) -> None:
        """Write to the calibration log."""
        try:
            log = self.query_one("#calibration-log", Log)
            log.write_line(message)
        except Exception:
            pass
