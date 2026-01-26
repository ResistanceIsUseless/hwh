"""
Glitch Timing Calibration

Measure and compensate for latency in glitch setups to enable
portable/shareable glitch configurations.

Latency sources:
- USB round-trip time (1-10ms typical)
- Device internal processing
- Wire propagation (~5ns/meter)
- Trigger detection time

Calibration allows:
- Measuring your setup's baseline latency
- Adjusting shared configs to work on your hardware
- Comparing timing between different setups
"""

import asyncio
import time
import statistics
from typing import Optional, List, Dict, Callable, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json


@dataclass
class LatencyMeasurement:
    """A single latency measurement."""
    trigger_time: float      # When trigger command sent
    glitch_time: float       # When glitch observed (LA capture)
    latency_ns: float        # Measured latency
    configured_width_ns: int
    measured_width_ns: float
    iteration: int


@dataclass
class JitterStats:
    """Statistical analysis of timing jitter."""
    mean_ns: float
    std_dev_ns: float
    min_ns: float
    max_ns: float
    p95_ns: float           # 95th percentile
    p99_ns: float           # 99th percentile
    sample_count: int

    def __repr__(self):
        return (f"Jitter: mean={self.mean_ns:.1f}ns, "
                f"std={self.std_dev_ns:.1f}ns, "
                f"range=[{self.min_ns:.1f}, {self.max_ns:.1f}]ns")


@dataclass
class CalibrationProfile:
    """
    Calibration data for a specific hardware setup.

    This allows glitch configs to be portable - you measure your
    setup's latency, and configs adjust automatically.
    """
    # Identification
    profile_name: str
    device_type: str         # e.g., "bolt", "faultycat"
    device_id: str           # Specific device serial/id

    # Setup description
    setup_description: str   # e.g., "10cm wire, direct to target"
    wire_length_cm: float = 0.0

    # Measured values
    trigger_latency_ns: float = 0.0      # Time from command to glitch start
    trigger_jitter: Optional[JitterStats] = None

    width_accuracy: float = 1.0           # Ratio of measured/configured width
    width_jitter: Optional[JitterStats] = None

    # Reference baseline (for comparison)
    reference_latency_ns: float = 0.0    # "Standard" latency this was calibrated against

    # Metadata
    calibration_date: str = ""
    sample_count: int = 0
    notes: str = ""

    def latency_offset(self) -> float:
        """
        Calculate offset to apply to configs calibrated on reference setup.

        If your setup is faster (lower latency), offset is negative.
        If your setup is slower (higher latency), offset is positive.
        """
        return self.trigger_latency_ns - self.reference_latency_ns

    def adjust_offset(self, config_offset_ns: int) -> int:
        """Adjust a config's offset for this setup."""
        return int(config_offset_ns + self.latency_offset())

    def adjust_width(self, config_width_ns: int) -> int:
        """Adjust a config's width for this setup's accuracy."""
        if self.width_accuracy == 0:
            return config_width_ns
        return int(config_width_ns / self.width_accuracy)

    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            'profile_name': self.profile_name,
            'device_type': self.device_type,
            'device_id': self.device_id,
            'setup_description': self.setup_description,
            'wire_length_cm': self.wire_length_cm,
            'trigger_latency_ns': self.trigger_latency_ns,
            'trigger_jitter': {
                'mean_ns': self.trigger_jitter.mean_ns,
                'std_dev_ns': self.trigger_jitter.std_dev_ns,
                'min_ns': self.trigger_jitter.min_ns,
                'max_ns': self.trigger_jitter.max_ns,
                'p95_ns': self.trigger_jitter.p95_ns,
                'p99_ns': self.trigger_jitter.p99_ns,
                'sample_count': self.trigger_jitter.sample_count,
            } if self.trigger_jitter else None,
            'width_accuracy': self.width_accuracy,
            'reference_latency_ns': self.reference_latency_ns,
            'calibration_date': self.calibration_date,
            'sample_count': self.sample_count,
            'notes': self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "CalibrationProfile":
        """Deserialize from dictionary."""
        jitter_data = data.get('trigger_jitter')
        trigger_jitter = None
        if jitter_data:
            trigger_jitter = JitterStats(
                mean_ns=jitter_data['mean_ns'],
                std_dev_ns=jitter_data['std_dev_ns'],
                min_ns=jitter_data['min_ns'],
                max_ns=jitter_data['max_ns'],
                p95_ns=jitter_data['p95_ns'],
                p99_ns=jitter_data['p99_ns'],
                sample_count=jitter_data['sample_count'],
            )

        return cls(
            profile_name=data['profile_name'],
            device_type=data['device_type'],
            device_id=data['device_id'],
            setup_description=data.get('setup_description', ''),
            wire_length_cm=data.get('wire_length_cm', 0.0),
            trigger_latency_ns=data['trigger_latency_ns'],
            trigger_jitter=trigger_jitter,
            width_accuracy=data.get('width_accuracy', 1.0),
            reference_latency_ns=data.get('reference_latency_ns', 0.0),
            calibration_date=data.get('calibration_date', ''),
            sample_count=data.get('sample_count', 0),
            notes=data.get('notes', ''),
        )

    def save(self, path: str):
        """Save profile to JSON file."""
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "CalibrationProfile":
        """Load profile from JSON file."""
        with open(path, 'r') as f:
            return cls.from_dict(json.load(f))


@dataclass
class PortableGlitchConfig:
    """
    A glitch configuration that can be shared and auto-adjusted
    for different hardware setups.
    """
    # Target info
    target_name: str         # e.g., "STM32F4 RDP Bypass"
    target_chip: str         # e.g., "STM32F407VG"

    # Logical timing (relative to calibration baseline)
    logical_width_ns: int
    logical_offset_ns: int
    repeat: int = 1

    # Calibration reference
    calibrated_on: str = ""  # Profile name this was calibrated with
    reference_latency_ns: float = 0.0

    # Success criteria
    success_pattern: str = ""

    # Metadata
    author: str = ""
    notes: str = ""
    created_date: str = ""

    def get_adjusted_params(self, profile: CalibrationProfile) -> Tuple[int, int]:
        """
        Get width and offset adjusted for a specific calibration profile.

        Returns:
            (adjusted_width_ns, adjusted_offset_ns)
        """
        adjusted_width = profile.adjust_width(self.logical_width_ns)
        adjusted_offset = profile.adjust_offset(self.logical_offset_ns)
        return adjusted_width, adjusted_offset

    def to_dict(self) -> Dict:
        return {
            'target_name': self.target_name,
            'target_chip': self.target_chip,
            'logical_width_ns': self.logical_width_ns,
            'logical_offset_ns': self.logical_offset_ns,
            'repeat': self.repeat,
            'calibrated_on': self.calibrated_on,
            'reference_latency_ns': self.reference_latency_ns,
            'success_pattern': self.success_pattern,
            'author': self.author,
            'notes': self.notes,
            'created_date': self.created_date,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "PortableGlitchConfig":
        return cls(**data)

    def save(self, path: str):
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "PortableGlitchConfig":
        with open(path, 'r') as f:
            return cls.from_dict(json.load(f))


class GlitchCalibrator:
    """
    Measure glitch timing latency and jitter.

    Methods:
    1. Loopback test - Connect glitch output to LA input
    2. Cross-device - Use one device's LA to measure another's glitch

    Example - Loopback calibration with Bolt:
        >>> calibrator = GlitchCalibrator(
        ...     glitch_backend=bolt,
        ...     la_backend=bolt,  # Same device for loopback
        ...     glitch_output_channel=0  # Which LA channel has glitch output
        ... )
        >>> profile = await calibrator.run_calibration(
        ...     profile_name="my_bolt_setup",
        ...     iterations=100
        ... )
        >>> print(f"Latency: {profile.trigger_latency_ns:.0f}ns")
        >>> print(f"Jitter: {profile.trigger_jitter}")
        >>> profile.save("my_calibration.json")

    Example - Cross-device calibration:
        >>> # Bolt glitches, Bus Pirate LA captures
        >>> calibrator = GlitchCalibrator(
        ...     glitch_backend=bolt,
        ...     la_backend=buspirate,
        ...     glitch_output_channel=0
        ... )
    """

    def __init__(
        self,
        glitch_backend,
        la_backend,
        glitch_output_channel: int = 0,
        la_sample_rate: int = 31_250_000,  # 31.25 MHz for Bolt
        log_callback: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize calibrator.

        Args:
            glitch_backend: Backend that triggers glitches
            la_backend: Backend with logic analyzer to capture glitch
            glitch_output_channel: LA channel connected to glitch output
            la_sample_rate: Logic analyzer sample rate
            log_callback: Logging callback
        """
        self.glitch = glitch_backend
        self.la = la_backend
        self.channel = glitch_output_channel
        self.sample_rate = la_sample_rate
        self.log = log_callback or print

        self.measurements: List[LatencyMeasurement] = []

    async def run_calibration(
        self,
        profile_name: str,
        device_type: str = "",
        setup_description: str = "",
        iterations: int = 100,
        test_width_ns: int = 500,
        cooldown_ms: float = 10.0,
        reference_latency_ns: float = 0.0
    ) -> CalibrationProfile:
        """
        Run calibration measurement.

        Args:
            profile_name: Name for this calibration profile
            device_type: Type of glitch device
            setup_description: Description of physical setup
            iterations: Number of measurements to take
            test_width_ns: Glitch width to use for testing
            cooldown_ms: Delay between tests
            reference_latency_ns: Reference baseline for comparison

        Returns:
            CalibrationProfile with measured values
        """
        self.measurements = []

        self.log(f"[Calibration] Starting calibration: {profile_name}")
        self.log(f"              Iterations: {iterations}")
        self.log(f"              Test width: {test_width_ns}ns")
        self.log(f"              LA channel: {self.channel}")
        self.log(f"              Sample rate: {self.sample_rate/1e6:.2f} MHz")

        # Configure glitch
        from ..backends import GlitchConfig
        config = GlitchConfig(width_ns=test_width_ns, offset_ns=0)
        self.glitch.configure_glitch(config)

        sample_period_ns = 1e9 / self.sample_rate

        for i in range(iterations):
            measurement = await self._measure_once(
                iteration=i,
                configured_width_ns=test_width_ns,
                sample_period_ns=sample_period_ns
            )

            if measurement:
                self.measurements.append(measurement)

            if (i + 1) % 10 == 0:
                self.log(f"              Progress: {i+1}/{iterations}")

            await asyncio.sleep(cooldown_ms / 1000)

        # Analyze results
        if not self.measurements:
            self.log("[Calibration] No valid measurements!")
            return CalibrationProfile(
                profile_name=profile_name,
                device_type=device_type,
                device_id="",
                setup_description=setup_description,
            )

        # Calculate latency statistics
        latencies = [m.latency_ns for m in self.measurements]
        trigger_jitter = self._calculate_jitter(latencies)

        # Calculate width accuracy
        widths = [m.measured_width_ns for m in self.measurements if m.measured_width_ns > 0]
        if widths:
            mean_width = statistics.mean(widths)
            width_accuracy = mean_width / test_width_ns
            width_jitter = self._calculate_jitter(widths)
        else:
            width_accuracy = 1.0
            width_jitter = None

        profile = CalibrationProfile(
            profile_name=profile_name,
            device_type=device_type or self._get_device_type(),
            device_id=self._get_device_id(),
            setup_description=setup_description,
            trigger_latency_ns=trigger_jitter.mean_ns,
            trigger_jitter=trigger_jitter,
            width_accuracy=width_accuracy,
            width_jitter=width_jitter,
            reference_latency_ns=reference_latency_ns,
            calibration_date=datetime.now().isoformat(),
            sample_count=len(self.measurements),
        )

        self.log(f"[Calibration] Complete!")
        self.log(f"              Latency: {trigger_jitter.mean_ns:.1f}ns "
                f"(±{trigger_jitter.std_dev_ns:.1f}ns)")
        self.log(f"              Width accuracy: {width_accuracy:.2%}")
        self.log(f"              Valid samples: {len(self.measurements)}/{iterations}")

        return profile

    async def _measure_once(
        self,
        iteration: int,
        configured_width_ns: int,
        sample_period_ns: float
    ) -> Optional[LatencyMeasurement]:
        """Perform a single latency measurement."""
        try:
            # Arm LA to capture on rising edge (glitch start)
            # We'll capture a small window and look for the glitch pulse

            # Record trigger time
            trigger_time = time.perf_counter_ns()

            # Start capture and trigger glitch nearly simultaneously
            # The LA should be waiting for trigger
            capture_task = asyncio.create_task(self._capture_glitch())

            # Small delay then trigger
            await asyncio.sleep(0.001)  # 1ms
            glitch_trigger_time = time.perf_counter_ns()
            self.glitch.trigger()

            # Wait for capture
            capture_data = await capture_task

            if not capture_data:
                return None

            # Find glitch pulse in capture
            pulse_start, pulse_width = self._find_pulse(
                capture_data,
                self.channel,
                sample_period_ns
            )

            if pulse_start is None:
                return None

            # Calculate latency
            # pulse_start is in samples from capture start
            # We need to account for capture setup time
            glitch_observed_ns = pulse_start * sample_period_ns

            # The latency is from when we sent trigger command to when glitch appeared
            # This is approximate since we can't know exact USB timing
            latency_ns = glitch_observed_ns  # Relative to capture start

            return LatencyMeasurement(
                trigger_time=trigger_time,
                glitch_time=glitch_trigger_time,
                latency_ns=latency_ns,
                configured_width_ns=configured_width_ns,
                measured_width_ns=pulse_width * sample_period_ns,
                iteration=iteration
            )

        except Exception as e:
            self.log(f"[Calibration] Measurement {iteration} failed: {e}")
            return None

    async def _capture_glitch(self) -> Optional[List[int]]:
        """Capture data from logic analyzer."""
        try:
            if hasattr(self.la, 'sump_capture'):
                result = await self.la.sump_capture(
                    rate=self.sample_rate,
                    samples=1024,
                    trigger_channel=self.channel,
                    trigger_edge="rising",
                    timeout=1.0
                )
                if result and 'raw_data' in result:
                    return list(result['raw_data'])
            return None
        except Exception:
            return None

    def _find_pulse(
        self,
        data: List[int],
        channel: int,
        sample_period_ns: float
    ) -> Tuple[Optional[int], int]:
        """
        Find a pulse on the specified channel.

        Returns:
            (pulse_start_sample, pulse_width_samples) or (None, 0) if not found
        """
        mask = 1 << channel
        in_pulse = False
        pulse_start = None
        pulse_width = 0

        for i, sample in enumerate(data):
            is_high = (sample & mask) != 0

            if is_high and not in_pulse:
                # Pulse start
                in_pulse = True
                pulse_start = i
            elif not is_high and in_pulse:
                # Pulse end
                pulse_width = i - pulse_start
                return pulse_start, pulse_width

        # Pulse didn't end in capture
        if in_pulse and pulse_start is not None:
            pulse_width = len(data) - pulse_start
            return pulse_start, pulse_width

        return None, 0

    def _calculate_jitter(self, values: List[float]) -> JitterStats:
        """Calculate jitter statistics from measurements."""
        if not values:
            return JitterStats(0, 0, 0, 0, 0, 0, 0)

        sorted_values = sorted(values)
        n = len(sorted_values)

        return JitterStats(
            mean_ns=statistics.mean(values),
            std_dev_ns=statistics.stdev(values) if n > 1 else 0,
            min_ns=min(values),
            max_ns=max(values),
            p95_ns=sorted_values[int(n * 0.95)] if n > 1 else sorted_values[0],
            p99_ns=sorted_values[int(n * 0.99)] if n > 1 else sorted_values[0],
            sample_count=n
        )

    def _get_device_type(self) -> str:
        """Get device type from backend."""
        if hasattr(self.glitch, 'device') and hasattr(self.glitch.device, 'device_type'):
            return self.glitch.device.device_type
        return "unknown"

    def _get_device_id(self) -> str:
        """Get device ID from backend."""
        if hasattr(self.glitch, 'device') and hasattr(self.glitch.device, 'serial'):
            return self.glitch.device.serial or ""
        return ""

    def get_measurements(self) -> List[LatencyMeasurement]:
        """Get raw measurements."""
        return self.measurements

    def export_measurements(self, path: str):
        """Export measurements to CSV."""
        with open(path, 'w') as f:
            f.write("iteration,latency_ns,configured_width_ns,measured_width_ns\n")
            for m in self.measurements:
                f.write(f"{m.iteration},{m.latency_ns:.1f},"
                       f"{m.configured_width_ns},{m.measured_width_ns:.1f}\n")


class CalibrationManager:
    """
    Manage calibration profiles.

    Stores profiles in ~/.config/hwh/calibrations/
    """

    def __init__(self, config_dir: str = None):
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            self.config_dir = Path.home() / ".config" / "hwh" / "calibrations"

        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.profiles: Dict[str, CalibrationProfile] = {}
        self._load_profiles()

    def _load_profiles(self):
        """Load all profiles from config directory."""
        for path in self.config_dir.glob("*.json"):
            try:
                profile = CalibrationProfile.load(str(path))
                self.profiles[profile.profile_name] = profile
            except Exception:
                pass

    def save_profile(self, profile: CalibrationProfile):
        """Save a calibration profile."""
        path = self.config_dir / f"{profile.profile_name}.json"
        profile.save(str(path))
        self.profiles[profile.profile_name] = profile

    def get_profile(self, name: str) -> Optional[CalibrationProfile]:
        """Get a profile by name."""
        return self.profiles.get(name)

    def list_profiles(self) -> List[str]:
        """List all profile names."""
        return list(self.profiles.keys())

    def delete_profile(self, name: str) -> bool:
        """Delete a profile."""
        if name not in self.profiles:
            return False

        path = self.config_dir / f"{name}.json"
        if path.exists():
            path.unlink()

        del self.profiles[name]
        return True

    def apply_calibration(
        self,
        config: PortableGlitchConfig,
        profile_name: str = None
    ) -> Tuple[int, int]:
        """
        Apply calibration to a portable config.

        Args:
            config: Portable glitch config
            profile_name: Profile to use (default: config's calibrated_on)

        Returns:
            (adjusted_width_ns, adjusted_offset_ns)
        """
        name = profile_name or config.calibrated_on
        profile = self.get_profile(name)

        if not profile:
            # No calibration, return original values
            return config.logical_width_ns, config.logical_offset_ns

        return config.get_adjusted_params(profile)


# Convenience functions

async def calibrate_setup(
    glitch_backend,
    la_backend,
    profile_name: str,
    channel: int = 0,
    iterations: int = 100,
    log_callback: Optional[Callable[[str], None]] = None
) -> CalibrationProfile:
    """
    Convenience function to calibrate a setup.

    Args:
        glitch_backend: Glitch device backend
        la_backend: Logic analyzer backend
        profile_name: Name for the calibration profile
        channel: LA channel connected to glitch output
        iterations: Number of measurements
        log_callback: Logging callback

    Returns:
        CalibrationProfile with results
    """
    calibrator = GlitchCalibrator(
        glitch_backend=glitch_backend,
        la_backend=la_backend,
        glitch_output_channel=channel,
        log_callback=log_callback
    )

    profile = await calibrator.run_calibration(
        profile_name=profile_name,
        iterations=iterations
    )

    # Auto-save to default location
    manager = CalibrationManager()
    manager.save_profile(profile)

    return profile
