"""
Logic Analyzer Triggered Glitching

Trigger glitches based on signal patterns captured by the logic analyzer:
- Long high/low periods (idle detection)
- Specific pulse widths
- Protocol events (start bits, chip select, etc.)
- Edge sequences

This enables precise timing attacks based on observable signal behavior.
"""

import asyncio
import time
from typing import Optional, List, Dict, Callable, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum


class TriggerPattern(Enum):
    """Types of signal patterns that can trigger glitches."""
    EDGE_RISING = "edge_rising"
    EDGE_FALLING = "edge_falling"
    PULSE_HIGH = "pulse_high"        # High pulse of specific width
    PULSE_LOW = "pulse_low"          # Low pulse of specific width
    IDLE_HIGH = "idle_high"          # Signal high for > threshold
    IDLE_LOW = "idle_low"            # Signal low for > threshold
    SEQUENCE = "sequence"            # Specific bit sequence
    SPI_CS_LOW = "spi_cs_low"        # SPI chip select goes low
    UART_START = "uart_start"        # UART start bit detected
    I2C_START = "i2c_start"          # I2C start condition
    CUSTOM = "custom"                # Custom pattern function


@dataclass
class PatternMatch:
    """A detected pattern match in captured data."""
    pattern_type: TriggerPattern
    channel: int
    sample_index: int
    timestamp_us: float
    duration_us: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LAGlitchConfig:
    """Configuration for LA-triggered glitching."""
    # Trigger pattern
    pattern: TriggerPattern
    channel: int = 0

    # Pattern parameters
    min_duration_us: float = 0.0      # Minimum pulse/idle duration
    max_duration_us: float = float('inf')  # Maximum duration
    bit_sequence: str = ""            # For SEQUENCE pattern (e.g., "10110")

    # Glitch parameters
    glitch_delay_us: float = 0.0      # Delay from trigger to glitch
    glitch_width_ns: int = 100
    glitch_offset_ns: int = 0

    # Repeat settings
    trigger_count: int = 1            # How many times to trigger (0=infinite)
    arm_delay_us: float = 0.0         # Re-arm delay after trigger


class SignalAnalyzer:
    """
    Analyze captured logic analyzer data for patterns.

    Works with data from SUMP captures (list of sample values where
    each bit represents a channel).
    """

    def __init__(self, sample_rate_hz: int = 1_000_000):
        """
        Initialize analyzer.

        Args:
            sample_rate_hz: Sample rate of captured data
        """
        self.sample_rate = sample_rate_hz
        self.sample_period_us = 1_000_000 / sample_rate_hz

    def find_edges(
        self,
        data: List[int],
        channel: int,
        edge_type: str = "both"
    ) -> List[Tuple[int, str]]:
        """
        Find all edges on a channel.

        Args:
            data: List of sample values
            channel: Channel number (0-7)
            edge_type: "rising", "falling", or "both"

        Returns:
            List of (sample_index, edge_type) tuples
        """
        edges = []
        mask = 1 << channel

        for i in range(1, len(data)):
            prev = (data[i-1] & mask) != 0
            curr = (data[i] & mask) != 0

            if prev != curr:
                if curr and edge_type in ("rising", "both"):
                    edges.append((i, "rising"))
                elif not curr and edge_type in ("falling", "both"):
                    edges.append((i, "falling"))

        return edges

    def find_pulses(
        self,
        data: List[int],
        channel: int,
        high: bool = True,
        min_samples: int = 1,
        max_samples: int = None
    ) -> List[Tuple[int, int]]:
        """
        Find pulses on a channel.

        Args:
            data: List of sample values
            channel: Channel number
            high: True for high pulses, False for low pulses
            min_samples: Minimum pulse width in samples
            max_samples: Maximum pulse width (None=no limit)

        Returns:
            List of (start_index, width_samples) tuples
        """
        pulses = []
        mask = 1 << channel
        in_pulse = False
        pulse_start = 0

        for i, sample in enumerate(data):
            is_high = (sample & mask) != 0
            target_state = is_high if high else not is_high

            if target_state and not in_pulse:
                # Pulse start
                in_pulse = True
                pulse_start = i
            elif not target_state and in_pulse:
                # Pulse end
                width = i - pulse_start
                if width >= min_samples and (max_samples is None or width <= max_samples):
                    pulses.append((pulse_start, width))
                in_pulse = False

        # Handle pulse at end of data
        if in_pulse:
            width = len(data) - pulse_start
            if width >= min_samples and (max_samples is None or width <= max_samples):
                pulses.append((pulse_start, width))

        return pulses

    def find_idle_periods(
        self,
        data: List[int],
        channel: int,
        high: bool = True,
        min_duration_us: float = 100.0
    ) -> List[PatternMatch]:
        """
        Find idle periods (long high or low states).

        Useful for detecting:
        - End of boot sequence
        - Waiting for user input
        - Between data packets

        Args:
            data: Captured samples
            channel: Channel to analyze
            high: True to find idle-high, False for idle-low
            min_duration_us: Minimum duration to consider "idle"

        Returns:
            List of PatternMatch objects
        """
        min_samples = int(min_duration_us / self.sample_period_us)
        pulses = self.find_pulses(data, channel, high=high, min_samples=min_samples)

        matches = []
        for start, width in pulses:
            duration_us = width * self.sample_period_us
            matches.append(PatternMatch(
                pattern_type=TriggerPattern.IDLE_HIGH if high else TriggerPattern.IDLE_LOW,
                channel=channel,
                sample_index=start,
                timestamp_us=start * self.sample_period_us,
                duration_us=duration_us,
                metadata={'width_samples': width}
            ))

        return matches

    def find_uart_start_bits(
        self,
        data: List[int],
        channel: int,
        baud_rate: int = 115200
    ) -> List[PatternMatch]:
        """
        Find UART start bits (falling edge followed by low period).

        UART idles high, start bit is low for 1 bit period.

        Args:
            data: Captured samples
            channel: UART RX/TX channel
            baud_rate: Expected baud rate

        Returns:
            List of start bit positions
        """
        bit_period_us = 1_000_000 / baud_rate
        bit_samples = int(bit_period_us / self.sample_period_us)

        # Allow 20% tolerance
        min_samples = int(bit_samples * 0.8)
        max_samples = int(bit_samples * 1.2)

        matches = []
        edges = self.find_edges(data, channel, "falling")

        for edge_idx, _ in edges:
            # Check if followed by appropriate low period
            end_idx = min(edge_idx + max_samples, len(data))
            mask = 1 << channel

            # Count low samples
            low_count = 0
            for i in range(edge_idx, end_idx):
                if (data[i] & mask) == 0:
                    low_count += 1
                else:
                    break

            if min_samples <= low_count <= max_samples:
                matches.append(PatternMatch(
                    pattern_type=TriggerPattern.UART_START,
                    channel=channel,
                    sample_index=edge_idx,
                    timestamp_us=edge_idx * self.sample_period_us,
                    duration_us=low_count * self.sample_period_us,
                    metadata={'baud_rate': baud_rate, 'bit_samples': bit_samples}
                ))

        return matches

    def find_spi_transactions(
        self,
        data: List[int],
        cs_channel: int,
        clk_channel: int = None
    ) -> List[PatternMatch]:
        """
        Find SPI transactions (CS low periods).

        Args:
            data: Captured samples
            cs_channel: Chip select channel
            clk_channel: Clock channel (optional, for counting clocks)

        Returns:
            List of SPI transaction matches
        """
        # Find CS low periods
        cs_lows = self.find_pulses(data, cs_channel, high=False, min_samples=1)

        matches = []
        for start, width in cs_lows:
            metadata = {'width_samples': width}

            # Count clock edges if clock channel specified
            if clk_channel is not None:
                clk_mask = 1 << clk_channel
                clk_edges = 0
                for i in range(start, min(start + width, len(data) - 1)):
                    if (data[i] & clk_mask) != (data[i+1] & clk_mask):
                        clk_edges += 1
                metadata['clock_edges'] = clk_edges
                metadata['bits_transferred'] = clk_edges // 2

            matches.append(PatternMatch(
                pattern_type=TriggerPattern.SPI_CS_LOW,
                channel=cs_channel,
                sample_index=start,
                timestamp_us=start * self.sample_period_us,
                duration_us=width * self.sample_period_us,
                metadata=metadata
            ))

        return matches

    def find_i2c_start(
        self,
        data: List[int],
        sda_channel: int,
        scl_channel: int
    ) -> List[PatternMatch]:
        """
        Find I2C start conditions (SDA falling while SCL high).

        Args:
            data: Captured samples
            sda_channel: SDA channel
            scl_channel: SCL channel

        Returns:
            List of I2C start condition matches
        """
        matches = []
        sda_mask = 1 << sda_channel
        scl_mask = 1 << scl_channel

        for i in range(1, len(data)):
            # Check for SDA falling edge
            sda_prev = (data[i-1] & sda_mask) != 0
            sda_curr = (data[i] & sda_mask) != 0

            if sda_prev and not sda_curr:
                # SDA falling - check if SCL is high
                scl_high = (data[i] & scl_mask) != 0
                if scl_high:
                    matches.append(PatternMatch(
                        pattern_type=TriggerPattern.I2C_START,
                        channel=sda_channel,
                        sample_index=i,
                        timestamp_us=i * self.sample_period_us,
                        metadata={'scl_channel': scl_channel}
                    ))

        return matches

    def find_bit_sequence(
        self,
        data: List[int],
        channel: int,
        sequence: str,
        bit_period_samples: int
    ) -> List[PatternMatch]:
        """
        Find a specific bit sequence on a channel.

        Args:
            data: Captured samples
            channel: Channel to search
            sequence: Bit sequence string (e.g., "10110")
            bit_period_samples: Samples per bit

        Returns:
            List of sequence matches
        """
        matches = []
        mask = 1 << channel
        seq_len = len(sequence)

        # Sample at middle of each bit period
        half_period = bit_period_samples // 2

        for start in range(0, len(data) - seq_len * bit_period_samples, bit_period_samples):
            match = True
            for bit_idx, expected in enumerate(sequence):
                sample_idx = start + bit_idx * bit_period_samples + half_period
                if sample_idx >= len(data):
                    match = False
                    break

                actual = '1' if (data[sample_idx] & mask) != 0 else '0'
                if actual != expected:
                    match = False
                    break

            if match:
                matches.append(PatternMatch(
                    pattern_type=TriggerPattern.SEQUENCE,
                    channel=channel,
                    sample_index=start,
                    timestamp_us=start * self.sample_period_us,
                    duration_us=seq_len * bit_period_samples * self.sample_period_us,
                    metadata={'sequence': sequence, 'bit_period': bit_period_samples}
                ))

        return matches


class LATriggeredGlitcher:
    """
    Glitch triggering based on logic analyzer patterns.

    Workflow:
    1. Capture with logic analyzer
    2. Analyze capture for patterns (idle periods, start bits, etc.)
    3. Calculate optimal glitch timing based on patterns
    4. Configure hardware trigger or software-timed glitch
    5. Arm and wait for trigger

    Example - Trigger glitch after boot idle:
        >>> glitcher = LATriggeredGlitcher(la_backend=bolt, glitch_backend=bolt)
        >>> # First, learn the pattern
        >>> patterns = await glitcher.learn_patterns(
        ...     pattern_type=TriggerPattern.IDLE_HIGH,
        ...     channel=0,
        ...     min_duration_us=1000  # 1ms idle = end of boot
        ... )
        >>> # Configure to glitch 500us after idle detected
        >>> glitcher.configure(
        ...     pattern=patterns[0],
        ...     glitch_delay_us=500,
        ...     glitch_width_ns=100
        ... )
        >>> # Arm and wait
        >>> result = await glitcher.arm_and_wait()
    """

    def __init__(
        self,
        la_backend,
        glitch_backend,
        sample_rate: int = 1_000_000,
        log_callback: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize LA-triggered glitcher.

        Args:
            la_backend: Backend with logic analyzer (SUMP) support
            glitch_backend: Backend for triggering glitches
            sample_rate: Logic analyzer sample rate
            log_callback: Logging callback
        """
        self.la = la_backend
        self.glitch = glitch_backend
        self.sample_rate = sample_rate
        self.log = log_callback or print

        self.analyzer = SignalAnalyzer(sample_rate)
        self.config: Optional[LAGlitchConfig] = None
        self._trigger_count = 0

    async def capture(
        self,
        samples: int = 4096,
        trigger_channel: int = None,
        trigger_edge: str = "falling"
    ) -> List[int]:
        """
        Capture data from logic analyzer.

        Args:
            samples: Number of samples to capture
            trigger_channel: Optional trigger channel
            trigger_edge: Trigger edge type

        Returns:
            List of sample values
        """
        self.log(f"[LA Glitch] Capturing {samples} samples at {self.sample_rate/1e6:.2f} MHz...")

        if hasattr(self.la, 'sump_capture'):
            result = await self.la.sump_capture(
                rate=self.sample_rate,
                samples=samples,
                trigger_channel=trigger_channel,
                trigger_edge=trigger_edge
            )
            if result and 'raw_data' in result:
                return list(result['raw_data'])

        self.log("[LA Glitch] Capture failed or not supported")
        return []

    async def learn_patterns(
        self,
        pattern_type: TriggerPattern,
        channel: int = 0,
        samples: int = 8192,
        **kwargs
    ) -> List[PatternMatch]:
        """
        Capture and analyze for specific patterns.

        Args:
            pattern_type: Type of pattern to look for
            channel: Channel to analyze
            samples: Capture size
            **kwargs: Pattern-specific parameters

        Returns:
            List of detected patterns
        """
        data = await self.capture(samples)
        if not data:
            return []

        self.log(f"[LA Glitch] Analyzing for {pattern_type.value} patterns...")

        if pattern_type == TriggerPattern.IDLE_HIGH:
            min_duration = kwargs.get('min_duration_us', 100)
            patterns = self.analyzer.find_idle_periods(data, channel, high=True, min_duration_us=min_duration)

        elif pattern_type == TriggerPattern.IDLE_LOW:
            min_duration = kwargs.get('min_duration_us', 100)
            patterns = self.analyzer.find_idle_periods(data, channel, high=False, min_duration_us=min_duration)

        elif pattern_type == TriggerPattern.UART_START:
            baud = kwargs.get('baud_rate', 115200)
            patterns = self.analyzer.find_uart_start_bits(data, channel, baud)

        elif pattern_type == TriggerPattern.SPI_CS_LOW:
            clk_ch = kwargs.get('clk_channel')
            patterns = self.analyzer.find_spi_transactions(data, channel, clk_ch)

        elif pattern_type == TriggerPattern.I2C_START:
            scl_ch = kwargs.get('scl_channel', channel + 1)
            patterns = self.analyzer.find_i2c_start(data, channel, scl_ch)

        elif pattern_type in (TriggerPattern.EDGE_RISING, TriggerPattern.EDGE_FALLING):
            edge_type = "rising" if pattern_type == TriggerPattern.EDGE_RISING else "falling"
            edges = self.analyzer.find_edges(data, channel, edge_type)
            patterns = [
                PatternMatch(
                    pattern_type=pattern_type,
                    channel=channel,
                    sample_index=idx,
                    timestamp_us=idx * self.analyzer.sample_period_us
                )
                for idx, _ in edges
            ]

        else:
            patterns = []

        self.log(f"[LA Glitch] Found {len(patterns)} patterns")
        return patterns

    def configure(
        self,
        pattern: TriggerPattern = TriggerPattern.EDGE_FALLING,
        channel: int = 0,
        glitch_delay_us: float = 0.0,
        glitch_width_ns: int = 100,
        glitch_offset_ns: int = 0,
        min_duration_us: float = 0.0,
        **kwargs
    ):
        """
        Configure glitch trigger.

        Args:
            pattern: Pattern type to trigger on
            channel: Channel to monitor
            glitch_delay_us: Delay from pattern to glitch
            glitch_width_ns: Glitch pulse width
            glitch_offset_ns: Additional offset
            min_duration_us: Minimum duration for pulse/idle patterns
        """
        self.config = LAGlitchConfig(
            pattern=pattern,
            channel=channel,
            min_duration_us=min_duration_us,
            glitch_delay_us=glitch_delay_us,
            glitch_width_ns=glitch_width_ns,
            glitch_offset_ns=glitch_offset_ns,
            **kwargs
        )

        self.log(f"[LA Glitch] Configured: {pattern.value} on CH{channel}")
        self.log(f"           Delay: {glitch_delay_us}us, Width: {glitch_width_ns}ns")

    async def arm_and_wait(self, timeout: float = 30.0) -> bool:
        """
        Arm the glitcher and wait for trigger pattern.

        For hardware triggers, configures the LA to trigger the glitch.
        For software triggers, continuously monitors for the pattern.

        Args:
            timeout: Maximum wait time in seconds

        Returns:
            True if glitch was triggered
        """
        if not self.config:
            self.log("[LA Glitch] Not configured!")
            return False

        self.log("[LA Glitch] Armed, waiting for trigger pattern...")

        # Configure glitch parameters
        from ..backends import GlitchConfig
        glitch_config = GlitchConfig(
            width_ns=self.config.glitch_width_ns,
            offset_ns=self.config.glitch_offset_ns
        )
        self.glitch.configure_glitch(glitch_config)

        start_time = time.time()

        while time.time() - start_time < timeout:
            # Capture a window of data
            data = await self.capture(samples=1024)
            if not data:
                await asyncio.sleep(0.1)
                continue

            # Check for pattern
            patterns = self._find_patterns(data)
            if patterns:
                pattern = patterns[0]
                self.log(f"[LA Glitch] Pattern detected at {pattern.timestamp_us:.1f}us")

                # Wait for glitch delay
                if self.config.glitch_delay_us > 0:
                    await asyncio.sleep(self.config.glitch_delay_us / 1_000_000)

                # Trigger glitch
                self.glitch.trigger()
                self._trigger_count += 1
                self.log("[LA Glitch] Glitch triggered!")
                return True

            await asyncio.sleep(0.01)

        self.log("[LA Glitch] Timeout waiting for pattern")
        return False

    def _find_patterns(self, data: List[int]) -> List[PatternMatch]:
        """Find configured pattern in data."""
        if not self.config:
            return []

        cfg = self.config

        if cfg.pattern == TriggerPattern.IDLE_HIGH:
            return self.analyzer.find_idle_periods(
                data, cfg.channel, high=True, min_duration_us=cfg.min_duration_us
            )
        elif cfg.pattern == TriggerPattern.IDLE_LOW:
            return self.analyzer.find_idle_periods(
                data, cfg.channel, high=False, min_duration_us=cfg.min_duration_us
            )
        elif cfg.pattern == TriggerPattern.EDGE_RISING:
            edges = self.analyzer.find_edges(data, cfg.channel, "rising")
            return [PatternMatch(
                pattern_type=cfg.pattern,
                channel=cfg.channel,
                sample_index=idx,
                timestamp_us=idx * self.analyzer.sample_period_us
            ) for idx, _ in edges[:1]]  # Return first match only
        elif cfg.pattern == TriggerPattern.EDGE_FALLING:
            edges = self.analyzer.find_edges(data, cfg.channel, "falling")
            return [PatternMatch(
                pattern_type=cfg.pattern,
                channel=cfg.channel,
                sample_index=idx,
                timestamp_us=idx * self.analyzer.sample_period_us
            ) for idx, _ in edges[:1]]
        elif cfg.pattern == TriggerPattern.SPI_CS_LOW:
            return self.analyzer.find_spi_transactions(data, cfg.channel)
        elif cfg.pattern == TriggerPattern.UART_START:
            return self.analyzer.find_uart_start_bits(data, cfg.channel)

        return []

    async def continuous_glitch(
        self,
        count: int = 0,
        cooldown_ms: float = 100.0,
        callback: Optional[Callable[[int], None]] = None
    ):
        """
        Continuously trigger glitches on pattern matches.

        Args:
            count: Number of glitches (0=infinite)
            cooldown_ms: Minimum time between glitches
            callback: Called after each glitch with trigger count
        """
        self.log(f"[LA Glitch] Starting continuous mode (count={count or 'infinite'})")

        triggered = 0
        while count == 0 or triggered < count:
            if await self.arm_and_wait(timeout=10.0):
                triggered += 1
                if callback:
                    callback(triggered)
                await asyncio.sleep(cooldown_ms / 1000)
            else:
                await asyncio.sleep(0.1)

        self.log(f"[LA Glitch] Complete: {triggered} glitches triggered")
