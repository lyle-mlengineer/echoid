import base64
import binascii
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Display name cannot be blank.")
        return normalized


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class FirebaseLoginRequest(BaseModel):
    id_token: str = Field(min_length=20)


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    display_name: str
    credits: int


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class GuestSessionResponse(BaseModel):
    guest_token: str
    token_type: str = "bearer"
    free_generation_available: bool


class TranscriptSegmentResponse(BaseModel):
    speaker: str
    text: str
    start_seconds: float
    end_seconds: float


class SpeakerRenameRequest(BaseModel):
    speaker: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    speaker_profile_id: UUID | None = None

    @field_validator("speaker", "name")
    @classmethod
    def normalize_speaker_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Speaker names cannot be blank.")
        return normalized


class SegmentTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Transcript text cannot be blank.")
        return normalized


def validate_speaker_image(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        media_type, encoded = value.split(",", 1)
        media_type = media_type.removeprefix("data:").removesuffix(";base64")
        if media_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise ValueError("Use a JPG, PNG, or WebP speaker image.")
        image = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("The speaker image is invalid.") from error
    if not image or len(image) > 2 * 1024 * 1024:
        raise ValueError("Speaker images must be smaller than 2 MB.")
    valid_signature = (
        (media_type == "image/jpeg" and image.startswith(b"\xff\xd8\xff"))
        or (media_type == "image/png" and image.startswith(b"\x89PNG\r\n\x1a\n"))
        or (media_type == "image/webp" and image.startswith(b"RIFF") and image[8:12] == b"WEBP")
    )
    if not valid_signature:
        raise ValueError("The speaker image does not match its file type.")
    return value


class SpeakerCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    image_data: str | None = Field(default=None, max_length=2_800_000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Speaker names cannot be blank.")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        return value.strip()

    @field_validator("image_data")
    @classmethod
    def validate_image(cls, value: str | None) -> str | None:
        return validate_speaker_image(value)


class SpeakerUpdateRequest(SpeakerCreateRequest):
    pass


class SpeakerResponse(BaseModel):
    id: UUID
    name: str
    description: str
    image_data: str | None
    created_at: datetime


class GenerationResponse(BaseModel):
    id: UUID
    filename: str
    status: str
    segments: list[TranscriptSegmentResponse]
    duration_seconds: float | None
    provider: str
    demo_mode: bool
    credits_charged: int
    created_at: datetime


class PaymentPackageResponse(BaseModel):
    id: str
    amount_kes: int
    credits: int


class PaymentResponse(BaseModel):
    id: UUID
    provider: str
    amount_kes: int
    credits: int
    status: str
    provider_reference: str | None
    transaction_reference: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MpesaStkRequest(BaseModel):
    package_id: str
    phone_number: str = Field(pattern=r"^(?:\+?254|0)?[17]\d{8}$")


class PaymentCreatedResponse(BaseModel):
    payment: PaymentResponse
    message: str
    checkout_url: str | None = None
    checkout_request_id: str | None = None
    qr_code: str | None = None
