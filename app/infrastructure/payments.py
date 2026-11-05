import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
import time

import httpx

from app.core.config import Settings


class PaymentProviderError(RuntimeError):
    pass


class MpesaClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return all(
            [
                self.settings.mpesa_consumer_key,
                self.settings.mpesa_consumer_secret,
                self.settings.mpesa_shortcode,
                self.settings.mpesa_passkey,
                self.settings.mpesa_callback_url,
                self.settings.mpesa_callback_token,
            ]
        )

    async def _access_token(self) -> str:
        if not self.configured:
            raise PaymentProviderError("M-Pesa credentials and callback URL are not configured.")
        auth = (
            self.settings.mpesa_consumer_key,
            self.settings.mpesa_consumer_secret,
        )
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{self.settings.mpesa_base_url.rstrip('/')}/oauth/v1/generate",
                params={"grant_type": "client_credentials"},
                auth=auth,
            )
            response.raise_for_status()
        return response.json()["access_token"]

    async def stk_push(self, payment_id: str, phone: str, amount: int) -> dict:
        token = await self._access_token()
        nairobi = timezone(timedelta(hours=3))
        timestamp = datetime.now(nairobi).strftime("%Y%m%d%H%M%S")
        password = base64.b64encode(
            f"{self.settings.mpesa_shortcode}{self.settings.mpesa_passkey}{timestamp}".encode()
        ).decode()
        payload = {
            "BusinessShortCode": self.settings.mpesa_shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": (
                "CustomerBuyGoodsOnline"
                if self.settings.mpesa_payment_type == "till"
                else "CustomerPayBillOnline"
            ),
            "Amount": amount,
            "PartyA": phone,
            "PartyB": self.settings.mpesa_paybill_or_till or self.settings.mpesa_shortcode,
            "PhoneNumber": phone,
            "CallBackURL": (
                f"{self.settings.mpesa_callback_url.rstrip('/')}"
                f"?token={self.settings.mpesa_callback_token or ''}"
            ),
            "AccountReference": payment_id[:12],
            "TransactionDesc": "EchoID credits",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.settings.mpesa_base_url.rstrip('/')}/mpesa/stkpush/v1/processrequest",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            response.raise_for_status()
        return response.json()

    async def create_qr(self, payment_id: str, amount: int) -> dict:
        token = await self._access_token()
        payload = {
            "MerchantName": "EchoID",
            "RefNo": payment_id[:12],
            "Amount": amount,
            "TrxCode": "BG" if self.settings.mpesa_payment_type == "till" else "PB",
            "CPI": self.settings.mpesa_paybill_or_till or self.settings.mpesa_shortcode,
            "Size": "300",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.settings.mpesa_base_url.rstrip('/')}/mpesa/qrcode/v1/generate",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            response.raise_for_status()
        return response.json()


def verify_stripe_signature(payload: bytes, signature: str, secret: str) -> bool:
    timestamp = None
    signatures: list[str] = []
    for part in signature.split(","):
        key, separator, value = part.partition("=")
        if separator and key == "t":
            timestamp = value
        elif separator and key == "v1":
            signatures.append(value)
    if not timestamp or not signatures:
        return False
    try:
        if abs(time.time() - int(timestamp)) > 300:
            return False
    except ValueError:
        return False
    signed_payload = timestamp.encode() + b"." + payload
    expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, candidate) for candidate in signatures)
