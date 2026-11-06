import os
import requests
from pathlib import Path
import time
from dotenv import load_dotenv

load_dotenv()


url = "https://api.pyannote.ai/v1/diarize"
api_key = os.getenv("PYANNOTE_API_KEY")
headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

audio_name = "raw-1.wav"
audio_path = Path("audio") / audio_name

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

if response.status_code != 200:
    print(f"Error: {response.status_code} - {response.text}")
else:
    result = response.json()
    print(result)

    job_id = result["jobId"]

    results = None

    while True:
        response = requests.get(
            f"https://api.pyannote.ai/v1/jobs/{job_id}", headers=headers
        )

        if response.status_code != 200:
            print(f"Error: {response.status_code} - {response.text}")
            break

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