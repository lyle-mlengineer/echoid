from dataclasses import dataclass
from typing import Protocol
import os
import requests
from dotenv import load_dotenv
import time

load_dotenv()


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


class PynnoteProvider:
    def __init__(self, pynnote_api_url: str, pynnote_api_key: str) -> None:
        self.pynnote_api_url = pynnote_api_url
        self.pynnote_api_key = pynnote_api_key

    def transcribe(
        self, filename: str, content: bytes, language: str | None = None
    ) -> TranscriptionResult:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        audio_url = "https://files.pyannote.ai/marklex1min.wav"

        data = {
            "url": audio_url,
            "model": "precision-2",
            "transcription": True,
            "transcriptionConfig": {
                "model": "parakeet-tdt-0.6b-v3"
            }
        }

        response = requests.post(url, headers=headers, json=data)

        response.raise_for_status()

        result = response.json()
        print(result)

        job_id = result["jobId"]

        transcriptions = []

        while True:
            response = requests.get(
                f"https://api.pyannote.ai/v1/jobs/{job_id}", headers=headers
            )

            response.raise_for_status()

            data = response.json()
            status = data["status"]

            if status in ["succeeded", "failed", "canceled"]:
                if status == "succeeded":
                    print("Job completed successfully!")
                    print(data["output"].keys())
                    transcriptions = data["output"]["turnLevelTranscription"]
                else:
                    print(f"Job {status}")
                break

            print(f"Job status: {status}, waiting...")
            time.sleep(10)

        print(transcriptions)

        segments = [
            TranscriptSegment(
                speaker=str(item["speaker"]),
                text=str(item["text"]),
                start_seconds=float(item["start"]),
                end_seconds=float(item["end"]),
            )
            for item in transcriptions
        ]

        if not segments:
            raise ValueError("The transcription provider returned no segments.")
        duration = None
        return TranscriptionResult(
            segments=segments,
            duration_seconds=float(duration) if duration is not None else None,
            provider="pynnote",
            demo_mode=False,
        )

url = "https://api.pyannote.ai/v1/diarize"
api_key = os.getenv("PYANNOTE_API_KEY")

provider = PynnoteProvider(url, api_key)
result = provider.transcribe(None, None, "en")
print(result)