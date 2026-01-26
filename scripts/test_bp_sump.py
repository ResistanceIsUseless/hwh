#!/usr/bin/env python3
"""
Test Bus Pirate SUMP (Logic Analyzer) mode.

This tests the SUMP protocol implementation for capturing logic signals
on Bus Pirate 5/6 devices.

IMPORTANT: Bus Pirate SUMP uses TWO serial ports:
- buspirate1 (CDC 0): Terminal/console - used to enter SUMP mode
- buspirate3 (CDC 1): Binary interface - used for SUMP protocol

Usage:
    python scripts/test_bp_sump.py

Requirements:
    - Bus Pirate 5/6 connected
    - pyserial installed
"""

import sys
import time
sys.path.insert(0, 'src')

import serial
import serial.tools.list_ports


def find_buspirate_ports() -> tuple[str | None, str | None]:
    """Find Bus Pirate console (buspirate1) and binary (buspirate3) ports"""
    console = None
    binary = None
    for port in serial.tools.list_ports.comports():
        if 'buspirate1' in port.device.lower():
            console = port.device
        elif 'buspirate3' in port.device.lower():
            binary = port.device
    return console, binary


def enter_sump_mode(console_port: str) -> bool:
    """Enter SUMP mode via terminal"""
    print(f"\n[1] Opening console port: {console_port}")
    ser = serial.Serial(console_port, 115200, timeout=2)
    time.sleep(0.2)
    ser.reset_input_buffer()

    # Wake up and check current state
    ser.write(b'\r\n')
    time.sleep(0.3)
    if ser.in_waiting > 0:
        response = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
        print(f"[*] Current state: {response.strip()[-30:]}")

    # First switch to HiZ mode to ensure clean state
    print("[2] Switching to HiZ mode...")
    ser.write(b'm 1\r\n')
    time.sleep(0.5)
    if ser.in_waiting > 0:
        response = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
        if 'HiZ' in response:
            print("[+] Now in HiZ mode")

    ser.reset_input_buffer()

    # Enter binmode menu
    print("[3] Entering binmode menu...")
    ser.write(b'binmode\r\n')
    time.sleep(0.5)

    if ser.in_waiting > 0:
        response = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
        if 'SUMP' in response:
            print("[+] Binmode menu displayed")

    # Select SUMP mode (option 1)
    print("[4] Selecting SUMP mode (option 1)...")
    ser.write(b'1\r\n')
    time.sleep(0.5)

    if ser.in_waiting > 0:
        response = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
        print(f"[*] Response: {response.strip()[:100]}")

        if 'Save setting' in response:
            # Answer 'y' to activate SUMP mode
            print("[5] Confirming SUMP mode activation...")
            ser.write(b'y\r\n')
            time.sleep(0.5)

            if ser.in_waiting > 0:
                response = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                print(f"[*] Final response: {response.strip()[:100]}")

    ser.close()
    time.sleep(0.5)
    return True


def test_sump_protocol(binary_port: str) -> bool:
    """Test SUMP protocol on binary interface"""
    print(f"\n[6] Opening binary port for SUMP: {binary_port}")

    from hwh.backends.sump import SUMPClient, SUMPConfig

    ser = serial.Serial(binary_port, 115200, timeout=2)
    time.sleep(0.2)

    client = SUMPClient(ser, debug=True)

    # Reset
    print("\n[7] Resetting SUMP device...")
    client.reset()

    # Identify
    print("\n[8] Requesting device ID...")
    success, device_id = client.identify()

    if not success:
        print(f"[!] SUMP not responding: {device_id}")
        print("    Make sure SUMP mode was activated on the console port")
        ser.close()
        return False

    print(f"[+] SUMP device ID: '{device_id}'")

    if device_id != '1ALS':
        print(f"[!] Unexpected ID - expected '1ALS', got '{device_id}'")
        print("    This may indicate the device is not in SUMP mode")

    # Get metadata
    print("\n[9] Requesting metadata...")
    metadata = client.get_metadata()
    if metadata:
        print(f"[+] Device metadata:")
        for key, value in metadata.items():
            if key == 'max_sample_rate':
                print(f"    {key}: {value/1e6:.1f} MHz")
            elif key == 'sample_memory':
                print(f"    {key}: {value/1024:.1f} KB")
            else:
                print(f"    {key}: {value}")
    else:
        print("[*] No metadata available")

    # Configure capture
    print("\n[10] Configuring capture...")
    config = SUMPConfig(
        sample_rate=1_000_000,   # 1 MHz
        sample_count=1024,       # 1K samples
        channels=8,
        base_clock=62_500_000,   # Bus Pirate 5/6 base clock
    )
    client.configure(config)
    print(f"[+] Configured: {config.sample_rate/1e6:.1f}MHz, {config.sample_count} samples")

    # Capture (immediate, no trigger)
    print("\n[11] Starting capture (2 second timeout)...")
    print("    Connect a signal to IO pins or it will capture ambient noise")

    capture = client.capture(timeout=2.0)

    ser.close()

    if capture:
        print(f"\n[+] Capture complete!")
        print(f"    Channels: {capture.channels}")
        print(f"    Sample rate: {capture.sample_rate/1e6:.1f}MHz")
        print(f"    Samples: {len(capture.samples[0]) if capture.samples else 0}")
        print(f"    Raw data: {len(capture.raw_data)} bytes")

        if capture.samples and len(capture.samples[0]) > 0:
            # Show first few samples per channel
            print("\n    First 20 samples per channel:")
            for ch in range(min(4, capture.channels)):
                samples = capture.samples[ch][:20]
                pattern = ''.join(['█' if s else '░' for s in samples])
                print(f"    CH{ch}: {pattern}")

            # Check for any activity
            print("\n    Channel activity:")
            for ch in range(capture.channels):
                samples = capture.samples[ch]
                ones = sum(samples)
                total = len(samples)
                if ones == 0:
                    print(f"    CH{ch}: LOW (always 0)")
                elif ones == total:
                    print(f"    CH{ch}: HIGH (always 1)")
                else:
                    pct = 100 * ones / total
                    print(f"    CH{ch}: ACTIVE ({pct:.1f}% high)")

        return True
    else:
        print("\n[!] Capture failed or timed out")
        return False


def exit_sump_mode(console_port: str):
    """Exit SUMP mode back to terminal"""
    print("\n[*] Exiting SUMP mode...")

    try:
        ser = serial.Serial(console_port, 115200, timeout=1)
        time.sleep(0.2)

        # Send escape and x to exit binmode
        ser.write(b'\x1b')  # ESC
        time.sleep(0.1)
        ser.write(b'x\r\n')  # Exit menu
        time.sleep(0.2)

        if ser.in_waiting > 0:
            response = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
            if '>' in response:
                print("[+] Exited to terminal")

        ser.close()
    except Exception as e:
        print(f"[*] Exit cleanup: {e}")


def test_sump_mode():
    """Main test function"""
    console_port, binary_port = find_buspirate_ports()

    if not console_port:
        print("[!] Bus Pirate console port not found (looking for 'buspirate1')")
        print("\nAvailable ports:")
        for port in serial.tools.list_ports.comports():
            print(f"    {port.device} - {port.description}")
        return False

    if not binary_port:
        print("[!] Bus Pirate binary port not found (looking for 'buspirate3')")
        print("\nAvailable ports:")
        for port in serial.tools.list_ports.comports():
            print(f"    {port.device} - {port.description}")
        return False

    print(f"[*] Found Bus Pirate:")
    print(f"    Console: {console_port}")
    print(f"    Binary:  {binary_port}")

    # Step 1: Enter SUMP mode via console
    if not enter_sump_mode(console_port):
        return False

    # Step 2: Test SUMP protocol on binary port
    success = test_sump_protocol(binary_port)

    # Step 3: Clean up
    exit_sump_mode(console_port)

    return success


if __name__ == '__main__':
    print("=" * 60)
    print("Bus Pirate SUMP (Logic Analyzer) Test")
    print("=" * 60)

    try:
        success = test_sump_mode()

        if success:
            print("\n" + "=" * 60)
            print("[+] SUMP test PASSED")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("[!] SUMP test FAILED")
            print("=" * 60)

    except KeyboardInterrupt:
        print("\n[*] Interrupted")
    except Exception as e:
        print(f"\n[!] Error: {e}")
        import traceback
        traceback.print_exc()
