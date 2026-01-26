"""
UART Baud Rate Scanner

Automatically detects UART baud rate by trying common rates and
analyzing received data for valid ASCII content.
"""

import asyncio
import time
from typing import Optional, List, Dict, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum

# Common baud rates to try (ordered by popularity)
COMMON_BAUD_RATES = [
    115200,  # Most common for modern devices
    9600,    # Classic default
    57600,
    38400,
    19200,
    230400,
    460800,
    921600,
    1000000,
    1500000,
    2000000,
    3000000,
    4800,
    2400,
    1200,
    300,
]

# Extended list for thorough scanning
EXTENDED_BAUD_RATES = COMMON_BAUD_RATES + [
    74880,   # ESP8266 boot loader
    76800,
    128000,
    153600,
    256000,
    500000,
    576000,
    750000,
    1152000,
]


class ScanResult(Enum):
    """Result classification for baud rate scan."""
    GOOD = "good"           # High confidence match
    POSSIBLE = "possible"   # Some valid data
    UNLIKELY = "unlikely"   # Mostly garbage
    NO_DATA = "no_data"     # No data received


@dataclass
class BaudScanResult:
    """Result from scanning a single baud rate."""
    baud_rate: int
    result: ScanResult
    score: float  # 0.0 to 1.0
    printable_ratio: float
    ascii_ratio: float
    newline_count: int
    framing_errors: int
    sample_data: bytes
    decoded_sample: str


@dataclass
class UARTScanReport:
    """Complete scan report."""
    best_baud: Optional[int] = None
    best_score: float = 0.0
    results: List[BaudScanResult] = field(default_factory=list)
    scan_duration: float = 0.0

    def get_candidates(self, min_score: float = 0.3) -> List[BaudScanResult]:
        """Get all baud rates above minimum score threshold."""
        return [r for r in self.results if r.score >= min_score]

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = ["UART Baud Rate Scan Results", "=" * 40]

        if self.best_baud:
            lines.append(f"Best match: {self.best_baud} baud (score: {self.best_score:.2f})")
        else:
            lines.append("No confident match found")

        lines.append(f"Scan duration: {self.scan_duration:.1f}s")
        lines.append("")

        candidates = self.get_candidates(0.2)
        if candidates:
            lines.append("Candidates:")
            for r in sorted(candidates, key=lambda x: x.score, reverse=True):
                lines.append(f"  {r.baud_rate:>7} baud: {r.result.value:>8} "
                           f"(score={r.score:.2f}, printable={r.printable_ratio:.0%})")
                if r.decoded_sample:
                    # Show first line of sample
                    sample = r.decoded_sample.split('\n')[0][:60]
                    if sample:
                        lines.append(f"           Sample: {repr(sample)}")

        return "\n".join(lines)


class UARTScanner:
    """
    Automatic UART baud rate detection.

    Works by trying different baud rates and analyzing the received
    data for characteristics of valid serial communication:
    - Printable ASCII characters
    - Common control characters (newlines, carriage returns)
    - Absence of framing errors (0x00, 0xFF patterns)

    Example:
        >>> scanner = UARTScanner(port="/dev/ttyUSB0")
        >>> report = await scanner.scan()
        >>> print(f"Detected baud rate: {report.best_baud}")
    """

    def __init__(
        self,
        port: str = None,
        backend = None,
        sample_time: float = 0.5,
        log_callback: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize scanner.

        Args:
            port: Serial port path (if using direct serial)
            backend: Backend with UART support (Bus Pirate, Tigard, etc.)
            sample_time: How long to sample at each baud rate (seconds)
            log_callback: Optional callback for log messages
        """
        self.port = port
        self.backend = backend
        self.sample_time = sample_time
        self.log = log_callback or print
        self._serial = None

    async def scan(
        self,
        baud_rates: List[int] = None,
        require_newlines: bool = False,
        stop_on_good: bool = True
    ) -> UARTScanReport:
        """
        Scan for valid baud rate.

        Args:
            baud_rates: List of rates to try (default: COMMON_BAUD_RATES)
            require_newlines: Only accept results with newline characters
            stop_on_good: Stop scanning when a good match is found

        Returns:
            UARTScanReport with results
        """
        if baud_rates is None:
            baud_rates = COMMON_BAUD_RATES

        report = UARTScanReport()
        start_time = time.time()

        self.log(f"[UART Scanner] Starting scan of {len(baud_rates)} baud rates...")

        for baud in baud_rates:
            result = await self._test_baud_rate(baud)
            report.results.append(result)

            self.log(f"  {baud:>7} baud: {result.result.value:>8} "
                    f"(score={result.score:.2f})")

            # Update best if this is better
            if result.score > report.best_score:
                if not require_newlines or result.newline_count > 0:
                    report.best_score = result.score
                    report.best_baud = baud

            # Stop early if we found a good match
            if stop_on_good and result.result == ScanResult.GOOD:
                self.log(f"[UART Scanner] Found good match at {baud} baud")
                break

        report.scan_duration = time.time() - start_time

        return report

    async def _test_baud_rate(self, baud: int) -> BaudScanResult:
        """Test a single baud rate and score the results."""
        data = await self._read_at_baud(baud)

        if not data:
            return BaudScanResult(
                baud_rate=baud,
                result=ScanResult.NO_DATA,
                score=0.0,
                printable_ratio=0.0,
                ascii_ratio=0.0,
                newline_count=0,
                framing_errors=0,
                sample_data=b"",
                decoded_sample=""
            )

        # Analyze the data
        score, metrics = self._analyze_data(data)

        # Classify result
        if score >= 0.7:
            result = ScanResult.GOOD
        elif score >= 0.4:
            result = ScanResult.POSSIBLE
        else:
            result = ScanResult.UNLIKELY

        # Try to decode
        try:
            decoded = data.decode('utf-8', errors='replace')
        except Exception:
            decoded = data.decode('latin-1', errors='replace')

        return BaudScanResult(
            baud_rate=baud,
            result=result,
            score=score,
            printable_ratio=metrics['printable_ratio'],
            ascii_ratio=metrics['ascii_ratio'],
            newline_count=metrics['newline_count'],
            framing_errors=metrics['framing_errors'],
            sample_data=data[:256],  # Keep first 256 bytes
            decoded_sample=decoded[:256]
        )

    async def _read_at_baud(self, baud: int) -> bytes:
        """Read data at the specified baud rate."""
        if self.backend:
            return await self._read_via_backend(baud)
        else:
            return await self._read_via_serial(baud)

    async def _read_via_backend(self, baud: int) -> bytes:
        """Read using a backend (Bus Pirate, etc.)."""
        from ..backends import UARTConfig

        try:
            # Configure UART
            config = UARTConfig(baudrate=baud)
            self.backend.configure_uart(config)

            # Wait for data
            await asyncio.sleep(self.sample_time)

            # Read available data
            data = self.backend.uart_read(4096, timeout_ms=100)
            return data or b""

        except Exception as e:
            self.log(f"    Error at {baud}: {e}")
            return b""

    async def _read_via_serial(self, baud: int) -> bytes:
        """Read using direct serial connection."""
        import serial

        try:
            # Open/reconfigure serial port
            if self._serial and self._serial.is_open:
                self._serial.close()

            self._serial = serial.Serial(
                port=self.port,
                baudrate=baud,
                timeout=0.1,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )

            # Clear any buffered data
            self._serial.reset_input_buffer()

            # Wait for new data
            await asyncio.sleep(self.sample_time)

            # Read available data
            data = b""
            while self._serial.in_waiting > 0:
                data += self._serial.read(self._serial.in_waiting)
                await asyncio.sleep(0.01)

            return data

        except Exception as e:
            self.log(f"    Error at {baud}: {e}")
            return b""

    def _analyze_data(self, data: bytes) -> Tuple[float, Dict]:
        """
        Analyze received data and calculate a confidence score.

        Returns:
            (score, metrics_dict)
        """
        if not data:
            return 0.0, {}

        total = len(data)

        # Count character types
        printable = 0
        ascii_chars = 0
        newlines = 0
        framing_errors = 0

        for byte in data:
            # Printable ASCII (space to ~)
            if 0x20 <= byte <= 0x7E:
                printable += 1
                ascii_chars += 1
            # Common control characters
            elif byte in (0x09, 0x0A, 0x0D):  # Tab, LF, CR
                ascii_chars += 1
                if byte == 0x0A:
                    newlines += 1
            # Extended ASCII (might be valid in some encodings)
            elif 0x80 <= byte <= 0xFF:
                pass  # Neutral
            # Likely framing errors
            elif byte == 0x00 or byte == 0xFF:
                framing_errors += 1

        # Calculate ratios
        printable_ratio = printable / total
        ascii_ratio = ascii_chars / total
        framing_ratio = framing_errors / total

        # Calculate score
        # High printable ratio is good
        score = printable_ratio * 0.5

        # ASCII ratio (including control chars) is good
        score += ascii_ratio * 0.3

        # Newlines suggest structured text output
        if newlines > 0:
            score += min(newlines / 10, 0.2)

        # Framing errors are bad
        score -= framing_ratio * 0.5

        # Clamp to 0-1
        score = max(0.0, min(1.0, score))

        metrics = {
            'printable_ratio': printable_ratio,
            'ascii_ratio': ascii_ratio,
            'newline_count': newlines,
            'framing_errors': framing_errors,
            'total_bytes': total,
        }

        return score, metrics

    def close(self):
        """Close any open connections."""
        if self._serial and self._serial.is_open:
            self._serial.close()
            self._serial = None


async def scan_uart_baud(
    port: str = None,
    backend = None,
    sample_time: float = 0.5,
    extended: bool = False,
    log_callback: Optional[Callable[[str], None]] = None
) -> UARTScanReport:
    """
    Convenience function to scan for UART baud rate.

    Args:
        port: Serial port path
        backend: Backend with UART support
        sample_time: Sample time per baud rate
        extended: Use extended baud rate list
        log_callback: Logging callback

    Returns:
        UARTScanReport with scan results
    """
    scanner = UARTScanner(
        port=port,
        backend=backend,
        sample_time=sample_time,
        log_callback=log_callback
    )

    baud_rates = EXTENDED_BAUD_RATES if extended else COMMON_BAUD_RATES

    try:
        return await scanner.scan(baud_rates=baud_rates)
    finally:
        scanner.close()


# UART Command Discovery
COMMON_COMMANDS = [
    "",          # Just enter
    "help",
    "?",
    "h",
    "menu",
    "debug",
    "admin",
    "shell",
    "sh",
    "bash",
    "root",
    "test",
    "diag",
    "diagnostic",
    "service",
    "engineer",
    "factory",
    "hidden",
    "secret",
    "backdoor",
    "enable",
    "config",
    "system",
    "info",
    "version",
    "status",
    "reboot",
    "reset",
    "exit",
    "quit",
    "logout",
    "login",
]


@dataclass
class CommandResult:
    """Result from testing a command."""
    command: str
    response: str
    response_length: int
    interesting: bool  # Different from default response
    notes: str = ""


class UARTCommandScanner:
    """
    Scan for hidden UART commands.

    Sends common commands and analyzes responses to find
    hidden functionality or debug interfaces.
    """

    def __init__(
        self,
        port: str = None,
        backend = None,
        baud_rate: int = 115200,
        log_callback: Optional[Callable[[str], None]] = None
    ):
        self.port = port
        self.backend = backend
        self.baud_rate = baud_rate
        self.log = log_callback or print
        self._serial = None
        self._baseline_response = None

    async def scan_commands(
        self,
        commands: List[str] = None,
        timeout: float = 1.0
    ) -> List[CommandResult]:
        """
        Try a list of commands and collect responses.

        Args:
            commands: Commands to try (default: COMMON_COMMANDS)
            timeout: Response timeout per command

        Returns:
            List of CommandResult
        """
        if commands is None:
            commands = COMMON_COMMANDS

        results = []

        # Get baseline response (empty command or garbage)
        self._baseline_response = await self._send_command("", timeout)

        self.log(f"[Command Scanner] Testing {len(commands)} commands...")

        for cmd in commands:
            response = await self._send_command(cmd, timeout)

            # Check if response is different from baseline
            interesting = self._is_interesting(response)

            result = CommandResult(
                command=cmd,
                response=response,
                response_length=len(response),
                interesting=interesting
            )

            if interesting:
                self.log(f"  [!] {cmd!r}: Interesting response ({len(response)} bytes)")
                result.notes = "Different from baseline"

            results.append(result)

        return results

    async def _send_command(self, cmd: str, timeout: float) -> str:
        """Send command and read response."""
        if self.backend:
            return await self._send_via_backend(cmd, timeout)
        else:
            return await self._send_via_serial(cmd, timeout)

    async def _send_via_backend(self, cmd: str, timeout: float) -> str:
        """Send via backend."""
        try:
            # Send command with newline
            self.backend.uart_write((cmd + "\r\n").encode())

            # Wait for response
            await asyncio.sleep(timeout)

            # Read response
            data = self.backend.uart_read(4096, timeout_ms=100)
            return data.decode('utf-8', errors='replace') if data else ""

        except Exception as e:
            return f"[Error: {e}]"

    async def _send_via_serial(self, cmd: str, timeout: float) -> str:
        """Send via direct serial."""
        import serial

        try:
            if not self._serial or not self._serial.is_open:
                self._serial = serial.Serial(
                    port=self.port,
                    baudrate=self.baud_rate,
                    timeout=0.1
                )

            # Clear buffer
            self._serial.reset_input_buffer()

            # Send command
            self._serial.write((cmd + "\r\n").encode())

            # Wait for response
            await asyncio.sleep(timeout)

            # Read response
            data = b""
            while self._serial.in_waiting > 0:
                data += self._serial.read(self._serial.in_waiting)
                await asyncio.sleep(0.01)

            return data.decode('utf-8', errors='replace')

        except Exception as e:
            return f"[Error: {e}]"

    def _is_interesting(self, response: str) -> bool:
        """Check if response is interesting (different from baseline)."""
        if not self._baseline_response:
            return len(response) > 0

        # Check for significant difference
        if abs(len(response) - len(self._baseline_response)) > 10:
            return True

        # Check for different content
        if response != self._baseline_response:
            # Ignore minor differences (timestamps, etc.)
            baseline_words = set(self._baseline_response.lower().split())
            response_words = set(response.lower().split())

            new_words = response_words - baseline_words
            if len(new_words) > 3:
                return True

        return False

    def close(self):
        """Close connections."""
        if self._serial and self._serial.is_open:
            self._serial.close()
