"""
BPIO UART - UART protocol handler for Bus Pirate 5/6.

This class provides UART communication using the BPIO2 FlatBuffers protocol.
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
            parity: Enable parity (default: False for none)
            stop_bits: Number of stop bits (default: 1)
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
        Write data to UART.

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
        Read bytes from UART.

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

        Args:
            write_data: Data to write (bytes or list)
            read_bytes: Number of bytes to read after writing

        Returns:
            Data read or None if not configured
        """
        if not self.config_check():
            return None

        # Convert to list if bytes
        if isinstance(write_data, bytes):
            write_data = list(write_data)

        return self.client.data_request(
            data_write=write_data,
            bytes_read=read_bytes
        )
