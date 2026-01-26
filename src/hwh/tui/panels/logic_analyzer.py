"""
Logic Analyzer Widget

Reusable logic analyzer display widget for TUI.
Can be embedded in device panels that support logic analyzer functionality.

Features:
- 8-channel waveform display
- ASCII art waveforms (like Bus Pirate's logic command)
- Scrollable capture buffer
- Trigger configuration
- Protocol decoding (SPI, I2C, UART)
"""

from typing import List, Optional, Tuple
from dataclasses import dataclass, field

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Container, Vertical, Horizontal
from textual.reactive import reactive

from .protocol_decoders import (
    ProtocolType, DecodedCapture, decode_protocol,
    SPITransaction, I2CTransaction, UARTFrame
)


@dataclass
class LogicCapture:
    """Captured logic data"""
    channels: int = 8
    sample_rate: int = 1000000  # 1MHz default
    samples: List[List[int]] = field(default_factory=list)
    trigger_position: int = 0
    decoded: Optional[DecodedCapture] = None  # Protocol decoded data


@dataclass
class ChannelConfig:
    """Per-channel configuration"""
    enabled: bool = True
    name: str = ""
    color: str = "#5E99AE"
    protocol_role: str = ""  # e.g., "CLK", "MOSI", "SDA"


class LogicAnalyzerWidget(Widget):
    """
    Logic analyzer waveform display widget.

    Displays captured digital signals as ASCII waveforms:
    CH0 ▔▔▔▔▔▔▁▁▁▁▁▁▔▔▔▔▔▔▁▁▁▁▁▁
    CH1 ▁▁▁▁▁▁▔▔▔▔▔▔▁▁▁▁▁▁▔▔▔▔▔▔

    Supports protocol decoding with inline annotations.
    """

    # Unicode characters for waveform drawing
    HIGH = "▔"
    LOW = "▁"
    RISING = "╱"
    FALLING = "╲"

    # Reactive properties - named to avoid conflict with Textual's scroll_offset
    waveform_offset = reactive(0)

    def __init__(
        self,
        channels: int = 8,
        visible_samples: int = 60,
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.num_channels = channels
        self.visible_samples = visible_samples

        # Channel configuration
        self.channel_configs = [
            ChannelConfig(name=f"CH{i}") for i in range(channels)
        ]

        # Capture data
        self.capture: Optional[LogicCapture] = None

        # Protocol decoding
        self._protocol = ProtocolType.NONE
        self._protocol_options: dict = {}
        self._channel_map: dict = {}

        # Display state
        self._waveform_lines: List[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="logic-analyzer"):
            # Header with scale
            yield Static(self._build_scale_line(), id="logic-scale", classes="logic-scale")

            # Waveform display area
            for i in range(self.num_channels):
                yield Static(
                    self._build_empty_channel(i),
                    id=f"logic-ch{i}",
                    classes="logic-channel"
                )

            # Protocol annotation line
            yield Static(
                "",
                id="logic-annotations",
                classes="logic-annotations"
            )

            # Footer with controls hint
            yield Static(
                "← → scroll | +/- zoom | space capture",
                classes="logic-hint"
            )

    def _build_scale_line(self) -> str:
        """Build the time scale header"""
        # Show sample numbers at regular intervals
        scale = "     "  # Padding for channel label
        for i in range(0, self.visible_samples, 10):
            pos = self.waveform_offset + i
            scale += f"{pos:<10}"
        return scale[:self.visible_samples + 5]

    def _build_empty_channel(self, channel: int) -> str:
        """Build an empty channel line"""
        label = f"CH{channel} "
        waveform = self.LOW * self.visible_samples
        return f"{label}{waveform}"

    def set_capture(self, capture: LogicCapture) -> None:
        """Set the capture data to display"""
        self.capture = capture

        # Decode protocol if one is set
        if self._protocol != ProtocolType.NONE and capture.samples:
            self._decode_protocol()

        self._update_display()

    def set_protocol(
        self,
        protocol: ProtocolType,
        channel_map: dict = None,
        **options
    ) -> None:
        """
        Set the protocol to decode.

        Args:
            protocol: Protocol type (SPI, I2C, UART, NONE)
            channel_map: Maps protocol signals to channels
                SPI: {'clk': 6, 'mosi': 7, 'miso': 4, 'cs': 5}
                I2C: {'scl': 1, 'sda': 0}
                UART: {'rx': 5}
            **options: Protocol-specific options (baud_rate, cpol, cpha, etc.)
        """
        self._protocol = protocol
        self._channel_map = channel_map or {}
        self._protocol_options = options

        # Update channel labels based on protocol
        self._update_channel_labels()

        # Re-decode if we have capture data
        if self.capture and self.capture.samples:
            self._decode_protocol()
            self._update_display()

    def _update_channel_labels(self) -> None:
        """Update channel labels based on protocol mapping"""
        # Reset all labels
        for i, cfg in enumerate(self.channel_configs):
            cfg.protocol_role = ""
            cfg.name = f"CH{i}"

        # Set protocol-specific labels
        if self._protocol == ProtocolType.SPI:
            labels = {'clk': 'CLK', 'mosi': 'MOSI', 'miso': 'MISO', 'cs': 'CS'}
        elif self._protocol == ProtocolType.I2C:
            labels = {'scl': 'SCL', 'sda': 'SDA'}
        elif self._protocol == ProtocolType.UART:
            labels = {'rx': 'RX', 'tx': 'TX'}
        else:
            return

        for signal, label in labels.items():
            ch = self._channel_map.get(signal, -1)
            if 0 <= ch < len(self.channel_configs):
                self.channel_configs[ch].protocol_role = label
                self.channel_configs[ch].name = f"{label}"

    def _decode_protocol(self) -> None:
        """Decode the captured data using the current protocol"""
        if not self.capture or not self.capture.samples:
            return

        self.capture.decoded = decode_protocol(
            samples=self.capture.samples,
            sample_rate=self.capture.sample_rate,
            protocol=self._protocol,
            channel_map=self._channel_map,
            **self._protocol_options
        )

    def get_decoded_summary(self) -> str:
        """Get a summary of decoded data"""
        if not self.capture or not self.capture.decoded:
            return "No decoded data"

        decoded = self.capture.decoded

        if decoded.protocol == ProtocolType.SPI:
            tx_count = len(decoded.spi_transactions)
            byte_count = sum(len(tx.mosi_bytes) for tx in decoded.spi_transactions)
            return f"SPI: {tx_count} transaction(s), {byte_count} byte(s)"

        elif decoded.protocol == ProtocolType.I2C:
            tx_count = len(decoded.i2c_transactions)
            if tx_count > 0:
                addrs = set(tx.address for tx in decoded.i2c_transactions)
                return f"I2C: {tx_count} transaction(s), addresses: {', '.join(f'0x{a:02X}' for a in addrs)}"
            return f"I2C: {tx_count} transaction(s)"

        elif decoded.protocol == ProtocolType.UART:
            frame_count = len(decoded.uart_frames)
            if frame_count > 0:
                chars = ''.join(
                    chr(f.byte.value) if f.byte and 32 <= f.byte.value < 127 else '.'
                    for f in decoded.uart_frames[:20]
                )
                if len(decoded.uart_frames) > 20:
                    chars += "..."
                return f"UART: {frame_count} byte(s): {chars}"
            return f"UART: {frame_count} byte(s)"

        return "Unknown protocol"

    def _update_display(self) -> None:
        """Update the waveform display"""
        if not self.capture or not self.capture.samples:
            return

        # Update scale
        try:
            scale_widget = self.query_one("#logic-scale", Static)
            scale_widget.update(self._build_scale_line())
        except Exception:
            pass

        # Update each channel
        for ch in range(min(self.num_channels, len(self.capture.samples))):
            if not self.channel_configs[ch].enabled:
                continue

            try:
                channel_widget = self.query_one(f"#logic-ch{ch}", Static)
                waveform = self._render_channel(ch)
                channel_widget.update(waveform)
            except Exception:
                pass

        # Update protocol annotations
        try:
            annotations_widget = self.query_one("#logic-annotations", Static)
            annotations = self._render_annotations()
            annotations_widget.update(annotations)
        except Exception:
            pass

    def _render_annotations(self) -> str:
        """Render protocol annotations for the visible window"""
        if not self.capture or not self.capture.decoded:
            return ""

        decoded = self.capture.decoded
        start = self.waveform_offset
        end = start + self.visible_samples

        # Build annotation line with decoded data at positions
        annotation_chars = [" "] * self.visible_samples
        label_pad = "     "  # Match channel label width

        if decoded.protocol == ProtocolType.SPI:
            for tx in decoded.spi_transactions:
                # Show MOSI bytes at their sample positions
                for byte_info in tx.mosi_bytes:
                    pos = byte_info.sample_start - start
                    if 0 <= pos < self.visible_samples - 2:
                        hex_str = f"{byte_info.value:02X}"
                        for i, c in enumerate(hex_str):
                            if pos + i < self.visible_samples:
                                annotation_chars[pos + i] = c

        elif decoded.protocol == ProtocolType.I2C:
            for tx in decoded.i2c_transactions:
                # Show address at start position
                pos = tx.start_sample - start
                if 0 <= pos < self.visible_samples - 4:
                    addr_str = f"{tx.address:02X}{'R' if tx.is_read else 'W'}"
                    for i, c in enumerate(addr_str):
                        if pos + i < self.visible_samples:
                            annotation_chars[pos + i] = c
                # Show data bytes
                for byte_info in tx.data_bytes:
                    pos = byte_info.sample_start - start
                    if 0 <= pos < self.visible_samples - 2:
                        hex_str = f"{byte_info.value:02X}"
                        for i, c in enumerate(hex_str):
                            if pos + i < self.visible_samples:
                                annotation_chars[pos + i] = c

        elif decoded.protocol == ProtocolType.UART:
            for frame in decoded.uart_frames:
                if frame.byte:
                    pos = frame.byte.sample_start - start
                    if 0 <= pos < self.visible_samples - 2:
                        # Show printable chars directly, others as hex
                        if 32 <= frame.byte.value < 127:
                            annotation_chars[pos] = chr(frame.byte.value)
                        else:
                            hex_str = f"{frame.byte.value:02X}"
                            for i, c in enumerate(hex_str):
                                if pos + i < self.visible_samples:
                                    annotation_chars[pos + i] = c

        return label_pad + "".join(annotation_chars)

    def _render_channel(self, channel: int) -> str:
        """Render a single channel's waveform"""
        if not self.capture or channel >= len(self.capture.samples):
            return self._build_empty_channel(channel)

        samples = self.capture.samples[channel]
        label = f"CH{channel} "

        # Get visible window
        start = self.waveform_offset
        end = min(start + self.visible_samples, len(samples))

        if start >= len(samples):
            return f"{label}{self.LOW * self.visible_samples}"

        # Build waveform
        waveform = ""
        prev_value = samples[start] if start < len(samples) else 0

        for i in range(start, end):
            if i >= len(samples):
                waveform += self.LOW
                continue

            value = samples[i]

            # Detect transitions
            if value != prev_value:
                if value > prev_value:
                    waveform += self.RISING
                else:
                    waveform += self.FALLING
            else:
                waveform += self.HIGH if value else self.LOW

            prev_value = value

        # Pad to visible width
        waveform = waveform.ljust(self.visible_samples, self.LOW)

        return f"{label}{waveform}"

    def scroll_left(self, amount: int = 10) -> None:
        """Scroll left (earlier in time)"""
        self.waveform_offset = max(0, self.waveform_offset - amount)
        self._update_display()

    def scroll_right(self, amount: int = 10) -> None:
        """Scroll right (later in time)"""
        if self.capture:
            max_offset = max(0, len(self.capture.samples[0]) - self.visible_samples)
            self.waveform_offset = min(max_offset, self.waveform_offset + amount)
        self._update_display()

    def scroll_to_trigger(self) -> None:
        """Scroll to trigger position"""
        if self.capture:
            self.waveform_offset = max(0, self.capture.trigger_position - 10)
            self._update_display()

    def enable_channel(self, channel: int, enabled: bool = True) -> None:
        """Enable or disable a channel"""
        if 0 <= channel < self.num_channels:
            self.channel_configs[channel].enabled = enabled
            self._update_display()

    def set_channel_name(self, channel: int, name: str) -> None:
        """Set custom name for a channel"""
        if 0 <= channel < self.num_channels:
            self.channel_configs[channel].name = name
            self._update_display()

    def load_demo_data(self) -> None:
        """Load demo capture data for testing"""
        import random

        # Generate some demo waveforms
        samples = []
        for ch in range(self.num_channels):
            channel_samples = []
            state = random.randint(0, 1)
            for i in range(1000):
                if random.random() < 0.05:  # 5% chance of transition
                    state = 1 - state
                channel_samples.append(state)
            samples.append(channel_samples)

        capture = LogicCapture(
            channels=self.num_channels,
            sample_rate=1000000,
            samples=samples,
            trigger_position=100
        )

        self.set_capture(capture)

    @staticmethod
    def decode_spi(
        clk_samples: List[int],
        mosi_samples: List[int],
        miso_samples: List[int],
        cs_samples: Optional[List[int]] = None,
        cpol: int = 0,
        cpha: int = 0
    ) -> Tuple[List[int], List[int]]:
        """
        Decode SPI protocol from captured samples.

        Returns tuple of (mosi_bytes, miso_bytes)
        """
        mosi_bytes = []
        miso_bytes = []

        # Find clock edges
        # This is a simplified decoder - real implementation would be more robust

        return mosi_bytes, miso_bytes

    @staticmethod
    def decode_i2c(
        scl_samples: List[int],
        sda_samples: List[int]
    ) -> List[dict]:
        """
        Decode I2C protocol from captured samples.

        Returns list of transactions with address, r/w, data, ack
        """
        transactions = []

        # Find start conditions (SDA falling while SCL high)
        # This is a simplified decoder

        return transactions

    @staticmethod
    def decode_uart(
        rx_samples: List[int],
        sample_rate: int,
        baud_rate: int = 115200,
        data_bits: int = 8,
        parity: str = "N",
        stop_bits: int = 1
    ) -> bytes:
        """
        Decode UART protocol from captured samples.

        Returns decoded bytes
        """
        decoded = bytearray()

        # Calculate samples per bit
        samples_per_bit = sample_rate // baud_rate

        # This is a simplified decoder
        # Real implementation would find start bits and sample at correct times

        return bytes(decoded)


class LogicAnalyzerPanel(Container):
    """
    Full logic analyzer panel with controls.

    Includes:
    - LogicAnalyzerWidget for display
    - Capture controls
    - Trigger configuration
    - Protocol decoders
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.widget = LogicAnalyzerWidget()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield self.widget

            # Controls
            with Horizontal(classes="logic-controls"):
                yield Static("Rate:")
                from textual.widgets import Select
                yield Select(
                    [("1MHz", "1000000"), ("10MHz", "10000000"), ("62.5MHz", "62500000")],
                    value="1000000",
                    id="logic-rate"
                )
                yield Static("Samples:")
                yield Select(
                    [("1K", "1024"), ("8K", "8192"), ("32K", "32768")],
                    value="8192",
                    id="logic-samples"
                )

            with Horizontal(classes="logic-buttons"):
                from textual.widgets import Button
                yield Button("Capture", id="btn-capture")
                yield Button("Stop", id="btn-stop")
                yield Button("<<", id="btn-scroll-left")
                yield Button(">>", id="btn-scroll-right")
                yield Button("Trigger", id="btn-goto-trigger")

    def load_demo_data(self) -> None:
        """Load demo capture data for testing"""
        import random

        # Generate some demo waveforms
        samples = []
        for ch in range(8):
            channel_samples = []
            state = random.randint(0, 1)
            for i in range(1000):
                if random.random() < 0.05:  # 5% chance of transition
                    state = 1 - state
                channel_samples.append(state)
            samples.append(channel_samples)

        capture = LogicCapture(
            channels=8,
            sample_rate=1000000,
            samples=samples,
            trigger_position=100
        )

        self.widget.set_capture(capture)
