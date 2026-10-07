"""SMTP envelope tests: OTPs must go to the account holder, never the sender."""

from email import message_from_string

import pytest
from email.utils import parseaddr

from backend import emailer
from backend.emailer import EmailDeliveryError


def _decoded_message(raw: str) -> str:
    parsed = message_from_string(raw)
    parts = []
    for part in parsed.walk():
        payload = part.get_payload(decode=True)
        if isinstance(payload, bytes):
            parts.append(payload.decode())
    return "\n".join(parts)


def test_the_suite_does_not_contact_the_configured_smtp_account(monkeypatch):
    monkeypatch.setattr(emailer.settings, "smtp_server", "smtp.example.test")
    monkeypatch.setattr(emailer.settings, "smtp_port", 587)
    monkeypatch.setattr(emailer.settings, "smtp_username", "sender@example.test")
    monkeypatch.setattr(emailer.settings, "smtp_password", "not-a-real-password")
    monkeypatch.setattr(emailer.settings, "smtp_from", None)
    monkeypatch.setattr(emailer.settings, "smtp_use_ssl", False)
    monkeypatch.setattr(emailer.settings, "smtp_use_tls", True)
    with pytest.raises(EmailDeliveryError, match="disabled during tests"):
        emailer.send_otp_email("person@example.test", "123456")


def test_otp_uses_the_requested_recipient_for_smtp_envelope(monkeypatch):
    delivered = {}

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def ehlo(self):
            return None

        def starttls(self):
            return None

        def login(self, *_args):
            return None

        def sendmail(self, from_addr, to_addrs, msg):
            delivered["from"] = from_addr
            delivered["to"] = to_addrs
            delivered["message"] = msg
            return {}

    monkeypatch.setattr(emailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(emailer.settings, "smtp_server", "smtp.example.test")
    monkeypatch.setattr(emailer.settings, "smtp_port", 587)
    monkeypatch.setattr(emailer.settings, "smtp_username", "sender@example.test")
    monkeypatch.setattr(emailer.settings, "smtp_password", "not-a-real-password")
    monkeypatch.setattr(emailer.settings, "smtp_use_ssl", False)
    monkeypatch.setattr(emailer.settings, "smtp_use_tls", True)

    emailer.send_otp_email("person@example.test", "123456")

    assert delivered["from"] == "sender@example.test"
    assert delivered["to"] == ["person@example.test"]
    message = message_from_string(delivered["message"])
    assert parseaddr(message["From"]) == ("Puchoo.si no-reply", "sender@example.test")
    assert message["To"] == "person@example.test"
    assert message["Subject"] == "123456 is your Puchoo.ai verification code"
    body = _decoded_message(delivered["message"])
    assert "expires in 5 minutes" in body
    assert "10 minutes" not in body
