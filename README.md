# EchoID backend

FastAPI monolith for speaker-aware audio transcripts, user and guest sessions, generation history, credit balances, and M-Pesa/card checkout.

## Run locally

Python 3.12 or newer is required. Create a virtual environment and install the project:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Without a `.env` file, the app uses a local SQLite database. For local PostgreSQL, set `DATABASE_URL` to a PostgreSQL URL using `localhost`. For Docker Compose, copy `.env.example` to `.env`, leave its PostgreSQL URL pointing at the `db` service, then run `docker compose up --build`.

Interactive API documentation is available at `/docs`; API routes are under `/api/v1`.
The responsive Jinja frontend is served at `/`, with `/login`, `/register`, `/dashboard`, `/studio`, `/gallery`, and `/billing` pages.

## Main API flows

- `POST /auth/guest` creates a guest token. Send it as `X-Guest-Token` to upload audio and use the single free guest generation.
- `POST /auth/register`, `POST /auth/login`, and `POST /auth/firebase` provide password and Firebase ID-token sign-in. Registration accepts `X-Guest-Token` to claim the guest's generation.
- `POST /generations` accepts a multipart `audio` file. Supported extensions: WAV, MP3, M4A, MP4, WebM, OGG, and FLAC. With a configured real provider, signed-in accounts spend one credit per generation by default; demo generations are free.
- `GET /generations`, `GET /generations/{id}`, and `DELETE /generations/{id}` manage a user's or guest's history.
- `GET /generations/{id}/export?format=json|txt|pdf` downloads transcripts. Guests must register or sign in before exporting.
- `GET /billing/packages` lists fixed KES credit packages. Authenticated users can start M-Pesa STK, QR, and manual till/paybill payments, or card checkout at `/billing/mpesa/*` and `/billing/card`.
- Provider callbacks are received at `/billing/webhooks/mpesa`, `/billing/webhooks/mpesa/c2b`, and `/billing/webhooks/stripe`. Callback credentials/signatures are verified, and payment crediting is idempotent.

## Provider configuration

Without `TRANSCRIPTION_API_URL`, generation uses a clearly marked demo adapter. It does not analyze the uploaded audio. To connect a transcription/diarization service, configure `TRANSCRIPTION_API_URL` and optionally `TRANSCRIPTION_API_KEY`. The configured service should accept a multipart `file` and return JSON in this shape:

```json
{
  "provider": "your-provider",
  "duration_seconds": 18.4,
  "segments": [
    {
      "speaker": "Speaker 1",
      "text": "Example transcript.",
      "start_seconds": 0.2,
      "end_seconds": 2.8
    }
  ]
}
```

Configure the Firebase project ID, Safaricom Daraja credentials/callback URL/token, M-Pesa till or paybill details, and Stripe secrets in `.env` to enable those integrations. Real provider calls are disabled when required credentials are missing. Register the M-Pesa C2B confirmation URL with Daraja when using manual or QR payment reconciliation.

## Checks

```powershell
pytest
```
