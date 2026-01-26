"""
Smart Glitch Campaign

Enhanced glitch parameter search with:
- Binary search for optimal parameters
- Result classification (SUCCESS, CRASH, NORMAL, TIMEOUT)
- Learning from results to focus on promising regions
- Statistical analysis and heatmap generation
"""

import asyncio
import time
import random
from typing import Optional, List, Dict, Callable, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


class GlitchResult(Enum):
    """Classification of glitch attempt results."""
    SUCCESS = "success"      # Desired outcome achieved
    CRASH = "crash"          # Target crashed/reset
    NORMAL = "normal"        # No effect observed
    TIMEOUT = "timeout"      # No response
    MUTE = "mute"            # Output suppressed (partial success)
    UNKNOWN = "unknown"      # Couldn't classify


@dataclass
class GlitchAttempt:
    """Record of a single glitch attempt."""
    width_ns: int
    offset_ns: int
    result: GlitchResult
    timestamp: float
    response: str = ""
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParameterRegion:
    """A region of parameter space."""
    width_min: int
    width_max: int
    offset_min: int
    offset_max: int
    score: float = 0.0
    attempts: int = 0
    successes: int = 0

    @property
    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts > 0 else 0.0

    def contains(self, width: int, offset: int) -> bool:
        return (self.width_min <= width <= self.width_max and
                self.offset_min <= offset <= self.offset_max)

    def subdivide(self) -> List["ParameterRegion"]:
        """Subdivide into 4 smaller regions."""
        width_mid = (self.width_min + self.width_max) // 2
        offset_mid = (self.offset_min + self.offset_max) // 2

        return [
            ParameterRegion(self.width_min, width_mid, self.offset_min, offset_mid),
            ParameterRegion(width_mid + 1, self.width_max, self.offset_min, offset_mid),
            ParameterRegion(self.width_min, width_mid, offset_mid + 1, self.offset_max),
            ParameterRegion(width_mid + 1, self.width_max, offset_mid + 1, self.offset_max),
        ]


@dataclass
class CampaignStats:
    """Statistics for a glitch campaign."""
    total_attempts: int = 0
    successes: int = 0
    crashes: int = 0
    normals: int = 0
    timeouts: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    best_params: Optional[Tuple[int, int]] = None

    @property
    def elapsed(self) -> float:
        end = self.end_time if self.end_time else time.time()
        return end - self.start_time if self.start_time else 0.0

    @property
    def rate(self) -> float:
        return self.total_attempts / self.elapsed if self.elapsed > 0 else 0.0

    @property
    def success_rate(self) -> float:
        return self.successes / self.total_attempts if self.total_attempts > 0 else 0.0


class ResultClassifier:
    """
    Classifies glitch results based on target response.

    Configure with patterns for different result types.
    """

    def __init__(self):
        self.success_patterns: List[str] = []
        self.crash_patterns: List[str] = [
            "reset", "reboot", "fault", "exception",
            "hard fault", "watchdog", "wdt"
        ]
        self.mute_patterns: List[str] = []

    def add_success_pattern(self, pattern: str):
        """Add a pattern that indicates success."""
        self.success_patterns.append(pattern.lower())

    def add_crash_pattern(self, pattern: str):
        """Add a pattern that indicates crash."""
        self.crash_patterns.append(pattern.lower())

    def classify(self, response: str, timeout: bool = False) -> GlitchResult:
        """Classify a response."""
        if timeout or not response:
            return GlitchResult.TIMEOUT

        response_lower = response.lower()

        # Check for success patterns
        for pattern in self.success_patterns:
            if pattern in response_lower:
                return GlitchResult.SUCCESS

        # Check for crash patterns
        for pattern in self.crash_patterns:
            if pattern in response_lower:
                return GlitchResult.CRASH

        # Check for mute (shorter than expected)
        for pattern in self.mute_patterns:
            if pattern in response_lower:
                return GlitchResult.MUTE

        return GlitchResult.NORMAL


class SmartGlitchCampaign:
    """
    Intelligent glitch parameter search.

    Strategies:
    - GRID: Traditional grid search (baseline)
    - RANDOM: Random sampling across parameter space
    - BINARY: Binary search focusing on promising regions
    - ADAPTIVE: Learn from results and focus on hot spots

    Example:
        >>> campaign = SmartGlitchCampaign(
        ...     glitch_backend=bolt,
        ...     monitor_backend=buspirate,
        ...     width_range=(50, 500),
        ...     offset_range=(0, 10000)
        ... )
        >>> campaign.classifier.add_success_pattern("flag{")
        >>> stats = await campaign.run(strategy="adaptive", max_attempts=1000)
    """

    def __init__(
        self,
        glitch_backend,
        monitor_backend=None,
        width_range: Tuple[int, int] = (50, 500),
        offset_range: Tuple[int, int] = (0, 10000),
        width_step: int = 10,
        offset_step: int = 100,
        log_callback: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize campaign.

        Args:
            glitch_backend: Backend for triggering glitches
            monitor_backend: Backend for monitoring target (UART, etc.)
            width_range: (min, max) glitch width in nanoseconds
            offset_range: (min, max) delay after trigger
            width_step: Step size for width in grid mode
            offset_step: Step size for offset in grid mode
            log_callback: Logging callback
        """
        self.glitch = glitch_backend
        self.monitor = monitor_backend
        self.width_range = width_range
        self.offset_range = offset_range
        self.width_step = width_step
        self.offset_step = offset_step
        self.log = log_callback or print

        self.classifier = ResultClassifier()
        self.attempts: List[GlitchAttempt] = []
        self.stats = CampaignStats()

        # For adaptive search
        self._regions: List[ParameterRegion] = []
        self._heatmap: Dict[Tuple[int, int], List[GlitchResult]] = defaultdict(list)

        self._running = False
        self._on_result: Optional[Callable[[GlitchAttempt], None]] = None

    def set_result_callback(self, callback: Callable[[GlitchAttempt], None]):
        """Set callback for each glitch result."""
        self._on_result = callback

    async def run(
        self,
        strategy: str = "adaptive",
        max_attempts: int = 1000,
        stop_on_success: bool = False,
        cooldown_ms: float = 10.0
    ) -> CampaignStats:
        """
        Run the glitch campaign.

        Args:
            strategy: Search strategy ("grid", "random", "binary", "adaptive")
            max_attempts: Maximum number of glitch attempts
            stop_on_success: Stop when first success is found
            cooldown_ms: Delay between glitches

        Returns:
            Campaign statistics
        """
        self._running = True
        self.stats = CampaignStats()
        self.stats.start_time = time.time()

        self.log(f"[SmartGlitch] Starting {strategy} search")
        self.log(f"  Width: {self.width_range[0]}-{self.width_range[1]} ns")
        self.log(f"  Offset: {self.offset_range[0]}-{self.offset_range[1]} ns")

        try:
            if strategy == "grid":
                await self._run_grid_search(max_attempts, stop_on_success, cooldown_ms)
            elif strategy == "random":
                await self._run_random_search(max_attempts, stop_on_success, cooldown_ms)
            elif strategy == "binary":
                await self._run_binary_search(max_attempts, stop_on_success, cooldown_ms)
            elif strategy == "adaptive":
                await self._run_adaptive_search(max_attempts, stop_on_success, cooldown_ms)
            else:
                raise ValueError(f"Unknown strategy: {strategy}")

        except asyncio.CancelledError:
            self.log("[SmartGlitch] Campaign cancelled")
        finally:
            self._running = False
            self.stats.end_time = time.time()

        self.log(f"[SmartGlitch] Complete: {self.stats.total_attempts} attempts, "
                f"{self.stats.successes} successes ({self.stats.success_rate:.1%})")

        return self.stats

    def stop(self):
        """Stop the campaign."""
        self._running = False

    async def _run_grid_search(
        self,
        max_attempts: int,
        stop_on_success: bool,
        cooldown_ms: float
    ):
        """Traditional grid search."""
        for width in range(self.width_range[0], self.width_range[1] + 1, self.width_step):
            for offset in range(self.offset_range[0], self.offset_range[1] + 1, self.offset_step):
                if not self._running or self.stats.total_attempts >= max_attempts:
                    return

                result = await self._try_glitch(width, offset)

                if stop_on_success and result == GlitchResult.SUCCESS:
                    return

                await asyncio.sleep(cooldown_ms / 1000)

    async def _run_random_search(
        self,
        max_attempts: int,
        stop_on_success: bool,
        cooldown_ms: float
    ):
        """Random sampling across parameter space."""
        for _ in range(max_attempts):
            if not self._running:
                return

            width = random.randint(self.width_range[0], self.width_range[1])
            offset = random.randint(self.offset_range[0], self.offset_range[1])

            result = await self._try_glitch(width, offset)

            if stop_on_success and result == GlitchResult.SUCCESS:
                return

            await asyncio.sleep(cooldown_ms / 1000)

    async def _run_binary_search(
        self,
        max_attempts: int,
        stop_on_success: bool,
        cooldown_ms: float
    ):
        """
        Binary search focusing on promising regions.

        Start with coarse sampling, then subdivide regions with interesting results.
        """
        # Initialize with full parameter space
        initial_region = ParameterRegion(
            self.width_range[0], self.width_range[1],
            self.offset_range[0], self.offset_range[1]
        )
        self._regions = [initial_region]

        while self._running and self.stats.total_attempts < max_attempts:
            if not self._regions:
                break

            # Pick region with highest score (or random if no scores yet)
            region = max(self._regions, key=lambda r: r.score + random.random() * 0.1)

            # Sample random point in region
            width = random.randint(region.width_min, region.width_max)
            offset = random.randint(region.offset_min, region.offset_max)

            result = await self._try_glitch(width, offset)

            # Update region stats
            region.attempts += 1
            if result == GlitchResult.SUCCESS:
                region.successes += 1
                region.score += 1.0
            elif result == GlitchResult.CRASH:
                region.score += 0.3  # Crashes are somewhat interesting
            elif result == GlitchResult.MUTE:
                region.score += 0.5  # Mutes might be partial success

            # Subdivide promising regions
            if region.attempts >= 5 and region.score > 0.5:
                self._regions.remove(region)
                self._regions.extend(region.subdivide())

            if stop_on_success and result == GlitchResult.SUCCESS:
                return

            await asyncio.sleep(cooldown_ms / 1000)

    async def _run_adaptive_search(
        self,
        max_attempts: int,
        stop_on_success: bool,
        cooldown_ms: float
    ):
        """
        Adaptive search that learns from results.

        Combines random exploration with exploitation of promising areas.
        """
        exploration_rate = 0.3  # 30% random exploration

        # Build initial heatmap with random samples
        initial_samples = min(100, max_attempts // 10)
        for _ in range(initial_samples):
            if not self._running:
                return

            width = random.randint(self.width_range[0], self.width_range[1])
            offset = random.randint(self.offset_range[0], self.offset_range[1])
            await self._try_glitch(width, offset)
            await asyncio.sleep(cooldown_ms / 1000)

        # Main adaptive loop
        while self._running and self.stats.total_attempts < max_attempts:
            if random.random() < exploration_rate:
                # Exploration: random sample
                width = random.randint(self.width_range[0], self.width_range[1])
                offset = random.randint(self.offset_range[0], self.offset_range[1])
            else:
                # Exploitation: sample near successful/interesting points
                width, offset = self._pick_promising_point()

            result = await self._try_glitch(width, offset)

            if stop_on_success and result == GlitchResult.SUCCESS:
                return

            await asyncio.sleep(cooldown_ms / 1000)

    def _pick_promising_point(self) -> Tuple[int, int]:
        """Pick a point near known interesting results."""
        # Find interesting points (success, crash, mute)
        interesting = [
            (w, o) for (w, o), results in self._heatmap.items()
            if any(r in (GlitchResult.SUCCESS, GlitchResult.CRASH, GlitchResult.MUTE)
                   for r in results)
        ]

        if not interesting:
            # Fall back to random
            return (
                random.randint(self.width_range[0], self.width_range[1]),
                random.randint(self.offset_range[0], self.offset_range[1])
            )

        # Pick a random interesting point and add jitter
        base_width, base_offset = random.choice(interesting)

        # Add gaussian jitter
        width = int(base_width + random.gauss(0, self.width_step * 2))
        offset = int(base_offset + random.gauss(0, self.offset_step * 2))

        # Clamp to valid range
        width = max(self.width_range[0], min(self.width_range[1], width))
        offset = max(self.offset_range[0], min(self.offset_range[1], offset))

        return width, offset

    async def _try_glitch(self, width: int, offset: int) -> GlitchResult:
        """Execute a single glitch attempt and record result."""
        timestamp = time.time()

        # Configure glitch
        from ..backends import GlitchConfig
        config = GlitchConfig(width_ns=width, offset_ns=offset)
        self.glitch.configure_glitch(config)

        # Clear monitor buffer
        response = ""
        timeout = False

        try:
            # Trigger glitch
            self.glitch.trigger()

            # Wait for response
            await asyncio.sleep(0.1)

            # Read monitor response
            if self.monitor:
                try:
                    data = self.monitor.uart_read(4096, timeout_ms=500)
                    response = data.decode('utf-8', errors='replace') if data else ""
                except Exception:
                    timeout = True

        except Exception as e:
            self.log(f"[SmartGlitch] Error: {e}")
            timeout = True

        # Classify result
        result = self.classifier.classify(response, timeout)

        # Record attempt
        attempt = GlitchAttempt(
            width_ns=width,
            offset_ns=offset,
            result=result,
            timestamp=timestamp,
            response=response[:256],  # Truncate for storage
            latency_ms=(time.time() - timestamp) * 1000
        )
        self.attempts.append(attempt)

        # Update heatmap
        # Quantize to grid for heatmap
        grid_width = (width // self.width_step) * self.width_step
        grid_offset = (offset // self.offset_step) * self.offset_step
        self._heatmap[(grid_width, grid_offset)].append(result)

        # Update stats
        self.stats.total_attempts += 1
        if result == GlitchResult.SUCCESS:
            self.stats.successes += 1
            self.stats.best_params = (width, offset)
            self.log(f"[SmartGlitch] SUCCESS at width={width}ns, offset={offset}ns")
        elif result == GlitchResult.CRASH:
            self.stats.crashes += 1
        elif result == GlitchResult.NORMAL:
            self.stats.normals += 1
        elif result == GlitchResult.TIMEOUT:
            self.stats.timeouts += 1

        # Callback
        if self._on_result:
            self._on_result(attempt)

        return result

    def get_heatmap_data(self) -> Dict[str, Any]:
        """Get heatmap data for visualization."""
        data = {}

        for (width, offset), results in self._heatmap.items():
            # Calculate score for this cell
            score = 0
            for r in results:
                if r == GlitchResult.SUCCESS:
                    score += 1.0
                elif r == GlitchResult.CRASH:
                    score += 0.3
                elif r == GlitchResult.MUTE:
                    score += 0.5

            data[(width, offset)] = {
                'score': score / len(results) if results else 0,
                'attempts': len(results),
                'successes': sum(1 for r in results if r == GlitchResult.SUCCESS),
                'crashes': sum(1 for r in results if r == GlitchResult.CRASH),
            }

        return data

    def export_results(self) -> List[Dict]:
        """Export all results as list of dicts."""
        return [
            {
                'width_ns': a.width_ns,
                'offset_ns': a.offset_ns,
                'result': a.result.value,
                'timestamp': a.timestamp,
                'response': a.response,
                'latency_ms': a.latency_ms,
            }
            for a in self.attempts
        ]

    def save_results(self, path: str):
        """Save results to JSON file."""
        import json
        with open(path, 'w') as f:
            json.dump({
                'stats': {
                    'total_attempts': self.stats.total_attempts,
                    'successes': self.stats.successes,
                    'crashes': self.stats.crashes,
                    'elapsed': self.stats.elapsed,
                    'best_params': self.stats.best_params,
                },
                'attempts': self.export_results(),
            }, f, indent=2)

    def load_results(self, path: str):
        """Load previous results to continue campaign."""
        import json
        with open(path, 'r') as f:
            data = json.load(f)

        for a in data.get('attempts', []):
            attempt = GlitchAttempt(
                width_ns=a['width_ns'],
                offset_ns=a['offset_ns'],
                result=GlitchResult(a['result']),
                timestamp=a['timestamp'],
                response=a.get('response', ''),
                latency_ms=a.get('latency_ms', 0),
            )
            self.attempts.append(attempt)

            # Update heatmap
            grid_width = (a['width_ns'] // self.width_step) * self.width_step
            grid_offset = (a['offset_ns'] // self.offset_step) * self.offset_step
            self._heatmap[(grid_width, grid_offset)].append(attempt.result)

        self.log(f"[SmartGlitch] Loaded {len(self.attempts)} previous attempts")
