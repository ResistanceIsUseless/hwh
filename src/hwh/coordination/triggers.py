"""
Trigger definitions for multi-device coordination.

Defines conditions that can trigger actions on other devices.
"""

import re
import asyncio
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, Any, List


class TriggerType(Enum):
    """Types of trigger conditions."""
    UART_PATTERN = auto()      # Regex match on UART data
    SPI_TRANSACTION = auto()   # SPI command detected
    I2C_ADDRESS = auto()       # I2C address access
    POWER_THRESHOLD = auto()   # ADC crosses threshold
    GPIO_EDGE = auto()         # GPIO pin change
    MEMORY_VALUE = auto()      # Memory location matches value
    TIME_DELAY = auto()        # Delay after another event
    MANUAL = auto()            # Manual trigger via UI


class TriggerEdge(Enum):
    """Edge type for threshold/GPIO triggers."""
    RISING = auto()
    FALLING = auto()
    BOTH = auto()


class ActionType(Enum):
    """Types of actions to perform when triggered."""
    GLITCH = auto()            # Trigger a glitch
    GPIO_PULSE = auto()        # Pulse a GPIO pin
    CAPTURE_START = auto()     # Start logic analyzer capture
    CAPTURE_STOP = auto()      # Stop capture
    LOG_EVENT = auto()         # Log the event
    CUSTOM = auto()            # Custom callback


class RoutingMode(Enum):
    """How the trigger is routed."""
    SOFTWARE = auto()          # Via USB/software (1-10ms latency)
    HARDWARE = auto()          # Via GPIO wire (<1μs latency)
    HYBRID = auto()            # Software detect + hardware trigger


@dataclass
class TriggerCondition:
    """
    Defines when a trigger should fire.

    Examples:
        # UART pattern trigger
        TriggerCondition(
            trigger_type=TriggerType.UART_PATTERN,
            config={"pattern": r"Password:.*", "timeout_ms": 5000}
        )

        # Power threshold trigger
        TriggerCondition(
            trigger_type=TriggerType.POWER_THRESHOLD,
            config={"threshold_mv": 2500, "edge": TriggerEdge.FALLING}
        )
    """
    trigger_type: TriggerType
    config: Dict[str, Any] = field(default_factory=dict)
    name: str = ""
    enabled: bool = True

    def __post_init__(self):
        if not self.name:
            self.name = f"{self.trigger_type.name.lower()}"

    def validate(self) -> bool:
        """Validate the trigger configuration."""
        if self.trigger_type == TriggerType.UART_PATTERN:
            if "pattern" not in self.config:
                return False
            try:
                re.compile(self.config["pattern"])
            except re.error:
                return False
        elif self.trigger_type == TriggerType.POWER_THRESHOLD:
            if "threshold_mv" not in self.config:
                return False
        elif self.trigger_type == TriggerType.GPIO_EDGE:
            if "pin" not in self.config:
                return False
        return True


@dataclass
class TriggerAction:
    """
    Defines what happens when a trigger fires.

    Examples:
        # Glitch action
        TriggerAction(
            action_type=ActionType.GLITCH,
            config={"width_ns": 100, "offset_ns": 500}
        )

        # GPIO pulse action
        TriggerAction(
            action_type=ActionType.GPIO_PULSE,
            config={"pin": 3, "duration_us": 10}
        )
    """
    action_type: ActionType
    config: Dict[str, Any] = field(default_factory=dict)
    callback: Optional[Callable] = None


@dataclass
class TriggerRoute:
    """
    Routes a trigger condition to an action on another device.

    Example:
        # UART pattern on Bus Pirate triggers glitch on Bolt
        route = TriggerRoute(
            name="password_glitch",
            source_device="buspirate",
            condition=TriggerCondition(
                trigger_type=TriggerType.UART_PATTERN,
                config={"pattern": r"Password:"}
            ),
            target_device="bolt",
            action=TriggerAction(
                action_type=ActionType.GLITCH,
                config={"width_ns": 100, "offset_ns": 500}
            ),
            routing_mode=RoutingMode.SOFTWARE
        )
    """
    name: str
    source_device: str
    condition: TriggerCondition
    target_device: str
    action: TriggerAction
    routing_mode: RoutingMode = RoutingMode.SOFTWARE
    enabled: bool = True

    # Statistics
    trigger_count: int = 0
    last_trigger_time: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for storage/display."""
        return {
            "name": self.name,
            "source_device": self.source_device,
            "condition": {
                "type": self.condition.trigger_type.name,
                "config": self.condition.config,
            },
            "target_device": self.target_device,
            "action": {
                "type": self.action.action_type.name,
                "config": self.action.config,
            },
            "routing_mode": self.routing_mode.name,
            "enabled": self.enabled,
            "trigger_count": self.trigger_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TriggerRoute":
        """Deserialize from dictionary."""
        condition = TriggerCondition(
            trigger_type=TriggerType[data["condition"]["type"]],
            config=data["condition"]["config"],
        )
        action = TriggerAction(
            action_type=ActionType[data["action"]["type"]],
            config=data["action"]["config"],
        )
        return cls(
            name=data["name"],
            source_device=data["source_device"],
            condition=condition,
            target_device=data["target_device"],
            action=action,
            routing_mode=RoutingMode[data.get("routing_mode", "SOFTWARE")],
            enabled=data.get("enabled", True),
        )


class TriggerMatcher:
    """
    Matches incoming data against trigger conditions.
    """

    def __init__(self):
        self._uart_buffer: Dict[str, str] = {}  # device_id -> buffer
        self._buffer_size = 4096

    def append_uart_data(self, device_id: str, data: str) -> None:
        """Append data to device's UART buffer."""
        if device_id not in self._uart_buffer:
            self._uart_buffer[device_id] = ""

        self._uart_buffer[device_id] += data

        # Trim if too large
        if len(self._uart_buffer[device_id]) > self._buffer_size:
            self._uart_buffer[device_id] = self._uart_buffer[device_id][-self._buffer_size:]

    def check_uart_pattern(self, device_id: str, pattern: str) -> Optional[re.Match]:
        """Check if pattern matches in device's UART buffer."""
        buffer = self._uart_buffer.get(device_id, "")
        return re.search(pattern, buffer)

    def clear_uart_buffer(self, device_id: str) -> None:
        """Clear device's UART buffer after match."""
        self._uart_buffer[device_id] = ""

    def check_condition(
        self,
        condition: TriggerCondition,
        device_id: str,
        context: Dict[str, Any] = None
    ) -> bool:
        """
        Check if a trigger condition is met.

        Args:
            condition: The condition to check
            device_id: Source device ID
            context: Additional context (power readings, GPIO states, etc.)

        Returns:
            True if condition is met
        """
        context = context or {}

        if not condition.enabled:
            return False

        if condition.trigger_type == TriggerType.UART_PATTERN:
            pattern = condition.config.get("pattern", "")
            match = self.check_uart_pattern(device_id, pattern)
            if match:
                # Store match in context for use by action
                context["match"] = match
                return True

        elif condition.trigger_type == TriggerType.POWER_THRESHOLD:
            threshold = condition.config.get("threshold_mv", 0)
            current_mv = context.get("power_mv", 0)
            edge = condition.config.get("edge", TriggerEdge.BOTH)
            previous_mv = context.get("previous_power_mv", current_mv)

            if edge == TriggerEdge.RISING:
                return previous_mv < threshold <= current_mv
            elif edge == TriggerEdge.FALLING:
                return previous_mv > threshold >= current_mv
            else:  # BOTH
                crossed = (previous_mv < threshold <= current_mv or
                          previous_mv > threshold >= current_mv)
                return crossed

        elif condition.trigger_type == TriggerType.GPIO_EDGE:
            pin = condition.config.get("pin", 0)
            edge = condition.config.get("edge", TriggerEdge.BOTH)
            gpio_state = context.get("gpio_state", {})
            previous_state = context.get("previous_gpio_state", {})

            current = gpio_state.get(pin, 0)
            previous = previous_state.get(pin, current)

            if edge == TriggerEdge.RISING:
                return previous == 0 and current == 1
            elif edge == TriggerEdge.FALLING:
                return previous == 1 and current == 0
            else:
                return previous != current

        elif condition.trigger_type == TriggerType.MANUAL:
            # Manual triggers are always checked via explicit trigger call
            return context.get("manual_trigger", False)

        return False


# Predefined trigger templates for common scenarios

def uart_password_trigger(pattern: str = r"Password:") -> TriggerCondition:
    """Create a UART trigger for password prompts."""
    return TriggerCondition(
        trigger_type=TriggerType.UART_PATTERN,
        config={"pattern": pattern},
        name="password_prompt"
    )


def uart_boot_trigger(pattern: str = r"Booting|Starting|U-Boot") -> TriggerCondition:
    """Create a UART trigger for boot messages."""
    return TriggerCondition(
        trigger_type=TriggerType.UART_PATTERN,
        config={"pattern": pattern},
        name="boot_message"
    )


def power_drop_trigger(threshold_mv: int = 2500) -> TriggerCondition:
    """Create a power threshold trigger for voltage drops."""
    return TriggerCondition(
        trigger_type=TriggerType.POWER_THRESHOLD,
        config={"threshold_mv": threshold_mv, "edge": TriggerEdge.FALLING},
        name="power_drop"
    )


def glitch_action(width_ns: int = 100, offset_ns: int = 500, repeat: int = 1) -> TriggerAction:
    """Create a glitch action with specified parameters."""
    return TriggerAction(
        action_type=ActionType.GLITCH,
        config={"width_ns": width_ns, "offset_ns": offset_ns, "repeat": repeat}
    )


def gpio_pulse_action(pin: int, duration_us: int = 10) -> TriggerAction:
    """Create a GPIO pulse action."""
    return TriggerAction(
        action_type=ActionType.GPIO_PULSE,
        config={"pin": pin, "duration_us": duration_us}
    )
