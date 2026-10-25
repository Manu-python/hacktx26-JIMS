"""Dependency-free priority scheduler for HackTX laser messages.

Rule-based classification is deliberately separate from queue scheduling.
This module does not know how the Arduino's serial/laser framing works.
"""

from __future__ import annotations

import heapq
import re
from dataclasses import dataclass
from itertools import count


@dataclass(frozen=True)
class Message:
    id: str
    text: str
    arrival_order: int


@dataclass(frozen=True)
class ScoredMessage:
    message: Message
    priority: int
    category: str
    matched_rule: str


# Highest matching rule wins. Add patterns here when expanding the demo.
# Using phrases plus context avoids treating all mentions of "fire" as alarms.
RULES = (
    (96, "EMERGENCY", "Danger to people", (
        r"\bfire\s+(?:detected|reported)\b",
        r"\boxygen\s+levels?\s+(?:dropping|below|critical)\b",
        r"\b(?:worker|personnel|person)\s+injured\b",
        r"\bmedical\s+assistance\s+(?:needed|required)\b",
        r"\b(?:emergency\s+)?evacuation\s+(?:ordered|required)\b",
        r"\bradiation\s+levels?\s+(?:exceeding|above)\b",
        r"\bwater\s+contamination\s+detected\b",
    )),
    (89, "CRITICAL", "Critical infrastructure event", (
        r"\bemergency\s+shutdown\s+requested\b",
        r"\bmain\s+power\s+(?:supply\s+)?failure\b",
        r"\bcritical\s+coolant\s+leak\b",
        r"\bprimary\s+communication\s+link\s+disconnected\b",
    )),
    (72, "HIGH", "Security or backup system event", (
        r"\bunauthorized\s+access\s+detected\b",
        r"\bbackup\s+communication\s+system\s+activated\b",
    )),
    (55, "MEDIUM", "Degraded performance", (
        r"\bnetwork\s+latency\s+increased\b",
        r"\breduced\s+efficiency\b",
        r"\befficiency\s+decreased\b",
        r"\bstorage\s+capacity\s+is\s+\d+%\s+full\b",
    )),
    (22, "LOW", "Routine telemetry", (
        r"\b(?:battery|fuel)\s+level\b",
        r"\b(?:humidity|temperature)\s+sensor\b",
        r"\batmospheric\s+pressure\b",
        r"\bexternal\s+temperature\b",
    )),
    (15, "INFO", "Normal or scheduled activity", (
        r"\b(?:operating|functioning)\s+normally\b",
        r"\bcompleted\s+successfully\b",
        r"\broutine\s+(?:maintenance|status)\b",
        r"\bsoftware\s+update\s+available\b",
        r"\bsensor\s+calibration\s+completed\b",
    )),
)


COMPILED_RULES = tuple(
    (score, category, reason, tuple(re.compile(p, re.IGNORECASE) for p in patterns))
    for score, category, reason, patterns in RULES
)


def is_negated(text: str, match_start: int) -> bool:
    """Avoid obvious false alarms such as 'no fire detected' or 'test message'."""
    if re.search(r"\b(?:false alarm|test message|exercise only|simulation only|drill)\b", text, re.I):
        return True
    preceding = re.findall(r"\b\w+\b", text[max(0, match_start - 40):match_start].lower())
    return any(word in {"no", "not", "never", "without"} for word in preceding[-4:])


def classify(message: Message) -> ScoredMessage:
    """Classify once when the message arrives; higher = more urgent."""
    for score, category, reason, patterns in COMPILED_RULES:
        for pattern in patterns:
            for match in pattern.finditer(message.text):
                if not is_negated(message.text, match.start()):
                    return ScoredMessage(message, score, category, reason)
    return ScoredMessage(message, 35, "UNCLASSIFIED", "No configured rule matched")


class PriorityScheduler:
    """Dynamic, non-preemptive queue. Equal scores transmit FIFO."""

    def __init__(self) -> None:
        self._heap: list[tuple[int, int, int, ScoredMessage]] = []
        self._sequence = count()

    def enqueue(self, message: Message) -> ScoredMessage:
        scored = classify(message)
        heapq.heappush(self._heap, (
            -scored.priority, message.arrival_order,
            next(self._sequence), scored,
        ))
        return scored

    def dequeue(self) -> ScoredMessage:
        """Pop the next message to transmit (raises IndexError when empty)."""
        return heapq.heappop(self._heap)[-1]

    def __len__(self) -> int:
        return len(self._heap)
