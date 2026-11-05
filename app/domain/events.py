from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID, uuid4


@dataclass(frozen=True)
class DomainEvent:
    event_id: UUID
    occurred_at: datetime


@dataclass(frozen=True)
class GenerationCompleted(DomainEvent):
    generation_id: UUID
    owner_id: UUID | None
    credits_charged: int

    @classmethod
    def create(
        cls, generation_id: UUID, owner_id: UUID | None, credits_charged: int
    ) -> "GenerationCompleted":
        return cls(
            event_id=uuid4(),
            occurred_at=datetime.now(timezone.utc),
            generation_id=generation_id,
            owner_id=owner_id,
            credits_charged=credits_charged,
        )


@dataclass(frozen=True)
class CreditsPurchased(DomainEvent):
    payment_id: UUID
    owner_id: UUID
    credits: int

    @classmethod
    def create(cls, payment_id: UUID, owner_id: UUID, credits: int) -> "CreditsPurchased":
        return cls(
            event_id=uuid4(),
            occurred_at=datetime.now(timezone.utc),
            payment_id=payment_id,
            owner_id=owner_id,
            credits=credits,
        )


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[Callable[[DomainEvent], None]]] = {}

    def subscribe(
        self, event_type: type[DomainEvent], handler: Callable[[DomainEvent], None]
    ) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def publish(self, event: DomainEvent) -> None:
        for handler in self._handlers.get(type(event), []):
            handler(event)
