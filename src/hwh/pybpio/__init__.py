"""
pybpio - Official Bus Pirate 5/6 BPIO2 FlatBuffers Protocol Library

Bundled from: https://github.com/DangerousPrototypes/BusPirate-BPIO2-flatbuffer-interface
License: Apache 2.0

This library provides Python bindings for the BPIO2 binary protocol used by
Bus Pirate 5 and 6 devices. It uses FlatBuffers for message serialization
and COBS encoding for packet framing.

Usage:
    from hwh.pybpio import BPIOClient, BPIOSPI, BPIOI2C

    # Connect to Bus Pirate on the BPIO2 port (usually buspirate3)
    client = BPIOClient('/dev/cu.usbmodem_buspirate3', baudrate=3000000)

    # Get device status
    status = client.status_request()
    print(f"Firmware: {status['version_firmware_major']}.{status['version_firmware_minor']}")

    # Configure SPI
    spi = BPIOSPI(client)
    spi.configure(speed=1000000, clock_polarity=False, clock_phase=False)

    # Read SPI flash JEDEC ID
    data = spi.transfer([0x9F], read_bytes=3)
    print(f"Flash ID: {data.hex()}")

    client.close()
"""

from .bpio_client import BPIOClient
from .bpio_base import BPIOBase
from .bpio_spi import BPIOSPI
from .bpio_i2c import BPIOI2C
from .bpio_uart import BPIOUART
from .bpio_1wire import BPIO1Wire

__all__ = [
    'BPIOClient',
    'BPIOBase',
    'BPIOSPI',
    'BPIOI2C',
    'BPIOUART',
    'BPIO1Wire',
]

__version__ = '2.0.0'
__author__ = 'DangerousPrototypes'
__license__ = 'Apache-2.0'
