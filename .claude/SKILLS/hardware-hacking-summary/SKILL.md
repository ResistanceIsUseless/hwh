---
name: hardware-hacking
description: Comprehensive reference for embedded security assessment including memory extraction, debug interfaces (JTAG/SWD/UART), fault injection, side-channel analysis, bootloader vulnerabilities, and hardware attack countermeasures.
---

# Hardware Hacking and Embedded Security: A Technical Reference

Hardware security has become the critical frontier in modern cybersecurity, where software protections ultimately rest on silicon foundations that can be probed, glitched, and compromised. This reference provides security professionals with practical methodologies for assessing embedded systems—from basic firmware extraction to advanced fault injection—along with the countermeasures that make devices resilient against physical attack. The techniques documented here apply across IoT devices, hardware wallets, automotive systems, and any embedded target where attackers have physical access.

## Memory extraction forms the foundation of hardware security assessment

Every hardware security engagement begins with firmware acquisition. The most common target is **SPI flash memory**, typically found in 8-pin SOIC packages from manufacturers like Winbond (W25Qxx series), Macronix (MX25L), and GigaDevice (GD25Q). These chips communicate via four signals: chip select (CS), clock (SCLK), and bidirectional data lines (MOSI/MISO).

The **CH341A programmer** ($5-15) handles most SPI extraction tasks using the flashrom utility. A typical extraction command reads `flashrom -p ch341a_spi -c "W25Q64.V" -r dump.bin`. However, the CH341A outputs 5V natively—modern 3.3V and 1.8V flash chips require voltage adapters to avoid damage. Professional tools like the **Dediprog SF600** ($300+) and **FlashcatUSB** support broader voltage ranges and faster read speeds.

In-circuit reading using **SOIC-8 test clips** (Pomona 5250/5252) avoids desoldering but introduces complications. The target MCU may hold the SPI bus, causing read failures. Mitigation strategies include holding the MCU in reset during extraction or cutting the chip's power trace to isolate it from the system. When clips fail—particularly with leadless WSON packages—hot air desoldering becomes necessary.

After extraction, **binwalk** analyzes firmware structure. The command `binwalk -Me dump.bin` recursively extracts embedded filesystems, compressed sections, and executable code. Entropy analysis (`binwalk -E dump.bin`) reveals encrypted regions that appear as high-entropy blocks distinct from compressed data.

**EEPROM extraction** follows similar patterns. I2C EEPROMs (24Cxx series) use 2-wire communication at addresses 0x50-0x57, while SPI EEPROMs (25xx series) interface identically to flash memory. These smaller storage devices often contain calibration data, cryptographic keys, or device-specific secrets.

Cold boot attacks exploit **DRAM data remanence**—the phenomenon where memory retains contents for seconds to minutes after power loss. Cooling DRAM modules with inverted compressed air cans (-50°C) or liquid nitrogen extends retention dramatically. The Princeton "Lest We Remember" research demonstrated full disk encryption key recovery from RAM contents, affecting BitLocker, LUKS, and FileVault implementations. Modern DDR4/DDR5 memory and memory scrambling features reduce but don't eliminate this attack vector.

## Debug interfaces provide direct access to device internals

**JTAG** (IEEE 1149.1) remains the most powerful debug interface, offering complete control over processor state and memory. The standard five-pin configuration—TCK (clock), TMS (mode select), TDI (data in), TDO (data out), and optional TRST (reset)—connects to a 16-state TAP controller. Critical JTAG capabilities include reading the 32-bit IDCODE for device identification, full memory access through boundary scan, and halt/step/continue CPU control.

ARM's **Serial Wire Debug (SWD)** reduces the pin count to two—SWDIO and SWCLK—while providing equivalent functionality. SWD shares pins with JTAG (SWDIO maps to TMS, SWCLK to TCK), and a specific 16-bit sequence (0x79E7) switches between protocols. Most ARM Cortex-M devices support both interfaces.

**Identifying debug interfaces** on unfamiliar boards requires systematic reconnaissance. Visual inspection reveals common patterns: unpopulated headers near the main processor, test pads with standardized spacing, or silk-screened labels. Ground pins show continuity to chassis/shield points. VCC pins measure stable 3.3V or 5V. UART TX pins fluctuate during boot as debug messages transmit, while RX remains stable at logic high.

The **JTAGulator** automates pin discovery across its 24 I/O channels. After setting the target voltage (measured first to avoid damage), the IDCODE scan (`I` command) rapidly identifies TCK, TMS, and TDO by searching for valid device IDs. The slower BYPASS scan (`B`) discovers TDI and optional TRST. For UART, the `U` command identifies TX/RX and determines baud rate automatically.

**OpenOCD** (Open On-Chip Debugger) provides the software interface for JTAG/SWD operations across hundreds of target devices. A typical STM32 configuration combines interface and target files:

```
openocd -f interface/stlink.cfg -c "transport select hla_swd" -f target/stm32f1x.cfg
```

Firmware extraction then uses `dump_image firmware.bin 0x08000000 0x20000` from the OpenOCD console. The tool supports most ARM Cortex devices, MIPS, ESP32, RISC-V, and many specialized architectures.

## Protection bypass techniques defeat debug lockouts

Manufacturers implement debug protection to prevent firmware extraction, but these mechanisms have known weaknesses. **STM32 Read-out Protection (RDP)** exemplifies the hierarchy: Level 0 permits full access, Level 1 blocks flash reads but allows SRAM access (reversible via mass erase), and Level 2 permanently disables debug interfaces by blowing physical fuses.

The **CVE-2020-8004 vulnerability** in STM32F1 devices allows extracting approximately 94% of flash content from RDP-1 protected chips. The attack exploits how the debug interface handles exception vectors—each vector read exposes the program counter value before protection engages. The **stm32f1-picopwner** tool implements this attack using a $4 Raspberry Pi Pico.

**Nordic nRF52 APPROTECT** disables the AHB-AP debug port while leaving the CTRL-AP accessible for recovery operations. Voltage glitching during boot can corrupt the APPROTECT register read from UICR, causing the AHB-AP to initialize despite protection being set. This technique enabled researchers to extract firmware from Apple AirTags and other nRF52-based devices.

Additional bypass techniques include:

- **Boot mode forcing**: Pulling the STM32 BOOT0 pin high forces boot from system memory where SWD may remain enabled
- **Debug interface race conditions**: Reading memory in the brief window before protection activates
- **Cold-boot stepping**: Extracting SRAM contents at power-on before encryption keys clear
- **Undocumented commands**: Scanning the JTAG instruction register for manufacturer test functions

## Fault injection corrupts security checks at the silicon level

Fault injection attacks deliberately cause CPU malfunctions to bypass security mechanisms. **Voltage glitching** briefly pulls the supply rail low using a MOSFET crowbar circuit, creating setup/hold time violations in CMOS logic. When voltage drops during a critical instruction—such as a signature verification branch—the CPU may skip the instruction entirely or corrupt the comparison result.

**Clock glitching** manipulates the clock signal to achieve similar effects. Inserting extra clock edges causes double-clocking, while removing edges creates instruction skips. The technique proves particularly effective against pipelined processors where instruction execution overlaps with decode operations.

**Electromagnetic Fault Injection (EMFI)** uses rapidly changing magnetic fields to induce localized faults without physical contact. A coil wound around a ferrite core, driven by several hundred volts, creates EM pulses that flip bits in specific chip regions. EMFI's spatial selectivity allows targeting individual subsystems—attacking the signature verification unit while leaving surrounding logic undisturbed.

The **ChipWhisperer platform** from NewAE Technology dominates open-source fault injection research. The entry-level ChipWhisperer-Lite ($250-300) provides both voltage and clock glitching with FPGA-based timing control. Critical parameters include:

| Parameter | Description | Typical Range |
|-----------|-------------|---------------|
| Glitch width | Duration of fault | 10ns - 1μs |
| Glitch offset | Delay from trigger | 0 - millions of cycles |
| Repeat | Consecutive pulses | 1 - 100+ |

The newer **ChipWhisperer-Husky** ($549) simplifies parameter tuning and adds a built-in logic analyzer for visualizing glitch effects. For EMFI, the **ChipSHOUTER** ($3,500+) provides professional-grade pulse generation, while the open-source **PicoEMP** ($50-133) offers budget-friendly EM injection with 1-4 second recovery between pulses.

Successful fault injection requires identifying vulnerable code points. Bootloader signature verification, password comparisons, and debug protection checks make ideal targets. Power trace analysis reveals when these operations execute—distinct computational patterns appear as characteristic waveforms that serve as trigger points.

## Real-world glitching attacks have compromised major platforms

The **Trezor One hardware wallet** attack demonstrated the complete fault injection chain. Researchers at Kraken Security Labs used voltage glitching to bypass the STM32F205's RDP protection, extracting the encrypted seed from flash. With physical access, a **4-digit PIN cracks in approximately 2 minutes**; a 9-digit PIN extends this to hours or days. The vulnerability exists in hardware and cannot be patched—users must rely on BIP39 passphrases for additional protection.

The **ESP32 secure boot bypass** (CVE-2020-13629) required approximately 35,000 EMFI experiments over 55 minutes to achieve three successful glitches. The attack window was just 10 microseconds after the bootloader copied to RAM, demonstrating how precise timing requirements make fault injection both challenging and ultimately achievable.

Xbox 360 security fell to the **Reset Glitch Attack**, where voltage manipulation during boot corrupted security checks and enabled unsigned code execution. This hack ran at scale, with modchips automating the glitch timing for consumer installation.

More recently, **AMD Secure Processor attacks** (2021) used voltage fault injection via the SVI2 interface to execute custom code on the AMD-SP, compromising SEV/SEV-SNP confidential computing protections and extracting VCEK seeds from production processors.

## Side-channel attacks extract secrets through unintended information leakage

Power consumption in CMOS circuits correlates with processed data through the **Hamming weight model**—operations on values with more bits set to '1' consume measurably more current. This data-dependent consumption enables key extraction without breaking cryptographic algorithms mathematically.

**Simple Power Analysis (SPA)** involves visual inspection of power traces to identify operations. The classic example targets RSA implementations using square-and-multiply exponentiation: multiplication operations create taller power spikes than squaring alone. By reading the spike pattern directly, an attacker recovers the private exponent bit-by-bit—tall spike indicates '1', shorter indicates '0'.

**Differential Power Analysis (DPA)** applies statistics to extract keys from noisy measurements. The attack collects thousands of power traces during cryptographic operations, then partitions them based on hypothetical intermediate values. The correct key hypothesis produces maximum correlation between predicted and actual power consumption. For **AES-128, DPA reduces the attack complexity from 2^128 brute force attempts to just 4,096 guesses** (16 bytes × 256 guesses per byte).

**Correlation Power Analysis (CPA)** refines DPA using Pearson correlation coefficients and precise leakage models. Attacks typically target the S-box output after the first AddRoundKey and SubBytes operations, where the relationship between known plaintext and hypothetical key bytes is most direct. Unprotected 8-bit AES implementations fall to CPA in fewer than 600 traces.

Measurement requires inserting a **shunt resistor** (1-100Ω) in series with the target's power supply, then capturing the voltage drop with an oscilloscope or dedicated capture hardware. ChipWhisperer devices include integrated measurement circuitry optimized for side-channel analysis.

**Electromagnetic analysis** offers advantages over direct power measurement: it requires no target modification, provides spatial selectivity through probe positioning, and can achieve higher signal-to-noise ratios by measuring near the cryptographic core. Near-field probes (Langer EMV-Technik RF1 set) operate from 30 MHz to 3 GHz, with probe size determining spatial resolution.

## Masking and hiding techniques defend against side-channel attacks

**Masking** splits sensitive variables into multiple shares where any d-1 shares reveal nothing about the original value. For Boolean masking, the secret s is split such that s = s₁ ⊕ s₂ ⊕ ... ⊕ sₐ, with all but one share generated randomly. Computations operate only on shares, preventing any single-point leakage. First-order masking protects against standard DPA; defeating d-order masking requires d+1 order attacks with exponentially more traces.

**Hiding techniques** reduce or obscure the signal rather than removing the correlation. Wave Dynamic Differential Logic (WDDL) uses dual-rail logic with constant power consumption regardless of processed data. Random delays between operations desynchronize traces, while noise injection increases the measurement baseline. Combined masking and hiding provides multiplicative security improvement.

**Constant-time implementations** eliminate timing variations entirely. The critical rule: secret information may only be used as input to operations where that input has no impact on execution time. This requires avoiding secret-dependent branches, memory accesses indexed by secrets, and variable-time instructions. Modern compilers may optimize away constant-time properties, necessitating verification at the assembly level.

## Certifications establish security evaluation standards

**FIPS 140-3** (effective September 2019, mandatory for new certifications since April 2022) defines four security levels with increasing physical protection requirements. Level 4 requires resistance to environmental attacks including voltage and temperature manipulation—effectively mandating fault injection countermeasures. Non-invasive security testing, including side-channel analysis, became explicit requirements in FIPS 140-3.

**Common Criteria** evaluates products against Evaluation Assurance Levels (EAL1-7), with vulnerability analysis (AVA_VAN) determining attack resistance requirements. **EAL5+ with AVA_VAN.5** is typical for smart cards and security modules, requiring demonstrated resistance to attackers with significant skills and specialized equipment.

**EMVCo** certification governs payment card security, with mandatory DPA/SPA testing since the late 1990s. The evaluation follows Joint Interpretation Library (JIL) methodology, assessing attack potential based on required expertise, time, and equipment cost.

**Test Vector Leakage Assessment (TVLA)** provides conformance testing without full key recovery. The Welch's t-test compares power traces from fixed versus random inputs; values exceeding **4.5 standard deviations** indicate detectable leakage with 99.999% confidence. TVLA detects vulnerability but doesn't quantify exploitability—failed tests may or may not enable practical key extraction.

## Secure boot establishes the foundation of embedded system trust

The secure boot chain validates each software stage before execution, anchored by an immutable **Root of Trust (RoT)** in ROM. The sequence flows from ROM bootloader (BL1) through secondary bootloader (SPL/BL2) to main bootloader (U-Boot/BL3) to the operating system, with each stage verifying the next's cryptographic signature against public keys stored in eFuses or OTP memory.

**U-Boot** dominates embedded Linux bootloaders, appearing in routers, IoT devices, e-readers, and industrial systems. Its extensive feature set creates substantial attack surface: network boot protocols (TFTP/NFS), filesystem parsers (ext4, squashfs), and image verification logic have all yielded critical vulnerabilities. CVE-2022-30790 enabled arbitrary write via IP defragmentation (CVSS 9.6), while CVE-2023-39902 allowed SPL authentication bypass on NXP i.MX 8M devices.

**ARM TrustZone** provides hardware-enforced isolation between Normal World and Secure World. The architecture defines exception levels from EL3 (Secure Monitor) down through S-EL1 (Secure Kernel) and S-EL0 (Secure Userspace). Trusted Execution Environments (TEEs) like Qualcomm QSEE, Samsung TEEGRIS, and OP-TEE run in Secure World, theoretically protected from Normal World compromise.

TrustZone attacks target multiple surfaces: SMC (Secure Monitor Call) handlers bridging worlds, vulnerabilities in third-party trustlets, and the secure boot chain itself. The **downgrade attack** proves particularly effective—loading older, vulnerable trustlet versions since verification keys remain unchanged across versions. This technique enabled complete TrustZone compromise on Google Nexus devices, Samsung Galaxy phones, and Huawei handsets.

**TPM-FAIL** (CVE-2019-11090, CVE-2019-16863) demonstrated timing attacks against TPM ECDSA implementations. Intel fTPM keys could be recovered in **4-20 minutes with local access**; VPN server keys fell in approximately 5 hours remotely. Physical TPMs communicating over the LPC bus are vulnerable to VMK sniffing during BitLocker unlock.

## Manufacturing test modes frequently persist into production

Development conveniences often become security vulnerabilities when devices ship without disabling debug features. **Hidden UART consoles** commonly expose root shells without authentication—simply connecting at the correct baud rate (usually 115200) yields full system access. These interfaces appear as 3-4 pin headers near power regulators, identifiable by TX pin voltage fluctuation during boot.

**Manufacturing test modes** include ISP (In-System Programming), DFU (Device Firmware Update), and BIST (Built-In Self-Test) interfaces. Allwinner SoCs enter FEL mode by shorting specific pins during reset, providing raw memory access regardless of secure boot configuration. MediaTek devices expose similar functionality through BROM (Boot ROM) interfaces.

## Lab setup requirements for hardware security testing

A functional hardware security lab requires several equipment categories. **Oscilloscopes** need sufficient bandwidth (100-350 MHz minimum) and sample rate (1 GSa/s+) to capture sub-clock-cycle detail. Budget options include the Rigol DS1054Z (~$375) and Siglent SDS1104X-E (~$500).

**Soldering equipment** must handle fine-pitch SMD work—temperature-controlled stations from Hakko, Weller, or the Pine64 PINECIL ($25) prove essential. Hot air rework stations enable component removal without PCB damage.

**Probing solutions** range from PCBite systems for hands-free test point access to specialized clips (SOIC, TSOP) for memory chips. Quality SMA cables and proper grounding prevent signal integrity issues during capture.

For **fault injection specifically**, remove filtering capacitors near target VCC to sharpen glitch delivery. Short cable runs between glitcher and target minimize propagation effects. FPGA-based trigger systems (included in ChipWhisperer platforms) provide the microsecond-precision timing that successful glitching requires.

## Conclusion

Hardware security assessment demands both broad knowledge and deep specialization. The techniques documented here—from basic UART discovery through advanced EMFI attacks—form a progressive skill set where each capability enables the next. Memory extraction provides the firmware for reverse engineering. Debug interfaces reveal runtime behavior. Fault injection bypasses protections that withstand all other attacks. Side-channel analysis extracts secrets from implementations that appear cryptographically sound.

Defensive thinking must parallel offensive capability. Proper secure boot implementation, debug interface hardening, fault injection countermeasures, and side-channel resistant cryptography represent the minimum baseline for security-critical embedded systems. Certification programs (FIPS 140-3, Common Criteria, EMVCo) provide evaluation frameworks, but attackers operate outside laboratory constraints—real-world security requires defense in depth across all documented attack surfaces.