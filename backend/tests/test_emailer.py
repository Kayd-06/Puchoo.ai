"""SMTP envelope tests: OTPs must go to the account holder, never the sender."""

from backend import emailer


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

        def send_message(self, message, from_addr, to_addrs):
            delivered["from"] = from_addr
            delivered["to"] = to_addrs
            delivered["header_to"] = message["To"]
            return {}

    monkeypatch.setattr(emailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(emailer.settings, "smtp_server", "smtp.example.test")
    monkeypatch.setattr(emailer.settings, "smtp_port", 587)
    monkeypatch.setattr(emailer.settings, "smtp_username", "sender@example.test")
    monkeypatch.setattr(emailer.settings, "smtp_password", "not-a-real-password")
    monkeypatch.setattr(emailer.settings, "smtp_use_ssl", False)
    monkeypatch.setattr(emailer.settings, "smtp_use_tls", True)

    emailer.send_otp_email("person@example.test", "123456")

    assert delivered == {
        "from": "sender@example.test",
        "to": ["person@example.test"],
        "header_to": "person@example.test",
    }
