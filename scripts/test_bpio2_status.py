#!/usr/bin/env python3
"""
Test BPIO2 connection and status retrieval.

This is the most basic test - just connect and get device status.
If this works, BPIO2 is properly connected.

Usage:
    python scripts/test_bpio2_status.py [port]
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from hwh.pybpio import BPIOClient

# Default to common Bus Pirate BPIO port
PORT = sys.argv[1] if len(sys.argv) > 1 else '/dev/cu.usbmodem6buspirate3'


def main():
    print(f"BPIO2 Status Test")
    print(f"Port: {PORT}")
    print("=" * 60)

    try:
        print("\n[1] Creating BPIOClient...")
        client = BPIOClient(PORT, baudrate=3000000, timeout=2, debug=False)
        print("    ✓ Client created")

        print("\n[2] Requesting status...")
        status = client.status_request()

        if not status:
            print("    ✗ Failed to get status!")
            client.close()
            return 1

        print("    ✓ Status received!")

        print("\n" + "=" * 60)
        print("DEVICE STATUS")
        print("=" * 60)

        # Version info
        print(f"\nVersion Information:")
        print(f"  FlatBuffers: {status.get('version_flatbuffers_major', '?')}.{status.get('version_flatbuffers_minor', '?')}")
        print(f"  Hardware: {status.get('version_hardware_major', '?')} REV{status.get('version_hardware_minor', '?')}")
        print(f"  Firmware: {status.get('version_firmware_major', '?')}.{status.get('version_firmware_minor', '?')}")
        print(f"  Git Hash: {status.get('version_firmware_git_hash', 'N/A')}")
        print(f"  Build Date: {status.get('version_firmware_build_date', 'N/A')}")

        # Mode info
        print(f"\nMode Information:")
        print(f"  Current Mode: {status.get('mode_current', 'Unknown')}")
        print(f"  Available: {status.get('modes_available', [])}")
        print(f"  Bit Order: {status.get('mode_bit_order', 'N/A')}")
        print(f"  Pin Labels: {status.get('mode_pin_labels', 'N/A')}")

        # Protocol limits
        print(f"\nProtocol Limits:")
        print(f"  Max Packet: {status.get('max_packet', 'N/A')}")
        print(f"  Max Write: {status.get('max_write', 'N/A')}")
        print(f"  Max Read: {status.get('max_read', 'N/A')}")

        # PSU info
        print(f"\nPower Supply:")
        print(f"  PSU Enabled: {status.get('psu_enabled', False)}")
        print(f"  Set Voltage: {status.get('psu_set_mv', 0)} mV")
        print(f"  Set Current: {status.get('psu_set_ma', 0)} mA")
        print(f"  Measured V: {status.get('psu_measured_mv', 0)} mV")
        print(f"  Measured I: {status.get('psu_measured_ma', 0)} mA")
        print(f"  OC Error: {status.get('psu_error_overcurrent', False)}")
        print(f"  Pull-ups: {status.get('pullup_enabled', False)}")

        # ADC values
        adc = status.get('adc_mv', [])
        if adc:
            print(f"\nADC Values (mV):")
            for i, val in enumerate(adc):
                print(f"  IO{i}: {val} mV")

        # IO state
        print(f"\nIO Configuration:")
        print(f"  Directions: {status.get('io_direction', 'N/A')}")
        print(f"  Values: {status.get('io_value', 'N/A')}")

        # System info
        print(f"\nSystem:")
        print(f"  LEDs: {status.get('leds', 'N/A')}")
        print(f"  Disk Size: {status.get('disk_size', 0)} bytes")
        print(f"  Disk Used: {status.get('disk_used', 0)} bytes")

        print("\n" + "=" * 60)
        print("✓ BPIO2 CONNECTION SUCCESSFUL!")
        print("=" * 60)

        client.close()
        return 0

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
