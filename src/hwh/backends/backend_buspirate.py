"""
Bus Pirate 5/6 backend using official BPIO2 FlatBuffers protocol.

This backend wraps the official pybpio library from DangerousPrototypes.

Supports: SPI, I2C, UART, 1-Wire, PSU control
Reference: https://docs.buspirate.com/docs/binmode-reference/protocol-bpio2/
"""

from typing import Any, Optional

from .base import (
    BusBackend, register_backend,
    SPIConfig, I2CConfig, UARTConfig
)
from ..detect import DeviceInfo

# Import bundled BPIO2 library
try:
    from ..pybpio import BPIOClient, BPIOSPI, BPIOI2C, BPIOUART
    BPIO_AVAILABLE = True
except ImportError as e:
    # pybpio import failed - will use serial fallback
    # This should not happen since pybpio is now bundled
    print(f"[BusPirate] Warning: Failed to import bundled pybpio: {e}")
    BPIOClient = None
    BPIOSPI = None
    BPIOI2C = None
    BPIOUART = None
    BPIO_AVAILABLE = False


class BusPirateBackend(BusBackend):
    """
    Backend for Bus Pirate 5/6 using official BPIO2 FlatBuffers interface.

    The Bus Pirate exposes two serial ports:
    - Port 0 (buspirate1): Terminal/console
    - Port 1 (buspirate3): BPIO2 binary interface

    We use the BPIO2 interface for programmatic control.
    When BPIO2 is not available, we fall back to terminal serial commands.
    """

    def __init__(self, device: DeviceInfo):
        super().__init__(device)
        self._client = None
        self._spi = None
        self._i2c = None
        self._uart = None
        self._current_mode = None
        self._serial_fallback = None  # Persistent serial connection for fallback mode
        self._psu_enabled = False
        self._psu_voltage_mv = 3300
        self._pullups_enabled = False

    def _open_serial_fallback(self) -> bool:
        """
        Open a persistent serial connection for fallback (non-BPIO) mode.

        Returns:
            True if serial connection established successfully
        """
        import serial
        import time

        if not self.device.port:
            return False

        try:
            print(f"[BusPirate] Opening serial connection: {self.device.port}")

            # Close any existing connection
            if self._serial_fallback:
                try:
                    self._serial_fallback.close()
                except Exception:
                    pass

            # Open serial port at 115200 baud (Bus Pirate default)
            self._serial_fallback = serial.Serial(
                self.device.port,
                115200,
                timeout=1,
                write_timeout=1
            )
            time.sleep(0.2)

            # Clear any pending data
            self._serial_fallback.reset_input_buffer()
            self._serial_fallback.reset_output_buffer()

            # Send a newline to get a fresh prompt
            self._serial_fallback.write(b"\r\n")
            time.sleep(0.3)

            # Read and discard any response
            if self._serial_fallback.in_waiting > 0:
                response = self._serial_fallback.read(self._serial_fallback.in_waiting)
                response_str = response.decode('utf-8', errors='ignore')
                print(f"[BusPirate] Initial response: {response_str[:100]}")

                # Check if we got a valid BP prompt
                if "HiZ>" in response_str or ">" in response_str:
                    print(f"[BusPirate] Serial fallback connected (HiZ mode)")
                    self._current_mode = "HiZ"
                elif "SPI>" in response_str:
                    print(f"[BusPirate] Serial fallback connected (SPI mode)")
                    self._current_mode = "SPI"
                elif "I2C>" in response_str:
                    print(f"[BusPirate] Serial fallback connected (I2C mode)")
                    self._current_mode = "I2C"
                elif "UART>" in response_str:
                    print(f"[BusPirate] Serial fallback connected (UART mode)")
                    self._current_mode = "UART"

            print(f"[BusPirate] Serial fallback connection established")
            return True

        except Exception as e:
            print(f"[BusPirate] Serial fallback connection failed: {e}")
            self._serial_fallback = None
            return False

    def _open_serial_fallback_to_port(self, port: str) -> bool:
        """
        Open a serial connection to a specific port for fallback mode.

        This is used when BPIO2 is connected but we need terminal access
        for features not supported in BPIO2 (like UART mode).

        Args:
            port: Serial port path (e.g., /dev/cu.usbmodem6buspirate1)

        Returns:
            True if serial connection established successfully
        """
        import serial
        import time

        if not port:
            return False

        try:
            print(f"[BusPirate] Opening serial connection to: {port}")

            # Close any existing connection
            if self._serial_fallback:
                try:
                    self._serial_fallback.close()
                except Exception:
                    pass

            # Open serial port at 115200 baud (Bus Pirate default)
            self._serial_fallback = serial.Serial(
                port,
                115200,
                timeout=1,
                write_timeout=1
            )
            time.sleep(0.2)

            # Clear any pending data
            self._serial_fallback.reset_input_buffer()
            self._serial_fallback.reset_output_buffer()

            # Send a newline to get a fresh prompt
            self._serial_fallback.write(b"\r\n")
            time.sleep(0.3)

            # Read and check response
            if self._serial_fallback.in_waiting > 0:
                response = self._serial_fallback.read(self._serial_fallback.in_waiting)
                response_str = response.decode('utf-8', errors='ignore')
                print(f"[BusPirate] Terminal response: {response_str[:100]}")

            print(f"[BusPirate] Serial fallback to {port} established")
            return True

        except Exception as e:
            print(f"[BusPirate] Serial fallback connection to {port} failed: {e}")
            self._serial_fallback = None
            return False

    def _send_serial_command(self, command: str, timeout: float = 1.0) -> tuple[bool, str]:
        """
        Send a command via the serial fallback connection and read response.

        Args:
            command: Command string to send (without newline)
            timeout: Read timeout in seconds

        Returns:
            Tuple of (success, response_string)
        """
        import time

        if not self._serial_fallback:
            return False, "No serial connection"

        try:
            # Clear input buffer
            self._serial_fallback.reset_input_buffer()

            # Send command with carriage return
            cmd_bytes = f"{command}\r\n".encode()
            print(f"[BusPirate] Sending: {command}")
            self._serial_fallback.write(cmd_bytes)

            # Wait for response
            time.sleep(0.3)

            # Read all available data
            response = b""
            end_time = time.time() + timeout
            while time.time() < end_time:
                if self._serial_fallback.in_waiting > 0:
                    response += self._serial_fallback.read(self._serial_fallback.in_waiting)
                    time.sleep(0.1)
                else:
                    if response:
                        break
                    time.sleep(0.1)

            response_str = response.decode('utf-8', errors='ignore')
            print(f"[BusPirate] Response: {response_str[:200]}")

            return True, response_str

        except Exception as e:
            print(f"[BusPirate] Serial command failed: {e}")
            return False, str(e)

    def _enter_binary_mode(self, console_port: str) -> bool:
        """
        Enter BPIO2 binary mode via the console port.

        Args:
            console_port: Path to the console port (buspirate1)

        Returns:
            True if binary mode was entered successfully
        """
        import serial
        import time

        try:
            print(f"[BusPirate] Entering binary mode via console: {console_port}")

            # Open console port at 115200 baud
            console = serial.Serial(console_port, 115200, timeout=2)
            time.sleep(0.1)

            # Clear any existing data
            console.reset_input_buffer()
            console.reset_output_buffer()

            # Send binmode command
            console.write(b'binmode\r\n')
            time.sleep(0.5)

            # Read response (should show menu)
            response = b''
            if console.in_waiting > 0:
                response = console.read(console.in_waiting)
                print(f"[BusPirate] Menu response: {response.decode('utf-8', errors='ignore')[:200]}")

            # Select BBIO2 (option 2)
            print(f"[BusPirate] Selecting BBIO2 binary mode...")
            console.write(b'2\r\n')
            time.sleep(0.5)

            # Read confirmation
            if console.in_waiting > 0:
                response = console.read(console.in_waiting)
                print(f"[BusPirate] Mode change response: {response.decode('utf-8', errors='ignore')[:200]}")

            console.close()
            print(f"[BusPirate] Binary mode command sent, waiting for mode switch...")
            time.sleep(1)  # Give it time to switch modes

            return True

        except Exception as e:
            print(f"[BusPirate] Failed to enter binary mode: {e}")
            return False

    def connect(self) -> bool:
        """Connect to Bus Pirate BPIO2 interface."""
        if not self.device.port:
            print(f"[BusPirate] No port specified for {self.device.name}")
            return False

        # Check if BPIO library is available
        if not BPIO_AVAILABLE:
            print(f"[BusPirate] BPIO library not available - using serial fallback")
            print(f"[BusPirate] Some features may be limited")
            # Establish persistent serial connection for fallback mode
            if self._open_serial_fallback():
                self._connected = True
                return True
            else:
                print(f"[BusPirate] Failed to open serial fallback connection")
                return False

        try:
            # BPIO2 runs on the second serial port (interface 3, not 1)
            # Bus Pirate exposes:
            #   - Interface 1 (/dev/*buspirate1): Console/terminal
            #   - Interface 3 (/dev/*buspirate3): BPIO2 binary mode
            console_port = self.device.port  # buspirate1
            bpio2_port = self.device.port.replace('buspirate1', 'buspirate3')

            # Also handle cu.usbmodem format on macOS
            if 'cu.usbmodem' in bpio2_port and 'buspirate1' in bpio2_port:
                bpio2_port = bpio2_port.replace('buspirate1', 'buspirate3')

            # Try 1: Attempt to connect to BPIO2 port (might already be in binary mode)
            print(f"[BusPirate] Attempting direct connection to BPIO2 port: {bpio2_port}")
            try:
                self._client = BPIOClient(
                    port=bpio2_port,
                    baudrate=3000000,
                    timeout=1,  # Short timeout for first attempt
                    debug=False
                )
                status = self._client.status_request()
                if status:
                    # Success! Already in binary mode
                    self._connected = True
                    mode = status.get('mode_current', 'unknown')
                    fw_ver = f"{status['version_firmware_major']}.{status['version_firmware_minor']}"
                    hw_ver = f"{status['version_hardware_major']} REV{status['version_hardware_minor']}"
                    print(f"[BusPirate] Connected successfully (already in binary mode)!")
                    print(f"[BusPirate] Firmware: v{fw_ver}")
                    print(f"[BusPirate] Hardware: v{hw_ver}")
                    print(f"[BusPirate] Current mode: {mode}")
                    self._current_mode = mode
                    return True
                else:
                    # No response, need to enter binary mode
                    print(f"[BusPirate] Not in binary mode, will attempt to enter it...")
                    self._client.close()
                    self._client = None
            except Exception as e:
                print(f"[BusPirate] Direct connection failed (expected): {e}")
                if self._client:
                    self._client.close()
                    self._client = None

            # Try 2: Enter binary mode via console
            if not self._enter_binary_mode(console_port):
                print(f"[BusPirate] Failed to enter binary mode")
                print(f"[BusPirate] The console port ({console_port}) may be in use by another program")
                print(f"[BusPirate] Check for: screen, minicom, or other terminal sessions")
                print(f"[BusPirate] Tip: If you have a terminal open, type 'binmode' then '2' to enable BPIO2")
                return False

            # Try 3: Connect to BPIO2 port after entering binary mode
            print(f"[BusPirate] Connecting to BPIO2 port after mode switch...")
            self._client = BPIOClient(
                port=bpio2_port,
                baudrate=3000000,
                timeout=2,
                debug=False
            )

            self._connected = True

            # Verify connection
            print(f"[BusPirate] Requesting status...")
            status = self._client.status_request()
            if status:
                mode = status.get('mode_current', 'unknown')
                fw_ver = f"{status['version_firmware_major']}.{status['version_firmware_minor']}"
                hw_ver = f"{status['version_hardware_major']} REV{status['version_hardware_minor']}"
                print(f"[BusPirate] Connected successfully!")
                print(f"[BusPirate] Firmware: v{fw_ver}")
                print(f"[BusPirate] Hardware: v{hw_ver}")
                print(f"[BusPirate] Current mode: {mode}")
                self._current_mode = mode
                return True
            else:
                print(f"[BusPirate] No response from status request after entering binary mode")
                self.disconnect()
                return False

        except Exception as e:
            print(f"[BusPirate] Connection failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def disconnect(self):
        """Disconnect from Bus Pirate."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

        if self._serial_fallback:
            try:
                self._serial_fallback.close()
            except Exception:
                pass
            self._serial_fallback = None

        self._spi = None
        self._i2c = None
        self._connected = False

    def get_info(self) -> dict[str, Any]:
        """Get Bus Pirate status information."""
        if not self._connected:
            return {"error": "Not connected"}

        # If BPIO client is available, use it
        if self._client:
            status = self._client.status_request()
            return status if status else {"error": "Status request failed"}

        # Fallback: return cached state from serial mode
        return {
            "mode": self._current_mode or "HiZ",
            "psu_enabled": self._psu_enabled,
            "psu_voltage": f"{self._psu_voltage_mv / 1000:.1f}V",
            "pullups_enabled": self._pullups_enabled,
            "serial_fallback": True
        }

    def get_status(self) -> dict[str, Any]:
        """
        Get device status for panel display.

        Returns:
            Dictionary with status information:
            - mode: Current protocol mode (HiZ, SPI, I2C, UART, etc.)
            - psu_enabled: Whether PSU is enabled
            - psu_voltage: PSU voltage string (e.g., "3.3V")
            - pullups_enabled: Whether pull-ups are enabled
            - firmware: Firmware version (if available)
            - hardware: Hardware version (if available)
        """
        if not self._connected:
            return {"error": "Not connected"}

        # If BPIO client is available, get full status
        if self._client:
            status = self._client.status_request()
            if status:
                return {
                    "mode": status.get('mode_current', 'HiZ'),
                    "psu_enabled": status.get('psu_enabled', False),
                    "psu_voltage": f"{status.get('psu_set_mv', 3300) / 1000:.1f}V",
                    "pullups_enabled": status.get('pullup_enabled', False),
                    "firmware": f"{status.get('version_firmware_major', 0)}.{status.get('version_firmware_minor', 0)}",
                    "hardware": f"{status.get('version_hardware_major', 0)} REV{status.get('version_hardware_minor', 0)}",
                }
            return {"error": "Status request failed"}

        # Fallback: return cached state from serial mode
        return {
            "mode": self._current_mode or "HiZ",
            "psu_enabled": self._psu_enabled,
            "psu_voltage": f"{self._psu_voltage_mv / 1000:.1f}V",
            "pullups_enabled": self._pullups_enabled,
            "serial_fallback": True
        }

    def get_full_status(self) -> dict[str, Any] | None:
        """
        Get full device status from BPIO2 for display in Status tab.

        Returns the raw status_request() response with all fields.
        Returns None if not connected or BPIO2 is not available.
        """
        if not self._connected:
            return None

        # Only available with BPIO2 client
        if self._client:
            return self._client.status_request()

        return None

    # --------------------------------------------------------------------------
    # SPI Interface
    # --------------------------------------------------------------------------

    def configure_spi(self, config: SPIConfig) -> bool:
        """Configure SPI interface."""
        if not self._connected:
            return False

        # If BPIO client is available, use it
        if self._client:
            # Create SPI interface if needed
            if not self._spi:
                self._spi = BPIOSPI(self._client)

            # Map config to BPIO2 parameters
            clock_polarity = bool((config.mode >> 1) & 1)  # CPOL
            clock_phase = bool(config.mode & 1)            # CPHA

            # Configure SPI mode with all parameters
            success = self._spi.configure(
                speed=config.speed_hz,
                clock_polarity=clock_polarity,
                clock_phase=clock_phase,
                chip_select_idle=config.cs_active_low,
            )

            if success:
                self._current_mode = "SPI"
                print(f"[BusPirate] SPI configured: {config.speed_hz}Hz, mode={config.mode}")

            return success

        # Fallback to serial command
        return self._send_serial_mode_command("SPI", config)

    def spi_transfer(self, write_data: bytes, read_len: int = 0) -> bytes:
        """Perform SPI transfer."""
        if not self._connected or not self._spi:
            return b''

        result = self._spi.transfer(write_data, read_bytes=read_len if read_len > 0 else None)
        return result if result else b''

    def spi_flash_read_id(self) -> bytes:
        """Read SPI flash JEDEC ID (0x9F command)."""
        if not self._connected or not self._spi:
            return b''
        return self.spi_transfer(b'\x9f', read_len=3)

    def spi_flash_read(self, address: int, length: int) -> bytes:
        """Read from SPI flash memory."""
        if not self._connected or not self._spi:
            return b''

        # Standard SPI flash read command: 0x03 + 24-bit address
        cmd = bytes([
            0x03,
            (address >> 16) & 0xFF,
            (address >> 8) & 0xFF,
            address & 0xFF
        ])
        return self.spi_transfer(cmd, read_len=length)

    # --------------------------------------------------------------------------
    # I2C Interface
    # --------------------------------------------------------------------------

    def configure_i2c(self, config: I2CConfig) -> bool:
        """Configure I2C interface."""
        if not self._connected:
            return False

        # If BPIO client is available, use it
        if self._client:
            # Create I2C interface if needed
            if not self._i2c:
                self._i2c = BPIOI2C(self._client)

            # Configure I2C mode
            success = self._i2c.configure(
                speed=config.speed_hz,
                clock_stretch=False
            )

            if success:
                self._current_mode = "I2C"
                print(f"[BusPirate] I2C configured: {config.speed_hz}Hz")

            return success

        # Fallback to serial command
        return self._send_serial_mode_command("I2C", config)

    def i2c_write(self, address: int, data: bytes) -> bool:
        """Write data to I2C device."""
        if not self._connected or not self._i2c:
            return False

        # I2C address is 7-bit, shifted left with W bit (0)
        addr_byte = (address << 1) & 0xFE

        result = self._i2c.transfer(
            write_data=bytes([addr_byte]) + data,
            read_bytes=0
        )
        return result is not False

    def i2c_read(self, address: int, length: int) -> bytes:
        """Read data from I2C device."""
        if not self._connected or not self._i2c:
            return b''

        # I2C address with R bit (1)
        addr_byte = ((address << 1) | 1) & 0xFF

        result = self._i2c.transfer(
            write_data=bytes([addr_byte]),
            read_bytes=length
        )
        return result if result else b''

    def i2c_write_read(self, address: int, write_data: bytes, read_len: int) -> bytes:
        """Write then read from I2C device (repeated start)."""
        if not self._connected or not self._i2c:
            return b''

        # Full transaction with repeated start
        addr_byte = (address << 1) & 0xFE

        result = self._i2c.transfer(
            write_data=bytes([addr_byte]) + write_data,
            read_bytes=read_len
        )
        return result if result else b''

    def i2c_scan(self, start_addr: int = 0x08, end_addr: int = 0x77) -> list[int]:
        """Scan I2C bus for devices."""
        if not self._connected or not self._i2c:
            return []

        # Use official scan implementation
        found = self._i2c.scan(start_addr=start_addr, end_addr=end_addr)

        # Convert from their format (address << 1) back to 7-bit addresses
        addresses = list(set(addr >> 1 for addr in found))
        addresses.sort()

        return addresses

    # --------------------------------------------------------------------------
    # UART Interface
    # --------------------------------------------------------------------------

    def configure_uart(self, config: UARTConfig) -> bool:
        """Configure UART interface.

        UART is defined in the BPIO2 FlatBuffers schema, but some firmware
        versions may not support it. We try BPIO2 first and fall back to
        terminal serial commands if it fails.
        """
        if not self._connected:
            return False

        # First, try BPIO2 protocol (UART is in the FlatBuffers schema)
        # Note: Some firmware versions list UART in modes_available but return
        # "Invalid mode name" when configuring. We try anyway and fall back if needed.
        if self._client and BPIOUART is not None:
            try:
                print(f"[BusPirate] Trying UART via BPIO2...")

                # Try to configure UART via BPIO2
                self._uart = BPIOUART(self._client)
                parity_bool = config.parity != 'N'  # BPIO uses bool for parity

                success = self._uart.configure(
                    speed=config.baudrate,
                    data_bits=config.data_bits,
                    parity=parity_bool,
                    stop_bits=config.stop_bits,
                    flow_control=False,
                    signal_inversion=False
                )

                if success:
                    self._current_mode = "UART"
                    print(f"[BusPirate] UART configured via BPIO2: {config.baudrate} baud")
                    return True
                else:
                    # BPIO2 UART may not be supported in this firmware version
                    # (returns "Invalid mode name" even though UART is listed)
                    print(f"[BusPirate] BPIO2 UART not supported in firmware, trying serial fallback...")
                    self._uart = None

            except Exception as e:
                print(f"[BusPirate] BPIO2 UART error: {e}, trying serial fallback...")
                self._uart = None

        # Fall back to serial terminal commands
        print(f"[BusPirate] Using terminal commands for UART configuration")

        # Try to establish serial fallback connection if not already open
        if not self._serial_fallback:
            console_port = self.device.port
            if console_port and 'buspirate3' in console_port:
                console_port = console_port.replace('buspirate3', 'buspirate1')
            if console_port:
                self._open_serial_fallback_to_port(console_port)

        return self._configure_uart_serial_fallback(config)

    def _configure_uart_serial_fallback(self, config: UARTConfig) -> bool:
        """
        Configure UART via serial terminal commands.

        Bus Pirate 5/6 UART configuration flow via 'm' menu:
        1. Send 'm' to enter mode selection menu
        2. Select option 3 for UART (menu: 1=HiZ, 2=1WIRE, 3=UART, 4=HDUART, 5=I2C, 6=SPI...)
        3. Answer "Use previous settings?" prompt with 'n' to configure fresh
        4. Configure speed, data bits, parity, stop bits, flow control, inversion
        5. Verify UART> prompt appears
        """
        if not self._serial_fallback:
            print("[BusPirate] No serial connection for UART config")
            return False

        try:
            import time

            print(f"[BusPirate] Configuring UART: {config.baudrate} baud, {config.data_bits}{config.parity}{config.stop_bits}")

            # Clear any pending data
            self._serial_fallback.reset_input_buffer()

            # Enter mode menu
            print("[BusPirate] Entering mode menu...")
            self._send_serial_command("m")
            time.sleep(0.5)

            # Select UART mode (option 3 in BP5/6 menu)
            # Menu: 1=HiZ, 2=1WIRE, 3=UART, 4=HDUART, 5=I2C, 6=SPI, 7=2WIRE, 8=3WIRE...
            print("[BusPirate] Selecting UART (option 3)...")
            success, response = self._send_serial_command("3")
            time.sleep(0.5)

            # Handle "Use previous settings?" prompt
            if "previous settings" in response.lower() or "y/n" in response.lower():
                # Say 'n' to configure with new settings (or 'y' to use previous)
                # For now, use previous settings if baud matches, otherwise configure new
                if str(config.baudrate) in response:
                    print("[BusPirate] Using previous UART settings")
                    success, response = self._send_serial_command("y")
                else:
                    print("[BusPirate] Configuring new UART settings...")
                    success, response = self._send_serial_command("n")
                time.sleep(0.3)

            # If we said 'n', we need to configure each setting
            # BP5/6 UART config prompts (in order):
            # 1. Speed selection (menu or direct entry)
            # 2. Data bits
            # 3. Parity
            # 4. Stop bits
            # 5. Hardware flow control
            # 6. Signal inversion

            # Handle speed selection
            if "speed" in response.lower() or "baud" in response.lower():
                # Send baud rate directly
                print(f"[BusPirate] Setting speed: {config.baudrate}")
                success, response = self._send_serial_command(str(config.baudrate))
                time.sleep(0.2)

            # Handle data bits (usually 8)
            if "data bits" in response.lower():
                print(f"[BusPirate] Setting data bits: {config.data_bits}")
                success, response = self._send_serial_command(str(config.data_bits))
                time.sleep(0.2)

            # Handle parity
            if "parity" in response.lower():
                parity_map = {"N": "1", "E": "2", "O": "3"}  # 1=None, 2=Even, 3=Odd
                parity_opt = parity_map.get(config.parity, "1")
                print(f"[BusPirate] Setting parity: {config.parity} (option {parity_opt})")
                _, response = self._send_serial_command(parity_opt)
                time.sleep(0.2)

            # Handle stop bits
            if "stop bits" in response.lower():
                print(f"[BusPirate] Setting stop bits: {config.stop_bits}")
                _, response = self._send_serial_command(str(config.stop_bits))
                time.sleep(0.2)

            # Handle flow control (usually None = option 1)
            if "flow control" in response.lower():
                print("[BusPirate] Setting flow control: None")
                _, response = self._send_serial_command("1")
                time.sleep(0.2)

            # Handle signal inversion (usually Non-inverted = option 1)
            if "inversion" in response.lower():
                print("[BusPirate] Setting signal inversion: None")
                _, response = self._send_serial_command("1")
                time.sleep(0.2)

            # Accept any remaining prompts with Enter
            for _ in range(3):
                if ">" not in response:
                    _, response = self._send_serial_command("")
                    time.sleep(0.2)
                else:
                    break

            # Verify we're in UART mode
            success, response = self._send_serial_command("")
            time.sleep(0.2)

            if "UART>" in response:
                self._current_mode = "UART"
                print(f"[BusPirate] UART configured successfully: {config.baudrate} baud")
                return True

            # Check one more time
            success, response = self._send_serial_command("")
            if "UART>" in response:
                self._current_mode = "UART"
                print(f"[BusPirate] UART configured: {config.baudrate} {config.data_bits}{config.parity}{config.stop_bits}")
                return True

            # If we got here but have some prompt, might still be OK
            if ">" in response:
                self._current_mode = "UART"
                print(f"[BusPirate] UART mode likely configured (prompt: {response.strip()[:20]})")
                return True

            print(f"[BusPirate] UART configuration uncertain - last response: {response[:100]}")
            return False

        except Exception as e:
            print(f"[BusPirate] UART config error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def uart_start_bridge(self, require_power: bool = True) -> bool:
        """
        Start transparent UART bridge mode.

        In bridge mode, the Bus Pirate acts as a transparent passthrough
        between the host serial port and the target UART. All data sent
        to the BP is forwarded to the target and vice versa.

        BP5/6 bridge command: 'bridge' from UART> prompt
        This enters transparent mode until reset.

        Args:
            require_power: If True (default), requires PSU to be enabled before
                          starting bridge mode. This ensures TX/RX pins have power.

        Returns:
            True if bridge mode started successfully
        """
        if not self._connected:
            return False

        # Check if power is enabled (required for TX/RX to work)
        if require_power and not self._psu_enabled:
            print("[BusPirate] Cannot start UART bridge: VOUT power not enabled")
            print("[BusPirate] Enable power supply first to power TX/RX pins")
            return False

        # BPIO mode - use the UART bridge feature
        if self._uart:
            # BPIO library handles bridge internally
            print("[BusPirate] UART bridge mode (BPIO)")
            return True

        # Serial fallback - send 'bridge' command
        if self._serial_fallback:
            import time

            # Make sure we're in UART mode first
            if self._current_mode != "UART":
                print("[BusPirate] Not in UART mode, cannot start bridge")
                return False

            # Send bridge command
            # BP5/6: 'bridge' enters transparent passthrough mode
            _, response = self._send_serial_command("bridge")
            time.sleep(0.2)

            # Bridge mode may show a message about entering bridge mode
            if "bridge" in response.lower() or "transparent" in response.lower():
                print("[BusPirate] UART bridge mode started")
                return True

            # Even without confirmation, assume bridge mode is active
            print("[BusPirate] UART bridge mode started (assumed)")
            return True

        return False

    def uart_write(self, data: bytes):
        """Write data to UART."""
        # BPIO mode
        if self._uart:
            self._uart.write(list(data))
            return

        # Serial fallback mode - send data directly
        if self._serial_fallback and self._current_mode == "UART":
            try:
                self._serial_fallback.write(data)
            except Exception as e:
                print(f"[BusPirate] UART write error: {e}")

    def uart_read(self, length: int, timeout_ms: int = 1000) -> bytes:
        """Read data from UART."""
        # BPIO mode
        if self._uart:
            result = self._uart.read(length)
            return result if result else b''

        # Serial fallback mode - read from serial
        if self._serial_fallback and self._current_mode == "UART":
            try:
                # Set timeout based on timeout_ms
                old_timeout = self._serial_fallback.timeout
                self._serial_fallback.timeout = timeout_ms / 1000.0

                # Read available data
                data = b''
                if self._serial_fallback.in_waiting > 0:
                    data = self._serial_fallback.read(min(length, self._serial_fallback.in_waiting))
                elif timeout_ms > 0:
                    # Wait for data with timeout
                    data = self._serial_fallback.read(1)  # Wait for at least 1 byte
                    if data and self._serial_fallback.in_waiting > 0:
                        data += self._serial_fallback.read(min(length - 1, self._serial_fallback.in_waiting))

                self._serial_fallback.timeout = old_timeout
                return data
            except Exception as e:
                print(f"[BusPirate] UART read error: {e}")
                return b''

        return b''

    def uart_auto_detect(
        self,
        baud_rates: list[int] | None = None,
        data_bits_options: list[int] | None = None,
        parity_options: list[str] | None = None,
        stop_bits_options: list[int] | None = None,
        test_duration_ms: int = 500,
        progress_callback=None
    ) -> list[dict[str, Any]]:
        """
        Auto-detect UART configuration by testing different combinations.

        This method tests various UART settings to find configurations that
        produce valid/readable data. It's useful for identifying unknown
        UART interfaces on target devices.

        Args:
            baud_rates: List of baud rates to test (default: common rates)
            data_bits_options: List of data bit settings (default: [8, 7])
            parity_options: List of parity settings (default: ['N', 'E', 'O'])
            stop_bits_options: List of stop bit settings (default: [1, 2])
            test_duration_ms: How long to listen for data at each setting (ms)
            progress_callback: Optional callback(current, total, config_str) -> bool
                              Return False to stop scanning

        Returns:
            List of configurations that received valid data, each containing:
            {
                'baudrate': int,
                'data_bits': int,
                'parity': str,
                'stop_bits': int,
                'data_received': bytes,
                'printable_ratio': float,  # Ratio of printable ASCII chars
                'likely_valid': bool       # True if high printable ratio
            }
        """
        import time

        if not self._connected:
            return []

        # Default configuration options
        if baud_rates is None:
            baud_rates = [115200, 9600, 57600, 38400, 19200, 230400, 460800, 921600]
        if data_bits_options is None:
            data_bits_options = [8, 7]
        if parity_options is None:
            parity_options = ['N', 'E', 'O']
        if stop_bits_options is None:
            stop_bits_options = [1, 2]

        results = []
        total_tests = len(baud_rates) * len(data_bits_options) * len(parity_options) * len(stop_bits_options)
        current_test = 0

        print(f"[BusPirate] Starting UART auto-detect ({total_tests} combinations)")

        for baud in baud_rates:
            for data_bits in data_bits_options:
                for parity in parity_options:
                    for stop_bits in stop_bits_options:
                        current_test += 1
                        config_str = f"{baud} {data_bits}{parity}{stop_bits}"

                        # Progress callback
                        if progress_callback:
                            if not progress_callback(current_test, total_tests, config_str):
                                print(f"[BusPirate] UART scan stopped by user")
                                return results

                        # Configure UART with this setting
                        config = UARTConfig(
                            baudrate=baud,
                            data_bits=data_bits,
                            parity=parity,
                            stop_bits=stop_bits
                        )

                        try:
                            if not self.configure_uart(config):
                                continue

                            # Wait and collect data
                            time.sleep(test_duration_ms / 1000.0)

                            # Try to read any available data
                            data = self.uart_read(256, timeout_ms=test_duration_ms)

                            if data and len(data) > 0:
                                # Calculate how much of the data is printable ASCII
                                printable_count = sum(1 for b in data if 32 <= b <= 126 or b in (9, 10, 13))
                                printable_ratio = printable_count / len(data) if len(data) > 0 else 0

                                # Consider it "likely valid" if >50% printable
                                likely_valid = printable_ratio > 0.5

                                result = {
                                    'baudrate': baud,
                                    'data_bits': data_bits,
                                    'parity': parity,
                                    'stop_bits': stop_bits,
                                    'data_received': data,
                                    'printable_ratio': printable_ratio,
                                    'likely_valid': likely_valid
                                }
                                results.append(result)

                                if likely_valid:
                                    print(f"[BusPirate] Found valid config: {config_str} ({printable_ratio:.0%} printable)")

                        except Exception as e:
                            print(f"[BusPirate] Error testing {config_str}: {e}")
                            continue

        print(f"[BusPirate] UART scan complete: {len(results)} configs received data")
        return results

    def uart_auto_detect_quick(
        self,
        test_duration_ms: int = 300,
        progress_callback=None
    ) -> list[dict[str, Any]]:
        """
        Quick UART auto-detect focusing on most common configurations.

        Tests only 8N1 format with common baud rates for faster scanning.

        Args:
            test_duration_ms: How long to listen at each baud rate
            progress_callback: Optional callback(current, total, config_str) -> bool

        Returns:
            List of configurations that received valid data
        """
        # Most common configurations only
        common_bauds = [115200, 9600, 57600, 38400, 19200, 230400]

        return self.uart_auto_detect(
            baud_rates=common_bauds,
            data_bits_options=[8],
            parity_options=['N'],
            stop_bits_options=[1],
            test_duration_ms=test_duration_ms,
            progress_callback=progress_callback
        )

    # --------------------------------------------------------------------------
    # UART Glitch Attack
    # --------------------------------------------------------------------------

    def uart_glitch(
        self,
        trigger_char: int = 13,
        trigger_delay: int = 1400,
        vary_time: int = 3,
        output_on_time: int = 7,
        cycle_delay: int = 100,
        normal_response: int = 80,
        num_attempts: int = 1000,
        bypass_ready: bool = True,
        progress_callback=None
    ) -> bool:
        """
        Execute UART glitch attack using Bus Pirate 5/6 'glitch' command.

        The Bus Pirate acts as a timing trigger - IO0 goes high during the glitch
        window. An external crowbar circuit or voltage fault injector is required
        to actually perform the glitch on the target.

        Timing values are in units of 10 nanoseconds.

        Args:
            trigger_char: ASCII character to send to target to initiate (default: 13 = CR)
            trigger_delay: Delay after trigger before glitch output (ns×10)
            vary_time: Timing variation increment per attempt (ns×10)
            output_on_time: Duration glitch output stays active (ns×10)
            cycle_delay: Wait time between attempts (ms)
            normal_response: ASCII char indicating failed glitch (default: 80 = 'P')
            num_attempts: Maximum number of glitch attempts
            bypass_ready: Skip IO1 ready signal checking
            progress_callback: Optional callback(attempt, total, message) -> bool (return False to stop)

        Returns:
            True if glitch was successful (abnormal response detected)
        """
        if not self._connected:
            print("[BusPirate] Not connected")
            return False

        import serial
        import time

        # Use the console port for glitch command
        port = self.device.port
        if not port:
            print("[BusPirate] No port available")
            return False

        try:
            ser = serial.Serial(port, 115200, timeout=2)
            time.sleep(0.1)
            ser.reset_input_buffer()

            # First, ensure we're in UART mode
            print("[BusPirate] Entering UART mode for glitch...")
            ser.write(b"uart\r\n")
            time.sleep(0.5)
            if ser.in_waiting > 0:
                response = ser.read(ser.in_waiting)
                print(f"[BusPirate] Mode response: {response.decode('utf-8', errors='ignore')[:100]}")

            # Start the glitch command
            print("[BusPirate] Starting glitch command...")
            ser.write(b"glitch\r\n")
            time.sleep(0.5)

            # Read initial prompt - "Use previous settings?"
            if ser.in_waiting > 0:
                response = ser.read(ser.in_waiting)
                response_str = response.decode('utf-8', errors='ignore')
                print(f"[BusPirate] Glitch prompt: {response_str[:200]}")

                # Answer "no" to use previous settings - we'll configure fresh
                if "previous" in response_str.lower():
                    ser.write(b"n\r\n")
                    time.sleep(0.3)

            # Configure each parameter
            def send_param(value, name):
                """Send a parameter value and read response"""
                ser.write(f"{value}\r\n".encode())
                time.sleep(0.2)
                if ser.in_waiting > 0:
                    resp = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                    print(f"[BusPirate] {name}: {resp[:50]}")

            # Send configuration parameters in order
            send_param(trigger_char, "Trigger char")
            send_param(trigger_delay, "Trigger delay")
            send_param(vary_time, "Vary time")
            send_param(output_on_time, "Output on time")
            send_param(cycle_delay, "Cycle delay")
            send_param(normal_response, "Normal response")
            send_param(num_attempts, "Num attempts")

            # Bypass ready check (y/n)
            bypass_str = "y" if bypass_ready else "n"
            send_param(bypass_str, "Bypass ready")

            # Now the glitch sequence should start
            print("[BusPirate] Glitch sequence starting...")

            # Monitor for results
            glitch_success = False
            attempts_seen = 0
            start_time = time.time()
            max_runtime = (num_attempts * cycle_delay / 1000) + 30  # Add 30s buffer

            while time.time() - start_time < max_runtime:
                if ser.in_waiting > 0:
                    data = ser.read(ser.in_waiting)
                    output = data.decode('utf-8', errors='ignore')

                    # Parse output for attempt numbers and results
                    if "attempt" in output.lower():
                        # Try to extract attempt number
                        import re
                        match = re.search(r'(\d+)', output)
                        if match:
                            attempts_seen = int(match.group(1))
                            if progress_callback:
                                if not progress_callback(attempts_seen, num_attempts, None):
                                    # User requested stop
                                    print("[BusPirate] Glitch stopped by user")
                                    ser.write(b"\x03")  # Ctrl+C to stop
                                    break

                    # Check for success indication
                    if "success" in output.lower() or "glitch!" in output.lower():
                        glitch_success = True
                        if progress_callback:
                            progress_callback(attempts_seen, num_attempts, "[+] GLITCH SUCCESS DETECTED!")
                        print(f"[BusPirate] GLITCH SUCCESS: {output}")
                        break

                    # Check for completion
                    if "complete" in output.lower() or "done" in output.lower():
                        print(f"[BusPirate] Glitch sequence completed")
                        break

                    print(f"[BusPirate] {output[:200]}")

                time.sleep(0.1)

            ser.close()
            return glitch_success

        except Exception as e:
            print(f"[BusPirate] Glitch error: {e}")
            import traceback
            traceback.print_exc()
            return False

    # --------------------------------------------------------------------------
    # Target Device Scanning
    # --------------------------------------------------------------------------

    def scan_target(self, power_voltage_mv: int = 3300, power_current_ma: int = 300,
                    enable_pullups: bool = True) -> dict[str, Any]:
        """
        Power up and scan a target device for all available interfaces.

        This is a general-purpose function that:
        1. Enables PSU to power the target
        2. Scans I2C bus for devices
        3. Tests SPI for flash chips
        4. Reads pin voltages and IO states

        Args:
            power_voltage_mv: PSU voltage in millivolts (default: 3.3V)
            power_current_ma: PSU current limit in milliamps (default: 300mA)
            enable_pullups: Enable pull-up resistors for I2C (default: True)

        Returns:
            Dictionary with scan results:
            {
                'psu': {'enabled': bool, 'voltage_mv': int, 'current_ma': int},
                'i2c_devices': [list of 7-bit addresses],
                'spi_flash': {'detected': bool, 'id': bytes, 'manufacturer': int},
                'pin_voltages': {pin_name: voltage_mv},
                'io_status': {pin_name: {'direction': str, 'value': str}}
            }
        """
        import time

        if not self._connected or not self._client:
            return {'error': 'Not connected'}

        results = {}

        # 1. Enable PSU
        print(f"[Scan] Enabling PSU: {power_voltage_mv}mV, {power_current_ma}mA limit...")
        self.set_psu(enabled=True, voltage_mv=power_voltage_mv, current_ma=power_current_ma)
        time.sleep(0.5)  # Give target time to power up

        # Get PSU status
        info = self.get_info()
        psu_info = {
            'enabled': info.get('psu_enabled', False),
            'set_voltage_mv': info.get('psu_set_mv', 0),
            'measured_voltage_mv': info.get('psu_measured_mv', 0),
            'measured_current_ma': info.get('psu_measured_ma', 0),
            'over_current': info.get('psu_current_error', False)
        }
        results['psu'] = psu_info

        print(f"[Scan] PSU: {psu_info['measured_voltage_mv']}mV, {psu_info['measured_current_ma']}mA")
        if psu_info['over_current']:
            print("[Scan] ⚠️  PSU over-current detected!")

        # Wait for target to boot
        time.sleep(1)

        # 2. Scan I2C
        print(f"[Scan] Scanning I2C bus...")
        if enable_pullups:
            self.set_pullups(enabled=True)

        self.configure_i2c(I2CConfig(speed_hz=100_000))  # 100kHz standard mode
        i2c_devices = self.i2c_scan(start_addr=0x08, end_addr=0x77)
        results['i2c_devices'] = i2c_devices

        if i2c_devices:
            print(f"[Scan] Found {len(i2c_devices)} I2C device(s): {[hex(a) for a in i2c_devices]}")
        else:
            print(f"[Scan] No I2C devices found")

        # 3. Test SPI
        print(f"[Scan] Testing SPI interface...")
        self.configure_spi(SPIConfig(speed_hz=1_000_000, mode=0))
        flash_id = self.spi_flash_read_id()

        spi_detected = flash_id and flash_id != b'\x00\x00\x00' and flash_id != b'\xff\xff\xff'
        results['spi_flash'] = {
            'detected': spi_detected,
            'id': flash_id.hex() if flash_id else None,
            'manufacturer': flash_id[0] if flash_id and len(flash_id) > 0 else None,
            'device': flash_id[1:3].hex() if flash_id and len(flash_id) >= 3 else None
        }

        if spi_detected:
            print(f"[Scan] SPI flash detected: {flash_id.hex()}")
        else:
            print(f"[Scan] No SPI flash detected")

        # 4. Read pin voltages
        info = self.get_info()
        if 'adc_mv' in info and info['adc_mv']:
            pin_voltages = {}
            pin_labels = info.get('mode_pin_labels', [])

            # Map pin labels to voltages
            for i, label in enumerate(pin_labels):
                if i < len(info['adc_mv']):
                    pin_voltages[label] = info['adc_mv'][i]

            results['pin_voltages'] = pin_voltages
            print(f"[Scan] Pin voltages captured: {len(pin_voltages)} pins")

        # 5. IO status
        io_status = {}
        io_dir = info.get('io_direction', 0)
        io_val = info.get('io_value', 0)

        for i in range(8):
            direction = 'OUT' if (io_dir >> i) & 1 else 'IN'
            value = 'HIGH' if (io_val >> i) & 1 else 'LOW'
            io_status[f'IO{i}'] = {'direction': direction, 'value': value}

        results['io_status'] = io_status

        return results

    # --------------------------------------------------------------------------
    # PSU Control (Bus Pirate specific)
    # --------------------------------------------------------------------------

    def set_psu(self, enabled: bool, voltage_mv: int = 3300, current_ma: int = 300) -> bool:
        """
        Control the onboard programmable power supply.

        Args:
            enabled: Enable/disable PSU
            voltage_mv: Output voltage in millivolts (1800-5000)
            current_ma: Current limit in milliamps (0 for unlimited)
        """
        if not self._connected:
            return False

        # If BPIO client is available, use it
        if self._client:
            if enabled:
                return self._client.configuration_request(
                    psu_enable=True,
                    psu_set_mv=voltage_mv,
                    psu_set_ma=current_ma
                )
            else:
                return self._client.configuration_request(
                    psu_disable=True
                )

        # Fallback to serial commands for when BPIO library isn't available
        return self._send_serial_psu_command(enabled, voltage_mv, current_ma)

    def _send_serial_psu_command(self, enabled: bool, voltage_mv: int = 3300, current_ma: int = 300) -> bool:
        """
        Send PSU command via serial terminal interface.

        Bus Pirate 5/6 PSU commands:
        - "W <voltage>" - Enable PSU with voltage (e.g., "W 3.3")
        - "w" - Disable PSU
        """
        if not self._serial_fallback:
            print(f"[BusPirate] No serial connection for PSU command")
            return False

        try:
            if enabled:
                # Set voltage and enable
                voltage_v = voltage_mv / 1000.0
                # Bus Pirate 5/6 uses "W" command for power supply enable
                cmd = f"W {voltage_v:.1f}"
                success, response = self._send_serial_command(cmd)

                if success:
                    self._psu_enabled = True
                    self._psu_voltage_mv = voltage_mv
                    # Check response for confirmation
                    response_lower = response.lower()
                    voltage_str = f"{voltage_v:.1f}"
                    if "power" in response_lower or "psu" in response_lower or ">" in response or voltage_str in response:
                        print(f"[BusPirate] PSU enabled: {voltage_v:.1f}V")
                        return True
                    elif "error" in response_lower or "invalid" in response_lower:
                        print(f"[BusPirate] PSU command error: {response[:100]}")
                        self._psu_enabled = False
                        return False
                    else:
                        # Command was sent, assume success
                        print(f"[BusPirate] PSU command sent (assuming success)")
                        return True
                return False
            else:
                # Disable power - send "w" command (lowercase)
                success, response = self._send_serial_command("w")
                if success:
                    self._psu_enabled = False
                    print(f"[BusPirate] PSU disabled")
                    return True
                return False

        except Exception as e:
            print(f"[BusPirate] Serial PSU command failed: {e}")
            return False

    def set_pullups(self, enabled: bool) -> bool:
        """Enable/disable internal pull-up resistors."""
        if not self._connected:
            return False

        # If BPIO client is available, use it
        if self._client:
            if enabled:
                return self._client.configuration_request(pullup_enable=True)
            else:
                return self._client.configuration_request(pullup_disable=True)

        # Fallback to serial commands
        return self._send_serial_pullup_command(enabled)

    def _send_serial_pullup_command(self, enabled: bool) -> bool:
        """
        Send pullup command via serial terminal interface.

        Bus Pirate 5/6 pullup commands:
        - "P" - Enable pull-up resistors
        - "p" - Disable pull-up resistors
        """
        if not self._serial_fallback:
            print(f"[BusPirate] No serial connection for pullup command")
            return False

        try:
            if enabled:
                # Enable pullups - "P" command
                success, response = self._send_serial_command("P")
            else:
                # Disable pullups - "p" command
                success, response = self._send_serial_command("p")

            if success:
                self._pullups_enabled = enabled
                status = "enabled" if enabled else "disabled"
                print(f"[BusPirate] Pull-ups {status}")
                return True
            return False

        except Exception as e:
            print(f"[BusPirate] Serial pullup command failed: {e}")
            return False

    def _send_serial_mode_command(self, mode: str, config=None) -> bool:
        """
        Send mode change command via serial terminal interface.

        Bus Pirate 5/6 terminal commands for mode selection:
        - Direct mode name: 'spi', 'i2c', 'uart', '1wire'
        - Menu-based: 'm' followed by number selection

        For non-interactive:
        - 'spi' - Enter SPI mode
        - 'i2c' - Enter I2C mode
        - 'uart' - Enter UART mode
        """
        if not self._serial_fallback:
            print(f"[BusPirate] No serial connection for mode command")
            return False

        try:
            mode_upper = mode.upper()
            mode_cmd = mode.lower()

            # Try direct mode command first
            print(f"[BusPirate] Setting mode to: {mode_upper}")
            success, response = self._send_serial_command(mode_cmd)

            if success:
                # Check if mode was successfully set
                response_upper = response.upper()
                if mode_upper in response_upper or f"{mode_upper}>" in response_upper or "ready" in response.lower():
                    self._current_mode = mode_upper
                    print(f"[BusPirate] Mode set to {mode_upper}")

                    # Apply additional configuration if provided
                    if config:
                        self._apply_mode_config(mode_upper, config)

                    return True

                # Check for prompt that indicates mode change
                if ">" in response:
                    # Mode likely changed, update internal state
                    self._current_mode = mode_upper
                    print(f"[BusPirate] Mode likely set to {mode_upper}")

                    if config:
                        self._apply_mode_config(mode_upper, config)

                    return True

            # If direct command didn't work, try menu-based approach
            print(f"[BusPirate] Trying menu-based mode selection...")
            success, menu_response = self._send_serial_command("m")

            if success and menu_response:
                print(f"[BusPirate] Mode menu: {menu_response[:200]}")

                # Map mode to menu number (Bus Pirate 5/6 menu)
                mode_numbers = {
                    "SPI": "5",
                    "I2C": "4",
                    "UART": "3",
                    "1WIRE": "6",
                }

                if mode_upper in mode_numbers:
                    success, result = self._send_serial_command(mode_numbers[mode_upper])

                    if success:
                        print(f"[BusPirate] Mode selection result: {result[:200]}")
                        self._current_mode = mode_upper

                        if config:
                            self._apply_mode_config(mode_upper, config)

                        return True

            return False

        except Exception as e:
            print(f"[BusPirate] Serial mode command failed: {e}")
            return False

    def _apply_mode_config(self, mode: str, config) -> None:
        """Apply mode-specific configuration (logging only for now)."""
        if mode == "SPI" and hasattr(config, 'speed_hz'):
            speed_khz = config.speed_hz // 1000
            print(f"[BusPirate] SPI configured: {speed_khz}kHz")

        elif mode == "I2C" and hasattr(config, 'speed_hz'):
            speed_khz = config.speed_hz // 1000
            print(f"[BusPirate] I2C configured: {speed_khz}kHz")

        elif mode == "UART" and hasattr(config, 'baudrate'):
            print(f"[BusPirate] UART configured: {config.baudrate} baud")

    # --------------------------------------------------------------------------
    # Logic Analyzer (SUMP Protocol)
    # --------------------------------------------------------------------------

    def enter_sump_mode(self) -> bool:
        """
        Enter SUMP logic analyzer mode.

        Bus Pirate uses SUMP protocol for logic analyzer functionality.
        This switches from BPIO2 mode to SUMP mode.
        """
        import serial
        import time

        if not self.device.port:
            return False

        # SUMP runs on the console port (buspirate1)
        console_port = self.device.port

        try:
            print(f"[BusPirate] Entering SUMP mode via: {console_port}")

            # Open console port
            ser = serial.Serial(console_port, 115200, timeout=2)
            time.sleep(0.1)
            ser.reset_input_buffer()
            ser.reset_output_buffer()

            # Send binmode command
            ser.write(b'binmode\r\n')
            time.sleep(0.5)

            # Read response
            if ser.in_waiting > 0:
                response = ser.read(ser.in_waiting)
                print(f"[BusPirate] Menu: {response.decode('utf-8', errors='ignore')[:100]}")

            # Select SUMP mode (option 1 in binmode menu)
            ser.write(b'1\r\n')
            time.sleep(0.5)

            if ser.in_waiting > 0:
                response = ser.read(ser.in_waiting)
                print(f"[BusPirate] SUMP mode: {response.decode('utf-8', errors='ignore')[:100]}")

            ser.close()
            time.sleep(0.5)

            return True

        except Exception as e:
            print(f"[BusPirate] SUMP mode failed: {e}")
            return False

    def capture_logic(
        self,
        sample_rate: int = 1_000_000,
        sample_count: int = 8192,
        channels: int = 8,
        trigger_channel: int | None = None,
        trigger_edge: str = "rising",
        timeout: float = 10.0
    ) -> dict | None:
        """
        Capture logic analyzer data using SUMP protocol.

        Args:
            sample_rate: Sample rate in Hz (max 62.5MHz on BP5/6)
            sample_count: Number of samples to capture
            channels: Number of channels (8 on Bus Pirate)
            trigger_channel: Channel to trigger on (None for immediate)
            trigger_edge: "rising" or "falling"
            timeout: Capture timeout in seconds

        Returns:
            Dictionary with capture data or None on error:
            {
                'channels': int,
                'sample_rate': int,
                'samples': List[List[int]],  # Per-channel sample lists
                'trigger_position': int,
                'raw_data': bytes
            }
        """
        import serial

        # Bus Pirate SUMP runs on the console port
        console_port = self.device.port

        try:
            # Enter SUMP mode first
            if not self.enter_sump_mode():
                return None

            # Open serial for SUMP
            print(f"[BusPirate] Opening SUMP connection: {console_port}")
            sump_serial = serial.Serial(console_port, 115200, timeout=2)

            # Import and use SUMP client
            from .sump import SUMPClient, SUMPConfig

            client = SUMPClient(sump_serial, debug=True)

            # Reset
            client.reset()

            # Check device
            success, device_id = client.identify()
            if not success:
                print(f"[BusPirate] SUMP not responding: {device_id}")
                sump_serial.close()
                return None

            print(f"[BusPirate] SUMP device: {device_id}")

            # Get metadata
            metadata = client.get_metadata()
            if metadata:
                print(f"[BusPirate] SUMP metadata: {metadata}")

            # Configure capture
            config = SUMPConfig(
                sample_rate=sample_rate,
                sample_count=sample_count,
                channels=channels,
                base_clock=62_500_000,  # Bus Pirate 5/6 base clock
            )

            # Set trigger
            if trigger_channel is not None and 0 <= trigger_channel < channels:
                config.trigger_mask = 1 << trigger_channel
                config.trigger_value = (1 << trigger_channel) if trigger_edge == "rising" else 0

            client.configure(config)

            # Capture
            print(f"[BusPirate] Starting capture...")
            capture = client.capture(timeout=timeout)

            sump_serial.close()

            if capture:
                return {
                    'channels': capture.channels,
                    'sample_rate': capture.sample_rate,
                    'samples': capture.samples,
                    'trigger_position': capture.trigger_position,
                    'raw_data': capture.raw_data
                }
            else:
                return None

        except ImportError:
            print("[BusPirate] pyserial not installed")
            return None
        except Exception as e:
            print(f"[BusPirate] Capture failed: {e}")
            import traceback
            traceback.print_exc()
            return None


# Register this backend for buspirate device type
register_backend("buspirate", BusPirateBackend)
