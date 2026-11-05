from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import Settings
from app.domain.entities import TranscriptSegment


@dataclass(frozen=True)
class TranscriptionResult:
    segments: list[TranscriptSegment]
    duration_seconds: float | None
    provider: str
    demo_mode: bool


class TranscriptionProvider(Protocol):
    demo_mode: bool

    async def transcribe(self, filename: str, content: bytes) -> TranscriptionResult: ...


class DemoTranscriptionProvider:
    demo_mode = True

    async def transcribe(self, filename: str, content: bytes) -> TranscriptionResult:
        return TranscriptionResult(
            segments=[
                TranscriptSegment(
                    speaker="Speaker 1",
                    text="[Demo only: configure a transcription provider to analyze audio]",
                    start_seconds=0,
                    end_seconds=0,
                )
            ],
            duration_seconds=None,
            provider="demo",
            demo_mode=True,
        )


class HttpTranscriptionProvider:
    demo_mode = False

    def __init__(self, api_url: str, api_key: str | None):
        self.api_url = api_url
        self.api_key = api_key

    async def transcribe(self, filename: str, content: bytes) -> TranscriptionResult:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                self.api_url,
                headers=headers,
                files={"file": (filename, content, "application/octet-stream")},
            )
            response.raise_for_status()
        payload = response.json()
        segments = [
            TranscriptSegment(
                speaker=str(item["speaker"]),
                text=str(item["text"]),
                start_seconds=float(item["start_seconds"]),
                end_seconds=float(item["end_seconds"]),
            )
            for item in payload["segments"]
        ]
        if not segments:
            raise ValueError("The transcription provider returned no segments.")
        duration = payload.get("duration_seconds")
        return TranscriptionResult(
            segments=segments,
            duration_seconds=float(duration) if duration is not None else None,
            provider=str(payload.get("provider", "external")),
            demo_mode=False,
        )


def build_transcription_provider(settings: Settings) -> TranscriptionProvider:
    if settings.transcription_api_url:
        return HttpTranscriptionProvider(
            settings.transcription_api_url, settings.transcription_api_key
        )
    return DemoTranscriptionProvider()
