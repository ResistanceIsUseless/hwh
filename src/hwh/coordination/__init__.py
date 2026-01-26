"""
Coordination Module - Multi-device trigger routing.

Provides infrastructure for coordinating multiple hardware devices
in attack scenarios, such as:
- UART pattern detection → glitch triggering
- Power threshold monitoring → fault injection
- Debug breakpoint → glitch timing
- Multi-device synchronized captures

Example:
    >>> from hwh.coordination import Coordinator, TriggerRoute
    >>> from hwh.coordination.triggers import (
    ...     TriggerType, TriggerCondition, TriggerAction, ActionType
    ... )
    >>>
    >>> coord = Coordinator()
    >>>
    >>> # Add a route: UART "Password:" → trigger glitch
    >>> coord.add_uart_glitch_route(
    ...     name="password_bypass",
    ...     uart_device="buspirate",
    ...     glitch_device="bolt",
    ...     pattern=r"Password:",
    ...     width_ns=100,
    ...     offset_ns=500
    ... )
    >>>
    >>> await coord.arm()  # Start monitoring
"""

from .triggers import (
    TriggerType,
    TriggerEdge,
    ActionType,
    RoutingMode,
    TriggerCondition,
    TriggerAction,
    TriggerRoute,
    TriggerMatcher,
    # Template functions
    uart_password_trigger,
    uart_boot_trigger,
    power_drop_trigger,
    glitch_action,
    gpio_pulse_action,
)

from .coordinator import (
    Coordinator,
    TriggerEvent,
    get_coordinator,
)

__all__ = [
    # Enums
    "TriggerType",
    "TriggerEdge",
    "ActionType",
    "RoutingMode",
    # Classes
    "TriggerCondition",
    "TriggerAction",
    "TriggerRoute",
    "TriggerMatcher",
    "Coordinator",
    "TriggerEvent",
    # Functions
    "get_coordinator",
    "uart_password_trigger",
    "uart_boot_trigger",
    "power_drop_trigger",
    "glitch_action",
    "gpio_pulse_action",
]
