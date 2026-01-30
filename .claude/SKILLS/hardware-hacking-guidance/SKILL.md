---
name: hardware-hacking-guidance
description: Comprehensive reference for embedded security assessment including memory extraction, debug interfaces (JTAG/SWD/UART), fault injection, side-channel analysis, bootloader vulnerabilities, and hardware attack countermeasures.
---

# Hardware Hacking and Embedded Security: A Technical Reference

Hardware security has become the critical frontier in modern cybersecurity, where software protections ultimately rest on silicon foundations that can be probed, glitched, and compromised. This reference provides security professionals with practical methodologies for assessing embedded systems—from basic firmware extraction to advanced fault injection—along with the countermeasures that make devices resilient against physical attack. The techniques documented here apply across IoT devices, hardware wallets, automotive systems, and any embedded target where attackers have physical access.

---

## Chapter 1: Introduction to Embedded Security

Embedded systems present a fundamentally different threat model than traditional IT infrastructure. Physical access changes everything—attackers can probe circuits, measure power consumption, inject faults, and extract firmware directly from memory chips. The attack surface includes debug interfaces left enabled, unencrypted storage, weak boot verification, and side-channel leakage from cryptographic operations.

### Threat Model Considerations

| Access Level | Capabilities | Example Attacks |
|--------------|--------------|-----------------|
| Remote | Network protocols, wireless interfaces | Firmware update exploitation, buffer overflows |
| Local | USB, serial ports, external storage | DFU attacks, malicious peripherals |
| Physical | PCB access, component manipulation | JTAG/UART access, chip-off extraction |
| Invasive | Decapping, microprobing | FIB modification, laser fault injection |

Security assessments must consider the realistic attacker profile. Consumer IoT faces opportunistic attackers with basic tools ($100-500 budget). Payment terminals and automotive systems face motivated attackers with moderate resources ($5,000-50,000). High-value targets like hardware security modules face nation-state capabilities with effectively unlimited budgets.

### Core Assessment Methodology

1. **Reconnaissance**: Identify components, locate debug interfaces, gather datasheets
2. **Firmware Acquisition**: Extract code via debug interfaces, flash dumps, or update mechanisms
3. **Static Analysis**: Reverse engineer binaries, identify vulnerabilities
4. **Dynamic Analysis**: Debug runtime behavior, fuzz interfaces
5. **Hardware Attacks**: Fault injection, side-channel analysis if warranted

---

## Chapter 2: Hardware Peripheral Interfaces

### UART (Universal Asynchronous Receiver/Transmitter)

UART provides asynchronous serial communication without a clock signal. The protocol relies on pre-agreed timing parameters—most commonly 115200 baud, 8 data bits, no parity, 1 stop bit (8N1).

**Pin Identification:**
- **TX (Transmit)**: Voltage fluctuates during boot as debug messages output
- **RX (Receive)**: Stable at logic high (3.3V or 5V) when idle
- **GND**: Continuity to chassis/shield ground
- **VCC**: Optional, stable 3.3V or 5V

**Discovery Tools:**
- Multimeter for voltage levels and continuity
- Logic analyzer for signal capture (Saleae Logic, DSLogic)
- **JTAGulator** automates UART discovery with `U` command

**Connection Workflow:**
```bash
# Identify USB-serial adapter device
dmesg | grep tty

# Connect with screen (common baud rates: 9600, 38400, 57600, 115200)
screen /dev/ttyUSB0 115200

# Or use minicom with hardware flow control disabled
minicom -D /dev/ttyUSB0 -b 115200
```

**Security Implications:**
UART consoles frequently expose root shells without authentication. Even when login prompts appear, default credentials or bootloader interrupts often bypass protection.

### SPI (Serial Peripheral Interface)

SPI uses four signals for synchronous, full-duplex communication:
- **SCLK**: Clock signal from master
- **MOSI**: Master Out, Slave In (data to device)
- **MISO**: Master In, Slave Out (data from device)
- **CS/SS**: Chip Select (active low)

Flash memory (W25Qxx, MX25L, GD25Q series) dominates SPI targets. Standard commands include:
- `0x9F`: Read JEDEC ID
- `0x03`: Read data
- `0x06`: Write enable
- `0x02`: Page program

### I2C (Inter-Integrated Circuit)

Two-wire protocol using SDA (data) and SCL (clock) with 7-bit addressing. Common targets include EEPROMs (24Cxx series at 0x50-0x57), sensors, and configuration chips.

```bash
# Scan I2C bus for devices
i2cdetect -y 1

# Read EEPROM contents
i2cdump -y 1 0x50
```

---

## Chapter 3: Identifying Components and Gathering Information

### Visual Reconnaissance

Systematic board inspection reveals attack surfaces before any tools connect:

1. **Main Processor**: Largest BGA/QFP package, often with manufacturer logo
2. **Memory**: 
   - Flash (8-pin SOIC/WSON): Winbond, Macronix, GigaDevice markings
   - DRAM (BGA): Samsung, Micron, SK Hynix
   - EEPROM (8-pin SOIC): Atmel, Microchip 24Cxx series
3. **Debug Headers**: Unpopulated 2.54mm headers, test point clusters
4. **Voltage Regulators**: Identify operating voltages (1.8V, 3.3V, 5V rails)

### Datasheet Research

Component markings yield part numbers for datasheet retrieval:
- **Manufacturer websites**: Primary source
- **Octopart.com**: Aggregates distributor datasheets
- **Alldatasheet.com**: Legacy and obscure parts

Critical datasheet sections:
- Pinout diagrams and package drawings
- Memory map and register definitions
- Debug interface specifications
- Boot mode configuration

### JTAG/SWD Discovery

**Physical Indicators:**
- 10-pin (ARM Cortex standard) or 20-pin (legacy ARM) headers
- 2x5 or 2x10 0.1" pitch headers near processor
- Test points labeled TCK, TMS, TDI, TDO, SWDIO, SWCLK

**JTAGulator Workflow:**
```
# Set target voltage first (measure before connecting!)
V -> Enter voltage (e.g., 3.3)

# IDCODE scan discovers TCK, TMS, TDO
I -> Scan for JTAG IDCODE

# BYPASS scan finds TDI
B -> BYPASS scan (slower, more thorough)

# SWD scan for ARM Cortex devices
S -> SWD scan
```

**IDCODE Interpretation:**
The 32-bit IDCODE identifies the device manufacturer and part:
- Bits 0: Always '1'
- Bits 11:1: Manufacturer ID (JEDEC standard)
- Bits 27:12: Part number
- Bits 31:28: Version

---

## Chapter 4: Introduction to Fault Injection

Fault injection deliberately induces hardware malfunctions to corrupt security-critical operations. When a processor experiences voltage droop, clock disruption, or electromagnetic interference during a security check, it may skip instructions, corrupt comparisons, or execute unintended code paths.

### Attack Categories

**Voltage Glitching:**
Briefly pulling VCC low causes setup/hold time violations in CMOS logic. A crowbar circuit using a fast MOSFET (IRLML6344) shorts the power rail through a low-value resistor for 10-100ns.

**Clock Glitching:**
Manipulating the clock signal creates similar effects:
- **Extra edges**: Double-clocking causes instruction skip
- **Missing edges**: CPU stalls, pipeline corruption
- **Frequency manipulation**: Timing violations in synchronous logic

**Electromagnetic Fault Injection (EMFI):**
Rapidly changing magnetic fields induce localized currents in chip metal layers. A coil driven by high-voltage pulses (200-500V) creates targeted bit flips without physical contact.

### Why Fault Injection Works

Security checks reduce to conditional branches in machine code:
```arm
; Simplified signature verification
LDR R0, [signature_valid]  ; Load verification result
CMP R0, #1                  ; Compare to expected value
BNE boot_failure            ; Branch if not equal
; ... continue secure boot ...
```

Glitching during `CMP` or `BNE` can:
- Corrupt the comparison, making invalid signatures appear valid
- Skip the branch entirely, continuing execution regardless of result
- Corrupt the loaded value before comparison

### Target Identification

Power trace analysis reveals vulnerable operations:
1. Capture power consumption during target operation
2. Identify distinctive patterns (crypto operations, memory access, comparisons)
3. Use pattern timing to trigger glitches at precise offsets

---

## Chapter 5: How to Inject Faults

### Voltage Glitch Hardware

**Budget Setup (~$50-100):**
- Raspberry Pi Pico or similar microcontroller for timing
- IRLML6344 N-channel MOSFET (fast switching, low Rds)
- 10-50Ω shunt resistor to limit current
- Decoupling capacitor removal from target

**Professional Setup:**
- **ChipWhisperer-Lite** ($250-300): Integrated glitcher with FPGA timing
- **ChipWhisperer-Husky** ($549): Enhanced capabilities, built-in logic analyzer
- **GIAnT** (Riscure): Commercial-grade with automated parameter search

### Glitch Parameter Space

| Parameter | Description | Typical Range |
|-----------|-------------|---------------|
| Width | Glitch duration | 10ns - 1μs |
| Offset | Delay from trigger | 0 - millions of cycles |
| Repeat | Consecutive pulses | 1 - 100+ |
| Voltage | Depth of glitch | Target VCC - 50% to 90% |

Success requires sweeping this parameter space systematically. Each combination may produce:
- **No effect**: Glitch too weak or mistimed
- **Reset/crash**: Glitch too strong
- **Success**: Security bypass achieved
- **Partial effect**: Useful for narrowing parameters

### EMFI Implementation

**PicoEMP** (~$50-133): Open-source EM injector using HV pulse generator
- 1-4 second recharge between pulses
- Requires XY positioning stage for targeting
- Probe tip size determines spatial resolution

**ChipSHOUTER** ($3,500+): Professional EMFI platform
- Faster pulse rates, more energy
- Integrated positioning and automation

### Practical Considerations

1. **Remove decoupling capacitors** near target VCC for sharper glitches
2. **Short cables** minimize propagation delay and ringing
3. **Stable trigger source** essential—FPGA-based triggers recommended
4. **Automate parameter sweeps** using Python scripting
5. **Document successful parameters** for reproducibility

---

## Chapter 6: Fault Injection Lab Setup

### Minimum Viable Lab

**Essential Equipment:**
- Oscilloscope (100MHz+, 1GSa/s): Rigol DS1054Z, Siglent SDS1104X-E
- ChipWhisperer-Lite or Husky
- USB-UART adapter (FT232, CP2102)
- Soldering station with fine tips
- Multimeter
- Target boards (STM32F1 Discovery, nRF52 DK)

**Software Stack:**
```bash
# ChipWhisperer installation
pip install chipwhisperer

# Jupyter for interactive analysis
pip install jupyter

# OpenOCD for debug interface
sudo apt install openocd
```

### Target Board Preparation

**STM32F1 Glitch Target Setup:**
1. Remove C13 (100nF decoupling) near VDD pins
2. Solder wire to VCAP pin for glitch injection
3. Connect SWD for firmware loading and monitoring
4. Add trigger output (GPIO toggle before security check)

**Power Measurement Setup:**
1. Cut VCC trace or remove ferrite bead
2. Insert 10-50Ω shunt resistor
3. Connect oscilloscope probe across shunt
4. Ensure common ground between scope and target

### First Glitch Attack Walkthrough

```python
# ChipWhisperer basic glitch setup
import chipwhisperer as cw

# Connect to ChipWhisperer
scope = cw.scope()
target = cw.target(scope)

# Configure glitch module
scope.glitch.clk_src = "clkgen"
scope.glitch.output = "enable_only"
scope.glitch.trigger_src = "ext_single"

# Parameter sweep
for width in range(1, 50):
    for offset in range(1000, 2000):
        scope.glitch.width = width
        scope.glitch.offset = offset
        
        # Arm and trigger
        scope.arm()
        target.simpleserial_write('g', bytearray([0]))  # Trigger target
        
        # Check for success condition
        response = target.simpleserial_read('r', 1)
        if response == SUCCESS_VALUE:
            print(f"Success! Width: {width}, Offset: {offset}")
```

---

## Chapter 7: Memory Extraction Case Study - Trezor One

### Background

The Trezor One hardware wallet stores cryptocurrency seeds in STM32F205 flash memory protected by Read-out Protection Level 2. Kraken Security Labs demonstrated complete seed extraction using voltage fault injection.

### Attack Methodology

**Phase 1: Fault Injection Setup**
- Target: STM32F205 VCAP1 pin (internal regulator output)
- Trigger: Power-on reset sequence
- Goal: Corrupt RDP check, enable debug access

**Phase 2: Parameter Discovery**
- Systematic sweep of glitch timing during boot
- ~1000 attempts to find working parameters
- Success indicated by JTAG becoming responsive

**Phase 3: Memory Extraction**
- Once RDP bypassed, standard SWD dump extracts flash
- Encrypted seed stored in flash requires PIN to decrypt
- PIN brute-force via extracted data: ~2 minutes for 4-digit PIN

### Defense Limitations

The vulnerability exists in silicon—no firmware update can fix it. Mitigations:
- Use BIP39 passphrase (not stored on device)
- Physical security of the device
- Consider Trezor Model T with different architecture

### Lessons Learned

1. Hardware security requires defense in depth
2. Debug protection alone is insufficient
3. Cryptographic secrets need additional encryption layers
4. Physical access = game over for most consumer devices

---

## Chapter 8: Introduction to Power Analysis

### The Physical Basis

CMOS logic consumes power proportional to switching activity. When a transistor switches state, it charges or discharges load capacitance:

```
P_dynamic = α × C × V² × f
```

Where α is the activity factor—the probability of switching. Operations on data with more '1' bits cause more transitions, consuming measurably more power.

### Measurement Setup

**Shunt Resistor Method:**
1. Insert 1-100Ω resistor in series with target VCC
2. Measure voltage drop across resistor (V = I × R)
3. Capture with oscilloscope or ChipWhisperer

**Current Probe Method:**
- Clamp-on current probes for non-invasive measurement
- Lower bandwidth, more noise than shunt

**EM Probe Method:**
- Near-field H-field probes capture magnetic emissions
- No target modification required
- Spatial selectivity enables targeting specific circuits

### Leakage Models

**Hamming Weight Model:**
Power correlates with the number of '1' bits in processed data:
```
P ≈ HW(data) × ε + noise
```

**Hamming Distance Model:**
Power correlates with bit transitions between consecutive values:
```
P ≈ HD(data_old, data_new) × ε + noise
```

---

## Chapter 9: Simple Power Analysis (SPA)

### Concept

SPA extracts secrets through direct visual inspection of power traces. No statistics required—the secret is visible in the waveform shape.

### Classic RSA Attack

RSA decryption uses modular exponentiation: `m = c^d mod n`

Square-and-multiply implementation:
```python
def square_and_multiply(base, exponent, modulus):
    result = 1
    for bit in bin(exponent)[2:]:  # MSB to LSB
        result = (result * result) % modulus  # Always square
        if bit == '1':
            result = (result * base) % modulus  # Multiply only for '1' bits
    return result
```

**The Vulnerability:**
- Square operations produce one power pattern
- Multiply operations produce a different (typically longer) pattern
- Reading the pattern directly reveals the exponent bits

### SPA Countermeasures

**Montgomery Ladder:**
Always performs both square and multiply, using only the result corresponding to the actual bit:
```python
def montgomery_ladder(base, exponent, modulus):
    R0, R1 = 1, base
    for bit in bin(exponent)[2:]:
        if bit == '0':
            R1 = (R0 * R1) % modulus
            R0 = (R0 * R0) % modulus
        else:
            R0 = (R0 * R1) % modulus
            R1 = (R1 * R1) % modulus
    return R0
```

**Blinding:**
Randomize inputs before computation, remove randomization after:
- RSA blinding: Multiply message by random r^e before decryption
- Result × r^(-1) yields correct plaintext

---

## Chapter 10: Differential Power Analysis (DPA)

### Beyond Visual Inspection

When individual operations aren't visually distinguishable, statistical methods extract the key from aggregate behavior across many traces.

### DPA Attack on AES

**Target Operation:** First round SubBytes output
```
S-box_output = SubBytes(plaintext[i] XOR key[i])
```

**Attack Procedure:**

1. **Collect traces:** Capture power during N encryptions with known plaintexts
2. **Hypothesize key byte:** For each possible key byte value (0-255):
   - Calculate intermediate value for all traces
   - Predict power consumption using Hamming weight
3. **Partition traces:** Group by predicted intermediate value
4. **Calculate difference:** Compare mean power of groups
5. **Identify key:** Correct hypothesis shows maximum difference

```python
# Simplified DPA attack structure
for key_guess in range(256):
    predictions = []
    for plaintext in plaintexts:
        intermediate = SBOX[plaintext[0] ^ key_guess]
        predictions.append(hamming_weight(intermediate))
    
    # Partition traces by prediction
    group_0 = traces[predictions < median(predictions)]
    group_1 = traces[predictions >= median(predictions)]
    
    # Difference of means
    diff = np.mean(group_1, axis=0) - np.mean(group_0, axis=0)
    
    if max(abs(diff)) > threshold:
        print(f"Key byte found: {key_guess}")
```

### Correlation Power Analysis (CPA)

CPA improves on DPA by using Pearson correlation instead of difference of means:

```python
def cpa_attack(traces, plaintexts):
    num_samples = traces.shape[1]
    correlations = np.zeros((256, num_samples))
    
    for key_guess in range(256):
        # Predicted power consumption
        hw_predictions = np.array([
            hamming_weight(SBOX[pt[0] ^ key_guess]) 
            for pt in plaintexts
        ])
        
        # Correlate with each time sample
        for t in range(num_samples):
            correlations[key_guess, t] = np.corrcoef(
                hw_predictions, traces[:, t]
            )[0, 1]
    
    # Key byte = guess with maximum correlation
    return np.argmax(np.max(np.abs(correlations), axis=1))
```

### Attack Complexity

**Unprotected AES-128:** ~500-1000 traces for full key recovery
**First-order masked:** ~50,000+ traces (higher-order attacks required)
**Combined countermeasures:** May require millions of traces or become impractical

---

## Chapter 11: Advanced Power Analysis Techniques

### Higher-Order DPA

First-order masking splits values into shares: `v = v₁ ⊕ v₂`

Attack requires combining leakage from both shares:
```python
# Second-order attack: combine samples from share processing
combined = traces[:, time_share1] * traces[:, time_share2]
# Then apply standard DPA to combined traces
```

Each additional masking order requires one more combination term, exponentially increasing trace requirements.

### Template Attacks

The theoretically optimal side-channel attack when profiling is possible:

**Profiling Phase (on identical device you control):**
1. Characterize power consumption for each possible intermediate value
2. Build multivariate Gaussian model: mean vector + covariance matrix

**Attack Phase:**
1. Capture traces from target device
2. Calculate probability of each key hypothesis given observed traces
3. Select maximum likelihood key

Template attacks extract more information per trace but require an identical profiling device.

### Machine Learning Approaches

Neural networks (CNNs, MLPs) increasingly replace classical statistical methods:
- Automatic feature extraction from raw traces
- Robustness to countermeasures like jitter and shuffling
- Transfer learning between device variants

### Electromagnetic Analysis

EM probes offer advantages over power measurement:
- **Non-invasive:** No target modification required
- **Spatial selectivity:** Position probe over cryptographic core
- **Higher bandwidth:** EM emissions contain higher-frequency content
- **Isolation:** Can measure individual components in complex SoCs

---

## Chapter 12: Differential Power Analysis Lab

### Equipment Setup

**Minimum Requirements:**
- ChipWhisperer-Lite with CW308 UFO target board
- STM32F3 or similar target with hardware AES
- Jupyter notebook environment

### Capture Procedure

```python
import chipwhisperer as cw
import numpy as np

# Connect hardware
scope = cw.scope()
target = cw.target(scope, cw.targets.SimpleSerial)

# Configure scope for power capture
scope.gain.gain = 45
scope.adc.samples = 5000
scope.adc.offset = 0
scope.clock.clkgen_freq = 7370000
scope.trigger.triggers = "tio4"

# Capture traces
num_traces = 5000
traces = np.zeros((num_traces, scope.adc.samples))
plaintexts = np.zeros((num_traces, 16), dtype=np.uint8)

for i in range(num_traces):
    # Random plaintext
    pt = np.random.randint(0, 256, 16, dtype=np.uint8)
    plaintexts[i] = pt
    
    # Arm scope and trigger encryption
    scope.arm()
    target.simpleserial_write('p', pt.tobytes())
    
    # Wait for completion and capture
    ret = scope.capture()
    traces[i] = scope.get_last_trace()
```

### CPA Implementation

```python
SBOX = [0x63, 0x7c, 0x77, ...]  # Full AES S-box

def hamming_weight(x):
    return bin(x).count('1')

def attack_byte(traces, plaintexts, byte_index):
    num_traces, num_samples = traces.shape
    best_corr = 0
    best_guess = 0
    
    for guess in range(256):
        # Hypothetical intermediate values
        hw = np.array([
            hamming_weight(SBOX[pt[byte_index] ^ guess])
            for pt in plaintexts
        ])
        
        # Correlation with each sample point
        for t in range(num_samples):
            corr = abs(np.corrcoef(hw, traces[:, t])[0, 1])
            if corr > best_corr:
                best_corr = corr
                best_guess = guess
    
    return best_guess, best_corr

# Attack all 16 key bytes
key = bytearray(16)
for i in range(16):
    key[i], corr = attack_byte(traces, plaintexts, i)
    print(f"Byte {i}: 0x{key[i]:02x} (correlation: {corr:.4f})")
```

---

## Chapter 13: Real-Life Attack Examples

### ESP32 Secure Boot Bypass (CVE-2020-13629)

**Target:** ESP32 with secure boot and flash encryption enabled

**Attack:** EMFI during boot sequence
- Trigger: Boot start detection via power monitoring
- Window: ~10μs after bootloader copy to RAM
- Success rate: ~35,000 experiments over 55 minutes for 3 successes

**Impact:** Execute unsigned code despite secure boot

### Xbox 360 Reset Glitch Hack

**Target:** Xbox 360 boot chain integrity check

**Attack:** Voltage glitch during POST
- MOSFET crowbar on CPU power rail
- Timing derived from POST code output
- Modchips automated the attack for consumer installation

**Impact:** Run unsigned code, enable homebrew and piracy

### AMD SEV Voltage Fault Injection (2021)

**Target:** AMD Secure Processor in EPYC CPUs

**Attack:** Voltage manipulation via SVI2 interface
- Undervolting causes computation errors
- Bypass SEV key derivation checks
- Extract VCEK seeds from production processors

**Impact:** Compromise confidential VM protections

### Trezor Model T Downgrade Attack

**Target:** TrustZone-based secure boot

**Attack:** Load older, vulnerable firmware version
- Signature verification passes (same signing key)
- Exploit known vulnerabilities in legacy firmware
- Extract secrets via debugger

**Lesson:** Version rollback protection essential for secure boot

---

## Chapter 14: Countermeasures and Certifications

### Side-Channel Countermeasures

**Masking:**
Split sensitive values into d shares: `s = s₁ ⊕ s₂ ⊕ ... ⊕ sₐ`
- Computations operate only on shares
- d-th order masking requires d+1 order attacks
- Significant performance overhead

**Hiding:**
Reduce or obscure signal-to-noise ratio:
- **Random delays:** Desynchronize traces
- **Shuffling:** Randomize operation order
- **Noise injection:** Add dummy operations
- **Dual-rail logic:** Constant power regardless of data

**Constant-Time Implementation:**
Eliminate timing variations entirely:
- No secret-dependent branches
- No secret-indexed memory access
- No variable-time instructions
- Verify at assembly level (compilers may optimize away)

### Fault Injection Countermeasures

**Detection:**
- Voltage/clock monitors trigger reset on anomaly
- Light sensors detect decapping
- Redundant computation with comparison

**Protection:**
- Redundant execution (compute twice, compare)
- Error-detecting codes on sensitive values
- Randomized timing to prevent synchronization

### Certification Standards

**FIPS 140-3:**
- Level 1: Basic security, no physical protection
- Level 2: Tamper-evident seals, role-based authentication
- Level 3: Tamper-resistant enclosures, identity-based authentication
- Level 4: Environmental failure protection, active tamper response

**Common Criteria:**
- EAL1-4: Functional testing and design review
- EAL5-7: Semi-formal to formal design verification
- AVA_VAN.5: Resistance to high attack potential

**EMVCo:**
- Mandatory DPA/SPA testing for payment cards
- Attack potential assessment per JIL methodology
- Ongoing evaluation as attack techniques evolve

### Test Vector Leakage Assessment (TVLA)

Non-specific leakage detection using statistical hypothesis testing:

```python
# TVLA t-test
def tvla(fixed_traces, random_traces):
    t_stat, p_value = scipy.stats.ttest_ind(
        fixed_traces, random_traces, axis=0
    )
    # |t| > 4.5 indicates detectable leakage
    return t_stat
```

**Threshold:** |t| > 4.5 indicates leakage with 99.999% confidence

TVLA detects vulnerability presence but doesn't quantify exploitability.

---

## Appendix A: Setting Up a Test Lab

### Budget Tiers

**Entry Level (~$500):**
- Oscilloscope: Rigol DS1054Z ($375)
- Logic analyzer: Saleae Logic 8 clone ($15-50)
- Soldering: Pine64 Pinecil ($25) + tips
- Adapters: FT232H breakout ($15)
- Multimeter: Basic digital ($20)

**Intermediate (~$1,500):**
- Add ChipWhisperer-Lite ($250)
- Siglent oscilloscope upgrade
- JTAGulator ($150)
- Hot air rework station ($100)
- PCBite probing system ($200)

**Professional (~$5,000+):**
- ChipWhisperer-Husky ($549)
- ChipSHOUTER EMFI ($3,500+)
- High-bandwidth oscilloscope (500MHz+)
- Professional rework station

### Essential Software

```bash
# Analysis and exploitation
pip install chipwhisperer
pip install binwalk
pip install pwntools

# Reverse engineering
# Ghidra (free): https://ghidra-sre.org/
# IDA Pro (commercial)
# radare2 (free)

# Debug interfaces
sudo apt install openocd gdb-multiarch

# Logic analysis
# PulseView (sigrok frontend)
sudo apt install sigrok pulseview
```

### Target Devices for Practice

- **STM32F1 Discovery boards:** RDP bypass exercises
- **ESP32 DevKit:** Flash extraction, secure boot testing  
- **nRF52 DK:** APPROTECT bypass research
- **Raspberry Pi Pico:** RP2040 for custom tools
- **Router/IoT devices:** Real-world UART/JTAG hunting

---

## Appendix B: Common Pinouts Reference

### JTAG Standard Pinouts

**ARM 10-pin (Cortex Debug Connector):**
```
     ┌───────────┐
VCC  │ 1      2  │ SWDIO/TMS
GND  │ 3      4  │ SWCLK/TCK
GND  │ 5      6  │ SWO/TDO
NC   │ 7      8  │ TDI
GND  │ 9     10  │ nRESET
     └───────────┘
```

**ARM 20-pin (Legacy):**
```
     ┌───────────────────────┐
VCC  │ 1                  2  │ VCC
nTRST│ 3                  4  │ GND
TDI  │ 5                  6  │ GND
TMS  │ 7                  8  │ GND
TCK  │ 9                 10  │ GND
RTCK │11                 12  │ GND
TDO  │13                 14  │ GND
nRST │15                 16  │ GND
NC   │17                 18  │ GND
NC   │19                 20  │ GND
     └───────────────────────┘
```

### SPI Flash Pinouts

**8-pin SOIC (most common):**
```
     ┌──────────┐
 CS  │1        8│ VCC
 DO  │2        7│ HOLD
 WP  │3        6│ CLK
GND  │4        5│ DI
     └──────────┘
```

### UART Pinouts

**Common 4-pin headers:**
```
GND | RX | TX | VCC
  or
VCC | GND | TX | RX
```

Voltage levels:
- 3.3V: Most modern MCUs
- 5V: Arduino, some legacy systems
- 1.8V: Low-power devices (rare)

### I2C Pinouts

**4-pin standard:**
```
VCC | GND | SDA | SCL
```

Common addresses:
- 0x50-0x57: EEPROMs (24Cxx)
- 0x68/0x69: RTC (DS3231)
- 0x76/0x77: Pressure sensors (BMP280)

---

## Quick Reference: Attack Decision Tree

```
Physical Access to Target
         │
         ▼
┌─────────────────────────────────────┐
│ 1. RECONNAISSANCE                    │
│    - Identify MCU, memory chips      │
│    - Locate debug headers, test pads │
│    - Gather datasheets               │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│ 2. DEBUG INTERFACE CHECK             │
│    - UART console available?         │
│    - JTAG/SWD responsive?            │
│    - Protection mechanisms?          │
└─────────────────┬───────────────────┘
                  │
         ┌───────┴───────┐
         ▼               ▼
    [Accessible]    [Protected]
         │               │
         ▼               ▼
┌───────────────┐ ┌───────────────────┐
│ Extract via   │ │ 3. PROTECTION     │
│ debug         │ │    BYPASS         │
│ interface     │ │    - Glitching    │
└───────────────┘ │    - Known CVEs   │
                  │    - Chip-off      │
                  └─────────┬─────────┘
                            │
                            ▼
                  ┌───────────────────┐
                  │ 4. SIDE-CHANNEL   │
                  │    (if crypto     │
                  │    keys needed)   │
                  │    - SPA/DPA/CPA  │
                  │    - TVLA first   │
                  └───────────────────┘
```

---

## Glossary

| Term | Definition |
|------|------------|
| **BGA** | Ball Grid Array - IC package with solder balls underneath |
| **CPA** | Correlation Power Analysis |
| **DPA** | Differential Power Analysis |
| **EMFI** | Electromagnetic Fault Injection |
| **eFuse** | Electrically programmable one-time fuse |
| **JTAG** | Joint Test Action Group (IEEE 1149.1) |
| **OTP** | One-Time Programmable memory |
| **RDP** | Read-out Protection (STM32 specific) |
| **RoT** | Root of Trust |
| **SPA** | Simple Power Analysis |
| **SWD** | Serial Wire Debug (ARM) |
| **TAP** | Test Access Port (JTAG controller) |
| **TEE** | Trusted Execution Environment |
| **TVLA** | Test Vector Leakage Assessment |
| **UART** | Universal Asynchronous Receiver/Transmitter |