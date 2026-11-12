<p align="center">
  <img src="./docs/cover.png" alt="EchoID — hear who spoke, with speaker-labelled transcripts" width="100%" />
</p>

<h1 align="center">EchoID</h1>

<p align="center">
  <strong>Every voice, heard clearly.</strong><br/>
  Turn a recording into a speaker-labelled transcript — then search it, correct it, and export it as PDF, text or JSON, with credit-based billing.
</p>

<p align="center">
  <a href="https://echoid.onrender.com/">
    <img src="https://img.shields.io/badge/Live%20demo-on%20Render-46E3B7?style=for-the-badge&logo=render&logoColor=white" alt="Live demo on Render" />
  </a>
  <a href="https://github.com/lyle-mlengineer/echoid/actions/workflows/ci.yml">
    <img src="https://img.shields.io/github/actions/workflow/status/lyle-mlengineer/echoid/ci.yml?style=for-the-badge&label=CI&logo=githubactions&logoColor=white" alt="CI status" />
  </a>
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/License-Apache%202.0-D22128?style=for-the-badge&logo=apache&logoColor=white" alt="Apache License 2.0" />
  <img src="https://img.shields.io/badge/PRs-welcome-07877C?style=for-the-badge" alt="Pull requests welcome" />
</p>

<p align="center">
  <a href="https://echoid.onrender.com/"><strong>Open the live app</strong></a> ·
  <a href="https://echoid.onrender.com/docs">API documentation</a> ·
  <a href="https://github.com/lyle-mlengineer/echoid/issues">Report a bug</a> ·
  <a href="https://github.com/lyle-mlengineer/echoid/issues">Request a feature</a>
</p>

> **The short version** — Upload a conversation. EchoID separates the voices and writes down what each person said, with timestamps and names you can correct. Try one recording as a guest; create an account to keep it, edit the transcript and export a clean record.

---

## What EchoID does — and who it is for

**EchoID is a speaker-aware transcription studio for recorded conversations.** Upload a meeting, interview or call, and it returns a transcript split by speaker — who spoke, when, and what they said. You can rename speakers, fix a line, filter by voice, play the audio back alongside the text, and export the result in the format your next step needs.

It is built for:

| You are… | EchoID gives you… |
|---|---|
| A **podcaster, interviewer or researcher** | A clean first draft with speakers separated, so editing starts from structure instead of a wall of text |
| A **journalist or note-taker** | Searchable, timestamped quotes you can verify against the recording |
| A **support, ops or sales team** | Readable records of calls without replaying every minute to find one sentence |
| A **team in Kenya & East Africa** | Native M-Pesa billing in Kenyan shillings, with cards as a fallback |

The product is one deliberately simple loop: **upload → diarize → review → export.**

## Product tour

| Capability | What you get |
|---|---|
| **Upload studio** | WAV, MP3, M4A, MP4, WebM, OGG or FLAC files up to 25 MB, with auto-detect or a chosen spoken language |
| **Speaker diarization** | Every segment carries a speaker label, start time and end time |
| **Guest trial** | One free generation per guest session; registering with the same browser claims the transcript |
| **Transcript review** | Rename a speaker, map the label to a saved profile, edit or delete individual lines, and play the audio while you read |
| **Speaker directory** | Reusable speaker profiles with a name, description and optional avatar (JPG, PNG or WebP under 2 MB) so recurring people stay consistent |
| **Filters** | Show only specific speakers, search the transcript, and carry the same filters into an export |
| **Exports** | JSON for tooling, plain text for documents, and a branded PDF with speaker colours, timestamps and a filter note |
| **History & dashboard** | A gallery of past transcripts, credit balance, voice count and recent activity |
| **Credits & billing** | Packs paid by M-Pesa or card — no subscription, and credits do not expire |
| **Accounts** | Email and password, plus Google sign-in through Firebase |

## How to use EchoID

**1. Open the studio.** Visit [the live studio](https://echoid.onrender.com/studio), or run it locally and go to `/studio`. No account is required to try it.

**2. Upload your audio.** Drop in a recording, pick a language or leave auto-detect on, and start the transcript.

**3. Review what was said.** EchoID returns speaker-labelled turns with timestamps. Rename `Speaker 1` to a real name, pick a saved speaker profile, correct a line, or delete turns that do not belong.

**4. Sign in to keep it.** Guests can preview a transcript but cannot export it. Register or continue with Google, and the guest generation is claimed by your new account.

**5. Export your way.** Download JSON, TXT or a branded PDF. Speaker and search filters apply to the export, so you can hand over just the voices or the lines that matter.

**6. Top up when you need more.** New accounts start with **5 free credits**; each real transcription costs **1 credit** by default. Guests get one free generation, and the built-in demo adapter never charges.

| Pack | Credits | Price (KES) | Approx. transcriptions |
|---|---:|---:|---:|
| Starter | 50 | 100 | 50 |
| Creator | 140 | 250 | 140 |
| Studio | 300 | 500 | 300 |

*Packs are defined in `app/api/routes.py`; the per-generation rate is set with `CREDIT_COST_PER_GENERATION`.*

### Paying for credits

- **M-Pesa STK push** — enter a Safaricom number and approve the prompt on the phone.
- **M-Pesa QR** — scan the returned Daraja QR code and pay.
- **M-Pesa Paybill or Till** — pay manually using the account reference EchoID issues.
- **Card** — Stripe Checkout as the fallback.

Payments are **idempotent**: each payment settles exactly once, under a row lock, and only after the provider confirms it. Amounts and currencies are checked against the order, and every credit movement is recorded in a ledger.

## Architecture

**EchoID is a domain-driven monolith, on purpose.** One FastAPI service serves the Jinja frontend and the JSON API from the same origin. Rich dataclass entities and domain events live in `app/domain`; Pydantic models guard the HTTP boundary in `app/api/schemas.py`; persistence and third-party providers stay in `app/infrastructure`.

```text
app/
├── main.py                  # App factory, routers, mounts and lifespan
├── web.py                   # Server-rendered pages
├── api/
│   ├── routes.py            # HTTP endpoints and orchestration
│   └── schemas.py           # Pydantic request/response contracts
├── core/
│   ├── config.py            # Typed settings from the environment
│   └── security.py          # Argon2 hashing and JWT access tokens
├── domain/
│   ├── entities.py          # Generation, Payment, TranscriptSegment
│   ├── events.py            # Domain events and an in-process event bus
│   └── languages.py         # Supported spoken languages
├── infrastructure/
│   ├── database.py          # Engine, sessions and additive migrations
│   ├── models.py            # SQLAlchemy persistence models
│   ├── transcription.py     # Provider protocol, HTTP adapter and demo adapter
│   ├── payments.py          # Daraja client and Stripe signature checks
│   └── transcript_pdf.py    # Branded ReportLab transcript layout
├── templates/               # Landing, studio, gallery, dashboard, billing, auth
├── static/                  # CSS and vanilla JavaScript
└── audio/                   # Sample audio mount
tests/                       # API, billing, export and page tests
```

**The money and transcript paths are treated as first-class.** Guest usage is enforced with a conditional database update, credit debits use a guarded `UPDATE … WHERE credits >= cost`, payment settlement is locked and idempotent, and deleting a transcript also removes its stored audio.

## Run it locally

**Prerequisites:** Python 3.12+. No database service is required for the default setup; a transcription provider key is only needed for real analysis.

### 1. Clone and install

```bash
git clone https://github.com/lyle-mlengineer/echoid.git
cd echoid
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

### 2. Configure the environment

```bash
cp .env.example .env               # Windows: Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Put the generated value in `SECRET_KEY`.

> **Database choice.** With no `DATABASE_URL`, EchoID uses SQLite at `./dev.db` and creates its tables on startup. The sample `.env` points at the `db` service in Docker Compose; for a local server either comment that line out (SQLite) or change it to `postgresql+psycopg://user:password@localhost:5432/echoid`.

> **The demo adapter does not transcribe.** Without `TRANSCRIPTION_API_URL`, EchoID returns clearly marked placeholder turns, does not inspect the uploaded audio, and charges no credits. Add a provider URL and key to turn on real transcription.

### 3. Run the app

```bash
uvicorn app.main:app --reload
```

| URL | What is there |
|---|---|
| `http://127.0.0.1:8000/` | Landing page and product explainer |
| `/studio` | Guest-capable upload and transcript review |
| `/gallery`, `/dashboard` | Past transcripts and account overview |
| `/billing` | Credit packs, M-Pesa and card checkout |
| `/login`, `/register` | Password and Google sign-in |
| `/docs` | Interactive OpenAPI documentation |
| `/api/v1` | JSON API root |

### Docker Compose

The compose file runs PostgreSQL and the API together:

```bash
cp .env.example .env
docker compose up --build
```

Keep the sample `DATABASE_URL` pointing at the `db` host. Uploads are mounted from `./uploads`.

### Core configuration

| Variable | Default | Purpose |
|---|---|---|
| `APP_ENV` | `development` | Set to `production` to enforce strong secrets |
| `SECRET_KEY` | development placeholder | JWT signing key — **must** be changed; production requires at least 32 bytes |
| `DATABASE_URL` | unset → `sqlite:///./dev.db` | SQLAlchemy connection string |
| `STORAGE_DIR` | `./uploads` | Where uploaded audio is stored |
| `ACCESS_TOKEN_MINUTES` | `60` | Access-token lifetime (guest tokens last 30 days) |
| `FREE_CREDITS` | `5` | Credits granted on registration |
| `CREDIT_COST_PER_GENERATION` | `1` | Credits charged per real transcription |
| `MAX_UPLOAD_MB` | `25` | Maximum upload size |

### Integration credentials

| Area | Variables |
|---|---|
| Transcription | `TRANSCRIPTION_API_URL`, `TRANSCRIPTION_API_KEY` |
| Google sign-in | `FIREBASE_PROJECT_ID`, `FIREBASE_API_KEY`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_APP_ID` |
| M-Pesa (Daraja) | `MPESA_BASE_URL`, `MPESA_CONSUMER_KEY`, `MPESA_CONSUMER_SECRET`, `MPESA_SHORTCODE`, `MPESA_PASSKEY`, `MPESA_CALLBACK_URL`, `MPESA_CALLBACK_TOKEN`, `MPESA_PAYBILL_OR_TILL`, `MPESA_PAYMENT_TYPE` |
| Cards | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `PAYMENT_SUCCESS_URL`, `PAYMENT_CANCEL_URL` |

The transcription service receives a multipart `file` (and `language` when one was chosen), and is expected to answer with:

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

Register these callbacks publicly:

- M-Pesa STK → `/api/v1/billing/webhooks/mpesa?token=<MPESA_CALLBACK_TOKEN>`
- M-Pesa C2B confirmation → `/api/v1/billing/webhooks/mpesa/c2b?token=<MPESA_CALLBACK_TOKEN>`
- Stripe → `/api/v1/billing/webhooks/stripe`, subscribed to `checkout.session.completed`

### Deploying to Render

Deploy the repository as a **Web Service** with:

- **Build:** `pip install .`
- **Start:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Environment:** `APP_ENV=production`, a strong `SECRET_KEY`, a PostgreSQL `DATABASE_URL`, your transcription provider, Firebase and payment credentials.

Attach a **persistent disk** and point `STORAGE_DIR` at it — uploaded audio lives on the local filesystem. In production, EchoID refuses a default or short `SECRET_KEY`, and a short `MPESA_CALLBACK_TOKEN` when one is set.

### Tests

```bash
pytest -q
```

The 12-test suite runs against a temporary SQLite database with the demo provider, so it needs no external services. It covers registration and guest claims, language validation, credit charging, speaker profiles, transcript edits, filtered exports, branded PDFs, ranged audio streaming, payment idempotency, Stripe signatures and the rendered pages. GitHub Actions runs the same suite on every push and pull request.

## Technologies used

<p align="center">
  <img src="https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/SQLAlchemy-D71F00?style=flat-square&logo=sqlalchemy&logoColor=white" alt="SQLAlchemy" />
  <img src="https://img.shields.io/badge/Pydantic-E92063?style=flat-square&logo=pydantic&logoColor=white" alt="Pydantic" />
  <img src="https://img.shields.io/badge/PostgreSQL-4169E1?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite" />
  <img src="https://img.shields.io/badge/Jinja2-B41717?style=flat-square&logo=jinja&logoColor=white" alt="Jinja2" />
  <img src="https://img.shields.io/badge/Uvicorn-499848?style=flat-square&logo=uvicorn&logoColor=white" alt="Uvicorn" />
</p>
<p align="center">
  <img src="https://img.shields.io/badge/ReportLab-D22128?style=flat-square" alt="ReportLab" />
  <img src="https://img.shields.io/badge/Firebase-FFCA28?style=flat-square&logo=firebase&logoColor=black" alt="Firebase" />
  <img src="https://img.shields.io/badge/M--Pesa-4CAF50?style=flat-square&logoColor=white" alt="M-Pesa" />
  <img src="https://img.shields.io/badge/Stripe-635BFF?style=flat-square&logo=stripe&logoColor=white" alt="Stripe" />
  <img src="https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white" alt="pytest" />
  <img src="https://img.shields.io/badge/GitHub%20Actions-2088FF?style=flat-square&logo=githubactions&logoColor=white" alt="GitHub Actions" />
  <img src="https://img.shields.io/badge/Render-46E3B7?style=flat-square&logo=render&logoColor=white" alt="Render" />
</p>

| Layer | Choice | Why |
|---|---|---|
| **Backend** | FastAPI + Uvicorn | Typed routes, multipart uploads, audio responses and free OpenAPI docs |
| **Domain** | Dataclasses + domain events | Speaker, credit and payment rules stay explicit and testable |
| **Persistence** | SQLAlchemy 2 + SQLite/PostgreSQL | Zero-setup locally, a relational ledger and history in production |
| **Validation** | Pydantic v2 + pydantic-settings | Strict upload forms, speaker profiles and typed configuration |
| **Auth** | Argon2 (`pwdlib`) + JWT (`PyJWT`) + Firebase | Local passwords with optional Google sign-in |
| **Transcription** | Pluggable HTTP provider + demo adapter | Any diarization service behind one small JSON contract |
| **Exports** | JSON, text and ReportLab PDF | Machine-readable, human-readable and presentation-ready output |
| **Payments** | Daraja (M-Pesa) + Stripe | Local rails first, cards as a fallback |
| **Frontend** | Jinja2 + vanilla CSS/JS | Server-rendered studio with no build step |
| **Type & design** | Nunito + DM Sans | Rounded display type on a cream, teal and gold system |
| **Testing** | pytest + Starlette TestClient | API, billing and page coverage without external services |
| **Delivery** | Docker, GitHub Actions and Render | Reproducible local stack, automated checks, public deployment |

## API surface

The JSON API lives under `/api/v1`; browser pages are server-rendered by Jinja. Authenticate with `Authorization: Bearer <token>` for an account, or `X-Guest-Token: <token>` for a guest session.

| Area | Routes |
|---|---|
| **Auth** | `POST /auth/guest`, `/auth/register`, `/auth/login`, `/auth/firebase`; `GET /auth/me` |
| **Generations** | `POST /generations` (multipart `audio`); `GET /generations`, `/generations/{id}`; `DELETE /generations/{id}` |
| **Transcript** | `PATCH /generations/{id}/speakers`; `PATCH`/`DELETE /generations/{id}/segments/{index}` |
| **Audio & export** | `GET /generations/{id}/audio` (supports range requests); `GET /generations/{id}/export?format=json\|txt\|pdf` |
| **Speakers** | `GET`/`POST /speakers`; `PATCH`/`DELETE /speakers/{id}` |
| **Billing** | `GET /billing/packages`, `/billing/payments`; `POST /billing/mpesa/stk`, `/billing/mpesa/qr`, `/billing/mpesa/manual`, `/billing/card` |
| **Webhooks** | `POST /billing/webhooks/mpesa`, `/billing/webhooks/mpesa/c2b`, `/billing/webhooks/stripe` |
| **Operations** | `GET /health` |

Exports accept repeatable `speakers` and a free-text `search` query, so a PDF can contain only the voices or lines you selected. Guest sessions may generate, review and edit once, but downloads require an account.

## Contributing

Contributions are welcome — especially around transcription adapters, billing edge cases and transcript accessibility.

1. **Fork** the repository and create a focused branch: `git checkout -b feat/speaker-profile-avatars`.
2. **Keep boundaries honest.** Domain rules belong in `app/domain`; HTTP validation belongs in `app/api/schemas.py`; provider calls belong in `app/infrastructure`.
3. **Add a test** for anything touching credits, payments, guest claims, exports or transcript state.
4. **Run the suite** with `pytest -q`, then open a pull request describing the what and the why.

Please do not commit `.env` files, provider keys, uploaded audio or real transcripts. For security issues, email the author privately instead of opening a public issue.

## Attribution

### Licence

EchoID is released under the **Apache License 2.0**. See [LICENSE](./LICENSE) for the full text.

### How to attribute

If you reference, fork or build on EchoID, keep the licence and copyright notice, and credit the project as:

> **EchoID by Lyle Okoth** — https://github.com/lyle-mlengineer/echoid

Modified distributions must state that changes were made, as required by Apache-2.0. Please do not imply endorsement by the author.

### Third-party credit

Google sign-in is provided by **Firebase** and **Google Identity**; M-Pesa payments use **Safaricom Daraja**; card payments use **Stripe**; PDF transcripts are laid out with **ReportLab**. The interface uses **Nunito** and **DM Sans** from Google Fonts. Any configured transcription or diarization service remains the property of its provider. All trademarks belong to their respective owners.

**The demo adapter does not process audio.** Recordings and transcripts in this repository's test fixtures are synthetic; do not commit real conversations.

---

## Author

**Lyle Okoth** — Machine Learning Engineer, Speech & Audio AI

I build and productionise machine learning systems end to end, from data pipelines and model training to low-latency serving and the product around them.

| | |
|---|---|
| **Email** | [lyleokoth.mlengineer@gmail.com](mailto:lyleokoth.mlengineer@gmail.com) |
| **GitHub** | [@lyle-mlengineer](https://github.com/lyle-mlengineer) |
| **Portfolio** | [lyle-mlengineer.github.io](https://lyle-mlengineer.github.io) |
| **LinkedIn** | [in/lyle-okoth](https://www.linkedin.com/in/lyle-okoth/) |
| **Medium** | [@lyle-okoth](https://medium.com/@lyle-okoth) |
| **X** | [@LyleOkoth](https://x.com/LyleOkoth) |

<p align="center">
  <a href="https://echoid.onrender.com/"><img src="https://img.shields.io/badge/Try%20EchoID-Live-07877C?style=for-the-badge" alt="Try EchoID live" /></a>
  <a href="mailto:lyleokoth.mlengineer@gmail.com"><img src="https://img.shields.io/badge/Email-D14836?style=for-the-badge&logo=gmail&logoColor=white" alt="Email Lyle Okoth" /></a>
</p>

<p align="center">
  <i>Every voice, heard clearly.</i><br/>
  © 2026 Lyle Okoth · Built with FastAPI, M-Pesa and a lot of listening.
</p>
