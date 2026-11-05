import asyncio
import hmac
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

import httpx
import jwt
from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.transport import requests as google_requests
from google.auth.exceptions import GoogleAuthError
from google.oauth2 import id_token as google_id_token
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (
    FirebaseLoginRequest,
    GenerationResponse,
    GuestSessionResponse,
    LoginRequest,
    MpesaStkRequest,
    PaymentCreatedResponse,
    PaymentPackageResponse,
    PaymentResponse,
    RegisterRequest,
    SegmentTextRequest,
    SpeakerCreateRequest,
    SpeakerResponse,
    SpeakerRenameRequest,
    SpeakerUpdateRequest,
    TokenResponse,
    UserResponse,
)
from app.core.config import Settings
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.domain.entities import Generation, Payment
from app.domain.events import EventBus
from app.infrastructure.models import (
    CreditLedgerRecord,
    GenerationRecord,
    GuestSessionRecord,
    PaymentRecord,
    SpeakerRecord,
    UserRecord,
    utc_now,
)
from app.infrastructure.payments import MpesaClient, PaymentProviderError, verify_stripe_signature
from app.infrastructure.transcript_pdf import clock, render_transcript_pdf, speaker_tones

router = APIRouter()
bearer_scheme = HTTPBearer(auto_error=False)
PACKAGES = {
    "starter": {"amount_kes": 100, "credits": 50},
    "creator": {"amount_kes": 250, "credits": 140},
    "studio": {"amount_kes": 500, "credits": 300},
}
ALLOWED_AUDIO = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
}


def get_db(request: Request):
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    x_guest_token: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> tuple[UserRecord | None, str | None]:
    settings = get_settings(request)
    token = credentials.credentials if credentials else x_guest_token
    if not token:
        raise HTTPException(status_code=401, detail="Sign in or provide a guest session token.")
    try:
        claims = decode_token(token, settings)
    except (jwt.InvalidTokenError, TypeError):
        raise HTTPException(status_code=401, detail="The supplied access token is invalid or expired.")
    subject = claims.get("sub")
    if claims.get("type") == "access" and credentials:
        user = db.get(UserRecord, subject)
        if user is None:
            raise HTTPException(status_code=401, detail="The account for this token no longer exists.")
        return user, None
    if claims.get("type") == "guest" and not credentials and isinstance(subject, str):
        try:
            UUID(subject)
        except ValueError:
            raise HTTPException(status_code=401, detail="The guest token is invalid.")
        guest_session = db.get(GuestSessionRecord, subject)
        if guest_session is None or guest_session.claimed_by_user_id is not None:
            raise HTTPException(status_code=401, detail="The guest session is no longer available.")
        return None, subject
    raise HTTPException(status_code=401, detail="The supplied token is not valid for this operation.")


def require_user(principal=Depends(get_principal)) -> UserRecord:
    user, _ = principal
    if user is None:
        raise HTTPException(status_code=401, detail="Create an account to access this feature.")
    return user


def _token_for_user(user: UserRecord, settings: Settings) -> TokenResponse:
    token = create_token(
        user.id,
        "access",
        settings,
        timedelta(minutes=settings.access_token_minutes),
    )
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            credits=user.credits,
        ),
    )


def _generation_response(record: GenerationRecord) -> GenerationResponse:
    return GenerationResponse(
        id=record.id,
        filename=record.filename,
        status=record.status,
        segments=json.loads(record.transcript_json),
        duration_seconds=record.duration_seconds,
        provider=record.provider,
        demo_mode=record.demo_mode,
        credits_charged=record.credits_charged,
        created_at=record.created_at,
    )


def _speaker_response(record: SpeakerRecord) -> SpeakerResponse:
    return SpeakerResponse(
        id=record.id,
        name=record.name,
        description=record.description,
        image_data=record.image_data,
        created_at=record.created_at,
    )


def _owned_speaker(db: Session, speaker_id: UUID, user: UserRecord) -> SpeakerRecord:
    record = db.get(SpeakerRecord, str(speaker_id))
    if record is None or record.user_id != user.id:
        raise HTTPException(status_code=404, detail="Speaker not found.")
    return record


def _owned_generation(
    db: Session, generation_id: UUID, principal: tuple[UserRecord | None, str | None]
) -> GenerationRecord:
    user, guest_id = principal
    record = db.get(GenerationRecord, str(generation_id))
    owns = record is not None and (
        (user is not None and record.user_id == user.id)
        or (guest_id is not None and record.guest_id == guest_id)
    )
    if not owns:
        raise HTTPException(status_code=404, detail="Generation not found.")
    return record


def _visible_segments(
    segments: list[dict], speakers: list[str], search: str
) -> list[dict]:
    wanted = {name.strip().casefold() for name in speakers if name and name.strip()}
    words = [word.casefold() for word in re.split(r"\s+", (search or "").strip()) if word]
    return [
        item
        for item in segments
        if (not wanted or item["speaker"].strip().casefold() in wanted)
        and all(word in item["text"].casefold() for word in words)
    ]


def _transcript_meta(record: GenerationRecord, segments: list[dict]) -> str:
    parts = []
    if record.created_at:
        parts.append(f"{record.created_at.day} {record.created_at:%b %Y}")
    if record.duration_seconds is not None:
        parts.append(f"{clock(record.duration_seconds)} min")
    parts.append(f"{len(segments)} speaker turn{'s' if len(segments) != 1 else ''}")
    if record.provider:
        parts.append(record.provider)
    return " · ".join(parts)


def _filter_note(speakers: list[str], search: str) -> str:
    names = [name.strip() for name in speakers if name and name.strip()]
    parts = []
    if names:
        parts.append("Showing " + ", ".join(names))
    if search and search.strip():
        parts.append(f"matching “{search.strip()}”")
    return f"Filtered — {' · '.join(parts)}" if parts else ""


def _payment_package(package_id: str) -> dict[str, int]:
    package = PACKAGES.get(package_id)
    if package is None:
        raise HTTPException(status_code=422, detail="Choose a valid credit package.")
    return package


def _parse_kes_amount(value: object) -> int:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail="M-Pesa callback is missing a valid amount.")
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise HTTPException(status_code=400, detail="M-Pesa callback amount must be a whole KES value.")
    return int(amount)


async def _json_object(request: Request) -> dict:
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise HTTPException(status_code=400, detail="Invalid JSON callback payload.") from error
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON callback payload.")
    return payload


def _new_payment(db: Session, user: UserRecord, provider: str, package_id: str) -> PaymentRecord:
    package = _payment_package(package_id)
    payment = PaymentRecord(
        user_id=user.id,
        provider=provider,
        amount_kes=package["amount_kes"],
        credits=package["credits"],
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def _settle_payment(
    db: Session,
    payment: PaymentRecord,
    event_bus: EventBus,
    transaction_reference: str | None = None,
) -> None:
    locked = db.scalar(
        select(PaymentRecord).where(PaymentRecord.id == payment.id).with_for_update()
    )
    if locked is None or locked.status == "completed":
        return
    user = db.get(UserRecord, locked.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Payment account not found.")
    domain_payment = Payment(
        id=UUID(locked.id),
        owner_id=UUID(user.id),
        amount_kes=locked.amount_kes,
        credits=locked.credits,
        status=locked.status,
    )
    try:
        domain_payment.complete()
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    locked.status = domain_payment.status
    locked.completed_at = utc_now()
    if transaction_reference:
        locked.transaction_reference = transaction_reference
    user.credits += locked.credits
    db.add(
        CreditLedgerRecord(
            user_id=user.id,
            amount=locked.credits,
            reference_type="payment",
            reference_id=locked.id,
        )
    )
    db.commit()
    for event in domain_payment.events:
        event_bus.publish(event)


def _fail_payment(db: Session, payment: PaymentRecord) -> None:
    locked = db.scalar(
        select(PaymentRecord).where(PaymentRecord.id == payment.id).with_for_update()
    )
    if locked is None or locked.status != "pending":
        return
    domain_payment = Payment(
        id=UUID(locked.id),
        owner_id=UUID(locked.user_id),
        amount_kes=locked.amount_kes,
        credits=locked.credits,
    )
    domain_payment.fail()
    locked.status = domain_payment.status
    db.commit()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/auth/guest", response_model=GuestSessionResponse)
def create_guest_session(
    request: Request,
    db: Session = Depends(get_db),
) -> GuestSessionResponse:
    settings = get_settings(request)
    guest_id = str(uuid4())
    token = create_token(guest_id, "guest", settings, timedelta(days=30))
    db.add(GuestSessionRecord(id=guest_id))
    db.commit()
    return GuestSessionResponse(guest_token=token, free_generation_available=True)


@router.post("/auth/register", response_model=TokenResponse, status_code=201)
def register(
    body: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
    x_guest_token: Annotated[str | None, Header()] = None,
) -> TokenResponse:
    settings = get_settings(request)
    email = str(body.email).lower()
    if db.scalar(select(UserRecord).where(UserRecord.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    guest_id = None
    if x_guest_token:
        try:
            claims = decode_token(x_guest_token, settings)
            guest_id = claims["sub"] if claims.get("type") == "guest" else None
            UUID(guest_id)
        except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
            raise HTTPException(status_code=401, detail="The guest session token is invalid or expired.")
        guest_session = db.get(GuestSessionRecord, guest_id)
        if guest_session is None or guest_session.claimed_by_user_id is not None:
            raise HTTPException(status_code=409, detail="This guest session has already been claimed.")
    user = UserRecord(
        email=email,
        display_name=body.display_name.strip(),
        password_hash=hash_password(body.password),
        credits=settings.free_credits,
    )
    db.add(user)
    try:
        db.flush()
        db.add(
            CreditLedgerRecord(
                user_id=user.id,
                amount=settings.free_credits,
                reference_type="signup",
                reference_id=user.id,
            )
        )
        if guest_id:
            guest_session.claimed_by_user_id = user.id
            db.query(GenerationRecord).filter(
                GenerationRecord.guest_id == guest_id
            ).update(
                {GenerationRecord.user_id: user.id, GenerationRecord.guest_id: None},
                synchronize_session=False,
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    db.refresh(user)
    return _token_for_user(user, settings)


@router.post("/auth/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    email = str(body.email).lower()
    user = db.scalar(select(UserRecord).where(UserRecord.email == email))
    if user is None or user.password_hash is None or not verify_password(
        body.password, user.password_hash
    ):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    return _token_for_user(user, get_settings(request))


@router.post("/auth/firebase", response_model=TokenResponse)
async def firebase_login(
    body: FirebaseLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    settings = get_settings(request)
    if not settings.firebase_project_id:
        raise HTTPException(status_code=503, detail="Firebase authentication is not configured.")
    try:
        claims = await asyncio.to_thread(
            google_id_token.verify_firebase_token,
            body.id_token,
            google_requests.Request(),
            audience=settings.firebase_project_id,
        )
    except (ValueError, GoogleAuthError) as error:
        raise HTTPException(status_code=401, detail="Firebase ID token verification failed.") from error
    email = claims.get("email")
    firebase_uid = claims.get("sub")
    if not isinstance(email, str) or not claims.get("email_verified") or not firebase_uid:
        raise HTTPException(status_code=401, detail="A verified Firebase email is required.")
    email = email.lower()
    user = db.scalar(select(UserRecord).where(UserRecord.email == email))
    if user is None:
        user = UserRecord(
            email=email,
            display_name=claims.get("name") or email.split("@", 1)[0],
            password_hash=None,
            credits=settings.free_credits,
            firebase_uid=firebase_uid,
        )
        db.add(user)
        db.flush()
        db.add(
            CreditLedgerRecord(
                user_id=user.id,
                amount=settings.free_credits,
                reference_type="signup",
                reference_id=user.id,
            )
        )
        db.commit()
        db.refresh(user)
    elif user.firebase_uid not in (None, firebase_uid):
        raise HTTPException(status_code=409, detail="This email is linked to another Firebase account.")
    else:
        user.firebase_uid = firebase_uid
        db.commit()
        db.refresh(user)
    return _token_for_user(user, settings)


@router.get("/auth/me", response_model=UserResponse)
def get_me(user: UserRecord = Depends(require_user)) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        credits=user.credits,
    )


@router.post("/generations", response_model=GenerationResponse, status_code=201)
async def create_generation(
    request: Request,
    audio: UploadFile = File(...),
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
) -> GenerationResponse:
    user, guest_id = principal
    settings: Settings = request.app.state.settings
    filename = Path(audio.filename or "audio").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_AUDIO:
        raise HTTPException(status_code=415, detail="Use WAV, MP3, M4A, MP4, WebM, OGG, or FLAC audio.")
    content = await audio.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if not content:
        raise HTTPException(status_code=422, detail="The uploaded audio file is empty.")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Audio files may not exceed {settings.max_upload_mb} MB.")
    provider = request.app.state.transcription_provider
    credits = (
        settings.credit_cost_per_generation
        if user and not provider.demo_mode
        else 0
    )
    if user and user.credits < credits:
        raise HTTPException(status_code=402, detail="Not enough credits. Purchase a credit package to continue.")
    guest_session = db.get(GuestSessionRecord, guest_id) if guest_id else None
    if guest_id and (guest_session is None or guest_session.generation_created):
        raise HTTPException(
            status_code=403,
            detail="Your free guest generation has been used. Sign up to continue.",
        )
    try:
        result = await provider.transcribe(filename, content)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        raise HTTPException(status_code=502, detail=f"Transcription failed: {error}") from error
    generation_id = uuid4()
    domain_generation = Generation(
        id=generation_id,
        owner_id=UUID(user.id) if user else None,
        guest_id=UUID(guest_id) if guest_id else None,
        filename=filename,
        provider=result.provider,
        demo_mode=result.demo_mode,
    )
    try:
        domain_generation.complete(result.segments, result.duration_seconds, credits)
    except ValueError as error:
        raise HTTPException(status_code=502, detail=f"Transcription result was invalid: {error}") from error

    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = settings.storage_dir / f"{generation_id}{suffix}"
    file_path.write_bytes(content)
    record = GenerationRecord(
        id=str(generation_id),
        user_id=user.id if user else None,
        guest_id=guest_id,
        filename=filename,
        content_type=ALLOWED_AUDIO[suffix],
        file_path=str(file_path),
        status=domain_generation.status,
        transcript_json=json.dumps(
            [
                {
                    "speaker": segment.speaker,
                    "text": segment.text,
                    "start_seconds": segment.start_seconds,
                    "end_seconds": segment.end_seconds,
                }
                for segment in domain_generation.segments
            ]
        ),
        duration_seconds=domain_generation.duration_seconds,
        provider=domain_generation.provider,
        demo_mode=domain_generation.demo_mode,
        credits_charged=credits,
    )
    try:
        if user and credits:
            debit = db.execute(
                update(UserRecord)
                .where(UserRecord.id == user.id, UserRecord.credits >= credits)
                .values(credits=UserRecord.credits - credits)
            )
            if debit.rowcount != 1:
                raise HTTPException(status_code=402, detail="Not enough credits. Purchase a credit package to continue.")
            db.add(
                CreditLedgerRecord(
                    user_id=user.id,
                    amount=-credits,
                    reference_type="generation",
                    reference_id=str(generation_id),
                )
            )
        if guest_id:
            guest_update = db.execute(
                update(GuestSessionRecord)
                .where(
                    GuestSessionRecord.id == guest_id,
                    GuestSessionRecord.generation_created.is_(False),
                    GuestSessionRecord.claimed_by_user_id.is_(None),
                )
                .values(generation_created=True)
            )
            if guest_update.rowcount != 1:
                raise HTTPException(
                    status_code=403,
                    detail="Your free guest generation has already been used.",
                )
        db.add(record)
        db.commit()
        db.refresh(record)
    except (IntegrityError, HTTPException):
        db.rollback()
        file_path.unlink(missing_ok=True)
        if guest_id:
            raise HTTPException(status_code=403, detail="Your free guest generation has already been used.")
        raise
    for event in domain_generation.events:
        request.app.state.event_bus.publish(event)
    return _generation_response(record)


@router.get("/generations", response_model=list[GenerationResponse])
def list_generations(
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[GenerationResponse]:
    user, guest_id = principal
    query = select(GenerationRecord).order_by(GenerationRecord.created_at.desc())
    query = query.where(
        GenerationRecord.user_id == user.id
        if user
        else GenerationRecord.guest_id == guest_id
    )
    return [_generation_response(item) for item in db.scalars(query).all()]


@router.get("/generations/{generation_id}", response_model=GenerationResponse)
def get_generation(
    generation_id: UUID,
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
) -> GenerationResponse:
    return _generation_response(_owned_generation(db, generation_id, principal))


@router.get("/generations/{generation_id}/audio")
def get_generation_audio(
    generation_id: UUID,
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
) -> FileResponse:
    record = _owned_generation(db, generation_id, principal)
    path = Path(record.file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="The audio for this transcript is no longer available.")
    return FileResponse(path, media_type=ALLOWED_AUDIO.get(path.suffix.lower(), "application/octet-stream"))


@router.get("/speakers", response_model=list[SpeakerResponse])
def list_speakers(
    search: str = Query(default="", max_length=120),
    user: UserRecord = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[SpeakerResponse]:
    query = select(SpeakerRecord).where(SpeakerRecord.user_id == user.id)
    search = search.strip()
    if search:
        query = query.where(
            SpeakerRecord.name.ilike(f"%{search}%")
            | SpeakerRecord.description.ilike(f"%{search}%")
        )
    query = query.order_by(SpeakerRecord.name)
    return [_speaker_response(record) for record in db.scalars(query).all()]


@router.post("/speakers", response_model=SpeakerResponse, status_code=201)
def create_speaker(
    request: SpeakerCreateRequest,
    user: UserRecord = Depends(require_user),
    db: Session = Depends(get_db),
) -> SpeakerResponse:
    record = SpeakerRecord(
        user_id=user.id,
        name=request.name,
        description=request.description,
        image_data=request.image_data,
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="A speaker with this name already exists.") from error
    db.refresh(record)
    return _speaker_response(record)


@router.patch("/speakers/{speaker_id}", response_model=SpeakerResponse)
def update_speaker(
    speaker_id: UUID,
    request: SpeakerUpdateRequest,
    user: UserRecord = Depends(require_user),
    db: Session = Depends(get_db),
) -> SpeakerResponse:
    record = _owned_speaker(db, speaker_id, user)
    record.name = request.name
    record.description = request.description
    record.image_data = request.image_data
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="A speaker with this name already exists.") from error
    db.refresh(record)
    return _speaker_response(record)


@router.delete("/speakers/{speaker_id}", status_code=204)
def delete_speaker(
    speaker_id: UUID,
    user: UserRecord = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    record = _owned_speaker(db, speaker_id, user)
    db.delete(record)
    db.commit()
    return Response(status_code=204)


@router.patch("/generations/{generation_id}/speakers", response_model=GenerationResponse)
def rename_generation_speaker(
    generation_id: UUID,
    request: SpeakerRenameRequest,
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
) -> GenerationResponse:
    record = _owned_generation(db, generation_id, principal)
    segments = json.loads(record.transcript_json)
    if not any(item["speaker"] == request.speaker for item in segments):
        raise HTTPException(status_code=404, detail="Speaker not found in this transcript.")
    name = request.name
    if request.speaker_profile_id is not None:
        user, _ = principal
        if user is None:
            raise HTTPException(status_code=401, detail="Sign in to use saved speakers.")
        name = _owned_speaker(db, request.speaker_profile_id, user).name
    for item in segments:
        if item["speaker"] == request.speaker:
            item["speaker"] = name
    record.transcript_json = json.dumps(segments)
    db.commit()
    db.refresh(record)
    return _generation_response(record)


@router.patch("/generations/{generation_id}/segments/{segment_index}", response_model=GenerationResponse)
def update_generation_segment(
    generation_id: UUID,
    segment_index: int,
    request: SegmentTextRequest,
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
) -> GenerationResponse:
    record = _owned_generation(db, generation_id, principal)
    segments = json.loads(record.transcript_json)
    if not 0 <= segment_index < len(segments):
        raise HTTPException(status_code=404, detail="Segment not found in this transcript.")
    segments[segment_index]["text"] = request.text
    record.transcript_json = json.dumps(segments)
    db.commit()
    db.refresh(record)
    return _generation_response(record)


@router.delete("/generations/{generation_id}/segments/{segment_index}", response_model=GenerationResponse)
def delete_generation_segment(
    generation_id: UUID,
    segment_index: int,
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
) -> GenerationResponse:
    record = _owned_generation(db, generation_id, principal)
    segments = json.loads(record.transcript_json)
    if not 0 <= segment_index < len(segments):
        raise HTTPException(status_code=404, detail="Segment not found in this transcript.")
    del segments[segment_index]
    record.transcript_json = json.dumps(segments)
    db.commit()
    db.refresh(record)
    return _generation_response(record)


@router.delete("/generations/{generation_id}", status_code=204)
def delete_generation(
    generation_id: UUID,
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
) -> Response:
    record = _owned_generation(db, generation_id, principal)
    Path(record.file_path).unlink(missing_ok=True)
    db.delete(record)
    db.commit()
    return Response(status_code=204)


@router.get("/generations/{generation_id}/export")
def export_generation(
    generation_id: UUID,
    format: str = Query(pattern="^(json|txt|pdf)$"),
    speakers: list[str] = Query(default=[]),
    search: str = Query(default="", max_length=200),
    principal=Depends(get_principal),
    db: Session = Depends(get_db),
) -> Response:
    user, _ = principal
    if user is None:
        raise HTTPException(status_code=401, detail="Create an account to download generation results.")
    record = _owned_generation(db, generation_id, principal)
    all_segments = json.loads(record.transcript_json)
    segments = _visible_segments(all_segments, speakers, search)
    if format == "json":
        return Response(
            content=json.dumps(
                {
                    "id": record.id,
                    "filename": record.filename,
                    "provider": record.provider,
                    "segments": segments,
                },
                indent=2,
            ),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="echoid-{record.id}.json"'},
        )
    lines = [f"{item['speaker']}: {item['text']}" for item in segments]
    if format == "txt":
        return PlainTextResponse(
            "\n".join(lines),
            headers={"Content-Disposition": f'attachment; filename="echoid-{record.id}.txt"'},
        )
    exported = datetime.now(timezone.utc)
    content = render_transcript_pdf(
        segments,
        speaker_tones(all_segments),
        title=record.filename,
        meta=_transcript_meta(record, segments),
        filter_note=_filter_note(speakers, search),
        reference=str(record.id),
        exported_on=f"{exported.day} {exported:%b %Y}",
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="echoid-{record.id}.pdf"'},
    )


@router.get("/billing/packages", response_model=list[PaymentPackageResponse])
def list_packages() -> list[PaymentPackageResponse]:
    return [
        PaymentPackageResponse(id=package_id, **package)
        for package_id, package in PACKAGES.items()
    ]


@router.get("/billing/payments", response_model=list[PaymentResponse])
def list_payments(user: UserRecord = Depends(require_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(PaymentRecord)
        .where(PaymentRecord.user_id == user.id)
        .order_by(PaymentRecord.created_at.desc())
    ).all()


@router.post("/billing/mpesa/stk", response_model=PaymentCreatedResponse, status_code=201)
async def mpesa_stk(
    body: MpesaStkRequest,
    request: Request,
    user: UserRecord = Depends(require_user),
    db: Session = Depends(get_db),
) -> PaymentCreatedResponse:
    settings = get_settings(request)
    client = MpesaClient(settings)
    if not client.configured:
        raise HTTPException(status_code=503, detail="M-Pesa Daraja is not configured.")
    payment = _new_payment(db, user, "mpesa_stk", body.package_id)
    phone = body.phone_number
    if phone.startswith("+"):
        phone = phone[1:]
    if phone.startswith("0"):
        phone = f"254{phone[1:]}"
    try:
        response_data = await client.stk_push(payment.id, phone, payment.amount_kes)
    except (httpx.HTTPError, ValueError, KeyError, PaymentProviderError) as error:
        _fail_payment(db, payment)
        raise HTTPException(status_code=502, detail=f"M-Pesa request failed: {error}") from error
    checkout_id = response_data.get("CheckoutRequestID")
    if not checkout_id:
        _fail_payment(db, payment)
        raise HTTPException(status_code=502, detail="M-Pesa did not return a checkout request ID.")
    payment.provider_reference = checkout_id
    db.commit()
    db.refresh(payment)
    return PaymentCreatedResponse(
        payment=PaymentResponse.model_validate(payment),
        message=response_data.get("CustomerMessage", "Approve the M-Pesa prompt on your phone."),
        checkout_request_id=checkout_id,
    )


@router.post("/billing/mpesa/qr", response_model=PaymentCreatedResponse, status_code=201)
async def mpesa_qr(
    package_id: str,
    request: Request,
    user: UserRecord = Depends(require_user),
    db: Session = Depends(get_db),
) -> PaymentCreatedResponse:
    client = MpesaClient(get_settings(request))
    if not client.configured:
        raise HTTPException(status_code=503, detail="M-Pesa Daraja is not configured.")
    payment = _new_payment(db, user, "mpesa_qr", package_id)
    try:
        response_data = await client.create_qr(payment.id, payment.amount_kes)
    except (httpx.HTTPError, ValueError, KeyError, PaymentProviderError) as error:
        _fail_payment(db, payment)
        raise HTTPException(status_code=502, detail=f"M-Pesa QR request failed: {error}") from error
    payment.provider_reference = payment.id
    db.commit()
    db.refresh(payment)
    if not isinstance(response_data.get("QRCode"), str):
        _fail_payment(db, payment)
        raise HTTPException(status_code=502, detail="M-Pesa did not return a QR code.")
    return PaymentCreatedResponse(
        payment=PaymentResponse.model_validate(payment),
        message=response_data.get("ResponseDescription", "Scan the returned M-Pesa QR code."),
        qr_code=response_data.get("QRCode"),
    )


@router.post("/billing/mpesa/manual", response_model=PaymentCreatedResponse, status_code=201)
def mpesa_manual(
    package_id: str,
    request: Request,
    user: UserRecord = Depends(require_user),
    db: Session = Depends(get_db),
) -> PaymentCreatedResponse:
    settings = get_settings(request)
    if not settings.mpesa_paybill_or_till:
        raise HTTPException(status_code=503, detail="M-Pesa till or paybill details are not configured.")
    payment = _new_payment(db, user, "mpesa_manual", package_id)
    payment.provider_reference = payment.id
    db.commit()
    db.refresh(payment)
    instructions = f"Pay KES {payment.amount_kes} to {settings.mpesa_payment_type} {settings.mpesa_paybill_or_till}; use {payment.id[:12]} as the account reference."
    return PaymentCreatedResponse(
        payment=PaymentResponse.model_validate(payment),
        message=instructions,
    )


@router.post("/billing/card", response_model=PaymentCreatedResponse, status_code=201)
async def card_checkout(
    package_id: str,
    request: Request,
    user: UserRecord = Depends(require_user),
    db: Session = Depends(get_db),
) -> PaymentCreatedResponse:
    settings = get_settings(request)
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Card payments are not configured.")
    payment = _new_payment(db, user, "stripe", package_id)
    form = {
        "mode": "payment",
        "success_url": settings.payment_success_url,
        "cancel_url": settings.payment_cancel_url,
        "client_reference_id": payment.id,
        "metadata[payment_id]": payment.id,
        "line_items[0][price_data][currency]": "kes",
        "line_items[0][price_data][product_data][name]": f"EchoID {payment.credits} credits",
        "line_items[0][price_data][unit_amount]": str(payment.amount_kes),
        "line_items[0][quantity]": "1",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data=form,
                auth=(settings.stripe_secret_key, ""),
            )
            response.raise_for_status()
            checkout = response.json()
    except (httpx.HTTPError, ValueError, KeyError) as error:
        _fail_payment(db, payment)
        raise HTTPException(status_code=502, detail=f"Card checkout creation failed: {error}") from error
    if not isinstance(checkout, dict) or not isinstance(checkout.get("id"), str) or not isinstance(
        checkout.get("url"), str
    ):
        _fail_payment(db, payment)
        raise HTTPException(status_code=502, detail="Card provider returned an invalid checkout session.")
    payment.provider_reference = checkout["id"]
    db.commit()
    db.refresh(payment)
    return PaymentCreatedResponse(
        payment=PaymentResponse.model_validate(payment),
        message="Continue to the secure card checkout page.",
        checkout_url=checkout["url"],
    )


@router.post("/billing/webhooks/mpesa")
async def mpesa_callback(
    request: Request,
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    settings = get_settings(request)
    expected = settings.mpesa_callback_token
    if not expected or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid M-Pesa callback token.")
    payload = await _json_object(request)
    callback_body = payload.get("Body")
    callback = callback_body.get("stkCallback") if isinstance(callback_body, dict) else None
    if not isinstance(callback, dict):
        raise HTTPException(status_code=400, detail="Invalid M-Pesa callback payload.")
    checkout_id = callback.get("CheckoutRequestID")
    result_code = callback.get("ResultCode")
    payment = db.scalar(
        select(PaymentRecord).where(PaymentRecord.provider_reference == checkout_id)
    )
    if payment is None or payment.provider != "mpesa_stk":
        return {"Result": "ignored"}
    if str(result_code) == "0":
        callback_metadata = callback.get("CallbackMetadata")
        items = callback_metadata.get("Item") if isinstance(callback_metadata, dict) else None
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise HTTPException(status_code=400, detail="Invalid M-Pesa callback metadata.")
        metadata = {item.get("Name"): item.get("Value") for item in items}
        paid_amount = _parse_kes_amount(metadata.get("Amount"))
        if paid_amount != payment.amount_kes:
            raise HTTPException(status_code=400, detail="M-Pesa amount does not match the payment.")
        _settle_payment(
            db,
            payment,
            request.app.state.event_bus,
            str(metadata.get("MpesaReceiptNumber", checkout_id)),
        )
    else:
        _fail_payment(db, payment)
    return {"Result": "accepted"}


@router.post("/billing/webhooks/mpesa/c2b")
async def mpesa_c2b_callback(
    request: Request,
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    expected = get_settings(request).mpesa_callback_token
    if not expected or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid M-Pesa callback token.")
    payload = await _json_object(request)
    account_reference = payload.get("BillRefNumber")
    transaction_id = payload.get("TransID")
    paid_amount = _parse_kes_amount(payload.get("TransAmount"))
    if not isinstance(account_reference, str) or not isinstance(transaction_id, str):
        raise HTTPException(status_code=400, detail="M-Pesa callback is missing its payment reference.")
    if not re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{3}", account_reference):
        raise HTTPException(status_code=400, detail="M-Pesa account reference is invalid.")
    payment = db.scalar(
        select(PaymentRecord).where(
            PaymentRecord.id.like(f"{account_reference}%"),
            PaymentRecord.provider.in_(["mpesa_manual", "mpesa_qr"]),
        )
    )
    if payment is None:
        return {"Result": "ignored"}
    if paid_amount != payment.amount_kes:
        raise HTTPException(status_code=400, detail="M-Pesa amount does not match the payment.")
    _settle_payment(db, payment, request.app.state.event_bus, transaction_id)
    return {"Result": "accepted"}


@router.post("/billing/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    settings = get_settings(request)
    if not settings.stripe_webhook_secret or not stripe_signature:
        raise HTTPException(status_code=503, detail="Stripe webhook verification is not configured.")
    payload = await request.body()
    if not verify_stripe_signature(payload, stripe_signature, settings.stripe_webhook_secret):
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature.")
    try:
        event = json.loads(payload)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook payload.") from error
    if not isinstance(event, dict):
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook payload.")
    if event.get("type") == "checkout.session.completed":
        event_data = event.get("data")
        checkout = event_data.get("object") if isinstance(event_data, dict) else None
        if not isinstance(checkout, dict):
            raise HTTPException(status_code=400, detail="Invalid Stripe checkout event.")
        metadata = checkout.get("metadata")
        payment_id = metadata.get("payment_id") if isinstance(metadata, dict) else None
        if not isinstance(payment_id, str):
            return {"received": "true"}
        payment = db.get(PaymentRecord, payment_id)
        if payment is not None and payment.provider == "stripe":
            if checkout.get("payment_status") != "paid":
                return {"received": "true"}
            if (
                checkout.get("amount_total") != payment.amount_kes
                or checkout.get("currency") != "kes"
            ):
                raise HTTPException(status_code=400, detail="Stripe amount does not match the payment.")
            _settle_payment(db, payment, request.app.state.event_bus, checkout.get("id"))
    return {"received": "true"}
