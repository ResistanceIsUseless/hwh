# Missing Features by Device

Comprehensive analysis of missing features for all supported hardware devices based on their documented capabilities versus current implementation status.

---

## Bus Pirate 5/6 (75% Complete)

### Hardware Capabilities (from spec)
- SPI, I2C, UART, 1-Wire bus protocols
- JTAG/SWD pin scanning
- Logic analyzer (SUMP protocol)
- Power supply (0-5V, 400mA)
- Pull-up resistors (2.2kΩ, 10kΩ)
- ADC voltage measurement
- PWM generation
- Frequency counter
- LED indicators

### Currently Implemented ✅
- SPI: Configure, transfer, read flash ID/data
- I2C: Configure, scan, read/write
- UART: Configure, bridge mode, auto-detect, glitch attack
- PSU: Enable/disable, voltage/current control
- Pull-ups: Enable/disable
- Status queries: Full BPIO2 device info
- Logic analyzer: SUMP capture
- ADC: Live voltage display on pinout diagrams

### Missing Features ❌

**SPI Flash Operations:**
- SPI flash write (page program 0x02)
- SPI flash erase (sector 0x20, block 0xD8, chip 0xC7)
- Flash verification
- Flash chip database integration (JEDEC ID → parameters)
- Write protection control (WRSR, RDSR)
- Quad SPI mode (if supported by firmware)

**JTAG/SWD Scanning:**
- JTAG pin detection (scan GPIO combinations)
- JTAG ID code readback
- SWD pin detection
- SWD DPIDR readback
- Boundary scan testing

**PWM & Frequency:**
- PWM configuration (frequency, duty cycle)
- PWM start/stop
- Frequency counter measurement
- Servo control mode

**Advanced IO:**
- Individual GPIO read/write (beyond protocol modes)
- GPIO interrupts
- Bitbang mode
- LED control (RGB, heartbeat patterns)

**Logic Analyzer Enhancements:**
- Export to PulseView format (.sr)
- Protocol decoders (SPI/I2C/UART/JTAG/SWD)
- Trigger conditions (pattern, edge, serial data)
- Continuous capture mode

**1-Wire Protocol:**
- 1-Wire search ROM
- 1-Wire temperature sensor read (DS18B20)
- 1-Wire EEPROM operations (DS2431)

**UART Enhancements:**
- Hardware flow control (RTS/CTS)
- Break signal
- Parity error detection
- Framing error detection
- 9-bit mode support

**Power Analysis:**
- Current measurement logging
- Power trace capture
- Overcurrent event logging

---

## Curious Bolt (60% Complete)

### Hardware Capabilities (from docs)
- Voltage glitching (crowbar, MOSFET-based)
- Logic analyzer (8 channels, 31.25 MHz, 100KB buffer)
- Power analysis / DPA (ADC for current traces)
- GPIO control
- External trigger input
- Programmable delay/width (8.3ns resolution)

### Currently Implemented ✅
- Glitch configuration (width, offset in nanoseconds → clock cycles)
- Arm/disarm/trigger
- Glitch sweep (parameter space search)
- Native `scope` library integration
- Logic analyzer via SUMP protocol
- External trigger configuration

### Missing Features ❌

**Glitch Enhancements:**
- Serial protocol fallback (native library not always available)
- Multi-glitch sequences (burst mode)
- Voltage level control (if hardware supports)
- Glitch success detection automation
- Parameter optimization via ML/genetic algorithms
- Glitch campaign save/restore

**Power Analysis:**
- ADC current trace capture
- DPA (Differential Power Analysis) engine
- CPA (Correlation Power Analysis) engine
- Trace alignment algorithms
- Statistical analysis tools
- AES key recovery workflows

**GPIO Control:**
- GPIO input/output configuration
- GPIO state monitoring
- External condition detection (for triggering)

**Logic Analyzer Enhancements:**
- Glitch + LA synchronized capture
- Trigger position marker
- Export to standard formats (.vcd, .sr)
- Protocol decoders

**Advanced Triggering:**
- Pattern-based triggers (LA → glitch)
- Power threshold triggers (DPA → glitch)
- Serial data pattern triggers
- Multi-condition AND/OR logic

---

## Tigard (45% Complete)

### Hardware Capabilities (from docs)
- SPI (via FT2232H Channel A)
- I2C (via FT2232H Channel A)
- UART (via FT2232H Channel A)
- JTAG (via OpenOCD)
- SWD (via OpenOCD)
- Level shifting (1.8V - 5V)

### Currently Implemented ✅
- SPI: Configure via pyftdi, transfer, read flash ID
- I2C: Configure via pyftdi, scan, read/write
- UART: Basic configuration
- Protocol switching

### Missing Features ❌

**SPI Flash Operations:**
- Flash write operations
- Flash erase operations
- Flash verification

**JTAG Debug (all missing):**
- OpenOCD subprocess integration
- TAP state machine control
- IDCODE scanning
- Boundary scan
- Memory read/write via JTAG
- Flash programming via JTAG

**SWD Debug (all missing):**
- OpenOCD subprocess integration
- DPIDR/IDR readback
- Memory read/write via SWD
- Breakpoint management
- Target halt/resume/reset
- Flash programming via SWD
- CoreSight debug register access

**Level Shifting:**
- VTARGET voltage detection
- VREF configuration
- Level shifter enable/disable control

**Advanced Features:**
- Simultaneous UART + JTAG (independent channels)
- Logic analyzer mode (if FTDI supports)

---

## ST-Link (90% Complete)

### Hardware Capabilities (from docs)
- SWD debugging (ARM CoreSight)
- JTAG debugging
- Target power detection
- GDB server (via OpenOCD)
- STM32 flash programming
- SWO trace (if V3)

### Currently Implemented ✅
- SWD: Connect, target detection
- Execution: Halt, resume, reset, step
- Memory: Read/write bytes + 32-bit words
- Registers: Read all (r0-r15, XPSR), write individual
- Breakpoints: Set/remove
- Flash: Program, erase, verify
- Firmware dump: Chunked read with progress

### Missing Features ❌

**JTAG Mode:**
- JTAG TAP detection
- JTAG chain scanning
- Non-ARM targets via JTAG

**SWO Trace (ST-Link V3):**
- SWO capture configuration
- ITM stimulus port decoding
- DWT watchpoint trace
- ETM instruction trace (if supported)

**Advanced Debug:**
- Vector table modification
- Option bytes programming (RDP, etc.)
- Access to System Memory (bootloader)
- RTT (Real-Time Transfer) support

**Target Power:**
- Target power control (if supported by variant)
- VTARGET voltage measurement

---

## Black Magic Probe (85% Complete)

### Hardware Capabilities (from docs)
- SWD debugging (native GDB server)
- JTAG debugging (native GDB server)
- Target power control
- UART passthrough
- SWO trace
- Multi-target support

### Currently Implemented ✅
- GDB MI integration via pygdbmi
- Serial fallback (when GDB unavailable)
- SWD/JTAG target scanning
- Target power control
- Execution: Halt, resume, reset, step
- Memory: Read/write
- Registers: Read/write with mapping
- Breakpoints: Set/remove
- Flash programming
- Firmware dump
- UART passthrough

### Missing Features ❌

**SWO Trace:**
- SWO capture via `monitor traceswo`
- ITM decoding
- Real-time trace display

**Multi-Target:**
- Simultaneous connection to multiple targets
- Target switching

**Advanced Debug:**
- RTT support (SEGGER extension)
- Custom monitor commands
- Exception handling configuration

**UART Enhancements:**
- UART baud rate auto-detection
- Hardware flow control on UART port

---

## FaultyCat (0% - Not Implemented)

### Hardware Capabilities (from docs)
- EMFI (Electromagnetic Fault Injection)
- Pulse width control
- Pulse power control
- Pin detection mode (SWD/JTAG scanning)
- Arduino Micro based

### Missing Everything ❌

**Core Glitching:**
- Serial protocol implementation
- Pulse configuration (duration, power)
- Arm/disarm/trigger
- Safety interlock status

**Pin Detection:**
- SWD pin detection
- JTAG pin detection
- GPIO scanning modes

**Advanced Features:**
- Pulse sequencing
- External trigger input
- Glitch success detection
- Automated parameter sweep

**Implementation Notes:**
- Requires reverse-engineering Arduino serial protocol
- May have custom firmware commands
- Check FaultyCat GitHub for protocol docs

---

## TI-Link/MSP-FET (0% - Not Implemented)

### Hardware Capabilities (from docs)
- JTAG debugging (MSP430/MSP432)
- Spy-Bi-Wire (2-wire JTAG)
- SWD debugging (MSP432 only)
- BSL UART (bootstrap loader)
- EnergyTrace++ (power profiling)
- Flash programming
- FRAM programming

### Missing Everything ❌

**Core Debug (via mspdebug):**
- mspdebug subprocess wrapper
- Target connection
- Memory read/write
- Flash programming
- FRAM programming
- Register access
- Breakpoints

**Spy-Bi-Wire:**
- 2-wire JTAG protocol
- Low-power debugging

**BSL UART:**
- Bootstrap loader communication
- Password unlock
- Mass erase
- Firmware upload

**EnergyTrace++:**
- Current measurement capture
- Power profiling
- Energy optimization analysis

**Implementation Notes:**
- Requires mspdebug installed
- May need TI's proprietary libmsp430.so/dylib
- Different drivers: tilib (proprietary), rf2500, ezfet, etc.

---

## Common UART Adapters (0% - Not Implemented)

### Devices
- CH340 (VID 0x1A86, PID 0x7523)
- CP2102 (VID 0x10C4, PID 0xEA60)
- PL2303 (VID 0x067B, PID 0x2303)

### Missing Everything ❌

**Basic UART:**
- Serial port configuration
- Baud rate selection
- Data bits, parity, stop bits
- Flow control

**Monitoring:**
- RX/TX data logging
- Hex/ASCII display
- Timestamp overlay
- Traffic statistics

**Implementation Notes:**
- Could use generic UART backend
- Useful as trigger sources for glitching
- Simple pyserial wrapper

---

## Shared Infrastructure Missing

### Protocol Decoders (for Logic Analyzer)
- **SPI Decoder:** CS edge, MOSI/MISO sampling, mode detection
- **I2C Decoder:** Start/stop conditions, address, ACK/NAK, data bytes
- **UART Decoder:** Baud rate estimation, frame extraction, parity check
- **JTAG Decoder:** TMS state machine, IR/DR shifts, IDCODE extraction
- **SWD Decoder:** Packet parsing, ACK detection, parity validation
- **1-Wire Decoder:** Reset pulse, presence, ROM commands, data

### Flash Chip Database
- **JEDEC ID Database:** Manufacturer, chip family, capacity
- **Command Sets:** Standard vs vendor-specific commands
- **Timing Parameters:** Page write time, sector erase time, chip erase time
- **Protection:** Block protection, write protection, OTP regions
- **Source:** Port flashrom's flashchips.c database

### Binary File Parsers
- **ELF Parser:** Load address, sections, symbols
- **Intel HEX Parser:** Segment parsing, checksum validation
- **S-Record Parser:** S19/S28/S37 formats
- **Binary Loader:** Auto-detect format, extract loadable sections

### Glitch Profile Database
- **STM32 RDP Bypass:** Known parameters for F0/F1/F4/L0/L1/L4 families
- **nRF52 APPROTECT Bypass:** Successful attack parameters
- **ESP32 Secure Boot:** Glitch timings for bootloader
- **LPC ReadProtect:** Attack profiles
- **Profile Sharing:** JSON import/export, community database

### Firmware Analysis Enhancements
- **Entropy Analysis:** Detect encrypted/compressed regions
- **String Extraction:** Improved regex patterns, Unicode support
- **Symbol Analysis:** Function detection, library identification
- **Vulnerability DB:** CVE matching, known backdoors
- **Diffing:** Compare two firmware versions

---

## Priority Recommendations

### High Priority (Maximum Impact)
1. **Bus Pirate SPI Flash Operations** - Very common use case
2. **Bolt Power Analysis** - Unique capability, high value
3. **FaultyCat Backend** - EMFI is unique, no other device provides it
4. **Protocol Decoders** - Benefits all logic analyzer features
5. **Flash Chip Database** - Benefits all SPI flash operations

### Medium Priority (Good Value)
6. **Tigard JTAG/SWD via OpenOCD** - Completes the device
7. **Bus Pirate JTAG/SWD Scanning** - Useful for reconnaissance
8. **TI-Link Backend** - For MSP430/MSP432 developers
9. **Glitch Profile Database** - Makes attacks more accessible
10. **Binary File Parsers** - Quality of life improvement

### Low Priority (Nice to Have)
11. **Bus Pirate PWM/Frequency** - Niche features
12. **Black Magic SWO Trace** - Advanced debugging
13. **ST-Link SWO Trace** - Advanced debugging
14. **UART Adapter Backends** - Limited functionality
15. **Firmware Analysis Enhancements** - Incremental improvements
