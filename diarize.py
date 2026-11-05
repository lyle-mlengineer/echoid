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


@dataclass(frozen=True)
class TranscriptionResult:
    segments: list[TranscriptSegment]
    duration_seconds: float | None
    provider: str
    demo_mode: bool

def get_audio_from_bytes(audio_bytes: bytes, sr: int = 16000) -> tuple:
    """
    Load audio from bytes and return the audio data and sample rate.
    """
    # Use librosa to load the audio from bytes
    audio_data, _ = sf.read(io.BytesIO(audio_bytes), dtype='float32')
    
    # Resample if necessary
    if sr != 16000:
        audio_data = librosa.resample(audio_data, orig_sr=_, target_sr=sr)
    
    return audio_data, sr

def get_audio_segments(audio_data: np.ndarray, diarization_model: nn.Module, diarization_processor: nn.Module,) -> list[dict[str, str]]:
    sampling_rate = diarization_processor.feature_extractor.sampling_rate
    inputs = diarization_processor(audio_data, sampling_rate=sampling_rate).to(diarization_model.device, dtype=diarization_model.dtype)

    with torch.inference_mode():
        logits = diarization_model(**inputs).logits  # (1, num_frames, 8), one frame every 10 ms

    segments = diarization_processor.extract_speaker_dict(logits, inputs.attention_mask)[0]

    return segments

def transcribe_segment(segment: dict[str, str], audio_data: np.ndarray, sampling_rate: int, transcription_pipeline) -> str:
    start_time = segment["Start"]
    end_time = segment["End"]
    speaker = segment["Speaker"]

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
    result = transcription_pipeline(
        audio_segment,
        generate_kwargs={"language": "english", "task": "transcribe"},
        return_timestamps=False
    )

    text = result["text"].strip()
    # print(f"speaker_{speaker}: {start_time:.2f}s - {end_time:.2f}s")
    # print(f"  {text}\n")

    return text

def transcribe_segments(segments: list[dict[str, str]], audio_data: np.ndarray, sampling_rate: int, transcription_pipeline) -> list[TranscriptSegment]:
    transcript_segments = []
    for segment in segments:
        text = transcribe_segment(segment, audio_data, sampling_rate, transcription_pipeline)
        if text:  # Only add segments that have transcribed text
            transcript_segments.append(
                TranscriptSegment(
                    speaker=f"speaker_{segment['Speaker']}",
                    text=text,
                    start_seconds=segment["Start"],
                    end_seconds=segment["End"],
                )
            )
    return transcript_segments

def merge_adjacent_speaker_segments(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
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

class TranscriptionProvider(Protocol):
    demo_mode: bool

    def transcribe(self, audio_file: str, content: bytes, diarization_model: torch.nn.Module, diarization_processor: nn.Module, transcription_pipeline) -> TranscriptionResult: ...

class LocalWhisperTranscriber(
    TranscriptionProvider
):
    demo_mode = False

    def __init__(self):
        super().__init__()

    def transcribe(self, audio_file: str, content: bytes, diarization_model: torch.nn.Module, diarization_processor: nn.Module, transcription_pipeline) -> TranscriptionResult:
        
        sampling_rate = diarization_processor.feature_extractor.sampling_rate
        # audio, sr = get_audio_from_bytes(content, sampling_rate)
        audio, _ = librosa.load(str(audio_file), sr=sampling_rate)
        audio_segments = get_audio_segments(audio, diarization_model, diarization_processor)
        print(f"Audio segments: {audio_segments}")
        segments = transcribe_segments(audio_segments, audio, sampling_rate, transcription_pipeline)
        print(f"Transcribed segments: {segments}")
        segments = merge_adjacent_speaker_segments(segments)
        print(f"Merged segments: {segments}")

        return TranscriptionResult(
            segments=segments,
            duration_seconds=None,
            provider="local_whisper",
            demo_mode=False,
        )

diarization_model_id = "nvidia/Nemotron-3-Diarization"
diarization_processor = AutoProcessor.from_pretrained(diarization_model_id)
diarization_model = AutoModelForAudioFrameClassification.from_pretrained(diarization_model_id)

# Load Whisper for transcription
whisper_model = "openai/whisper-small"
transcription_pipeline = pipeline("automatic-speech-recognition", model=whisper_model)

transcriber: TranscriptionProvider = LocalWhisperTranscriber()
audio_name = "raw-1.wav"
audio_path = Path("audio") / audio_name
audio_bytes = audio_path.read_bytes()

result = transcriber.transcribe(str(audio_path), audio_bytes, diarization_model, diarization_processor, transcription_pipeline)
print(result)