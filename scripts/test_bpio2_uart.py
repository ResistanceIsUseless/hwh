#!/usr/bin/env python3
"""
Test script for BPIO2 UART mode.

Tests the UART implementation following the same pattern as BPIOSPI.
This will verify if UART mode switching works via the BPIO2 FlatBuffers protocol.

Usage:
    python test_bpio2_uart.py [port]

Example:
    python test_bpio2_uart.py /dev/cu.usbmodem6buspirate3
"""

import sys
import os

# Add the hwh package to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from hwh.pybpio import BPIOClient, BPIOUART

# Default to common Bus Pirate BPIO port
PORT = sys.argv[1] if len(sys.argv) > 1 else '/dev/cu.usbmodem6buspirate3'


def test_status():
    """Test status request to see available modes."""
    print("=" * 60)
    print("TEST 1: Status Request - Check available modes")
    print("=" * 60)

    client = BPIOClient(PORT, baudrate=3000000, timeout=2, debug=False)

    status = client.status_request()
    if not status:
        print("ERROR: Failed to get status")
        client.close()
        return None

    print(f"Firmware: {status['version_firmware_major']}.{status['version_firmware_minor']}")
    print(f"Git hash: {status['version_firmware_git_hash']}")
    print(f"Available modes: {status['modes_available']}")
    print(f"Current mode: {status['mode_current']}")

    if 'UART' in status['modes_available']:
        print("\n✓ UART is listed in available modes")
    else:
        print("\n✗ UART is NOT in available modes")

    client.close()
    return status


def test_mode_switching():
    """Test switching to different modes."""
    print("\n" + "=" * 60)
    print("TEST 2: Mode Switching Test")
    print("=" * 60)

    client = BPIOClient(PORT, baudrate=3000000, timeout=2, debug=False)

    results = {}

    # Test each mode
    modes_to_test = ['HiZ', 'SPI', 'I2C', 'UART', '1WIRE']

    for mode in modes_to_test:
        print(f"\nTrying to switch to {mode} mode...")
        success = client.configuration_request(
            mode=mode,
            mode_configuration={'speed': 100000}
        )

        if success:
            # Verify by checking status
            status = client.status_request()
            current = status['mode_current'] if status else 'UNKNOWN'
            results[mode] = (True, current)
            print(f"  ✓ {mode}: SUCCESS (current mode: {current})")
        else:
            results[mode] = (False, None)
            print(f"  ✗ {mode}: FAILED")

    client.close()
    return results


def test_uart_via_bpiouart():
    """Test UART mode using the BPIOUART wrapper class."""
    print("\n" + "=" * 60)
    print("TEST 3: UART via BPIOUART Class")
    print("=" * 60)

    client = BPIOClient(PORT, baudrate=3000000, timeout=2, debug=False)

    uart = BPIOUART(client)

    print("\nConfiguring UART: 115200 baud, 8N1...")
    success = uart.configure(
        speed=115200,
        data_bits=8,
        parity=False,
        stop_bits=1,
        flow_control=False,
        signal_inversion=False
    )

    if success:
        print("  ✓ UART configured successfully!")

        # Verify mode
        status = client.status_request()
        print(f"  Current mode: {status['mode_current']}")
        print(f"  Pin labels: {status['mode_pin_labels']}")

        # Try sending some test data (will go out TX pin)
        print("\n  Sending test data 'Hello UART!'...")
        result = uart.send_string("Hello UART!\r\n")
        if result is not False:
            print("  ✓ Data sent successfully")
        else:
            print("  ✗ Failed to send data")

        # Try reading (may timeout if nothing connected to RX)
        print("\n  Attempting to read (may timeout)...")
        data = uart.read(10)
        if data:
            print(f"  ✓ Received: {data}")
        else:
            print("  - No data received (expected if nothing connected to RX)")

    else:
        print("  ✗ UART configuration FAILED!")
        print("  This means the firmware doesn't support UART mode via BPIO2")

    client.close()
    return success


def test_uart_with_psu():
    """Test UART with PSU enabled (required for TX/RX to work)."""
    print("\n" + "=" * 60)
    print("TEST 4: UART with PSU Enabled")
    print("=" * 60)

    client = BPIOClient(PORT, baudrate=3000000, timeout=2, debug=False)

    uart = BPIOUART(client)

    print("\nConfiguring UART with PSU @ 3.3V...")
    success = uart.configure(
        speed=115200,
        data_bits=8,
        parity=False,
        stop_bits=1,
        psu_enable=True,
        psu_set_mv=3300
    )

    if success:
        print("  ✓ UART configured with PSU!")

        # Check PSU status
        status = client.status_request()
        print(f"  PSU enabled: {status['psu_enabled']}")
        print(f"  PSU voltage: {status['psu_measured_mv']} mV")
        print(f"  Current mode: {status['mode_current']}")
    else:
        print("  ✗ Configuration FAILED!")

    # Clean up - disable PSU
    client.configuration_request(psu_disable=True)
    client.close()
    return success


def main():
    print(f"BPIO2 UART Test Script")
    print(f"Port: {PORT}")
    print()

    # Run tests
    status = test_status()
    if not status:
        print("\nERROR: Could not connect to Bus Pirate")
        return 1

    results = test_mode_switching()

    uart_works = test_uart_via_bpiouart()

    if uart_works:
        test_uart_with_psu()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print("\nMode switching results:")
    for mode, (success, current) in results.items():
        status = "✓ WORKS" if success else "✗ FAILS"
        print(f"  {mode}: {status}")

    if uart_works:
        print("\n✓ UART mode via BPIO2 WORKS!")
        print("  The BPIOUART class can be used for UART communication.")
    else:
        print("\n✗ UART mode via BPIO2 DOES NOT WORK")
        print("  The firmware returns 'Invalid mode name' for UART.")
        print("  Workaround: Use terminal commands via buspirate1 port.")

    return 0 if uart_works else 1


if __name__ == '__main__':
    sys.exit(main())
