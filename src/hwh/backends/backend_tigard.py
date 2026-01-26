"""
Tigard backend using pyftdi for SPI/I2C/UART and OpenOCD for JTAG/SWD.

Reference: https://github.com/tigard-tools/tigard
"""

import socket
import time
from typing import Any, Optional

from .base import (
    BusBackend, DebugBackend, register_backend,
    SPIConfig, I2CConfig, UARTConfig
)
from ..detect import DeviceInfo


class TigardBackend(BusBackend):
    """
    Backend for Tigard (FT2232H-based) hardware tool.
    
    Uses pyftdi for bus protocols (SPI, I2C, UART).
    JTAG/SWD requires OpenOCD - see TigardDebugBackend.
    
    Tigard has two channels:
    - Channel A: UART
    - Channel B: SPI/I2C/JTAG/SWD (directly controlled via MPSSE)
    """
    
    # FTDI device URL format for pyftdi
    FTDI_URL_TEMPLATE = "ftdi://ftdi:2232h:{serial}/2"  # Channel B
    
    def __init__(self, device: DeviceInfo):
        super().__init__(device)
        self._spi = None
        self._i2c = None
        self._uart = None
        self._ftdi_url = None
        self._current_protocol = None
    
    def connect(self) -> bool:
        """Connect to Tigard via pyftdi."""
        try:
            from pyftdi.ftdi import Ftdi
        except ImportError:
            print("[Tigard] pyftdi not installed")
            print("  Install with: pip install pyftdi")
            return False
        
        try:
            # Build FTDI URL
            if self.device.serial:
                self._ftdi_url = f"ftdi://ftdi:2232h:{self.device.serial}/2"
            else:
                # Use first available FT2232H
                self._ftdi_url = "ftdi://ftdi:2232h/2"
            
            # Verify device is accessible
            Ftdi.show_devices()
            self._connected = True
            print(f"[Tigard] Ready at {self._ftdi_url}")
            return True
            
        except Exception as e:
            print(f"[Tigard] Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from Tigard."""
        if self._spi:
            try:
                self._spi.close()
            except Exception:
                pass
            self._spi = None
        
        if self._i2c:
            try:
                self._i2c.close()
            except Exception:
                pass
            self._i2c = None
        
        self._connected = False
        self._current_protocol = None
    
    def get_info(self) -> dict[str, Any]:
        """Get Tigard information."""
        return {
            "name": "Tigard",
            "ftdi_url": self._ftdi_url,
            "current_protocol": self._current_protocol,
            "capabilities": ["spi", "i2c", "uart", "jtag", "swd"],
        }
    
    # --------------------------------------------------------------------------
    # SPI Interface
    # --------------------------------------------------------------------------
    
    def configure_spi(self, config: SPIConfig) -> bool:
        """Configure SPI interface."""
        if not self._connected:
            return False
        
        # Close any existing protocol controller
        self._close_current_protocol()
        
        try:
            from pyftdi.spi import SpiController
            
            ctrl = SpiController()
            ctrl.configure(self._ftdi_url)
            
            # Get SPI port with configuration
            # Mode maps to CPOL/CPHA
            self._spi = ctrl.get_port(
                cs=0,
                freq=config.speed_hz,
                mode=config.mode
            )
            
            self._current_protocol = "SPI"
            print(f"[Tigard] SPI configured: {config.speed_hz}Hz, mode {config.mode}")
            return True
            
        except Exception as e:
            print(f"[Tigard] SPI configuration failed: {e}")
            return False
    
    def spi_transfer(self, write_data: bytes, read_len: int = 0) -> bytes:
        """Perform SPI transfer."""
        if not self._spi:
            return b''
        
        try:
            if read_len > 0 and write_data:
                # Write then read
                return bytes(self._spi.exchange(write_data, read_len))
            elif read_len > 0:
                # Read only
                return bytes(self._spi.read(read_len))
            elif write_data:
                # Write only
                self._spi.write(write_data)
                return b''
            return b''
            
        except Exception as e:
            print(f"[Tigard] SPI transfer failed: {e}")
            return b''
    
    def spi_flash_read_id(self) -> bytes:
        """Read SPI flash JEDEC ID (command 0x9F)."""
        return self.spi_transfer(b'\x9f', read_len=3)
    
    def spi_flash_read(self, address: int, length: int) -> bytes:
        """Read from SPI flash."""
        # Standard read command: 0x03 + 24-bit address
        cmd = bytes([0x03, (address >> 16) & 0xFF, (address >> 8) & 0xFF, address & 0xFF])
        return self.spi_transfer(cmd, read_len=length)

    def spi_flash_write(self, address: int, data: bytes) -> bool:
        """
        Write data to SPI flash using page program (0x02).
        Handles page boundaries (256 bytes) automatically.
        """
        if not self._spi:
            return False

        PAGE_SIZE = 256
        offset = 0
        total = len(data)

        while offset < total:
            # Calculate page-aligned write
            page_offset = address % PAGE_SIZE
            chunk_size = min(PAGE_SIZE - page_offset, total - offset)
            chunk = data[offset:offset + chunk_size]

            # Write enable
            if not self._spi_write_enable():
                print(f"[Tigard] Write enable failed at 0x{address:06X}")
                return False

            # Page program command: 0x02 + 24-bit address + data
            cmd = bytes([
                0x02,
                (address >> 16) & 0xFF,
                (address >> 8) & 0xFF,
                address & 0xFF
            ]) + chunk

            self.spi_transfer(cmd)

            # Wait for write to complete
            if not self._spi_wait_ready(timeout_ms=100):
                print(f"[Tigard] Write timeout at 0x{address:06X}")
                return False

            address += chunk_size
            offset += chunk_size

        return True

    def spi_flash_erase(self, address: int = 0, erase_type: str = "chip") -> bool:
        """
        Erase SPI flash.

        Args:
            address: Start address (for sector/block erase)
            erase_type: "sector" (4KB), "block" (64KB), or "chip"
        """
        if not self._spi:
            return False

        # Write enable required before erase
        if not self._spi_write_enable():
            print("[Tigard] Write enable failed for erase")
            return False

        if erase_type == "chip":
            # Chip erase: 0xC7 or 0x60
            self.spi_transfer(b'\xC7')
            print("[Tigard] Chip erase started (may take several seconds)...")
            timeout = 60000  # 60 seconds for chip erase
        elif erase_type == "block":
            # Block erase (64KB): 0xD8 + 24-bit address
            cmd = bytes([0xD8, (address >> 16) & 0xFF, (address >> 8) & 0xFF, address & 0xFF])
            self.spi_transfer(cmd)
            print(f"[Tigard] Block erase at 0x{address:06X}")
            timeout = 2000  # 2 seconds for block
        elif erase_type == "sector":
            # Sector erase (4KB): 0x20 + 24-bit address
            cmd = bytes([0x20, (address >> 16) & 0xFF, (address >> 8) & 0xFF, address & 0xFF])
            self.spi_transfer(cmd)
            print(f"[Tigard] Sector erase at 0x{address:06X}")
            timeout = 500  # 500ms for sector
        else:
            print(f"[Tigard] Unknown erase type: {erase_type}")
            return False

        # Wait for erase to complete
        if not self._spi_wait_ready(timeout_ms=timeout):
            print("[Tigard] Erase timeout")
            return False

        print("[Tigard] Erase complete")
        return True

    def _spi_write_enable(self) -> bool:
        """Send write enable command (0x06) and verify WEL bit."""
        if not self._spi:
            return False

        # Send write enable
        self.spi_transfer(b'\x06')

        # Read status register and check WEL bit
        status = self.spi_transfer(b'\x05', read_len=1)
        if status and (status[0] & 0x02):  # WEL bit set
            return True

        return False

    def _spi_wait_ready(self, timeout_ms: int = 1000) -> bool:
        """Wait for flash to be ready (BUSY bit cleared)."""
        import time

        start = time.time()
        timeout_s = timeout_ms / 1000.0

        while (time.time() - start) < timeout_s:
            status = self.spi_transfer(b'\x05', read_len=1)
            if status and not (status[0] & 0x01):  # BUSY bit cleared
                return True
            time.sleep(0.001)  # 1ms poll interval

        return False

    def spi_flash_read_status(self) -> int:
        """Read SPI flash status register."""
        status = self.spi_transfer(b'\x05', read_len=1)
        return status[0] if status else 0

    def spi_flash_write_enable(self) -> bool:
        """Public wrapper for write enable."""
        return self._spi_write_enable()

    # --------------------------------------------------------------------------
    # I2C Interface
    # --------------------------------------------------------------------------
    
    def configure_i2c(self, config: I2CConfig) -> bool:
        """Configure I2C interface."""
        if not self._connected:
            return False
        
        self._close_current_protocol()
        
        try:
            from pyftdi.i2c import I2cController
            
            ctrl = I2cController()
            ctrl.configure(self._ftdi_url, frequency=config.speed_hz)
            self._i2c = ctrl
            
            self._current_protocol = "I2C"
            print(f"[Tigard] I2C configured: {config.speed_hz}Hz")
            return True
            
        except Exception as e:
            print(f"[Tigard] I2C configuration failed: {e}")
            return False
    
    def i2c_write(self, address: int, data: bytes) -> bool:
        """Write data to I2C device."""
        if not self._i2c:
            return False
        
        try:
            port = self._i2c.get_port(address)
            port.write(data)
            return True
        except Exception as e:
            print(f"[Tigard] I2C write failed: {e}")
            return False
    
    def i2c_read(self, address: int, length: int) -> bytes:
        """Read data from I2C device."""
        if not self._i2c:
            return b''
        
        try:
            port = self._i2c.get_port(address)
            return bytes(port.read(length))
        except Exception as e:
            print(f"[Tigard] I2C read failed: {e}")
            return b''
    
    def i2c_write_read(self, address: int, write_data: bytes, read_len: int) -> bytes:
        """Write then read from I2C device (repeated start)."""
        if not self._i2c:
            return b''
        
        try:
            port = self._i2c.get_port(address)
            return bytes(port.exchange(write_data, read_len))
        except Exception as e:
            print(f"[Tigard] I2C exchange failed: {e}")
            return b''
    
    def i2c_scan(self) -> list[int]:
        """Scan I2C bus for devices."""
        if not self._i2c:
            return []
        
        found = []
        for addr in range(0x08, 0x78):
            try:
                port = self._i2c.get_port(addr)
                port.read(0)  # Try to read - will raise if no ACK
                found.append(addr)
            except Exception:
                pass
        
        return found
    
    # --------------------------------------------------------------------------
    # UART Interface
    # --------------------------------------------------------------------------
    
    def configure_uart(self, config: UARTConfig) -> bool:
        """Configure UART interface (uses Channel A)."""
        if not self._connected:
            return False
        
        try:
            import serial
            
            # UART is on the first serial port associated with the FT2232H
            # This is typically the device.port
            if self.device.port:
                self._uart = serial.Serial(
                    self.device.port,
                    baudrate=config.baudrate,
                    bytesize=config.data_bits,
                    parity=config.parity,
                    stopbits=config.stop_bits,
                    timeout=1
                )
                self._current_protocol = "UART"
                print(f"[Tigard] UART configured: {config.baudrate} baud")
                return True
            else:
                print("[Tigard] No serial port available for UART")
                return False
                
        except Exception as e:
            print(f"[Tigard] UART configuration failed: {e}")
            return False
    
    def uart_write(self, data: bytes):
        """Write data to UART."""
        if self._uart:
            self._uart.write(data)
    
    def uart_read(self, length: int, timeout_ms: int = 1000) -> bytes:
        """Read data from UART."""
        if not self._uart:
            return b''
        
        self._uart.timeout = timeout_ms / 1000.0
        return self._uart.read(length)
    
    # --------------------------------------------------------------------------
    # Helpers
    # --------------------------------------------------------------------------
    
    def _close_current_protocol(self):
        """Close current protocol controller before switching."""
        if self._spi:
            try:
                self._spi._controller.close()
            except Exception:
                pass
            self._spi = None
        
        if self._i2c:
            try:
                self._i2c.close()
            except Exception:
                pass
            self._i2c = None


class TigardDebugBackend(DebugBackend):
    """
    Tigard debug backend using OpenOCD for JTAG/SWD.

    This wraps OpenOCD subprocess calls since pyftdi doesn't support
    debug protocols directly.
    """

    # OpenOCD target configurations
    TARGET_CONFIGS = {
        "stm32f1": "target/stm32f1x.cfg",
        "stm32f4": "target/stm32f4x.cfg",
        "stm32l4": "target/stm32l4x.cfg",
        "nrf52": "target/nrf52.cfg",
        "esp32": "target/esp32.cfg",
        "rp2040": "target/rp2040.cfg",
        "lpc1768": "target/lpc1768.cfg",
        "samd21": "target/at91samdXX.cfg",
    }

    def __init__(self, device: DeviceInfo):
        super().__init__(device)
        self._openocd_proc = None
        self._telnet = None
        self._interface = "swd"  # "swd" or "jtag"
        self._target = "auto"
        self._openocd_port = 4444

    def connect(self) -> bool:
        """Start OpenOCD server for Tigard."""
        import subprocess
        import shutil
        import time

        # Check for OpenOCD
        if not shutil.which("openocd"):
            print("[Tigard] OpenOCD not found")
            print("  Install: brew install openocd")
            return False

        # Build OpenOCD command
        cmd = ["openocd"]

        # Tigard interface config
        if self._interface == "swd":
            cmd.extend(["-f", "interface/ftdi/tigard.cfg"])
            cmd.extend(["-c", "transport select swd"])
        else:
            cmd.extend(["-f", "interface/ftdi/tigard.cfg"])
            cmd.extend(["-c", "transport select jtag"])

        # Target config
        if self._target != "auto" and self._target in self.TARGET_CONFIGS:
            cmd.extend(["-f", self.TARGET_CONFIGS[self._target]])
        else:
            # Try auto-detect with a generic config
            cmd.extend(["-c", "adapter speed 1000"])

        print(f"[Tigard] Starting OpenOCD: {' '.join(cmd)}")

        try:
            self._openocd_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Wait for OpenOCD to start
            time.sleep(2)

            # Check if process is still running
            if self._openocd_proc.poll() is not None:
                stderr = self._openocd_proc.stderr.read()
                print(f"[Tigard] OpenOCD failed to start: {stderr[:200]}")
                return False

            # Connect via telnet
            if self._connect_telnet():
                self._connected = True
                print("[Tigard] OpenOCD connected")
                return True
            else:
                self._openocd_proc.terminate()
                return False

        except Exception as e:
            print(f"[Tigard] Failed to start OpenOCD: {e}")
            return False

    def _connect_telnet(self) -> bool:
        """Connect to OpenOCD telnet interface."""
        import socket

        try:
            self._telnet = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._telnet.settimeout(5)
            self._telnet.connect(("localhost", self._openocd_port))

            # Read initial prompt
            self._telnet.recv(1024)
            return True

        except Exception as e:
            print(f"[Tigard] Telnet connection failed: {e}")
            return False

    def _send_command(self, cmd: str) -> str:
        """Send command to OpenOCD and return response."""
        if not self._telnet:
            return ""

        try:
            self._telnet.sendall((cmd + "\n").encode())
            import time
            time.sleep(0.1)  # Wait for response

            response = b""
            self._telnet.settimeout(1)
            try:
                while True:
                    chunk = self._telnet.recv(4096)
                    if not chunk:
                        break
                    response += chunk
            except socket.timeout:
                pass

            return response.decode(errors="ignore").strip()

        except Exception as e:
            print(f"[Tigard] Command failed: {e}")
            return ""

    def disconnect(self):
        """Stop OpenOCD server."""
        if self._telnet:
            try:
                self._send_command("shutdown")
                self._telnet.close()
            except Exception:
                pass
            self._telnet = None

        if self._openocd_proc:
            try:
                self._openocd_proc.terminate()
                self._openocd_proc.wait(timeout=5)
            except Exception:
                self._openocd_proc.kill()
            self._openocd_proc = None

        self._connected = False

    def get_info(self) -> dict[str, Any]:
        return {
            "name": "Tigard Debug (OpenOCD)",
            "interface": self._interface,
            "target": self._target,
            "connected": self._connected,
        }

    def set_interface(self, interface: str) -> None:
        """Set debug interface: 'swd' or 'jtag'"""
        if interface.lower() in ("swd", "jtag"):
            self._interface = interface.lower()

    def set_target(self, target: str) -> None:
        """Set target configuration."""
        self._target = target.lower()

    def connect_target(self, target: str = "auto") -> bool:
        """Connect to target (called after OpenOCD is running)."""
        self._target = target
        response = self._send_command("targets")
        return "halted" in response.lower() or "running" in response.lower()

    def halt(self) -> bool:
        """Halt the target CPU."""
        response = self._send_command("halt")
        return "halted" in response.lower() or not response.startswith("Error")

    def resume(self) -> bool:
        """Resume target execution."""
        response = self._send_command("resume")
        return not response.startswith("Error")

    def reset(self, halt: bool = False) -> bool:
        """Reset the target."""
        cmd = "reset halt" if halt else "reset run"
        response = self._send_command(cmd)
        return not response.startswith("Error")

    def read_memory(self, address: int, size: int) -> bytes:
        """Read memory from target."""
        # Use mdw (memory display word) command
        words = (size + 3) // 4
        response = self._send_command(f"mdw 0x{address:08x} {words}")

        # Parse response: "0x20000000: 12345678 87654321 ..."
        data = bytearray()
        for line in response.splitlines():
            if ":" in line:
                parts = line.split(":")[1].strip().split()
                for word in parts:
                    try:
                        val = int(word, 16)
                        data.extend(val.to_bytes(4, "little"))
                    except ValueError:
                        pass

        return bytes(data[:size])

    def write_memory(self, address: int, data: bytes) -> bool:
        """Write memory to target."""
        # Use mww (memory write word) command
        for i in range(0, len(data), 4):
            chunk = data[i:i+4]
            if len(chunk) < 4:
                chunk = chunk + b'\x00' * (4 - len(chunk))
            val = int.from_bytes(chunk, "little")
            response = self._send_command(f"mww 0x{address + i:08x} 0x{val:08x}")
            if "Error" in response:
                return False
        return True

    def set_breakpoint(self, address: int) -> int:
        """Set a hardware breakpoint."""
        response = self._send_command(f"bp 0x{address:08x} 2 hw")
        # Returns breakpoint number on success
        if "breakpoint" in response.lower():
            return 1  # Simplified - real impl would parse BP number
        return 0

    def remove_breakpoint(self, bp_id: int) -> bool:
        """Remove a breakpoint."""
        response = self._send_command(f"rbp {bp_id}")
        return not response.startswith("Error")

    def read_registers(self) -> dict[str, int]:
        """Read CPU registers."""
        response = self._send_command("reg")

        regs = {}
        for line in response.splitlines():
            # Parse lines like "r0: 0x12345678"
            if ":" in line and "0x" in line:
                parts = line.split(":")
                if len(parts) >= 2:
                    name = parts[0].strip()
                    try:
                        val = int(parts[1].strip().split()[0], 16)
                        regs[name] = val
                    except (ValueError, IndexError):
                        pass

        return regs

    def dump_firmware(self, address: int, size: int) -> bytes:
        """Dump firmware from target."""
        print(f"[Tigard] Dumping {size} bytes from 0x{address:08x}...")

        # Use dump_image command for efficiency
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            temp_path = f.name

        response = self._send_command(f"dump_image {temp_path} 0x{address:08x} {size}")

        if os.path.exists(temp_path):
            with open(temp_path, "rb") as f:
                data = f.read()
            os.unlink(temp_path)
            print(f"[Tigard] Dumped {len(data)} bytes")
            return data

        # Fallback to read_memory
        print("[Tigard] dump_image failed, using read_memory (slower)...")
        return self.read_memory(address, size)

    def flash_firmware(self, address: int, data: bytes) -> bool:
        """Flash firmware to target."""
        import tempfile
        import os

        print(f"[Tigard] Flashing {len(data)} bytes to 0x{address:08x}...")

        # Write data to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(data)
            temp_path = f.name

        # Use flash write_image command
        response = self._send_command(f"flash write_image erase {temp_path} 0x{address:08x}")
        os.unlink(temp_path)

        if "Error" in response:
            print(f"[Tigard] Flash failed: {response[:100]}")
            return False

        print("[Tigard] Flash complete")
        return True


# Register backends
register_backend("tigard", TigardBackend)
