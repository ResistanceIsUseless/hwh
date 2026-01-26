"""
BPIO UART - UART protocol handler for Bus Pirate 5/6.

This class provides UART communication using the BPIO2 FlatBuffers protocol,
following the same pattern as BPIOSPI and BPIOI2C.

UART VIA BPIO2 NOT IMPLEMENTED (confirmed 2025-01):
    UART is listed in modes_available but the firmware does not have
    BPIO handler functions for UART mode. Only HW1WIRE, HWI2C, and HWSPI
    have BPIO handlers implemented in bpio_transactions.c.

    The firmware code in bpio.c:102-104 returns an error when trying
    to switch to a mode without a BPIO handler:
        if(bpio_mode_handlers[i].bpio_handler==NULL) return true; // error

    This is not a bug - UART BPIO support simply hasn't been written yet.
    See: https://github.com/DangerousPrototypes/BusPirate5-firmware/blob/main/src/binmode/bpio.c

    Workaround: Use terminal commands via buspirate1 (console) port.
    See backend_buspirate.py for the fallback implementation.

UART configuration parameters (from bpio.fbs schema):
- speed: Baud rate in Hz (default: 115200)
- data_bits: Data bits for UART (default: 8)
- parity: Parity setting (False=None, True=Even)
- stop_bits: Stop bits (1 or 2, default: 1)
- flow_control: Hardware flow control (default: False)
- signal_inversion: Invert TX/RX signals (default: False)
"""
from .bpio_base import BPIOBase


class BPIOUART(BPIOBase):
    def __init__(self, client):
        super().__init__(client)

    def configure(
        self,
        speed: int = 115200,
        data_bits: int = 8,
        parity: bool = False,
        stop_bits: int = 1,
        flow_control: bool = False,
        signal_inversion: bool = False,
        **kwargs
    ):
        """
        Configure UART mode.

        Args:
            speed: Baud rate in Hz (default: 115200)
            data_bits: Number of data bits (default: 8)
            parity: Enable parity - False=None, True=Even (default: False)
            stop_bits: Number of stop bits - 1 or 2 (default: 1)
            flow_control: Enable hardware flow control (default: False)
            signal_inversion: Invert TX/RX signals (default: False)
            **kwargs: Additional arguments passed to configuration_request

        Returns:
            True if configuration was successful
        """
        kwargs['mode'] = 'UART'

        # Get existing mode_configuration or create new one
        mode_configuration = kwargs.get('mode_configuration', {})

        # Set UART configuration parameters
        mode_configuration['speed'] = speed
        mode_configuration['data_bits'] = data_bits
        mode_configuration['parity'] = parity
        mode_configuration['stop_bits'] = stop_bits
        mode_configuration['flow_control'] = flow_control
        mode_configuration['signal_inversion'] = signal_inversion

        kwargs['mode_configuration'] = mode_configuration

        success = self.client.configuration_request(**kwargs)
        self.configured = success
        return success

    def write(self, data):
        """
        Write data to UART TX.

        For UART, we don't use start/stop conditions like SPI.
        Data is simply written out the TX pin.

        Args:
            data: Bytes or list of bytes to write

        Returns:
            Result from data_request or None if not configured
        """
        if not self.config_check():
            return None

        # Convert to list if bytes
        if isinstance(data, bytes):
            data = list(data)

        return self.client.data_request(
            data_write=data
        )

    def read(self, num_bytes: int):
        """
        Read bytes from UART RX.

        Args:
            num_bytes: Number of bytes to read

        Returns:
            Bytes read or None if not configured
        """
        if not self.config_check():
            return None

        return self.client.data_request(
            bytes_read=num_bytes
        )

    def transfer(self, write_data=None, read_bytes: int = 0):
        """
        Perform a UART transfer (write then read).

        This writes data to TX and then reads from RX.
        Unlike SPI, UART is asynchronous so the read may not
        be directly related to the write.

        Args:
            write_data: Data to write (bytes or list), or None
            read_bytes: Number of bytes to read after writing

        Returns:
            Data read or None if not configured
        """
        if not self.config_check():
            return None

        # Convert to list if bytes
        if write_data is not None and isinstance(write_data, bytes):
            write_data = list(write_data)

        return self.client.data_request(
            data_write=write_data,
            bytes_read=read_bytes
        )

    def send_string(self, text: str, encoding: str = 'utf-8'):
        """
        Send a string over UART.

        Convenience method for sending text data.

        Args:
            text: String to send
            encoding: Text encoding (default: utf-8)

        Returns:
            Result from data_request or None if not configured
        """
        return self.write(text.encode(encoding))

    def read_until(self, terminator: bytes = b'\n', max_bytes: int = 256):
        """
        Read bytes until a terminator is found.

        Note: This is a polling approach - reads bytes one at a time
        until terminator is found or max_bytes reached.

        Args:
            terminator: Byte sequence to stop at (default: newline)
            max_bytes: Maximum bytes to read (default: 256)

        Returns:
            Bytes read including terminator, or None if not configured
        """
        if not self.config_check():
            return None

        result = bytearray()
        for _ in range(max_bytes):
            byte = self.read(1)
            if byte is None or len(byte) == 0:
                break
            result.extend(byte)
            if result.endswith(terminator):
                break

        return bytes(result) if result else None
