import hashlib
import hmac
import time

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.entities import TranscriptSegment
from app.infrastructure.models import PaymentRecord, UserRecord
from app.infrastructure.payments import verify_stripe_signature
from app.infrastructure.transcription import TranscriptionResult
from app.main import create_app


def make_client(tmp_path):
    settings = Settings(
        secret_key="test-key-with-more-than-enough-entropy-value",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        storage_dir=tmp_path / "uploads",
        free_credits=3,
        mpesa_callback_token="callback-secret",
    )
    return TestClient(create_app(settings))


def test_registration_login_and_generation_exports(tmp_path):
    with make_client(tmp_path) as client:
        registration = client.post(
            "/api/v1/auth/register",
            json={
                "email": "user@example.com",
                "display_name": "Test User",
                "password": "safe-passphrase-123",
            },
        )
        assert registration.status_code == 201
        access_token = registration.json()["access_token"]
        assert registration.json()["user"]["credits"] == 3
        headers = {"Authorization": f"Bearer {access_token}"}

        generated = client.post(
            "/api/v1/generations",
            headers=headers,
            files={"audio": ("meeting.wav", b"sample audio", "audio/wav")},
        )
        assert generated.status_code == 201
        result = generated.json()
        assert result["demo_mode"] is True
        assert result["segments"][0]["speaker"] == "Speaker 1"
        assert client.get("/api/v1/auth/me", headers=headers).json()["credits"] == 3
        assert client.get(
            f"/api/v1/generations/{result['id']}/export?format=txt",
            headers=headers,
        ).text.startswith("Speaker 1:")
        assert client.get(
            f"/api/v1/generations/{result['id']}/export?format=pdf",
            headers=headers,
        ).headers["content-type"] == "application/pdf"

        renamed = client.patch(
            f"/api/v1/generations/{result['id']}/speakers",
            headers=headers,
            json={"speaker": "Speaker 1", "name": "Alice"},
        )
        assert renamed.status_code == 200
        assert [item["speaker"] for item in renamed.json()["segments"]] == [
            "Alice",
            "Speaker 2",
            "Alice",
            "Speaker 3",
        ]
        assert client.get(
            f"/api/v1/generations/{result['id']}/export?format=txt",
            headers=headers,
        ).text.count("Alice:") == 2
        assert client.get(
            f"/api/v1/generations/{result['id']}/export?format=json",
            headers=headers,
        ).json()["segments"][0]["speaker"] == "Alice"
        assert client.patch(
            f"/api/v1/generations/{result['id']}/speakers",
            headers=headers,
            json={"speaker": "Unknown", "name": "Bob"},
        ).status_code == 404

        login = client.post(
            "/api/v1/auth/login",
            json={"email": "USER@example.com", "password": "safe-passphrase-123"},
        )
        assert login.status_code == 200
        assert client.post(
            "/api/v1/auth/login",
            json={"email": "user@example.com", "password": "wrong-password"},
        ).status_code == 401


def test_guest_gets_one_generation_and_can_claim_it(tmp_path):
    with make_client(tmp_path) as client:
        guest_token = client.post("/api/v1/auth/guest").json()["guest_token"]
        guest_headers = {"X-Guest-Token": guest_token}
        first = client.post(
            "/api/v1/generations",
            headers=guest_headers,
            files={"audio": ("memo.mp3", b"audio", "audio/mpeg")},
        )
        assert first.status_code == 201
        assert client.get(
            f"/api/v1/generations/{first.json()['id']}",
            headers=guest_headers,
        ).status_code == 200
        assert client.get(
            f"/api/v1/generations/{first.json()['id']}/export?format=txt",
            headers=guest_headers,
        ).status_code == 401
        second = client.post(
            "/api/v1/generations",
            headers=guest_headers,
            files={"audio": ("memo.mp3", b"audio", "audio/mpeg")},
        )
        assert second.status_code == 403

        registered = client.post(
            "/api/v1/auth/register",
            headers=guest_headers,
            json={
                "email": "guest@example.com",
                "display_name": "Guest",
                "password": "another-safe-password",
            },
        )
        assert registered.status_code == 201
        account_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        assert client.get(
            f"/api/v1/generations/{first.json()['id']}/export?format=json",
            headers=account_headers,
        ).status_code == 200
        assert client.get("/api/v1/generations", headers=guest_headers).status_code == 401
        assert client.post(
            "/api/v1/auth/register",
            headers=guest_headers,
            json={
                "email": "second@example.com",
                "display_name": "Second",
                "password": "another-safe-password",
            },
        ).status_code == 409


def test_guest_cannot_download_and_bad_audio_is_rejected(tmp_path):
    with make_client(tmp_path) as client:
        token = client.post("/api/v1/auth/guest").json()["guest_token"]
        response = client.post(
            "/api/v1/generations",
            headers={"X-Guest-Token": token},
            files={"audio": ("notes.exe", b"not audio", "application/octet-stream")},
        )
        assert response.status_code == 415
        assert client.get("/api/v1/billing/packages").status_code == 200


def test_jinja_pages_and_responsive_assets_are_served(tmp_path):
    with make_client(tmp_path) as client:
        pages = {
            "/": "HEAR",
            "/login": "Log in to EchoID",
            "/register": "Create my account",
            "/dashboard": "Latest transcripts",
            "/studio": "Drop your audio right here",
            "/gallery": "The gallery",
            "/billing": "Pick your credit pack.",
        }
        for path, expected in pages.items():
            response = client.get(path)
            assert response.status_code == 200
            assert expected in response.text
        css = client.get("/static/css/styles.css")
        script = client.get("/static/js/app.js")
        assert css.status_code == 200
        assert "@media (max-width: 680px)" in css.text
        assert script.status_code == 200
        assert "data-transcribe" in client.get("/studio").text
        assert "data-speaker-dialog" in client.get("/studio").text


def test_mpesa_callback_credits_once_and_checks_amount(tmp_path):
    with make_client(tmp_path) as client:
        registration = client.post(
            "/api/v1/auth/register",
            json={
                "email": "payer@example.com",
                "display_name": "Payer",
                "password": "safe-payment-password",
            },
        )
        user_id = registration.json()["user"]["id"]
        session = client.app.state.session_factory()
        try:
            user = session.get(UserRecord, user_id)
            payment = PaymentRecord(
                user_id=user.id,
                provider="mpesa_stk",
                provider_reference="checkout-123",
                amount_kes=100,
                credits=50,
            )
            session.add(payment)
            session.commit()
        finally:
            session.close()

        payload = {
            "Body": {
                "stkCallback": {
                    "CheckoutRequestID": "checkout-123",
                    "ResultCode": 0,
                    "CallbackMetadata": {
                        "Item": [
                            {"Name": "Amount", "Value": 100},
                            {"Name": "MpesaReceiptNumber", "Value": "ABC123"},
                        ]
                    },
                }
            }
        }
        callback_url = "/api/v1/billing/webhooks/mpesa?token=callback-secret"
        assert client.post(callback_url, json=payload).status_code == 200
        assert client.post(callback_url, json=payload).status_code == 200
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        assert client.get("/api/v1/auth/me", headers=headers).json()["credits"] == 53
        payments = client.get("/api/v1/billing/payments", headers=headers)
        assert payments.status_code == 200
        assert payments.json()[0]["transaction_reference"] == "ABC123"

        payload["Body"]["stkCallback"]["CallbackMetadata"]["Item"][0]["Value"] = 101
        assert client.post(callback_url, json=payload).status_code == 400


def test_real_transcription_provider_charges_one_credit(tmp_path):
    class RealProvider:
        demo_mode = False

        async def transcribe(self, filename, content):
            return TranscriptionResult(
                segments=[TranscriptSegment("Speaker 1", "Hello.", 0, 1)],
                duration_seconds=1,
                provider="test-provider",
                demo_mode=False,
            )

    with make_client(tmp_path) as client:
        client.app.state.transcription_provider = RealProvider()
        registered = client.post(
            "/api/v1/auth/register",
            json={
                "email": "transcriber@example.com",
                "display_name": "Transcriber",
                "password": "transcription-passphrase",
            },
        )
        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        generated = client.post(
            "/api/v1/generations",
            headers=headers,
            files={"audio": ("meeting.wav", b"sample audio", "audio/wav")},
        )
        assert generated.status_code == 201
        assert generated.json()["credits_charged"] == 1
        assert client.get("/api/v1/auth/me", headers=headers).json()["credits"] == 2


def test_stripe_webhook_signature_verification():
    payload = b'{"type":"checkout.session.completed"}'
    timestamp = str(int(time.time()))
    secret = "whsec-test-secret"
    digest = hmac.new(
        secret.encode(),
        timestamp.encode() + b"." + payload,
        hashlib.sha256,
    ).hexdigest()
    assert verify_stripe_signature(payload, f"t={timestamp},v1={digest}", secret)
    assert not verify_stripe_signature(payload, f"t=1,v1={digest}", secret)


def test_mpesa_manual_payment_reconciles_c2b_callback(tmp_path):
    with make_client(tmp_path) as client:
        registration = client.post(
            "/api/v1/auth/register",
            json={
                "email": "manual@example.com",
                "display_name": "Manual Payer",
                "password": "manual-payment-passphrase",
            },
        )
        user_id = registration.json()["user"]["id"]
        session = client.app.state.session_factory()
        try:
            user = session.get(UserRecord, user_id)
            payment = PaymentRecord(
                user_id=user.id,
                provider="mpesa_manual",
                provider_reference=None,
                amount_kes=100,
                credits=50,
            )
            session.add(payment)
            session.commit()
            payment_id = payment.id
        finally:
            session.close()

        payload = {
            "BillRefNumber": payment_id[:12],
            "TransID": "MANUAL123",
            "TransAmount": "100.00",
        }
        callback_url = "/api/v1/billing/webhooks/mpesa/c2b?token=callback-secret"
        assert client.post(callback_url, json=payload).status_code == 200
        assert client.post(callback_url, json=payload).status_code == 200
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        assert client.get("/api/v1/auth/me", headers=headers).json()["credits"] == 53
