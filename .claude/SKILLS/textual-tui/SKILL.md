---
name: textual-tui
description: Principles and best practices for designing clean, intuitive terminal user interfaces with excellent UX and visual hierarchy.
---

# Terminal User Interface Design Principles

This skill provides guidance for creating professional, intuitive TUI applications that users find pleasant and efficient to work with.

## When to Use This Skill

- Designing new TUI layouts and workflows
- Improving user experience and discoverability
- Creating consistent visual hierarchy
- Planning keyboard-driven interfaces
- Designing information-dense displays
- Building multi-panel or split-view interfaces

---

## Core Design Principles

### 1. Progressive Disclosure

**Principle**: Show simple interfaces first, reveal complexity only when needed.

**Good:**
```
┌─ Devices ───────────────────┐
│ ● Bus Pirate 5              │
│ ○ Curious Bolt              │
│                             │
│ [Refresh]                   │
└─────────────────────────────┘
```

**Bad:**
```
┌─ Devices ───────────────────┐
│ Bus Pirate 5               │
│ VID: 0x1209 PID: 0x7331    │
│ Serial: BP0000001          │
│ Firmware: 1.2.3            │
│ Capabilities: [SPI, I2C..]  │
│ Connection: USB 2.0        │
│ [Connect] [Disconnect]     │
│ [Configure] [Advanced...]  │
│                             │
│ Curious Bolt               │
│ VID: 0x2E8A PID: 0x000A    │
│ ...                         │
└─────────────────────────────┘
```

**Why**: Users need to see connected devices immediately. Details can be revealed on selection or in a details panel.

**Application**:
- Start with a simple device list
- Show details in a side panel when selected
- Hide advanced options behind an "Advanced..." button or separate screen

---

### 2. Visual Hierarchy

**Principle**: Use borders, colors, and spacing to show importance and relationships.

**Good Layout:**
```
┌─────────────────────────────────────────────────┐
│ hwh - Hardware Hacking Toolkit                  │  ← Header: App identity
├─────────────────────────────────────────────────┤
│ F1:Devices  F2:Firmware  F3:Split  F12:Help    │  ← Tab bar: Primary navigation
├──────────────┬──────────────────────────────────┤
│              │                                  │
│   Devices    │  ┌─ Bus Pirate 5 ───────────┐  │
│              │  │                           │  │
│ ● Bus Pirate │  │ Status: Connected         │  │  ← Clear borders define regions
│ ○ Bolt       │  │ Port: /dev/ttyACM0       │  │
│              │  │                           │  │
│              │  │ [SPI] [I2C] [UART]       │  │
│              │  │                           │  │
│              │  └───────────────────────────┘  │
│              │                                  │
├──────────────┴──────────────────────────────────┤
│ F5:Refresh  Ctrl+Q:Quit                        │  ← Footer: Global shortcuts
└─────────────────────────────────────────────────┘
```

**Hierarchy Elements:**
- **Double borders**: Primary containers (main panels)
- **Single borders**: Secondary elements (cards, groups)
- **No borders**: Tertiary content (text, lists)
- **Color**: Success (green), errors (red), warnings (yellow), info (cyan)
- **Spacing**: Related items grouped, unrelated items separated

---

### 3. Keyboard-First Navigation

**Principle**: Every action should be reachable via keyboard. Mouse is optional.

**Standard Conventions:**
- **F1-F12**: Primary views/modes
- **Ctrl+[key]**: Global actions (Ctrl+Q quit, Ctrl+S save)
- **Tab/Shift+Tab**: Cycle between focusable elements
- **Enter**: Activate/confirm
- **Escape**: Cancel/go back/close modal
- **Arrow keys**: Navigate lists/tables
- **Space**: Toggle checkboxes/switches
- **Home/End**: Jump to start/end
- **Page Up/Down**: Scroll large areas

**Discoverability:**
- Show key bindings in footer: `F5:Refresh  F12:Help  Ctrl+Q:Quit`
- Use Help screen (F12) to list all shortcuts
- Show shortcuts in buttons: `[R]efresh` highlights the mnemonic key

**Example Footer:**
```
┌─────────────────────────────────────────────────┐
│ F1:Devices  F2:Firmware  F3:Split  F5:Refresh  │
│ Ctrl+Q:Quit                                     │
└─────────────────────────────────────────────────┘
```

---

### 4. Status Indicators

**Principle**: System state should be visible at a glance.

**Connection Status:**
- **● Green**: Connected and active
- **○ Gray**: Disconnected or inactive
- **◐ Yellow**: Connecting/busy
- **✗ Red**: Error state

**Example:**
```
Devices:
● Bus Pirate 5        Connected
◐ Curious Bolt        Connecting...
✗ Tigard              Error: Permission denied
○ ST-Link             Disconnected
```

**Progress Indicators:**
```
Dumping flash: [████████████░░░░░░░░] 65% (512 KB / 1024 KB)
```

**Real-time Status:**
```
┌─ Status ─────────────────┐
│ Glitch:    Armed         │  ← State
│ Trigger:   External      │
│ Attempts:  1,247         │  ← Counter
│ Success:   3             │  ← Important metric
│ Elapsed:   00:02:15      │  ← Time
└──────────────────────────┘
```

---

### 5. Information Density vs. Clarity

**Principle**: Pack information efficiently without overwhelming users.

**Hexadecimal Dump** (Information-dense but readable):
```
┌─ Firmware: router.bin ──────────────────────────────┐
│ 00000000  7F 45 4C 46 02 01 01 00  00 00 00 00 00 │ .ELF........... │
│ 00000010  02 00 B7 00 01 00 00 00  80 10 00 00 00 │ ............... │
│ 00000020  00 00 00 00 00 00 00 34  00 00 00 00 00 │ .......4....... │
└─────────────────────────────────────────────────────┘
         ↑              ↑               ↑
      Address        Hex bytes       ASCII
```

**Data Table** (Scannable structure):
```
┌─ Glitch Results ─────────────────────────────────────┐
│ Delay  Width  Result  Details                        │
├──────────────────────────────────────────────────────┤
│  500    100    SUC    "ACCESS GRANTED"               │ ← Green highlight
│  500    110    NRM    "Access denied"                │
│  500    120    RST    [no response]                  │ ← Yellow
│  510    100    HNG    [timeout]                      │ ← Red
└──────────────────────────────────────────────────────┘
```

**Guidelines:**
- Use tables for structured data
- Use monospace for technical output (hex, logs)
- Group related fields visually
- Use color sparingly for emphasis
- Truncate long strings with ellipsis: `"Very long message th..."`

---

### 6. Feedback and Affordances

**Principle**: Users should know what's clickable and get immediate feedback.

**Button States:**
```
[  Connect  ]     ← Default
[ >Connect< ]     ← Focused (keyboard navigation)
[**Connect**]     ← Pressed (visual feedback)
[╳ Connect  ]     ← Disabled (unavailable)
```

**Loading States:**
```
[  Connect  ]  →  [ ⟳ Connecting... ]  →  [ ✓ Connected ]
```

**Notifications:**
```
┌─────────────────────────────────────┐
│ ✓ Device connected successfully     │  ← Success (auto-dismiss)
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ ⚠ Connection lost, retrying...      │  ← Warning (stays visible)
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ ✗ Permission denied: /dev/ttyUSB0   │  ← Error (requires user action)
│   [Retry]  [Close]                  │
└─────────────────────────────────────┘
```

**Principles:**
- **Instant feedback**: Button press should feel responsive (<100ms)
- **Clear affordances**: Buttons look clickable, borders indicate focus
- **Appropriate persistence**: Errors require acknowledgment, success auto-dismisses
- **Error recovery**: Offer retry/fix options, not just "OK"

---

### 7. Modal vs. Modeless

**Principle**: Use modals sparingly, prefer inline actions.

**Good (Inline):**
```
┌─ Devices ───────────────┐
│ ● Bus Pirate 5          │ ← Click to expand
│   Port: /dev/ttyACM0    │ ← Inline detail
│   [Disconnect]          │
│                         │
│ ○ Curious Bolt          │
│   [Connect]             │
└─────────────────────────┘
```

**When to Use Modals:**
- Destructive actions requiring confirmation
- Complex multi-field forms
- Critical information that demands attention
- Blocking operations (e.g., "Applying firmware update...")

**Modal Example:**
```
┌────────────────────────────────────────┐
│              Erase Flash?              │
│                                        │
│  This will permanently erase all data  │
│  on the flash chip. This cannot be     │
│  undone.                               │
│                                        │
│  [ Cancel ]  [ Erase Flash Chip ]      │
│                   ↑                    │
│             Dangerous action (red)     │
└────────────────────────────────────────┘
```

---

### 8. Consistent Layout Patterns

**Principle**: Similar tasks should have similar interfaces.

**Standard Panel Structure:**
```
┌─ [Panel Name] ──────────────────────┐
│                                     │  ← Title bar
├─────────────────────────────────────┤
│ [Primary Actions]                   │  ← Action toolbar
├─────────────────────────────────────┤
│                                     │
│   Main Content Area                 │  ← Content
│                                     │
├─────────────────────────────────────┤
│ Status: Ready  |  00:01:23          │  ← Status bar
└─────────────────────────────────────┘
```

**Apply consistently:**
- Device panels: All use same structure
- Configuration forms: Same field ordering
- Results displays: Same table format
- Error messages: Same icon and color

---

### 9. Split Views and Multi-Panel

**Principle**: Allow users to monitor multiple things simultaneously.

**Horizontal Split (Side-by-Side):**
```
┌──────────────────┬──────────────────┐
│                  │                  │
│  Bus Pirate      │  Curious Bolt    │
│  UART Monitor    │  Glitcher        │
│                  │                  │
│  > login:        │  Width:  350ns   │
│  > admin         │  Repeat: 1000    │
│  > Password:     │                  │
│  >               │  [ARM] [FIRE]    │
│                  │                  │
└──────────────────┴──────────────────┘
     Monitor              Control
```

**Vertical Split (Top/Bottom):**
```
┌─────────────────────────────────────┐
│  Target Output (UART)               │
│                                     │
│  > Boot sequence starting...        │
│  > Checking flash integrity...      │
│  > ACCESS GRANTED ← Success!        │
├─────────────────────────────────────┤
│  Logic Analyzer (SPI)               │
│                                     │
│  ─┐ CS                              │
│   ┝━━┯━━┯━━┯━━━━━━━━━━━━━━━━━━━━━  │
│  ━┷━┷━┷━┷━ MOSI                     │
│    │ │ │ └─ Data bytes...           │
│    │ │ └─── READ (0x03)             │
└─────────────────────────────────────┘
```

**Guidelines:**
- Resizable dividers (drag to adjust)
- Equal space by default, resize to emphasize
- Clear visual separation (borders)
- Independent scrolling per panel
- Toggle split view (F3 key)

---

### 10. Color Palette

**Principle**: Use color meaningfully, not decoratively.

**Semantic Colors:**
- **Green**: Success, connected, safe operations
- **Red**: Errors, dangerous actions, critical states
- **Yellow**: Warnings, in-progress, attention needed
- **Cyan**: Information, hints, secondary actions
- **Gray**: Disabled, inactive, less important

**Background Palette (Dark Theme):**
- **Surface**: `#1A1B1F` (darkest - main background)
- **Surface+1**: `#232428` (containers, cards)
- **Surface+2**: `#2C2D32` (elevated elements, modals)
- **Border**: `#3A3B40` (dividers, outlines)

**Text:**
- **Primary**: `#E0E0E0` (high contrast)
- **Secondary**: `#A0A0A0` (less important)
- **Disabled**: `#606060` (inactive)

**Accent:**
- **Primary**: `#4A9EFF` (interactive elements)
- **Success**: `#4CAF50`
- **Warning**: `#FFA726`
- **Error**: `#F44336`

**Example:**
```
┌─ Glitch Results ─────────────────┐
│ Delay  Width  Result             │
├───────────────────────────────────┤
│  500    100    [SUC] (green)     │
│  500    110    [NRM] (gray)      │
│  500    120    [RST] (yellow)    │
│  510    100    [HNG] (red)       │
└───────────────────────────────────┘
```

---

## Layout Patterns

### Master-Detail

**Use for**: Device lists, file browsers, configuration panels

```
┌────────────┬─────────────────────────────┐
│  Master    │  Detail                     │
│            │                             │
│ Device 1   │  ┌─ Device 1 Details ────┐ │
│>Device 2   │  │ Name: Bus Pirate 5    │ │
│ Device 3   │  │ Port: /dev/ttyACM0    │ │
│            │  │ Firmware: v1.2.3      │ │
│            │  │                        │ │
│            │  │ [Configure]            │ │
│            │  └────────────────────────┘ │
└────────────┴─────────────────────────────┘
```

### Tabbed

**Use for**: Multiple independent views, modes, or tools

```
┌─────────────────────────────────────────┐
│ [Devices] [Firmware] [Coordination]     │ ← Tabs
├─────────────────────────────────────────┤
│                                         │
│         Tab Content Here                │
│                                         │
└─────────────────────────────────────────┘
```

### Dashboard

**Use for**: Monitoring multiple metrics simultaneously

```
┌───────────┬──────────┬──────────────┐
│ Voltage   │ Current  │ Temperature  │
│  3.30V    │  125mA   │    42°C      │
├───────────┴──────────┴──────────────┤
│  Power Trace (live)                 │
│  ▁▂▃▅▇█▇▅▃▂▁▂▃▅▇█▇▅▃▂▁           │
├─────────────────────────────────────┤
│  Glitch Attempts: 1,247             │
│  Success Rate:    0.24%             │
└─────────────────────────────────────┘
```

### Wizard/Flow

**Use for**: Multi-step processes, configuration, onboarding

```
┌────────────────────────────────────┐
│  Step 1 of 3: Device Selection     │ ← Progress
├────────────────────────────────────┤
│                                    │
│  Select hardware device:           │
│  ○ Bus Pirate 5                    │
│  ● Curious Bolt                    │
│  ○ Tigard                          │
│                                    │
│              [Next →]              │ ← Navigation
└────────────────────────────────────┘
```

---

## Common Widgets and When to Use Them

### Lists
**Use for**: Devices, files, options, results
- Simple selection
- Scrollable
- Single or multi-select

### Tables
**Use for**: Structured data with multiple columns
- Sortable headers
- Row selection
- Aligned columns

### Trees
**Use for**: Hierarchical data
- File systems
- JSON/XML structures
- Nested configurations

### Forms
**Use for**: User input
- Labels + inputs
- Validation feedback
- Submit button

### Progress Bars
**Use for**: Long-running operations
- Determinate (known duration): `[████░░░░] 50%`
- Indeterminate (unknown): `[⟳ Working...]`

### Logs/Console
**Use for**: Real-time output
- Auto-scroll to bottom
- Color-coded levels
- Timestamp prefix

### Sparklines
**Use for**: Trend visualization in small space
- Power consumption
- Network traffic
- Temperature over time

---

## Accessibility Principles

1. **Keyboard Navigation**: Every action reachable via keyboard
2. **Clear Focus**: Visible focus indicator (bracket, highlight, border)
3. **Meaningful Colors**: Don't rely on color alone (use icons + text)
4. **Consistent Language**: Same terms for same concepts
5. **Error Messages**: Specific and actionable, not just "Error"

---

## Performance Considerations

1. **Lazy Loading**: Load large datasets incrementally
2. **Virtual Scrolling**: Only render visible rows in long lists
3. **Throttle Updates**: Don't update UI faster than ~30fps
4. **Pagination**: Break huge datasets into pages
5. **Async Operations**: Never block UI for I/O

---

## Testing Your Design

**Questions to ask:**

1. **Discoverability**: Can a new user find core features within 30 seconds?
2. **Efficiency**: Can an expert user complete tasks with minimal keystrokes?
3. **Feedback**: Is every action acknowledged immediately?
4. **Error Recovery**: Can users undo or retry failed actions?
5. **Consistency**: Do similar things work similarly?
6. **Information Hierarchy**: Can you identify the most important info at a glance?

---

## Anti-Patterns to Avoid

❌ **Don't**: Bury actions in nested menus
✅ **Do**: Put common actions in visible buttons/shortcuts

❌ **Don't**: Use color as the only indicator
✅ **Do**: Combine color with icons and text

❌ **Don't**: Block UI for long operations
✅ **Do**: Show progress, allow cancellation

❌ **Don't**: Use technical jargon in UI labels
✅ **Do**: Use clear, user-friendly language

❌ **Don't**: Make every feature visible at once
✅ **Do**: Progressive disclosure - simple first, complexity on demand

❌ **Don't**: Ignore keyboard users
✅ **Do**: Every action accessible via keyboard

❌ **Don't**: Flash UI updates rapidly
✅ **Do**: Throttle updates to reasonable rate

---

## Example: Well-Designed Device Panel

```
┌─ Bus Pirate 5 ─────────────────────────────────────┐
│ ● Connected  /dev/ttyACM0  v1.2.3     [Disconnect] │ ← Status + Quick Action
├────────────────────────────────────────────────────┤
│ [SPI] [I2C] [UART] [Logic Analyzer]               │ ← Mode Switcher
├────────────────────────────────────────────────────┤
│                                                    │
│ ┌─ SPI Configuration ────────────────────────┐    │
│ │ Speed: [1 MHz      ▼]                      │    │ ← Form
│ │ Mode:  [Mode 0     ▼]                      │    │
│ │ CS:    [Pin 0      ▼]                      │    │
│ │                                             │    │
│ │         [Apply]                             │    │
│ └─────────────────────────────────────────────┘    │
│                                                    │
│ ┌─ Operations ──────────────────────────────┐     │
│ │ [Read Flash ID]                           │     │ ← Actions
│ │ [Dump Flash]                              │     │
│ │ [Erase Chip]  ⚠                           │     │
│ └───────────────────────────────────────────┘     │
│                                                    │
│ ┌─ Console ────────────────────────────────┐      │
│ │ > Flash ID: EF 40 18 (Winbond W25Q128)   │      │ ← Output
│ │ > Ready.                                  │      │
│ └───────────────────────────────────────────┘     │
│                                                    │
├────────────────────────────────────────────────────┤
│ Status: Ready  |  00:00:15                        │ ← Footer
└────────────────────────────────────────────────────┘
```

**What makes this good:**
- Status visible at top
- Quick disconnect button
- Clear mode tabs
- Grouped related controls
- Visual hierarchy (borders)
- Dangerous action (Erase) marked with ⚠
- Live feedback in console
- Footer shows state and timer

---

## References

- Nielsen Norman Group: https://www.nngroup.com/
- Stripe's TUI Design Principles
- Charm Bracelet TUI Gallery: https://charm.sh/
- Material Design (adapted for TUI)
