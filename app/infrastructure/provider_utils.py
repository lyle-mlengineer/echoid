from dataclasses import dataclass
from typing import Protocol
from pathlib import Path
import torch
import torch.nn as nn
import numpy as np
from transformers import AutoModelForAudioFrameClassification, AutoProcessor, pipeline
import librosa
import soundfile as sf
import io
from app.core.config import Settings
from app.domain.entities import TranscriptSegment

@dataclass(frozen=True)
class Segment:
    speaker: str
    start_seconds: float
    end_seconds: float

@dataclass(frozen=True)
class TranscriptionResult:
    segments: list[TranscriptSegment]
    duration_seconds: float | None
    provider: str
    demo_mode: bool

async def save_audio_bytes_to_file(audio_bytes: bytes, file_path: Path) -> None:
    """
    Save audio bytes to a file.
    """
    with open(file_path, "wb") as f:
        f.write(audio_bytes)

async def get_audio_segments(audio_data: np.ndarray, diarization_model: nn.Module, diarization_processor: nn.Module) -> list[Segment]:
    sampling_rate = diarization_processor.feature_extractor.sampling_rate
    inputs = diarization_processor(audio_data, sampling_rate=sampling_rate).to(diarization_model.device, dtype=diarization_model.dtype)

    with torch.inference_mode():
        logits = diarization_model(**inputs).logits  # (1, num_frames, 8), one frame every 10 ms

    segments = diarization_processor.extract_speaker_dict(logits, inputs.attention_mask)[0]
    segments = [
        Segment(
            speaker=segment["Speaker"],
            start_seconds=segment["Start"],
            end_seconds=segment["End"],
        )
        for segment in segments
    ]

    return segments

async def transcribe_segment(segment: Segment, audio_data: np.ndarray, sampling_rate: int, transcription_pipeline, language: str | None = None) -> str:
    start_time = segment.start_seconds
    end_time = segment.end_seconds
    speaker = segment.speaker

    # Convert start and end times to sample indices
    start_sample = int(start_time * sampling_rate)
    end_sample = int(end_time * sampling_rate)

    # Extract the audio segment
    audio_segment = audio_data[start_sample:end_sample]

    # Skip very short segments
    if end_sample - start_sample < sampling_rate * 0.5:  # Less than 0.5 seconds
        print(f"speaker_{speaker}: {start_time:.2f}s - {end_time:.2f}s [too short to transcribe]")
        return ""

    # Use the transcription pipeline to transcribe the audio segment
    # Transcribe the segment
    generate_kwargs: dict = {"task": "transcribe"}
    if language:
        generate_kwargs["language"] = language
    result = transcription_pipeline(
        audio_segment,
        generate_kwargs=generate_kwargs,
        return_timestamps=False
    )

    text = result["text"].strip()
    # print(f"speaker_{speaker}: {start_time:.2f}s - {end_time:.2f}s")
    # print(f"  {text}\n")

    return text

async def transcribe_segments(segments: list[Segment], audio_data: np.ndarray, sampling_rate: int, transcription_pipeline, language: str | None = None) -> list[TranscriptSegment]:
    transcript_segments = []
    for segment in segments:
        text = await transcribe_segment(segment, audio_data, sampling_rate, transcription_pipeline, language)
        if text:  # Only add segments that have transcribed text
            transcript_segments.append(
                TranscriptSegment(
                    speaker=f"speaker_{segment.speaker}",
                    text=text,
                    start_seconds=segment.start_seconds,
                    end_seconds=segment.end_seconds,
                )
            )
    return transcript_segments

async def merge_adjacent_speaker_segments(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    if not segments:
        return []

    merged_segments = [segments[0]]

    for current in segments[1:]:
        last = merged_segments[-1]
        if current.speaker == last.speaker:
            # Merge segments
            print(f"Merging segments for {current.speaker}: {last.start_seconds:.2f}s - {last.end_seconds:.2f}s and {current.start_seconds:.2f}s - {current.end_seconds:.2f}s")
            merged_segments[-1] = TranscriptSegment(
                speaker=last.speaker,
                text=last.text + " " + current.text,
                start_seconds=last.start_seconds,
                end_seconds=max(last.end_seconds, current.end_seconds),
            )
        else:
            print(f"Adding new segment for {current.speaker}: {current.start_seconds:.2f}s - {current.end_seconds:.2f}s")
            merged_segments.append(current)

    return merged_segments