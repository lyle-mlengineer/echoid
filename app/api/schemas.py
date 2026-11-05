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
