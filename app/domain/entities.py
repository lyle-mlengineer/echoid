from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from app.domain.events import CreditsPurchased, DomainEvent, GenerationCompleted


@dataclass(frozen=True)
class TranscriptSegment:
    speaker: str
    text: str
    start_seconds: float
    end_seconds: float

    def __post_init__(self) -> None:
        if not self.speaker.strip() or not self.text.strip():
            raise ValueError("Transcript segments require a speaker and text.")
        if self.start_seconds < 0 or self.end_seconds < self.start_seconds:
            raise ValueError("Transcript segment timestamps are invalid.")


@dataclass
class Generation:
    id: UUID
    owner_id: UUID | None
    guest_id: UUID | None
    filename: str
    status: str = "processing"
    segments: list[TranscriptSegment] = field(default_factory=list)
    duration_seconds: float | None = None
    provider: str = "demo"
    demo_mode: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    events: list[DomainEvent] = field(default_factory=list, repr=False)

    def complete(
        self,
        segments: list[TranscriptSegment],
        duration_seconds: float | None,
        credits_charged: int,
    ) -> None:
        if self.status != "processing":
            raise ValueError("Only processing generations can be completed.")
        if not segments:
            raise ValueError("A completed generation must contain transcript segments.")
        if duration_seconds is not None and duration_seconds < 0:
            raise ValueError("Generation duration cannot be negative.")
        self.segments = segments
        self.duration_seconds = duration_seconds
        self.status = "completed"
        self.events.append(
            GenerationCompleted.create(self.id, self.owner_id, credits_charged)
        )


@dataclass
class Payment:
    id: UUID
    owner_id: UUID
    amount_kes: int
    credits: int
    status: str = "pending"
    events: list[DomainEvent] = field(default_factory=list, repr=False)

    def complete(self) -> None:
        if self.status != "pending":
            raise ValueError("Only pending payments can be completed.")
        if self.amount_kes <= 0 or self.credits <= 0:
            raise ValueError("Completed payments must have a positive amount and credit value.")
        self.status = "completed"
        self.events.append(CreditsPurchased.create(self.id, self.owner_id, self.credits))

    def fail(self) -> None:
        if self.status != "pending":
            raise ValueError("Only pending payments can be failed.")
        self.status = "failed"
