"""
Protocol Decoders for Logic Analyzer

Decodes captured digital signals into protocol-specific data:
- SPI: MOSI/MISO bytes with chip select framing
- I2C: Address, R/W, data bytes with ACK/NACK
- UART: Decoded bytes with framing errors
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum


class ProtocolType(Enum):
    """Supported protocol types"""
    NONE = "none"
    SPI = "spi"
    I2C = "i2c"
    UART = "uart"


@dataclass
class DecodedByte:
    """A decoded byte with position information"""
    value: int
    start_sample: int
    end_sample: int
    error: bool = False
    error_msg: str = ""


@dataclass
class SPITransaction:
    """Decoded SPI transaction"""
    mosi_bytes: List[DecodedByte] = field(default_factory=list)
    miso_bytes: List[DecodedByte] = field(default_factory=list)
    start_sample: int = 0
    end_sample: int = 0


@dataclass
class I2CTransaction:
    """Decoded I2C transaction"""
    address: int = 0
    is_read: bool = False
    data_bytes: List[DecodedByte] = field(default_factory=list)
    acks: List[bool] = field(default_factory=list)  # True = ACK, False = NACK
    start_sample: int = 0
    end_sample: int = 0


@dataclass
class UARTFrame:
    """Decoded UART frame"""
    byte: DecodedByte = None
    parity_ok: bool = True
    framing_ok: bool = True


@dataclass
class DecodedCapture:
    """Container for all decoded protocol data"""
    protocol: ProtocolType = ProtocolType.NONE
    spi_transactions: List[SPITransaction] = field(default_factory=list)
    i2c_transactions: List[I2CTransaction] = field(default_factory=list)
    uart_frames: List[UARTFrame] = field(default_factory=list)
    annotations: List[Tuple[int, int, str]] = field(default_factory=list)  # (start, end, text)


class SPIDecoder:
    """
    SPI Protocol Decoder

    Decodes SPI signals from captured samples.
    Supports Mode 0-3 (CPOL/CPHA combinations).
    """

    def __init__(
        self,
        cpol: int = 0,
        cpha: int = 0,
        bit_order_msb: bool = True,
        word_size: int = 8
    ):
        self.cpol = cpol  # Clock polarity (idle state)
        self.cpha = cpha  # Clock phase (sample edge)
        self.bit_order_msb = bit_order_msb
        self.word_size = word_size

    def decode(
        self,
        clk_samples: List[int],
        mosi_samples: List[int],
        miso_samples: Optional[List[int]] = None,
        cs_samples: Optional[List[int]] = None
    ) -> List[SPITransaction]:
        """
        Decode SPI data from captured samples.

        Args:
            clk_samples: Clock signal samples
            mosi_samples: Master Out Slave In samples
            miso_samples: Master In Slave Out samples (optional)
            cs_samples: Chip Select samples (optional, active low)

        Returns:
            List of SPITransaction objects
        """
        if not clk_samples or not mosi_samples:
            return []

        transactions = []
        current_tx = None

        # Determine sample edge based on mode
        # CPHA=0: Sample on first edge (rising for CPOL=0, falling for CPOL=1)
        # CPHA=1: Sample on second edge (falling for CPOL=0, rising for CPOL=1)
        sample_on_rising = (self.cpol == 0) != (self.cpha == 1)

        mosi_bits = []
        miso_bits = []
        bit_starts = []

        prev_clk = clk_samples[0]
        prev_cs = cs_samples[0] if cs_samples else 0

        for i in range(1, len(clk_samples)):
            clk = clk_samples[i]
            cs = cs_samples[i] if cs_samples else 0

            # Check for CS transitions
            if cs_samples:
                if prev_cs == 1 and cs == 0:  # CS falling - start transaction
                    if current_tx is not None:
                        transactions.append(current_tx)
                    current_tx = SPITransaction(start_sample=i)
                    mosi_bits = []
                    miso_bits = []
                    bit_starts = []
                elif prev_cs == 0 and cs == 1:  # CS rising - end transaction
                    if current_tx is not None:
                        # Flush remaining bits
                        self._flush_bits(current_tx, mosi_bits, miso_bits, bit_starts)
                        current_tx.end_sample = i
                        transactions.append(current_tx)
                        current_tx = None
                        mosi_bits = []
                        miso_bits = []
                        bit_starts = []

            # Only process if CS is active (low) or no CS provided
            cs_active = cs_samples is None or cs == 0

            if cs_active:
                if current_tx is None:
                    current_tx = SPITransaction(start_sample=i)

                # Detect clock edge
                rising_edge = prev_clk == 0 and clk == 1
                falling_edge = prev_clk == 1 and clk == 0

                # Sample on appropriate edge
                sample_edge = rising_edge if sample_on_rising else falling_edge

                if sample_edge:
                    mosi_bits.append(mosi_samples[i])
                    if miso_samples:
                        miso_bits.append(miso_samples[i])
                    bit_starts.append(i)

                    # Complete byte
                    if len(mosi_bits) == self.word_size:
                        self._flush_bits(current_tx, mosi_bits, miso_bits, bit_starts)
                        mosi_bits = []
                        miso_bits = []
                        bit_starts = []

            prev_clk = clk
            prev_cs = cs

        # Handle any remaining transaction
        if current_tx is not None:
            if mosi_bits:
                self._flush_bits(current_tx, mosi_bits, miso_bits, bit_starts)
            current_tx.end_sample = len(clk_samples) - 1
            transactions.append(current_tx)

        return transactions

    def _flush_bits(
        self,
        tx: SPITransaction,
        mosi_bits: List[int],
        miso_bits: List[int],
        bit_starts: List[int]
    ):
        """Convert accumulated bits to bytes"""
        if not mosi_bits:
            return

        # Convert bits to byte
        mosi_byte = 0
        for i, bit in enumerate(mosi_bits):
            if self.bit_order_msb:
                mosi_byte = (mosi_byte << 1) | bit
            else:
                mosi_byte |= bit << i

        start = bit_starts[0] if bit_starts else 0
        end = bit_starts[-1] if bit_starts else 0

        tx.mosi_bytes.append(DecodedByte(
            value=mosi_byte,
            start_sample=start,
            end_sample=end
        ))

        if miso_bits:
            miso_byte = 0
            for i, bit in enumerate(miso_bits):
                if self.bit_order_msb:
                    miso_byte = (miso_byte << 1) | bit
                else:
                    miso_byte |= bit << i

            tx.miso_bytes.append(DecodedByte(
                value=miso_byte,
                start_sample=start,
                end_sample=end
            ))


class I2CDecoder:
    """
    I2C Protocol Decoder

    Decodes I2C signals from captured samples.
    Detects start/stop conditions, address, R/W, data, and ACK/NACK.
    """

    def decode(
        self,
        scl_samples: List[int],
        sda_samples: List[int]
    ) -> List[I2CTransaction]:
        """
        Decode I2C data from captured samples.

        Args:
            scl_samples: Clock signal samples
            sda_samples: Data signal samples

        Returns:
            List of I2CTransaction objects
        """
        if not scl_samples or not sda_samples:
            return []

        transactions = []
        current_tx = None
        bits = []
        bit_starts = []
        byte_count = 0

        prev_scl = scl_samples[0]
        prev_sda = sda_samples[0]

        for i in range(1, len(scl_samples)):
            scl = scl_samples[i]
            sda = sda_samples[i]

            # START condition: SDA falling while SCL high
            if prev_scl == 1 and scl == 1 and prev_sda == 1 and sda == 0:
                if current_tx is not None:
                    transactions.append(current_tx)
                current_tx = I2CTransaction(start_sample=i)
                bits = []
                bit_starts = []
                byte_count = 0

            # STOP condition: SDA rising while SCL high
            elif prev_scl == 1 and scl == 1 and prev_sda == 0 and sda == 1:
                if current_tx is not None:
                    current_tx.end_sample = i
                    transactions.append(current_tx)
                    current_tx = None
                    bits = []
                    bit_starts = []

            # Sample data on SCL rising edge
            elif prev_scl == 0 and scl == 1 and current_tx is not None:
                bits.append(sda)
                bit_starts.append(i)

                # After 8 bits, next bit is ACK/NACK
                if len(bits) == 9:
                    # First 8 bits are data, 9th is ACK
                    data_bits = bits[:8]
                    ack = bits[8] == 0  # ACK = SDA low

                    # Convert bits to byte
                    byte_val = 0
                    for bit in data_bits:
                        byte_val = (byte_val << 1) | bit

                    start = bit_starts[0]
                    end = bit_starts[7]

                    if byte_count == 0:
                        # First byte is address + R/W
                        current_tx.address = byte_val >> 1
                        current_tx.is_read = bool(byte_val & 1)
                    else:
                        current_tx.data_bytes.append(DecodedByte(
                            value=byte_val,
                            start_sample=start,
                            end_sample=end
                        ))

                    current_tx.acks.append(ack)
                    byte_count += 1
                    bits = []
                    bit_starts = []

            prev_scl = scl
            prev_sda = sda

        # Handle incomplete transaction
        if current_tx is not None:
            current_tx.end_sample = len(scl_samples) - 1
            transactions.append(current_tx)

        return transactions


class UARTDecoder:
    """
    UART Protocol Decoder

    Decodes asynchronous serial data from captured samples.
    """

    def __init__(
        self,
        baud_rate: int = 115200,
        sample_rate: int = 1000000,
        data_bits: int = 8,
        parity: str = "N",  # N, E, O
        stop_bits: int = 1,
        idle_high: bool = True
    ):
        self.baud_rate = baud_rate
        self.sample_rate = sample_rate
        self.data_bits = data_bits
        self.parity = parity
        self.stop_bits = stop_bits
        self.idle_high = idle_high
        self.samples_per_bit = sample_rate / baud_rate

    def decode(self, rx_samples: List[int]) -> List[UARTFrame]:
        """
        Decode UART data from captured samples.

        Args:
            rx_samples: Received data signal samples

        Returns:
            List of UARTFrame objects
        """
        if not rx_samples:
            return []

        frames = []
        i = 0
        idle_level = 1 if self.idle_high else 0
        start_level = 0 if self.idle_high else 1

        while i < len(rx_samples) - int(self.samples_per_bit * (self.data_bits + 2)):
            # Look for start bit (transition from idle to start level)
            if rx_samples[i] == idle_level:
                i += 1
                continue

            if rx_samples[i] == start_level:
                # Found potential start bit
                start_sample = i

                # Sample in middle of each bit
                bit_offset = self.samples_per_bit / 2

                # Verify start bit
                sample_pos = int(i + bit_offset)
                if sample_pos >= len(rx_samples) or rx_samples[sample_pos] != start_level:
                    i += 1
                    continue

                # Read data bits
                bits = []
                for b in range(self.data_bits):
                    sample_pos = int(i + bit_offset + self.samples_per_bit * (b + 1))
                    if sample_pos >= len(rx_samples):
                        break
                    bits.append(rx_samples[sample_pos])

                if len(bits) != self.data_bits:
                    i += 1
                    continue

                # Convert bits to byte (LSB first for UART)
                byte_val = 0
                for b, bit in enumerate(bits):
                    byte_val |= bit << b

                # Check parity if enabled
                parity_ok = True
                if self.parity != "N":
                    parity_pos = int(i + bit_offset + self.samples_per_bit * (self.data_bits + 1))
                    if parity_pos < len(rx_samples):
                        parity_bit = rx_samples[parity_pos]
                        ones = sum(bits)
                        if self.parity == "E":
                            expected = ones % 2
                        else:  # O
                            expected = (ones + 1) % 2
                        parity_ok = parity_bit == expected

                # Check stop bit
                stop_offset = self.data_bits + 1
                if self.parity != "N":
                    stop_offset += 1

                stop_pos = int(i + bit_offset + self.samples_per_bit * stop_offset)
                framing_ok = stop_pos >= len(rx_samples) or rx_samples[stop_pos] == idle_level

                end_sample = int(i + self.samples_per_bit * (stop_offset + self.stop_bits))

                frames.append(UARTFrame(
                    byte=DecodedByte(
                        value=byte_val,
                        start_sample=start_sample,
                        end_sample=end_sample,
                        error=not (parity_ok and framing_ok),
                        error_msg="" if (parity_ok and framing_ok) else
                                  ("parity" if not parity_ok else "framing")
                    ),
                    parity_ok=parity_ok,
                    framing_ok=framing_ok
                ))

                # Move past this frame
                i = end_sample
            else:
                i += 1

        return frames


def decode_protocol(
    samples: List[List[int]],
    sample_rate: int,
    protocol: ProtocolType,
    channel_map: dict = None,
    **kwargs
) -> DecodedCapture:
    """
    High-level protocol decoder.

    Args:
        samples: List of channel sample lists
        sample_rate: Sample rate in Hz
        protocol: Protocol type to decode
        channel_map: Maps channel names to sample indices
            SPI: {'clk': 0, 'mosi': 1, 'miso': 2, 'cs': 3}
            I2C: {'scl': 0, 'sda': 1}
            UART: {'rx': 0}
        **kwargs: Protocol-specific options

    Returns:
        DecodedCapture with decoded data and annotations
    """
    result = DecodedCapture(protocol=protocol)

    if protocol == ProtocolType.NONE or not samples:
        return result

    # Default channel mappings
    if channel_map is None:
        if protocol == ProtocolType.SPI:
            channel_map = {'clk': 6, 'mosi': 7, 'miso': 4, 'cs': 5}
        elif protocol == ProtocolType.I2C:
            channel_map = {'scl': 1, 'sda': 0}
        elif protocol == ProtocolType.UART:
            channel_map = {'rx': 5}

    try:
        if protocol == ProtocolType.SPI:
            decoder = SPIDecoder(
                cpol=kwargs.get('cpol', 0),
                cpha=kwargs.get('cpha', 0),
                bit_order_msb=kwargs.get('msb_first', True)
            )
            clk = samples[channel_map['clk']] if channel_map['clk'] < len(samples) else []
            mosi = samples[channel_map['mosi']] if channel_map['mosi'] < len(samples) else []
            miso = samples[channel_map.get('miso', -1)] if channel_map.get('miso', -1) < len(samples) else None
            cs = samples[channel_map.get('cs', -1)] if channel_map.get('cs', -1) < len(samples) else None

            result.spi_transactions = decoder.decode(clk, mosi, miso, cs)

            # Generate annotations
            for tx in result.spi_transactions:
                for byte in tx.mosi_bytes:
                    result.annotations.append((
                        byte.start_sample,
                        byte.end_sample,
                        f"MOSI: 0x{byte.value:02X}"
                    ))
                for byte in tx.miso_bytes:
                    result.annotations.append((
                        byte.start_sample,
                        byte.end_sample,
                        f"MISO: 0x{byte.value:02X}"
                    ))

        elif protocol == ProtocolType.I2C:
            decoder = I2CDecoder()
            scl = samples[channel_map['scl']] if channel_map['scl'] < len(samples) else []
            sda = samples[channel_map['sda']] if channel_map['sda'] < len(samples) else []

            result.i2c_transactions = decoder.decode(scl, sda)

            # Generate annotations
            for tx in result.i2c_transactions:
                rw = "R" if tx.is_read else "W"
                result.annotations.append((
                    tx.start_sample,
                    tx.start_sample + 50,
                    f"Addr: 0x{tx.address:02X} {rw}"
                ))
                for i, byte in enumerate(tx.data_bytes):
                    ack = "ACK" if tx.acks[i + 1] else "NAK"
                    result.annotations.append((
                        byte.start_sample,
                        byte.end_sample,
                        f"0x{byte.value:02X} {ack}"
                    ))

        elif protocol == ProtocolType.UART:
            decoder = UARTDecoder(
                baud_rate=kwargs.get('baud_rate', 115200),
                sample_rate=sample_rate,
                data_bits=kwargs.get('data_bits', 8),
                parity=kwargs.get('parity', 'N'),
                stop_bits=kwargs.get('stop_bits', 1)
            )
            rx = samples[channel_map['rx']] if channel_map['rx'] < len(samples) else []

            result.uart_frames = decoder.decode(rx)

            # Generate annotations
            for frame in result.uart_frames:
                if frame.byte:
                    char = chr(frame.byte.value) if 32 <= frame.byte.value < 127 else '.'
                    err = " ERR" if frame.byte.error else ""
                    result.annotations.append((
                        frame.byte.start_sample,
                        frame.byte.end_sample,
                        f"0x{frame.byte.value:02X} '{char}'{err}"
                    ))

    except Exception as e:
        # Add error annotation
        result.annotations.append((0, 100, f"Decode error: {e}"))

    return result
