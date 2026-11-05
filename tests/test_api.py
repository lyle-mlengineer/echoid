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
        branded = client.get(
            f"/api/v1/generations/{result['id']}/export?format=pdf",
            headers=headers,
        )
        assert branded.headers["content-type"] == "application/pdf"
        assert branded.content.startswith(b"%PDF")
        assert b"EchoID transcript - meeting.wav" in branded.content
        assert b"Made by Lyle Okoth" in branded.content
        filtered_pdf = client.get(
            f"/api/v1/generations/{result['id']}/export?format=pdf&speakers=Speaker+2",
            headers=headers,
        )
        assert filtered_pdf.content.startswith(b"%PDF")
        assert len(filtered_pdf.content) < len(branded.content)

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


def test_speaker_directory_crud_search_and_image_validation(tmp_path):
    with make_client(tmp_path) as client:
        registration = client.post(
            "/api/v1/auth/register",
            json={
                "email": "speakers@example.com",
                "display_name": "Speaker Owner",
                "password": "safe-speaker-password",
            },
        )
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        image_data = "data:image/png;base64,iVBORw0KGgo="
        created = client.post(
            "/api/v1/speakers",
            headers=headers,
            json={
                "name": "  Jordan  ",
                "description": "  Project lead  ",
                "image_data": image_data,
            },
        )
        assert created.status_code == 201
        profile = created.json()
        assert profile["name"] == "Jordan"
        assert profile["description"] == "Project lead"
        assert profile["image_data"] == image_data
        assert client.get("/api/v1/speakers?search=lead", headers=headers).json()[0]["id"] == profile["id"]
        assert client.get("/api/v1/speakers?search=missing", headers=headers).json() == []
        assert client.get("/api/v1/speakers").status_code == 401
        other_account = client.post(
            "/api/v1/auth/register",
            json={
                "email": "other-speakers@example.com",
                "display_name": "Other Owner",
                "password": "other-safe-password",
            },
        )
        other_headers = {"Authorization": f"Bearer {other_account.json()['access_token']}"}
        assert client.get("/api/v1/speakers", headers=other_headers).json() == []
        assert client.patch(
            f"/api/v1/speakers/{profile['id']}",
            headers=other_headers,
            json={"name": "Stolen profile", "description": "", "image_data": None},
        ).status_code == 404
        generation = client.post(
            "/api/v1/generations",
            headers=headers,
            files={"audio": ("meeting.wav", b"sample audio", "audio/wav")},
        ).json()
        renamed = client.patch(
            f"/api/v1/generations/{generation['id']}/speakers",
            headers=headers,
            json={
                "speaker": "Speaker 1",
                "name": "Ignored custom name",
                "speaker_profile_id": profile["id"],
            },
        )
        assert renamed.status_code == 200
        assert [segment["speaker"] for segment in renamed.json()["segments"]].count("Jordan") == 2
        assert client.post(
            "/api/v1/speakers",
            headers=headers,
            json={"name": "Invalid image", "image_data": "data:image/png;base64,ZmFrZQ=="},
        ).status_code == 422

        updated = client.patch(
            f"/api/v1/speakers/{profile['id']}",
            headers=headers,
            json={"name": "Jordan Lee", "description": "Updated details", "image_data": None},
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Jordan Lee"
        assert updated.json()["image_data"] is None
        assert client.delete(f"/api/v1/speakers/{profile['id']}", headers=headers).status_code == 204
        assert client.get("/api/v1/speakers", headers=headers).json() == []


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
        assert "data-speaker-editor" in client.get("/studio").text


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


def register(client, email):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "display_name": email.split("@")[0], "password": "safe-passphrase-123"},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_export_follows_speaker_filter_and_word_search(tmp_path):
    with make_client(tmp_path) as client:
        headers = register(client, "filters@example.com")
        result = client.post(
            "/api/v1/generations",
            headers=headers,
            files={"audio": ("meeting.wav", b"sample audio", "audio/wav")},
        ).json()
        export = f"/api/v1/generations/{result['id']}/export"

        single = client.get(export, headers=headers, params={"format": "txt", "speakers": "Speaker 1"})
        assert single.status_code == 200
        assert single.text.strip().split("\n") == [
            "Speaker 1: [Demo only: configure a transcription provider to analyze audio]",
        ] * 2
        assert "Speaker 2:" not in single.text

        several = client.get(
            export,
            headers=headers,
            params={"format": "json", "speakers": ["Speaker 1", "Speaker 3"]},
        )
        assert [item["speaker"] for item in several.json()["segments"]] == [
            "Speaker 1",
            "Speaker 1",
            "Speaker 3",
        ]

        words = client.get(export, headers=headers, params={"format": "txt", "search": "configure PROVIDER"})
        assert len(words.text.strip().split("\n")) == 4
        assert client.get(
            export, headers=headers, params={"format": "txt", "search": "quarterly"}
        ).text == ""

        combined = client.get(
            export,
            headers=headers,
            params={"format": "json", "speakers": "Speaker 3", "search": "analyze"},
        )
        assert [item["speaker"] for item in combined.json()["segments"]] == ["Speaker 3"]
        assert client.get(
            export,
            headers=headers,
            params={"format": "json", "speakers": "Speaker 3", "search": "quarterly"},
        ).json()["segments"] == []


def test_generation_audio_is_streamed_to_its_owner_only(tmp_path):
    with make_client(tmp_path) as client:
        owner = register(client, "owner@example.com")
        result = client.post(
            "/api/v1/generations",
            headers=owner,
            files={"audio": ("meeting.wav", b"sample audio", "audio/wav")},
        ).json()
        audio = f"/api/v1/generations/{result['id']}/audio"

        full = client.get(audio, headers=owner)
        assert full.status_code == 200
        assert full.headers["content-type"] == "audio/wav"
        assert full.content == b"sample audio"

        partial = client.get(audio, headers={**owner, "Range": "bytes=0-3"})
        assert partial.status_code == 206
        assert partial.content == b"samp"

        guest_token = client.post("/api/v1/auth/guest").json()["guest_token"]
        guest = client.post(
            "/api/v1/generations",
            headers={"X-Guest-Token": guest_token},
            files={"audio": ("memo.mp3", b"guest audio", "audio/mpeg")},
        ).json()
        assert client.get(
            f"/api/v1/generations/{guest['id']}/audio", headers={"X-Guest-Token": guest_token}
        ).content == b"guest audio"
        assert client.get(audio, headers=register(client, "other@example.com")).status_code == 404


def test_segments_can_be_edited_and_deleted_by_their_owner(tmp_path):
    with make_client(tmp_path) as client:
        owner = register(client, "editor@example.com")
        result = client.post(
            "/api/v1/generations",
            headers=owner,
            files={"audio": ("meeting.wav", b"sample audio", "audio/wav")},
        ).json()
        generation = f"/api/v1/generations/{result['id']}"
        segment = f"{generation}/segments"

        edited = client.patch(f"{segment}/1", headers=owner, json={"text": "  Revised line.  "})
        assert edited.status_code == 200
        assert edited.json()["segments"][1]["text"] == "Revised line."
        assert client.get(generation, headers=owner).json()["segments"][1]["text"] == "Revised line."
        assert "Speaker 2: Revised line." in client.get(
            f"{generation}/export", headers=owner, params={"format": "txt"}
        ).text

        assert client.patch(f"{segment}/1", headers=owner, json={"text": "   "}).status_code == 422
        assert client.patch(f"{segment}/9", headers=owner, json={"text": "Nope"}).status_code == 404
        assert client.patch(f"{segment}/-1", headers=owner, json={"text": "Nope"}).status_code == 404

        removed = client.delete(f"{segment}/0", headers=owner)
        assert removed.status_code == 200
        assert [item["speaker"] for item in removed.json()["segments"]] == [
            "Speaker 2",
            "Speaker 1",
            "Speaker 3",
        ]
        assert client.delete(f"{segment}/9", headers=owner).status_code == 404

        intruder = register(client, "intruder@example.com")
        assert client.patch(f"{segment}/0", headers=intruder, json={"text": "Mine now"}).status_code == 404
        assert client.delete(f"{segment}/0", headers=intruder).status_code == 404

        guest_token = client.post("/api/v1/auth/guest").json()["guest_token"]
        guest = client.post(
            "/api/v1/generations",
            headers={"X-Guest-Token": guest_token},
            files={"audio": ("memo.wav", b"guest audio", "audio/wav")},
        ).json()
        guest_segment = f"/api/v1/generations/{guest['id']}/segments/0"
        guest_headers = {"X-Guest-Token": guest_token}
        assert client.patch(guest_segment, headers=guest_headers, json={"text": "Guest edit"}).json()["segments"][0]["text"] == "Guest edit"
        assert client.delete(guest_segment, headers=guest_headers).json()["segments"][0]["speaker"] == "Speaker 2"
