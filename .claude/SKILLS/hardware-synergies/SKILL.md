---
name: hardware-synergies
description: Multi-device workflow patterns for coordinated attacks, glitching campaigns, and simultaneous protocol monitoring across hardware hacking tools.
---

# Hardware Synergies & Multi-Device Workflows

This skill provides specialized knowledge for combining multiple hardware devices in coordinated attack scenarios, monitoring setups, and debugging workflows that wouldn't be possible with a single device.

## When to Use This Skill

- Implementing multi-device coordination features
- Designing glitch campaigns with separate trigger and executor devices
- Planning simultaneous protocol monitoring (UART + SPI + I2C)
- Building trigger routing systems (UART pattern → glitch)
- Coordinating debug probes with fault injection
- Power analysis combined with glitching
- Evaluating device combination strategies by budget

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

**hwh Implementation:**
```python
# In coordination/coordinator.py
coordinator = Coordinator()
coordinator.add_route(
    trigger=UARTPatternTrigger(device="Bus Pirate", pattern="Password:"),
    action=GlitchAction(device="Curious Bolt", width=350, offset=500)
)
coordinator.arm()
```

---

### 2. Glitcher + Monitor

**Pattern:** Glitch device attacks target, monitoring device observes results.

**Why:** Need to classify glitch results (success/crash/normal) to optimize parameters. Glitcher often can't monitor target output simultaneously.

**Devices:**
- **Glitchers:** Bolt, FaultyCat
- **Monitors:** Bus Pirate (UART/SPI/I2C), Black Magic Probe (UART), Tigard (UART)
- **Connection:** Shared connections to target + synchronized capture

**hwh Implementation:**
```python
# In workflows/glitch_monitor.py
from hwh.workflows import GlitchMonitorWorkflow

workflow = GlitchMonitorWorkflow(
    glitcher=bolt_backend,
    monitor=buspirate_backend,
    success_pattern=b"UNLOCKED"
)

results = await workflow.run_sweep(
    width_range=(100, 500, 10),
    offset_range=(0, 1000, 50)
)
```

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

**Example Workflow:**
```python
# Set breakpoint at secure_check function
debug.halt()
debug.set_breakpoint(0x08001234)

# Configure glitch
glitcher.set_params(width=200, offset=100)

# Run until breakpoint
debug.resume()
debug.wait_for_halt()

# Arm glitcher and single-step
glitcher.arm()
debug.step()  # Glitch fires during this instruction

# Check result
if target.read_uart() == b"ACCESS GRANTED":
    print("Bypass successful!")
```

---

### 4. Multiple Protocol Monitoring

**Pattern:** Monitor multiple communication channels simultaneously.

**Why:** Targets often use multiple interfaces (UART console + SPI flash + I2C EEPROM). Need to correlate activity.

**Devices:**
- **Monitor 1:** Bus Pirate (UART on target)
- **Monitor 2:** Tigard (SPI flash)
- **Monitor 3:** Black Magic Probe (debug + memory)
- **Connection:** Shared GND, independent protocol monitoring

**Use Case:** Router firmware analysis
- UART: Boot console output
- SPI: Flash chip reads during boot
- Debug: Memory dumps and register inspection

---

### 5. Power Analysis + Glitching

**Pattern:** Analyze power consumption to identify crypto operations, trigger glitch at vulnerable moment.

**Why:** DPA/CPA can identify when AES starts, prime moment for glitching key schedule.

**Devices:**
- **Power Analyzer:** Bolt (ADC current trace)
- **Glitcher:** Bolt (same device) or FaultyCat (external)
- **Connection:** Internal (Bolt) or power threshold trigger → GPIO (external glitcher)

**Example:**
```python
# Learn power signature of AES operation
bolt.start_power_trace()
target.encrypt(known_plaintext)
aes_signature = bolt.get_power_trace()

# Configure trigger on power spike (indicates AES start)
bolt.set_trigger_threshold(threshold=aes_signature.peak * 0.9)
bolt.set_glitch_delay(500)  # 500ns after trigger

# Automated glitch campaign
for width in range(50, 200, 10):
    bolt.set_glitch_width(width)
    bolt.arm()
    result = target.encrypt_and_check(known_plaintext)
    if result.corrupted_key:
        print(f"Key extraction at width={width}!")
        break
```

---

## Specific Attack Scenarios

### Scenario 1: UART Password Bypass via Glitching

**Goal:** Glitch target when it checks password, skip authentication.

**Hardware Setup:**
```
Target UART TX ──→ Bus Pirate RX (monitors for "Password:")
                         │
                         ├─→ Pattern detected in hwh
                         │
Bus Pirate GPIO ─wire──→ Bolt Trigger Input
                              │
                              └─→ Glitch fires (pre-configured width/offset)
```

**hwh Implementation:**
1. Press F4 to enter Coordination Mode
2. Configure trigger pattern: "Password:"
3. Configure glitch parameters: width=350ns, offset=500ns
4. Click "ARM COORDINATOR"
5. Send password attempt to target
6. Glitch fires automatically when pattern detected
7. Monitor target response for bypass success

**Code Pattern:**
```python
coordinator = Coordinator()
coordinator.add_route(
    trigger=UARTPatternTrigger(
        device="Bus Pirate",
        pattern=b"Password:",
        gpio_pin=2
    ),
    action=GlitchAction(
        device="Curious Bolt",
        trigger_input="EXT",
        width=350,
        offset=500
    )
)

coordinator.arm()
# Glitch fires automatically on next password prompt
```

---

### Scenario 2: STM32 RDP Bypass (Instruction-Level)

**Goal:** Glitch STM32 secure boot check at exact instruction using debug probe.

**Hardware Setup:**
```
ST-Link SWD ──→ Target (debug control)
    │
    └─GPIO──→ Bolt Trigger (fires glitch on step)
```

**Workflow:**
1. Identify RDP check instruction via reverse engineering: `0x08000ABC`
2. Load firmware with debug probe
3. Set breakpoint at `0x08000ABC`
4. Arm glitcher with pre-calibrated parameters
5. Single-step through RDP check while glitching
6. Check if RDP disabled

**Code:**
```python
from hwh.backends import get_backend

stlink = get_backend(device_info_stlink)
bolt = get_backend(device_info_bolt)

# Flash and halt
stlink.flash("firmware.bin")
stlink.halt()

# Set breakpoint at RDP check
stlink.set_breakpoint(0x08000ABC)

# Configure glitch
bolt.set_params(width=180, offset=50)

# Attempt bypass
stlink.resume()
stlink.wait_for_halt()  # Stopped at 0x08000ABC
bolt.arm()
stlink.step()  # Glitch fires during this instruction

# Verify bypass
if stlink.read_memory(0x1FFFC000, 2) == b'\xAA\x00':  # RDP level 0
    print("RDP bypass successful!")
```

---

### Scenario 3: Multi-Channel Firmware Analysis

**Goal:** Monitor all communication channels during target boot to understand initialization sequence.

**Hardware Setup:**
```
Bus Pirate ──→ Target UART (console output)
Tigard     ──→ Target SPI (flash chip)
ST-Link    ──→ Target SWD (memory/registers)
```

**Workflow:**
1. Connect all three devices in Split View (F3)
2. Start synchronized capture on all channels
3. Power cycle target
4. Correlate UART messages with SPI reads and memory accesses
5. Identify vulnerability windows (e.g., unsigned code execution between boot stages)

**Benefits:**
- See exactly what's loaded from flash (SPI)
- Correlate with boot messages (UART)
- Inspect memory state at each stage (SWD)
- Find timing windows for fault injection

---

## Device Capability Matrix

| Device | UART | SPI | I2C | JTAG | SWD | Glitch | ADC | Logic Analyzer |
|--------|------|-----|-----|------|-----|--------|-----|----------------|
| Bus Pirate 5/6 | ✅ | ✅ | ✅ | Scan | Scan | ❌ | ✅ | ✅ (SUMP) |
| Curious Bolt | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ (SUMP) |
| Tigard | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| FaultyCat | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ EMFI | ❌ | ❌ |
| ST-Link | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| Black Magic | ✅ | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |
| TI-Link | ✅ BSL | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ | ❌ |

---

## Recommended Device Combinations

### Budget: $150-200 (Starter)
- **Bus Pirate 5** ($40) - Protocol monitoring, logic analyzer
- **Curious Bolt** ($150) - Voltage glitching, power analysis
- **Total:** $190

**Capabilities:** UART/SPI/I2C monitoring + voltage glitching. Covers 80% of embedded security work.

**Limitations:** No debug probe (can't do instruction-level glitching or memory dumps from protected targets).

---

### Budget: $300-400 (Intermediate)
- **Bus Pirate 5** ($40) - Protocol monitoring
- **Curious Bolt** ($150) - Voltage glitching
- **Tigard** ($50) - SWD/JTAG debugging + protocols
- **Total:** $240

**Capabilities:** Full protocol support + debugging + glitching. Can do instruction-level attacks.

**Alternative:** Replace Tigard with ST-Link V3 ($70) for faster SWD and better tool support.

---

### Budget: $500+ (Professional)
- **Bus Pirate 5** ($40) - Monitoring
- **Curious Bolt** ($150) - Voltage glitching
- **FaultyCat** ($120) - EMFI glitching
- **Tigard** ($50) - Debug
- **Black Magic Probe** ($70) - GDB server + UART
- **Total:** $430

**Capabilities:** Multiple glitch modalities (voltage + EMFI), redundant monitoring, flexible debugging. Can handle most targets.

**Premium Add:** ChipWhisperer Husky ($500+) for professional power analysis and clock glitching.

---

## Coordination Implementation in hwh

### Hardware Triggers (Lowest Latency)

**Best for:** Sub-microsecond timing requirements (fault injection)

**Setup:** Physical wire from trigger device GPIO to glitcher trigger input.

**Example:**
```
Bus Pirate GPIO2 ──wire──→ Bolt EXT_TRIGGER
```

When pattern detected, Bus Pirate sets GPIO high, Bolt fires glitch.

**Implementation:**
```python
# Configure trigger output
buspirate.configure_gpio(pin=2, mode="output", initial=False)

# Configure glitch input
bolt.set_trigger_source("external")
bolt.arm()

# In UART handler
if b"Password:" in uart_data:
    buspirate.set_gpio(pin=2, high=True)
    time.sleep(0.001)  # Hold trigger 1ms
    buspirate.set_gpio(pin=2, high=False)
```

---

### Software Coordination (Higher Latency)

**Best for:** Less timing-critical scenarios, complex trigger logic

**Setup:** USB communication between devices coordinated by hwh.

**Example:** UART pattern detection → glitch via separate USB commands

**Implementation:**
```python
# In coordination/coordinator.py
class Coordinator:
    def add_route(self, trigger: Trigger, action: Action):
        self.routes.append((trigger, action))

    async def monitor(self):
        while self.armed:
            for trigger, action in self.routes:
                if await trigger.check():
                    await action.execute()

# Usage
coordinator = Coordinator()
coordinator.add_route(
    trigger=UARTPatternTrigger(device=buspirate, pattern=b"Boot"),
    action=GlitchAction(device=bolt, width=350, offset=500)
)
await coordinator.monitor()
```

**Latency:** Typically 1-10ms depending on USB polling rate and OS scheduling.

---

## Development Priorities for Multi-Device Features

### Phase 1: Basic Coordination (In Progress)
- [x] Device pool management
- [x] Multi-device TUI tabs
- [x] Split view for simultaneous monitoring
- [ ] Simple trigger routing (UART pattern → glitch)
- [ ] Coordination view (F4 key)

### Phase 2: Advanced Triggers
- [ ] Power threshold triggers (ADC → glitch)
- [ ] GPIO hardware triggers (low latency)
- [ ] Logic analyzer pattern triggers (protocol-level)
- [ ] Composite triggers (pattern + timing + threshold)

### Phase 3: Workflows
- [ ] Automated glitch campaigns with result classification
- [ ] Multi-channel capture correlation
- [ ] Debug + glitch synchronization
- [ ] Campaign result visualization (heatmaps)

### Phase 4: Advanced Analysis
- [ ] Power analysis + glitch automation
- [ ] Multi-device logic analyzer correlation
- [ ] Automated vulnerability discovery workflows
- [ ] Campaign sharing and calibration profiles

---

## Code Examples

### Multi-Device Glitch Campaign

```python
from hwh.workflows import AdaptiveGlitchCampaign

campaign = AdaptiveGlitchCampaign(
    glitcher=bolt,
    monitor=buspirate,
    success_classifier=lambda response: b"UNLOCKED" in response
)

# Intelligent parameter search (focuses on promising regions)
results = await campaign.run(
    width_range=(100, 500),
    offset_range=(0, 2000),
    max_attempts=5000,
    strategy="adaptive"  # vs "exhaustive"
)

# Export successful parameters
campaign.export_success_configs("stm32_rdp_bypass.json")
```

---

### Coordinated Protocol Capture

```python
from hwh.coordination import ProtocolCapture

capture = ProtocolCapture()
capture.add_channel(buspirate, protocol="UART", baud=115200)
capture.add_channel(tigard, protocol="SPI", speed=1000000)

# Synchronized start
capture.start()
target.power_cycle()
time.sleep(5)  # Capture boot sequence
capture.stop()

# Correlate events
timeline = capture.get_timeline()
for event in timeline:
    print(f"{event.timestamp}ms - {event.device}: {event.data}")

# Find patterns
uart_boot = timeline.filter(device="Bus Pirate", contains=b"U-Boot")
spi_reads = timeline.filter(device="Tigard", protocol="SPI", command=0x03)

print(f"U-Boot loaded at {uart_boot[0].timestamp}ms")
print(f"First SPI read at {spi_reads[0].timestamp}ms")
```

---

## References

- **Coordination View:** `tui/panels/coordination.py`
- **Workflow System:** `workflows/base.py`, `workflows/glitch_monitor.py`
- **Trigger Framework:** `coordination/triggers.py`
- **Device Pool:** `tui/device_pool.py`

For implementation details, see the main `HARDWARE_SYNERGIES.md` file in this directory.
