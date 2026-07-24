"""Serial diagnostics helpers for detector validation output."""

from dataclasses import dataclass
import re
import time
from typing import Optional


_DEBUG_LINE_PATTERNS = (
    ("loop_gap_active_max_us", re.compile(r"^LOOP_GAP_ACTIVE_MAX_US:(\d+)$")),
    ("angle_age_ms", re.compile(r"^ANGLE_AGE_MS:(\d+)$")),
)


@dataclass(frozen=True)
class CommandRttSample:
    command: str
    response: str
    rtt_ms: float


def parse_detector_debug_line(line: str) -> Optional[tuple[str, int]]:
    """Parse temporary ESP32 detector validation text lines."""
    text = line.strip()
    for key, pattern in _DEBUG_LINE_PATTERNS:
        match = pattern.match(text)
        if match:
            return key, int(match.group(1))
    return None


def parse_ads_health_line(line: str) -> Optional[dict[str, int]]:
    """Parse the firmware ADS_HEALTH line using the same lowercase keys as ROS."""
    text = line.strip()
    if not text.startswith("ADS_HEALTH:"):
        return None

    counters: dict[str, int] = {}
    try:
        for item in text.split(":", 1)[1].split(","):
            key, value = item.split("=", 1)
            counters[key.strip().lower()] = int(value.strip())
    except (TypeError, ValueError):
        return None
    return counters


class CommandRttTracker:
    """Tracks one outstanding serial command and its first text response."""

    def __init__(self) -> None:
        self._pending_command: Optional[str] = None
        self._sent_at_s: Optional[float] = None

    def record(self, command: str, now_s: Optional[float] = None) -> None:
        clean_command = command.strip()
        if not clean_command:
            return
        self._pending_command = clean_command
        self._sent_at_s = time.perf_counter() if now_s is None else now_s

    def finish(self, response: str, now_s: Optional[float] = None) -> Optional[CommandRttSample]:
        if self._pending_command is None or self._sent_at_s is None:
            return None
        ended_at_s = time.perf_counter() if now_s is None else now_s
        sample = CommandRttSample(
            command=self._pending_command,
            response=response.strip(),
            rtt_ms=(ended_at_s - self._sent_at_s) * 1000.0,
        )
        self._pending_command = None
        self._sent_at_s = None
        return sample
