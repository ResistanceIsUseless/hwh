"""
Multi-device Coordinator

Manages trigger routing between multiple hardware devices for coordinated attacks.
"""

import asyncio
import time
from typing import Dict, Optional, List, Callable, Any
from dataclasses import dataclass, field

from .triggers import (
    TriggerRoute, TriggerCondition, TriggerAction, TriggerMatcher,
    TriggerType, ActionType, RoutingMode, TriggerEdge
)
from ..tui.device_pool import DevicePool, DeviceRole, get_global_pool
from ..backends import Backend, GlitchBackend, BusBackend


@dataclass
class TriggerEvent:
    """Record of a trigger event."""
    timestamp: float
    route_name: str
    source_device: str
    target_device: str
    action_type: str
    success: bool
    details: str = ""


class Coordinator:
    """
    Coordinates trigger routing between multiple hardware devices.

    The Coordinator monitors source devices for trigger conditions and
    executes actions on target devices when conditions are met.

    Example:
        >>> coord = Coordinator()
        >>> coord.add_route(TriggerRoute(
        ...     name="uart_glitch",
        ...     source_device="buspirate",
        ...     condition=TriggerCondition(
        ...         trigger_type=TriggerType.UART_PATTERN,
        ...         config={"pattern": r"Password:"}
        ...     ),
        ...     target_device="bolt",
        ...     action=TriggerAction(
        ...         action_type=ActionType.GLITCH,
        ...         config={"width_ns": 100, "offset_ns": 500}
        ...     )
        ... ))
        >>> await coord.arm()
        >>> # Coordinator now monitors Bus Pirate UART for "Password:"
        >>> # and triggers glitch on Bolt when detected
    """

    def __init__(self, device_pool: Optional[DevicePool] = None):
        """
        Initialize the coordinator.

        Args:
            device_pool: DevicePool instance. If None, uses global pool.
        """
        self.pool = device_pool or get_global_pool()
        self.routes: Dict[str, TriggerRoute] = {}
        self.matcher = TriggerMatcher()
        self.events: List[TriggerEvent] = []

        self._armed = False
        self._monitoring_task: Optional[asyncio.Task] = None
        self._uart_tasks: Dict[str, asyncio.Task] = {}

        # Callbacks for UI integration
        self._on_trigger: Optional[Callable[[TriggerEvent], None]] = None
        self._on_status_change: Optional[Callable[[str], None]] = None
        self._log_callback: Optional[Callable[[str], None]] = None

    def set_callbacks(
        self,
        on_trigger: Optional[Callable[[TriggerEvent], None]] = None,
        on_status_change: Optional[Callable[[str], None]] = None,
        log_callback: Optional[Callable[[str], None]] = None
    ) -> None:
        """Set callbacks for UI integration."""
        self._on_trigger = on_trigger
        self._on_status_change = on_status_change
        self._log_callback = log_callback

    def log(self, message: str) -> None:
        """Log a message."""
        if self._log_callback:
            self._log_callback(message)

    def add_route(self, route: TriggerRoute) -> bool:
        """
        Add a trigger route.

        Args:
            route: The trigger route to add

        Returns:
            True if added successfully
        """
        if not route.condition.validate():
            self.log(f"Invalid condition for route {route.name}")
            return False

        self.routes[route.name] = route
        self.log(f"Added route: {route.name} ({route.source_device} → {route.target_device})")
        return True

    def remove_route(self, name: str) -> bool:
        """Remove a route by name."""
        if name in self.routes:
            del self.routes[name]
            self.log(f"Removed route: {name}")
            return True
        return False

    def get_route(self, name: str) -> Optional[TriggerRoute]:
        """Get a route by name."""
        return self.routes.get(name)

    def enable_route(self, name: str) -> bool:
        """Enable a route."""
        if name in self.routes:
            self.routes[name].enabled = True
            return True
        return False

    def disable_route(self, name: str) -> bool:
        """Disable a route."""
        if name in self.routes:
            self.routes[name].enabled = False
            return True
        return False

    def list_routes(self) -> List[TriggerRoute]:
        """Get all routes."""
        return list(self.routes.values())

    async def arm(self) -> bool:
        """
        Arm the coordinator to start monitoring for triggers.

        Returns:
            True if armed successfully
        """
        if self._armed:
            return True

        if not self.routes:
            self.log("No routes configured")
            return False

        # Validate all routes have connected devices
        for route in self.routes.values():
            if route.source_device not in self.pool.devices:
                self.log(f"Source device {route.source_device} not in pool")
                return False
            if route.target_device not in self.pool.devices:
                self.log(f"Target device {route.target_device} not in pool")
                return False

        # Start monitoring tasks
        self._armed = True
        self._monitoring_task = asyncio.create_task(self._monitor_loop())

        # Start UART monitoring for each source device with UART triggers
        uart_sources = set()
        for route in self.routes.values():
            if route.condition.trigger_type == TriggerType.UART_PATTERN:
                uart_sources.add(route.source_device)

        for device_id in uart_sources:
            task = asyncio.create_task(self._uart_monitor_loop(device_id))
            self._uart_tasks[device_id] = task

        self.log(f"Armed with {len(self.routes)} routes")
        if self._on_status_change:
            self._on_status_change("ARMED")

        return True

    async def disarm(self) -> None:
        """Disarm the coordinator and stop monitoring."""
        self._armed = False

        # Cancel monitoring task
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None

        # Cancel UART tasks
        for task in self._uart_tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._uart_tasks.clear()

        self.log("Disarmed")
        if self._on_status_change:
            self._on_status_change("READY")

    @property
    def is_armed(self) -> bool:
        """Check if coordinator is armed."""
        return self._armed

    async def _monitor_loop(self) -> None:
        """Main monitoring loop that checks for trigger conditions."""
        while self._armed:
            try:
                context = {}

                for route in self.routes.values():
                    if not route.enabled:
                        continue

                    # Check condition
                    if self.matcher.check_condition(
                        route.condition,
                        route.source_device,
                        context
                    ):
                        # Trigger matched!
                        await self._execute_action(route, context)

                        # Clear buffer to prevent re-triggering
                        if route.condition.trigger_type == TriggerType.UART_PATTERN:
                            self.matcher.clear_uart_buffer(route.source_device)

                await asyncio.sleep(0.01)  # 10ms check interval

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log(f"Monitor error: {e}")
                await asyncio.sleep(0.1)

    async def _uart_monitor_loop(self, device_id: str) -> None:
        """Monitor UART data from a device."""
        device_state = self.pool.get_device(device_id)
        if not device_state or not device_state.backend:
            return

        backend = device_state.backend

        while self._armed:
            try:
                # Read UART data if available
                if hasattr(backend, 'uart_read'):
                    data = await backend.uart_read()
                    if data:
                        self.matcher.append_uart_data(device_id, data.decode('utf-8', errors='ignore'))
                elif hasattr(backend, 'read_uart'):
                    data = backend.read_uart()
                    if data:
                        self.matcher.append_uart_data(device_id, data.decode('utf-8', errors='ignore'))

                await asyncio.sleep(0.01)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log(f"UART monitor error ({device_id}): {e}")
                await asyncio.sleep(0.1)

    async def _execute_action(self, route: TriggerRoute, context: Dict[str, Any]) -> None:
        """Execute the action for a triggered route."""
        timestamp = time.time()
        route.trigger_count += 1
        route.last_trigger_time = timestamp

        self.log(f"Trigger: {route.name} ({route.source_device} → {route.target_device})")

        # Get target device backend
        target_state = self.pool.get_device(route.target_device)
        if not target_state or not target_state.backend:
            self._record_event(route, timestamp, False, "Target device not available")
            return

        backend = target_state.backend
        action = route.action
        success = False
        details = ""

        try:
            if action.action_type == ActionType.GLITCH:
                success = await self._execute_glitch(backend, action.config)
                details = f"width={action.config.get('width_ns')}ns"

            elif action.action_type == ActionType.GPIO_PULSE:
                success = await self._execute_gpio_pulse(backend, action.config)
                details = f"pin={action.config.get('pin')}"

            elif action.action_type == ActionType.CAPTURE_START:
                success = await self._execute_capture_start(backend, action.config)
                details = "capture started"

            elif action.action_type == ActionType.CAPTURE_STOP:
                success = await self._execute_capture_stop(backend, action.config)
                details = "capture stopped"

            elif action.action_type == ActionType.LOG_EVENT:
                self.log(f"Event: {action.config.get('message', route.name)}")
                success = True
                details = "logged"

            elif action.action_type == ActionType.CUSTOM:
                if action.callback:
                    if asyncio.iscoroutinefunction(action.callback):
                        await action.callback(route, context)
                    else:
                        action.callback(route, context)
                    success = True
                    details = "custom callback"

        except Exception as e:
            details = str(e)
            self.log(f"Action failed: {e}")

        self._record_event(route, timestamp, success, details)

    async def _execute_glitch(self, backend: Backend, config: Dict[str, Any]) -> bool:
        """Execute a glitch action."""
        if not isinstance(backend, GlitchBackend):
            # Try to use glitch methods anyway
            pass

        width_ns = config.get("width_ns", 100)
        offset_ns = config.get("offset_ns", 0)
        repeat = config.get("repeat", 1)

        # Configure and trigger glitch
        if hasattr(backend, 'configure_glitch'):
            from ..backends import GlitchConfig
            glitch_config = GlitchConfig(
                width_ns=width_ns,
                offset_ns=offset_ns,
                repeat=repeat
            )
            backend.configure_glitch(glitch_config)

        if hasattr(backend, 'trigger'):
            backend.trigger()
            return True
        elif hasattr(backend, 'glitch_trigger'):
            await backend.glitch_trigger()
            return True

        return False

    async def _execute_gpio_pulse(self, backend: Backend, config: Dict[str, Any]) -> bool:
        """Execute a GPIO pulse action."""
        pin = config.get("pin", 0)
        duration_us = config.get("duration_us", 10)

        if hasattr(backend, 'gpio_pulse'):
            backend.gpio_pulse(pin, duration_us)
            return True
        elif hasattr(backend, 'pulse_gpio'):
            await backend.pulse_gpio(pin, duration_us)
            return True

        return False

    async def _execute_capture_start(self, backend: Backend, config: Dict[str, Any]) -> bool:
        """Start logic analyzer capture."""
        rate = config.get("rate", 1000000)
        samples = config.get("samples", 4096)

        if hasattr(backend, 'sump_arm'):
            await backend.sump_arm(rate=rate, samples=samples)
            return True

        return False

    async def _execute_capture_stop(self, backend: Backend, config: Dict[str, Any]) -> bool:
        """Stop logic analyzer capture."""
        if hasattr(backend, 'sump_disarm'):
            await backend.sump_disarm()
            return True

        return False

    def _record_event(self, route: TriggerRoute, timestamp: float, success: bool, details: str) -> None:
        """Record a trigger event."""
        event = TriggerEvent(
            timestamp=timestamp,
            route_name=route.name,
            source_device=route.source_device,
            target_device=route.target_device,
            action_type=route.action.action_type.name,
            success=success,
            details=details
        )
        self.events.append(event)

        # Keep only last 1000 events
        if len(self.events) > 1000:
            self.events = self.events[-1000:]

        # Callback for UI
        if self._on_trigger:
            self._on_trigger(event)

    def get_events(self, limit: int = 100) -> List[TriggerEvent]:
        """Get recent trigger events."""
        return self.events[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """Get coordinator statistics."""
        total_triggers = sum(r.trigger_count for r in self.routes.values())
        success_count = sum(1 for e in self.events if e.success)

        return {
            "armed": self._armed,
            "route_count": len(self.routes),
            "total_triggers": total_triggers,
            "success_rate": success_count / len(self.events) if self.events else 0,
            "event_count": len(self.events),
            "routes": {
                name: {
                    "source": route.source_device,
                    "target": route.target_device,
                    "trigger_count": route.trigger_count,
                    "enabled": route.enabled,
                }
                for name, route in self.routes.items()
            }
        }

    async def manual_trigger(self, route_name: str) -> bool:
        """
        Manually trigger a route (for testing).

        Args:
            route_name: Name of the route to trigger

        Returns:
            True if trigger executed
        """
        route = self.routes.get(route_name)
        if not route:
            return False

        context = {"manual_trigger": True}
        await self._execute_action(route, context)
        return True

    # Convenience methods for common setups

    def add_uart_glitch_route(
        self,
        name: str,
        uart_device: str,
        glitch_device: str,
        pattern: str,
        width_ns: int = 100,
        offset_ns: int = 500
    ) -> TriggerRoute:
        """
        Add a common UART pattern → glitch route.

        Args:
            name: Route name
            uart_device: Device ID for UART monitoring
            glitch_device: Device ID for glitching
            pattern: Regex pattern to match
            width_ns: Glitch width in nanoseconds
            offset_ns: Glitch offset in nanoseconds

        Returns:
            The created route
        """
        route = TriggerRoute(
            name=name,
            source_device=uart_device,
            condition=TriggerCondition(
                trigger_type=TriggerType.UART_PATTERN,
                config={"pattern": pattern}
            ),
            target_device=glitch_device,
            action=TriggerAction(
                action_type=ActionType.GLITCH,
                config={"width_ns": width_ns, "offset_ns": offset_ns}
            ),
            routing_mode=RoutingMode.SOFTWARE
        )
        self.add_route(route)
        return route

    def add_power_glitch_route(
        self,
        name: str,
        power_device: str,
        glitch_device: str,
        threshold_mv: int,
        width_ns: int = 100,
        edge: TriggerEdge = TriggerEdge.FALLING
    ) -> TriggerRoute:
        """
        Add a power threshold → glitch route.

        Args:
            name: Route name
            power_device: Device ID for power monitoring
            glitch_device: Device ID for glitching
            threshold_mv: Power threshold in millivolts
            width_ns: Glitch width in nanoseconds
            edge: Trigger on rising, falling, or both edges

        Returns:
            The created route
        """
        route = TriggerRoute(
            name=name,
            source_device=power_device,
            condition=TriggerCondition(
                trigger_type=TriggerType.POWER_THRESHOLD,
                config={"threshold_mv": threshold_mv, "edge": edge}
            ),
            target_device=glitch_device,
            action=TriggerAction(
                action_type=ActionType.GLITCH,
                config={"width_ns": width_ns}
            ),
            routing_mode=RoutingMode.SOFTWARE
        )
        self.add_route(route)
        return route


# Global coordinator instance
_global_coordinator: Optional[Coordinator] = None


def get_coordinator() -> Coordinator:
    """Get or create the global coordinator instance."""
    global _global_coordinator
    if _global_coordinator is None:
        _global_coordinator = Coordinator()
    return _global_coordinator
