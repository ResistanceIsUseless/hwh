"""
Protocol Replay and MITM

Capture, modify, and replay SPI/I2C/UART traffic for:
- Bootloader signature check testing
- Authentication bypass attempts
- Protocol fuzzing
"""

import asyncio
import time
from typing import Optional, List, Dict, Callable, Any
from dataclasses import dataclass, field
from enum import Enum


class Protocol(Enum):
    """Supported protocols for replay."""
    SPI = "spi"
    I2C = "i2c"
    UART = "uart"


@dataclass
class Transaction:
    """A captured or crafted protocol transaction."""
    protocol: Protocol
    timestamp: float
    write_data: bytes
    read_data: bytes = b""
    address: int = 0          # I2C address or SPI CS
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self):
        if self.protocol == Protocol.I2C:
            return f"I2C[0x{self.address:02X}] W:{self.write_data.hex()} R:{self.read_data.hex()}"
        elif self.protocol == Protocol.SPI:
            return f"SPI W:{self.write_data.hex()} R:{self.read_data.hex()}"
        else:
            return f"UART TX:{self.write_data.hex()}"


@dataclass
class CaptureSession:
    """A capture session with multiple transactions."""
    protocol: Protocol
    start_time: float
    transactions: List[Transaction] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add(self, tx: Transaction):
        self.transactions.append(tx)

    def duration(self) -> float:
        if not self.transactions:
            return 0.0
        return self.transactions[-1].timestamp - self.start_time

    def save(self, path: str):
        """Save session to JSON file."""
        import json
        data = {
            'protocol': self.protocol.value,
            'start_time': self.start_time,
            'metadata': self.metadata,
            'transactions': [
                {
                    'timestamp': tx.timestamp,
                    'write_data': tx.write_data.hex(),
                    'read_data': tx.read_data.hex(),
                    'address': tx.address,
                    'metadata': tx.metadata,
                }
                for tx in self.transactions
            ]
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: str) -> "CaptureSession":
        """Load session from JSON file."""
        import json
        with open(path, 'r') as f:
            data = json.load(f)

        session = cls(
            protocol=Protocol(data['protocol']),
            start_time=data['start_time'],
            metadata=data.get('metadata', {})
        )

        for tx_data in data['transactions']:
            tx = Transaction(
                protocol=session.protocol,
                timestamp=tx_data['timestamp'],
                write_data=bytes.fromhex(tx_data['write_data']),
                read_data=bytes.fromhex(tx_data.get('read_data', '')),
                address=tx_data.get('address', 0),
                metadata=tx_data.get('metadata', {})
            )
            session.add(tx)

        return session


class ProtocolCapture:
    """
    Capture protocol traffic for later replay or analysis.

    Example:
        >>> capture = ProtocolCapture(backend=buspirate, protocol=Protocol.SPI)
        >>> session = await capture.start(duration=5.0)
        >>> print(f"Captured {len(session.transactions)} transactions")
        >>> session.save("boot_sequence.json")
    """

    def __init__(
        self,
        backend,
        protocol: Protocol,
        log_callback: Optional[Callable[[str], None]] = None
    ):
        self.backend = backend
        self.protocol = protocol
        self.log = log_callback or print
        self._capturing = False

    async def start(
        self,
        duration: float = 5.0,
        max_transactions: int = 1000
    ) -> CaptureSession:
        """
        Capture protocol traffic.

        Note: This requires the backend to support passive monitoring.
        For SPI/I2C, we'd typically use the logic analyzer to decode.

        Args:
            duration: Capture duration in seconds
            max_transactions: Maximum transactions to capture

        Returns:
            CaptureSession with captured traffic
        """
        session = CaptureSession(
            protocol=self.protocol,
            start_time=time.time()
        )

        self._capturing = True
        self.log(f"[Capture] Starting {self.protocol.value} capture for {duration}s...")

        start = time.time()
        while self._capturing and (time.time() - start) < duration:
            if len(session.transactions) >= max_transactions:
                break

            # Read any available data
            try:
                if self.protocol == Protocol.UART:
                    data = self.backend.uart_read(256, timeout_ms=100)
                    if data:
                        tx = Transaction(
                            protocol=Protocol.UART,
                            timestamp=time.time(),
                            write_data=data
                        )
                        session.add(tx)

                # For SPI/I2C passive capture, we'd use LA decoder
                await asyncio.sleep(0.01)

            except Exception as e:
                self.log(f"[Capture] Error: {e}")

        self._capturing = False
        self.log(f"[Capture] Captured {len(session.transactions)} transactions")
        return session

    def stop(self):
        """Stop capture."""
        self._capturing = False


class ProtocolReplay:
    """
    Replay captured protocol traffic.

    Supports:
    - Exact replay with original timing
    - Modified replay (change data, skip transactions)
    - Fuzzing mode (random modifications)

    Example:
        >>> session = CaptureSession.load("boot_sequence.json")
        >>> replay = ProtocolReplay(backend=buspirate)
        >>> # Modify signature bytes before replay
        >>> session.transactions[5].write_data = b'\\x00' * 256
        >>> await replay.play(session)
    """

    def __init__(
        self,
        backend,
        log_callback: Optional[Callable[[str], None]] = None
    ):
        self.backend = backend
        self.log = log_callback or print

    async def play(
        self,
        session: CaptureSession,
        preserve_timing: bool = True,
        speed_factor: float = 1.0,
        callback: Optional[Callable[[Transaction, bytes], None]] = None
    ) -> List[bytes]:
        """
        Replay a capture session.

        Args:
            session: Captured session to replay
            preserve_timing: Maintain original timing between transactions
            speed_factor: Speed multiplier (2.0 = 2x speed)
            callback: Called after each transaction (tx, response)

        Returns:
            List of responses from target
        """
        responses = []
        prev_time = session.start_time

        self.log(f"[Replay] Playing {len(session.transactions)} {session.protocol.value} transactions...")

        for tx in session.transactions:
            # Wait to preserve timing
            if preserve_timing and len(responses) > 0:
                delay = (tx.timestamp - prev_time) / speed_factor
                if delay > 0:
                    await asyncio.sleep(delay)
            prev_time = tx.timestamp

            # Execute transaction
            try:
                response = await self._execute_transaction(tx)
                responses.append(response)

                if callback:
                    callback(tx, response)

            except Exception as e:
                self.log(f"[Replay] Error: {e}")
                responses.append(b"")

        self.log(f"[Replay] Complete: {len(responses)} transactions replayed")
        return responses

    async def _execute_transaction(self, tx: Transaction) -> bytes:
        """Execute a single transaction."""
        if tx.protocol == Protocol.SPI:
            return self.backend.spi_transfer(tx.write_data, len(tx.read_data))

        elif tx.protocol == Protocol.I2C:
            if tx.read_data:
                return self.backend.i2c_write_read(tx.address, tx.write_data, len(tx.read_data))
            else:
                self.backend.i2c_write(tx.address, tx.write_data)
                return b""

        elif tx.protocol == Protocol.UART:
            self.backend.uart_write(tx.write_data)
            await asyncio.sleep(0.1)
            return self.backend.uart_read(256, timeout_ms=100) or b""

        return b""


class ProtocolFuzzer:
    """
    Fuzz protocol transactions to find vulnerabilities.

    Strategies:
    - Bit flip: Flip random bits in data
    - Byte mutation: Replace random bytes
    - Length variation: Truncate or extend data
    - Boundary testing: Use boundary values (0x00, 0xFF, etc.)

    Example:
        >>> fuzzer = ProtocolFuzzer(backend=buspirate)
        >>> fuzzer.add_baseline(original_session)
        >>> # Fuzz the signature verification transaction
        >>> results = await fuzzer.fuzz_transaction(
        ...     transaction_index=5,
        ...     iterations=100,
        ...     strategy="bit_flip"
        ... )
    """

    def __init__(
        self,
        backend,
        log_callback: Optional[Callable[[str], None]] = None
    ):
        self.backend = backend
        self.log = log_callback or print
        self.baseline: Optional[CaptureSession] = None
        self.results: List[Dict] = []

    def add_baseline(self, session: CaptureSession):
        """Set baseline session for fuzzing."""
        self.baseline = session

    async def fuzz_transaction(
        self,
        transaction_index: int,
        iterations: int = 100,
        strategy: str = "bit_flip",
        check_callback: Optional[Callable[[bytes], bool]] = None
    ) -> List[Dict]:
        """
        Fuzz a specific transaction.

        Args:
            transaction_index: Index of transaction to fuzz
            iterations: Number of fuzz iterations
            strategy: Fuzzing strategy
            check_callback: Called with response, return True if interesting

        Returns:
            List of interesting results
        """
        if not self.baseline:
            self.log("[Fuzzer] No baseline set!")
            return []

        if transaction_index >= len(self.baseline.transactions):
            self.log("[Fuzzer] Invalid transaction index!")
            return []

        original_tx = self.baseline.transactions[transaction_index]
        interesting = []

        self.log(f"[Fuzzer] Fuzzing transaction {transaction_index} with {strategy}...")
        self.log(f"         Original: {original_tx.write_data.hex()}")

        import random

        for i in range(iterations):
            # Create fuzzed data
            fuzzed = bytearray(original_tx.write_data)

            if strategy == "bit_flip":
                # Flip random bit
                byte_idx = random.randint(0, len(fuzzed) - 1)
                bit_idx = random.randint(0, 7)
                fuzzed[byte_idx] ^= (1 << bit_idx)

            elif strategy == "byte_replace":
                # Replace random byte
                byte_idx = random.randint(0, len(fuzzed) - 1)
                fuzzed[byte_idx] = random.randint(0, 255)

            elif strategy == "boundary":
                # Use boundary values
                byte_idx = random.randint(0, len(fuzzed) - 1)
                fuzzed[byte_idx] = random.choice([0x00, 0xFF, 0x7F, 0x80])

            elif strategy == "truncate":
                # Truncate data
                new_len = random.randint(1, len(fuzzed))
                fuzzed = fuzzed[:new_len]

            elif strategy == "extend":
                # Extend with padding
                extra = random.randint(1, 16)
                fuzzed.extend([random.randint(0, 255) for _ in range(extra)])

            # Execute fuzzed transaction
            fuzzed_tx = Transaction(
                protocol=original_tx.protocol,
                timestamp=time.time(),
                write_data=bytes(fuzzed),
                address=original_tx.address
            )

            try:
                replay = ProtocolReplay(self.backend, log_callback=lambda x: None)
                response = await replay._execute_transaction(fuzzed_tx)

                # Check if interesting
                is_interesting = False
                if check_callback:
                    is_interesting = check_callback(response)
                elif response != original_tx.read_data:
                    # Different response = potentially interesting
                    is_interesting = True

                if is_interesting:
                    result = {
                        'iteration': i,
                        'fuzzed_data': bytes(fuzzed).hex(),
                        'response': response.hex(),
                        'strategy': strategy,
                    }
                    interesting.append(result)
                    self.log(f"[Fuzzer] Interesting at iteration {i}: {bytes(fuzzed).hex()}")

            except Exception as e:
                # Errors might also be interesting
                result = {
                    'iteration': i,
                    'fuzzed_data': bytes(fuzzed).hex(),
                    'error': str(e),
                    'strategy': strategy,
                }
                interesting.append(result)
                self.log(f"[Fuzzer] Error at iteration {i}: {e}")

        self.results.extend(interesting)
        self.log(f"[Fuzzer] Found {len(interesting)} interesting results")
        return interesting
