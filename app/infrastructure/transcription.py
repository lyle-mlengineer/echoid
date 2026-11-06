from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
# import librosa
# import torch

import httpx
# from transformers import AutoModelForAudioFrameClassification, AutoProcessor, pipeline

from app.core.config import Settings
from app.domain.entities import TranscriptSegment
from app.domain.languages import WHISPER_NAMES

# from app.infrastructure.provider_utils import (
#     Segment, merge_adjacent_speaker_segments, save_audio_bytes_to_file, get_audio_segments, transcribe_segments
# )


@dataclass(frozen=True)
class TranscriptionResult:
    segments: list[TranscriptSegment]
    duration_seconds: float | None
    provider: str
    demo_mode: bool


class TranscriptionProvider(Protocol):
    demo_mode: bool

    async def transcribe(
        self, filename: str, content: bytes, language: str | None = None
    ) -> TranscriptionResult: ...


class DemoTranscriptionProvider:
    demo_mode = True

    async def transcribe(
        self, filename: str, content: bytes, language: str | None = None
    ) -> TranscriptionResult:
        return TranscriptionResult(
            segments=[
                TranscriptSegment(
                    speaker="Speaker 1",
                    text="[Demo only: configure a transcription provider to analyze audio]",
                    start_seconds=0,
                    end_seconds=2,
                ),
                TranscriptSegment(
                    speaker="Speaker 2",
                    text="[Demo only: configure a transcription provider to analyze audio]",
                    start_seconds=2,
                    end_seconds=4,
                ),
                TranscriptSegment(
                    speaker="Speaker 1",
                    text="[Demo only: configure a transcription provider to analyze audio]",
                    start_seconds=4,
                    end_seconds=6,
                ),
                TranscriptSegment(
                    speaker="Speaker 3",
                    text="[Demo only: configure a transcription provider to analyze audio]",
                    start_seconds=6,
                    end_seconds=10,
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

    async def transcribe(
        self, filename: str, content: bytes, language: str | None = None
    ) -> TranscriptionResult:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        data = {"language": language} if language else {}
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                self.api_url,
                headers=headers,
                files={"file": (filename, content, "application/octet-stream")},
                data=data,
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

# class NematronWhisperProviderLocal(TranscriptionProvider):
#     demo_mode = False

#     def __init__(self, whisper_model_id: str, nematron_model_id: str):
#         self.diarization_processor = AutoProcessor.from_pretrained(nematron_model_id)
#         self.diarization_model = AutoModelForAudioFrameClassification.from_pretrained(nematron_model_id)
#         self.transcription_pipeline = pipeline("automatic-speech-recognition", model=whisper_model_id)
#         self.sampling_rate = self.diarization_processor.feature_extractor.sampling_rate

#     async def transcribe(
#         self, filename: str, content: bytes, language: str | None = None
#     ) -> TranscriptionResult:
#         parent_dir = Path(__file__).parent.parent
#         audio_dir = parent_dir / "audio" / "raw"
#         audio_path = audio_dir / filename
#         await save_audio_bytes_to_file(content, audio_path)
#         audio, _ = librosa.load(str(audio_path), sr=self.sampling_rate)
#         audio_segments = await get_audio_segments(audio, self.diarization_model, self.diarization_processor)
#         segments = await transcribe_segments(
#             audio_segments,
#             audio,
#             self.sampling_rate,
#             self.transcription_pipeline,
#             language=WHISPER_NAMES.get(language or ""),
#         )
#         segments = await merge_adjacent_speaker_segments(segments)
        
#         return TranscriptionResult(
#             segments=segments,
#             duration_seconds=None,
#             provider="local_whisper",
#             demo_mode=False,
#         )


def build_transcription_provider(settings: Settings) -> TranscriptionProvider:
    # if settings.whisper_model_id and settings.nematron_model_id:
    #     return NematronWhisperProviderLocal(
    #         whisper_model_id=settings.whisper_model_id,
    #         nematron_model_id=settings.nematron_model_id
    #     )
    
    if settings.transcription_api_url:
        return HttpTranscriptionProvider(
            settings.transcription_api_url, settings.transcription_api_key
        )
    return DemoTranscriptionProvider()
