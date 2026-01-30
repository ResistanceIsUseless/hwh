# Hardware Synergies & Multi-Device Workflows

This document identifies opportunities to combine multiple hardware devices for powerful attack scenarios, monitoring setups, and debugging workflows that wouldn't be possible with a single device.

---

## Core Synergy Patterns

### 1. Trigger Source + Glitch Executor

**Pattern:** One device monitors for attack opportunity, triggers glitch on another device.

**Why:** Most glitchers lack sophisticated trigger detection. Separating monitoring from glitching provides:
- Better trigger accuracy (dedicated monitoring hardware)
- More trigger options (UART patterns, power signatures, GPIO events)
- Lower latency (hardware triggers vs software)

**Devices:**
- **Trigger Sources:** Bus Pirate (UART/SPI/I2C monitoring), Bolt (power analysis), Black Magic Probe (UART)
- **Glitch Executors:** Bolt, FaultyCat
- **Connection:** GPIO wire (hardware) or USB coordination (software)

---

### 2. Glitcher + Monitor

**Pattern:** Glitch device attacks target, monitoring device observes results.

**Why:** Need to classify glitch results (success/crash/normal) to optimize parameters. Glitcher often can't monitor target output simultaneously.

**Devices:**
- **Glitchers:** Bolt, FaultyCat
- **Monitors:** Bus Pirate (UART/SPI/I2C), Black Magic Probe (UART), Tigard (UART)
- **Connection:** Shared connections to target + synchronized capture

---

### 3. Debug Probe + Glitcher

**Pattern:** Debug probe controls target execution, glitcher injects faults at precise instruction.

**Why:** Instruction-level glitching requires:
- Setting breakpoint at attack point
- Halting target
- Arming glitcher
- Single-stepping or resuming
- Glitch fires at exact instruction

**Devices:**
- **Debug Probes:** ST-Link, Black Magic Probe, Tigard (SWD/JTAG)
- **Glitchers:** Bolt, FaultyCat
- **Connection:** Debug probe controls timing, GPIO triggers glitcher

---

### 4. Multiple Protocol Monitoring

**Pattern:** Monitor multiple communication channels simultaneously.

**Why:** Targets often use multiple interfaces (UART console + SPI flash + I2C EEPROM). Need to correlate activity.

**Devices:**
- **Monitor 1:** Bus Pirate (UART on target)
- **Monitor 2:** Tigard (SPI flash)
- **Monitor 3:** Black Magic Probe (debug + memory)
- **Connection:** Shared GND, independent protocol monitoring

---

### 5. Power Analysis + Glitching

**Pattern:** Analyze power consumption to identify crypto operations, trigger glitch at vulnerable moment.

**Why:** DPA/CPA can identify when AES starts, prime moment for glitching key schedule.

**Devices:**
- **Power Analyzer:** Bolt (ADC current trace)
- **Glitcher:** Bolt (same device) or FaultyCat (external)
- **Connection:** Internal (Bolt) or power threshold trigger → GPIO (external glitcher)

---

## Specific Attack Scenarios

### Scenario 1: UART Password Bypass via Glitching

**Goal:** Glitch target when it checks password, skip authentication.

**Setup:**
```
Target UART TX ──→ Bus Pirate RX (monitors for "Password:")
                         │
                         ├─→ Pattern detected in hwh
                         │
Bus Pirate GPIO ─wire──→ Bolt Trigger Input
                              │
                              └─→ Glitch fires (pre-configured width/offset)
```

**Implementation:**
1. Bus Pirate configured in UART bridge mode on target console
2. Bolt configured with glitch parameters (width: 100ns, offset: 500ns)
3. hwh Coordination mode monitors UART stream
4. On detecting "Password:" pattern, Bus Pirate pulses GPIO pin
5. Bolt triggers glitch when GPIO edge detected
6. Bus Pirate captures glitch result on UART

**Devices:** Bus Pirate + Bolt (hardware GPIO trigger)

**Latency:** <1μs (GPIO hardware trigger)

**Alternative:** Software coordination (Bus Pirate detects → hwh triggers Bolt via USB)
- **Latency:** 1-10ms (USB round-trip)
- **Suitable for:** Boot-level glitching where timing isn't instruction-precise

---

### Scenario 2: STM32 RDP Bypass via Debug + Glitch

**Goal:** Bypass STM32 Read Protection by glitching option byte check.

**Setup:**
```
ST-Link ──SWD──→ Target MCU
    │                │
    │                │ (power line)
    │                ▼
    │           Bolt Glitcher (crowbar on VCC)
    │                │
    └──GPIO trigger──┘
```

**Implementation:**
1. ST-Link connects via SWD, reads FLASH_OPTCR register (RDP level)
2. ST-Link sets breakpoint at option byte verification code
3. ST-Link halts target at breakpoint
4. Bolt armed with glitch parameters (from STM32F4 profile)
5. ST-Link pulses GPIO to trigger Bolt
6. ST-Link single-steps target while Bolt glitches
7. ST-Link verifies RDP bypass by reading protected flash

**Devices:** ST-Link + Bolt

**Key Advantage:** Instruction-level precision (breakpoint-based triggering)

**Profile Database:** Can store known-good parameters for STM32F0/F1/F4/L0/L1/L4

---

### Scenario 3: SPI Flash Dump + Analysis While Target Running

**Goal:** Read SPI flash chip while target is running (in-system programming).

**Setup:**
```
Tigard ──SPI──→ Flash Chip ←──SPI──→ Target MCU
                    ↑
                    └─ Shared bus (target must tri-state or be held in reset)

Black Magic Probe ──SWD──→ Target MCU (holds in reset via NRST)
```

**Implementation:**
1. Black Magic Probe connects via SWD
2. Black Magic Probe asserts NRST (holds target in reset)
3. Tigard configures SPI mode
4. Tigard reads flash chip (RDID, READ commands)
5. hwh firmware analysis scans for credentials/keys
6. Black Magic Probe releases reset (target resumes)

**Devices:** Tigard + Black Magic Probe

**Why Not Single Device:**
- Bus Pirate can't hold target in reset while SPI reading
- Black Magic can't do SPI flash operations
- Combination provides both capabilities

---

### Scenario 4: Multi-Channel Firmware Extraction

**Goal:** Dump firmware from multiple storage locations simultaneously.

**Setup:**
```
Bus Pirate 1 ──SPI──→ External Flash (firmware)
Bus Pirate 2 ──I2C──→ EEPROM (config data)
ST-Link ──SWD──→ MCU Internal Flash
Black Magic Probe ──UART──→ Console (monitor for crashes)
```

**Implementation:**
1. Bus Pirate 1 dumps SPI flash to file
2. Bus Pirate 2 dumps I2C EEPROM to file
3. ST-Link dumps internal flash to file
4. Black Magic Probe monitors UART for errors/crashes
5. hwh correlates all dumps with timestamps
6. Firmware analysis runs on combined image

**Devices:** 2× Bus Pirate + ST-Link + Black Magic Probe

**Benefit:** Complete system firmware extraction in parallel

---

### Scenario 5: Power Analysis Guided Glitching (DPA → Glitch)

**Goal:** Use power analysis to identify AES operation start, glitch key schedule.

**Setup:**
```
Bolt ADC ──→ Target VCC (measures current)
    │
    ├─→ DPA identifies AES start pattern
    │
    └─→ Internal trigger → Glitch at precise offset
```

**Implementation:**
1. Bolt captures power traces while target encrypts
2. hwh DPA engine correlates traces to find AES round starts
3. Bolt configured to trigger glitch at power signature (threshold crossing)
4. Automated sweep of glitch offsets from trigger point
5. Bus Pirate monitors UART output for corrupted ciphertext (success indicator)

**Devices:** Bolt + Bus Pirate (UART monitor)

**Advanced:** Bolt can do both power analysis AND glitching internally, making it self-contained for this attack.

---

### Scenario 6: JTAG Pin Detection + Glitch Attack

**Goal:** Find JTAG pins on unknown board, then use for precise glitch triggering.

**Setup:**
```
Phase 1: Discovery
  FaultyCat ──scan──→ Unknown pins
                 ↓
           Identifies JTAG (TDO/TDI/TCK/TMS)

Phase 2: Debug Connection
  Tigard ──JTAG──→ Target (now known pins)
       │
       └─→ Sets breakpoint at authentication check

Phase 3: Glitch Attack
  FaultyCat ──→ Glitches on GPIO trigger from Tigard
```

**Implementation:**
1. FaultyCat pin detection mode scans board
2. Identifies JTAG pins (IDCODE readback confirms)
3. Tigard connects via JTAG (OpenOCD)
4. Tigard sets breakpoint at sensitive code
5. Tigard triggers FaultyCat via GPIO
6. FaultyCat glitches, Tigard verifies result

**Devices:** FaultyCat + Tigard

**Why:** FaultyCat's EMFI + pin detection is reconnaissance, Tigard provides debug control, FaultyCat re-used for actual attack.

---

### Scenario 7: Dual-Device Logic Analysis

**Goal:** Capture both sides of an encrypted communication channel.

**Setup:**
```
Bus Pirate ──SUMP──→ Captures plaintext UART (Device A TX)
Bolt ──SUMP──→ Captures ciphertext SPI (to Device B)
```

**Implementation:**
1. Bus Pirate logic analyzer on plaintext UART channel
2. Bolt logic analyzer on encrypted SPI channel
3. Both captures synchronized by shared trigger (e.g., GPIO edge)
4. hwh correlates plaintext → ciphertext
5. Crypto analysis identifies encryption algorithm/key

**Devices:** Bus Pirate + Bolt

**Benefit:** Two independent logic analyzers with synchronized triggering

---

### Scenario 8: Bootloader Analysis + Glitching

**Goal:** Analyze bootloader behavior under normal conditions, then glitch security checks.

**Setup:**
```
Phase 1: Analysis
  Black Magic Probe ──SWD──→ Target
      │
      └─→ Traces bootloader execution, identifies signature check

Phase 2: Glitching
  Bolt ──VCC glitch──→ Target (at signature check)
  Black Magic Probe ──UART──→ Monitors boot messages
```

**Implementation:**
1. Black Magic Probe runs bootloader in GDB, sets breakpoints
2. Identifies signature verification routine
3. Measures timing from boot to signature check
4. Bolt configured to glitch at calculated offset from boot
5. Bolt power-cycles target and glitches
6. Black Magic Probe UART captures boot messages (success = unsigned firmware boot)

**Devices:** Black Magic Probe + Bolt

**Key Insight:** Debug probe provides reconnaissance, glitcher performs attack, debug probe verifies result.

---

### Scenario 9: Continuous Integration Hardware Testing

**Goal:** Automated testing of embedded firmware on real hardware.

**Setup:**
```
ST-Link ──SWD──→ Target (programs firmware)
Bus Pirate ──UART──→ Target (runs test commands)
Bolt ──Logic Analyzer──→ Target GPIO (verifies timing)
```

**Implementation:**
1. ST-Link programs new firmware build
2. ST-Link resets target
3. Bus Pirate UART runs automated test suite
4. Bolt logic analyzer captures GPIO timing
5. hwh validates test results, generates report

**Devices:** ST-Link + Bus Pirate + Bolt

**Use Case:** Hardware-in-the-loop CI/CD

---

### Scenario 10: Multi-Target Glitch Campaign

**Goal:** Run glitch parameter sweep on multiple targets in parallel.

**Setup:**
```
Bolt 1 ──→ Target A (offset 0-1000, width 50-150)
Bolt 2 ──→ Target B (offset 1000-2000, width 50-150)
Bus Pirate ──→ Monitors both targets' UART outputs
```

**Implementation:**
1. Two Bolts configured with different parameter ranges
2. Bus Pirate multi-channel UART monitoring (if supported)
3. hwh coordinates parallel sweeps
4. Results merged into unified database
5. Successful parameters identified faster

**Devices:** 2× Bolt + Bus Pirate

**Benefit:** Parallelized parameter search reduces attack time from hours to minutes

---

## Coordination Mechanisms

### Hardware GPIO Triggers (Recommended)

**Latency:** <1μs

**Wiring:**
```
Source Device GPIO Output ───wire───> Target Device Trigger Input
Common GND ───wire───> Common GND
```

**Advantages:**
- Ultra-low latency
- No software jitter
- Deterministic timing
- Works for instruction-level precision

**Disadvantages:**
- Requires physical wiring
- Limited to devices with GPIO outputs/trigger inputs

**Supported Devices:**
- **GPIO Output:** Bus Pirate (any IO pin), Tigard (FTDI GPIOs), ST-Link (NRST), Black Magic (UART pins in GPIO mode)
- **Trigger Input:** Bolt (dedicated trigger pins), FaultyCat (trigger input)

---

### Software USB Coordination

**Latency:** 1-10ms (variable)

**Flow:**
```
Source Device → USB → hwh Coordinator → USB → Target Device
```

**Advantages:**
- No extra wiring needed
- Flexible routing (any device → any device)
- Can combine multiple conditions
- Easy to reconfigure

**Disadvantages:**
- High latency (USB round-trip)
- Timing jitter (OS scheduling)
- Not suitable for instruction-level glitching

**Use Cases:**
- Boot-level glitching (timing tolerance >10ms)
- UART pattern → glitch (after boot message)
- Event-driven attacks (user input → glitch)

**Implementation in hwh:**
```python
# Proposed API
coordinator = Coordinator(app)
route = TriggerRoute(
    source_device="buspirate",
    source_condition=TriggerCondition.UART_PATTERN,
    source_config={"pattern": r"Password:.*", "port": "uart"},
    target_device="bolt",
    target_action="glitch",
    target_config={"width_ns": 100, "offset_ns": 500},
    routing_mode="software"  # or "hardware" for GPIO
)
coordinator.add_route(route)
coordinator.arm()
```

---

### Hybrid Coordination

**Best of Both Worlds:**
1. Software detects high-level condition (UART pattern, power threshold)
2. Software arms glitcher + configures parameters
3. Hardware GPIO provides final trigger (low latency)

**Example:**
```
1. Bus Pirate monitors UART for "Bootloader Ready"
2. hwh detects pattern, sends command to Bus Pirate: "pulse GPIO3 on next byte"
3. Bus Pirate UART receives next byte → GPIO3 pulse (hardware, <1μs)
4. Bolt triggers on GPIO3 edge
```

**Benefit:** Combines flexibility of software with precision of hardware.

---

## Device Capability Matrix

| Device | UART Monitor | SPI/I2C Mon | Debug (SWD/JTAG) | Glitch | Logic Analyzer | Power Analysis | GPIO Trigger Out | Trigger In |
|--------|--------------|-------------|------------------|--------|----------------|----------------|------------------|------------|
| **Bus Pirate** | ✅ Excellent | ✅ Excellent | ⚠️ Scan only | ⚠️ UART glitch | ✅ SUMP | ❌ | ✅ Any IO pin | ❌ |
| **Bolt** | ❌ | ❌ | ❌ | ✅ Excellent | ✅ SUMP | ✅ DPA/CPA | ⚠️ GPIO | ✅ Dedicated |
| **Tigard** | ✅ Good | ✅ Good | ⚠️ Via OpenOCD | ❌ | ⚠️ Via FTDI | ❌ | ⚠️ FTDI GPIO | ❌ |
| **ST-Link** | ❌ | ❌ | ✅ Excellent | ❌ | ❌ | ❌ | ⚠️ NRST | ❌ |
| **Black Magic** | ✅ Good | ❌ | ✅ Excellent | ❌ | ❌ | ❌ | ⚠️ UART GPIO | ❌ |
| **FaultyCat** | ❌ | ❌ | ⚠️ Pin detect | ✅ EMFI | ❌ | ❌ | ❌ | ✅ Dedicated |
| **TI-Link** | ⚠️ BSL UART | ❌ | ✅ SBW/JTAG | ❌ | ❌ | ✅ EnergyTrace | ❌ | ❌ |

**Legend:**
- ✅ Excellent: Native support, production-ready
- ⚠️ Limited: Partial support or requires external tools
- ❌ Not supported

---

## Recommended Device Combinations

### Budget Setup ($100-200)
**Devices:** Bus Pirate 5 + Bolt
- **Justification:** Bus Pirate handles all protocols (SPI/I2C/UART/1-Wire) + logic analyzer. Bolt adds voltage glitching + power analysis.
- **Coverage:** 80% of hardware hacking scenarios
- **Missing:** JTAG/SWD debug (can add ST-Link for $20)

### Professional Setup ($300-500)
**Devices:** Bus Pirate 5 + Bolt + ST-Link V3 + Tigard
- **Justification:**
  - Bus Pirate: Protocol king (SPI/I2C/UART/1-Wire)
  - Bolt: Glitching + power analysis + logic analyzer
  - ST-Link V3: Best ARM debug probe
  - Tigard: JTAG/SWD backup + independent SPI/I2C
- **Coverage:** 95% of scenarios
- **Missing:** EMFI glitching (add FaultyCat for $150)

### Complete Arsenal ($500-800)
**Devices:** Bus Pirate 5 + Bolt + ST-Link V3 + Black Magic Probe + Tigard + FaultyCat
- **Justification:** Every tool for every job
- **Redundancy Benefits:**
  - 2× UART monitors (Bus Pirate + Black Magic)
  - 2× SPI/I2C (Bus Pirate + Tigard)
  - 2× SWD/JTAG (ST-Link + Black Magic + Tigard)
  - 2× Glitchers (Bolt voltage + FaultyCat EMFI)
  - 2× Logic analyzers (Bus Pirate + Bolt)
- **Coverage:** 100% of documented scenarios

### Specialized: Glitching Focus ($300-400)
**Devices:** Bolt + FaultyCat + Bus Pirate + ST-Link
- **Justification:**
  - Bolt: Voltage glitching + power analysis (DPA/CPA)
  - FaultyCat: EMFI glitching (different attack vector)
  - Bus Pirate: UART monitoring for glitch result classification
  - ST-Link: Debug probe for instruction-level trigger precision
- **Use Case:** Maximum glitching capability with trigger/monitor support

### Specialized: Debugging Focus ($150-250)
**Devices:** ST-Link V3 + Black Magic Probe + Tigard
- **Justification:**
  - ST-Link: Best ARM debug, SWO trace
  - Black Magic: Standalone GDB server, no OpenOCD needed
  - Tigard: JTAG for non-ARM targets via OpenOCD
- **Use Case:** Firmware reverse engineering, debugging, development

---

## Implementation Priorities for Synergies

### Phase 1: Core Coordination Framework
1. Create `src/hwh/coordination/` module
2. Implement `TriggerCondition`, `TriggerRoute`, `Coordinator` classes
3. Add GPIO output support to Bus Pirate backend
4. Add external trigger support to Bolt backend
5. Build Coordination UI panel (F4 key)

### Phase 2: Software Triggers
1. UART pattern matching (regex on RX stream)
2. SPI/I2C transaction detection
3. Memory value monitoring (via debug probe)
4. Power threshold crossing (Bolt ADC)
5. Time-based triggers (delay after event)

### Phase 3: Hardware Triggers
1. Bus Pirate GPIO pulse on UART pattern
2. ST-Link NRST control as trigger
3. Bolt GPIO output on power threshold
4. Tigard FTDI GPIO control

### Phase 4: Advanced Workflows
1. Glitch campaigns with result classification
2. DPA-guided glitch parameter optimization
3. Multi-target parallel sweeps
4. Debug-assisted glitching (breakpoint triggers)
5. Automated firmware extraction workflows

---

## Use Case Examples

### Real-World Scenario 1: IoT Device Boot Bypass
**Target:** IoT camera with locked bootloader

**Attack Flow:**
1. **Bus Pirate:** UART monitoring finds boot message "Checking signature..."
2. **Coordination:** hwh detects pattern, arms Bolt
3. **Bolt:** Glitches VCC 500ns after pattern detected
4. **Bus Pirate:** Captures result: "Signature check skipped, booting unsigned firmware"
5. **Success:** Unsigned firmware boots, shell access gained

**Devices Used:** Bus Pirate + Bolt (software coordination)

---

### Real-World Scenario 2: STM32F4 RDP Level 2 Bypass
**Target:** STM32F407 with Read Protection Level 2

**Attack Flow:**
1. **ST-Link:** Connects via SWD, verifies RDP=2 (flash read disabled)
2. **ST-Link:** Sets breakpoint at option byte check (address from datasheet)
3. **Coordination:** hwh configures ST-Link to pulse GPIO on breakpoint hit
4. **Bolt:** Armed with STM32F4 glitch profile (width=60ns, offset=120ns)
5. **ST-Link:** Halts at breakpoint, pulses GPIO
6. **Bolt:** Glitches on GPIO edge
7. **ST-Link:** Verifies flash now readable (RDP bypass successful)
8. **ST-Link:** Dumps firmware to file

**Devices Used:** ST-Link + Bolt (hardware GPIO trigger)

---

### Real-World Scenario 3: Multi-Chip Firmware Extraction
**Target:** Router with main SoC + external SPI flash + I2C EEPROM

**Extraction Flow:**
1. **Bus Pirate 1:** Dumps SPI flash (16MB, takes 5 minutes)
2. **Bus Pirate 2:** Dumps I2C EEPROM (256KB, takes 30 seconds)
3. **Black Magic Probe:** Holds SoC in reset (prevents interference)
4. **hwh:** Correlates timestamps, merges firmware images
5. **Firmware Tab:** Analyzes combined image for secrets

**Devices Used:** 2× Bus Pirate + Black Magic Probe

---

## Future Enhancements

### ML-Guided Glitching
- Train model on successful glitch parameters
- Predict optimal parameters for new targets
- Adaptive sweep that learns from results

### Distributed Glitch Campaigns
- Network multiple hwh instances
- Distribute parameter space across machines
- Aggregate results in central database
- Cloud-based glitch-as-a-service

### Automated Attack Chains
- Define multi-stage attacks as workflows
- hwh executes entire chain autonomously
- Example: Pin detection → Debug connection → Glitch → Firmware dump

### Community Glitch Database
- Share successful attack parameters
- Search by target (chip model, bootloader version)
- Import/export profiles
- Verify profiles before use (cryptographic signing)
