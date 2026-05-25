"""Simple in-process async event bus."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

EventHandler = Callable[[Any], Awaitable[None]]


@dataclass(slots=True)
class DomainEvent:
    name: str
    payload: dict[str, Any]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        self._handlers[event_name].append(handler)

    async def publish(self, event: DomainEvent) -> None:
        for handler in self._handlers[event.name]:
            await handler(event.payload)


event_bus = EventBus()
