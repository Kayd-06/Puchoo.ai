"""Send transactional verification codes without exposing them in logs."""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid, parseaddr

from backend.config import settings


class EmailDeliveryError(RuntimeError):
    pass


def _mailbox(value: str | None, label: str) -> str:
    """Return a single safe mailbox, rejecting malformed sender configuration."""

    _display_name, mailbox = parseaddr((value or "").strip())
    mailbox = mailbox.lower()
    if not mailbox or "@" not in mailbox:
        raise EmailDeliveryError(f"invalid {label}")
    return mailbox


def send_otp_email(to_email: str, otp_code: str) -> None:
    message = _message(to_email)
    message["Subject"] = f"{otp_code} is your Puchoo.si verification code"
    message.attach(MIMEText(_text(otp_code), "plain", "utf-8"))
    message.attach(MIMEText(_html(otp_code), "html", "utf-8"))
    _deliver(message)


def send_email_changed_notice(to_email: str) -> None:
    """Tell the previous address that the account email was changed."""

    message = _message(to_email)
    message["Subject"] = "Your Puchoo.si email address was changed"
    text = (
        "Puchoo.si\n\n"
        "The email address on your Puchoo.si account was just changed.\n"
        "If you made this change, you can ignore this email.\n"
        "If you did not, reset your password and contact support.\n"
    )
    html = """
    <html>
      <body style="margin:0;background:#f4f7fb;font-family:Helvetica,Arial,sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 0;">
          <tr><td align="center">
            <table width="100%" style="max-width:480px;background:#ffffff;border-radius:16px;padding:32px;">
              <tr><td>
                <p style="margin:0;color:#6b7280;font-size:13px;">Puchoo.si</p>
                <h1 style="margin:12px 0 0;color:#111827;font-size:22px;font-weight:600;">Your email address was changed</h1>
                <p style="margin:16px 0 0;color:#6b7280;font-size:14px;line-height:1.5;">
                  If you made this change, you can ignore this email. If you did not, reset your password.
                </p>
              </td></tr>
            </table>
          </td></tr>
        </table>
      </body>
    </html>
    """
    message.attach(MIMEText(text, "plain", "utf-8"))
    message.attach(MIMEText(html, "html", "utf-8"))
    _deliver(message)


def _message(to_email: str) -> MIMEMultipart:
    _display_name, recipient = parseaddr(to_email.strip())
    recipient = recipient.lower()
    if not recipient or "@" not in recipient:
        raise EmailDeliveryError("invalid recipient")
    message = MIMEMultipart("alternative")
    sender = _mailbox(settings.smtp_from or settings.smtp_username or "no-reply@puchoo.ai", "sender")
    message["From"] = formataddr((settings.smtp_from_name, sender))
    message["To"] = recipient
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[-1])
    message["Auto-Submitted"] = "auto-generated"
    message["X-Auto-Response-Suppress"] = "All"
    message._puchoo_recipient = recipient  # type: ignore[attr-defined]
    message._puchoo_sender = sender  # type: ignore[attr-defined]
    return message


def _deliver(message: MIMEMultipart) -> None:
    if not all(
        [
            settings.smtp_server,
            settings.smtp_port,
            settings.smtp_username,
            settings.smtp_password,
        ]
    ):
        raise EmailDeliveryError("SMTP is not configured")
    if settings.smtp_use_ssl and settings.smtp_use_tls:
        raise EmailDeliveryError("SMTP cannot use SSL and STARTTLS together")

    recipient = message._puchoo_recipient  # type: ignore[attr-defined]
    sender = message._puchoo_sender  # type: ignore[attr-defined]
    try:
        smtp_class = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
        with smtp_class(settings.smtp_server, settings.smtp_port, timeout=20) as smtp:
            smtp.ehlo()
            if settings.smtp_use_tls:
                smtp.starttls()
                smtp.ehlo()
            smtp.login(settings.smtp_username, settings.smtp_password)
            # Deliberately use the SMTP envelope API instead of inferred MIME
            # recipients. The envelope recipient is the account address supplied
            # to the app, never a header injected by the client.
            refused = smtp.sendmail(
                from_addr=sender,
                to_addrs=[recipient],
                msg=message.as_string(),
            )
            if refused:
                raise EmailDeliveryError("recipient refused")
    except EmailDeliveryError:
        raise
    except (OSError, ValueError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError("delivery failed") from exc


def _text(otp_code: str) -> str:
    return (
        "Puchoo.si\n\n"
        f"Your verification code is {otp_code}.\n\n"
        "Enter it to finish logging in. This code expires in 5 minutes.\n"
        "If you did not try to log in, you can ignore this email.\n"
    )


def _html(otp_code: str) -> str:
    return f"""
    <html>
      <body style="margin:0;background:#f4f7fb;font-family:Helvetica,Arial,sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 0;">
          <tr><td align="center">
            <table width="100%" style="max-width:480px;background:#ffffff;border-radius:16px;padding:32px;">
              <tr><td>
                <p style="margin:0;color:#6b7280;font-size:13px;">Puchoo.si</p>
                <h1 style="margin:12px 0 0;color:#111827;font-size:22px;font-weight:600;">Your verification code</h1>
                <p style="margin:24px 0;letter-spacing:0.3em;font-size:32px;color:#111827;">{otp_code}</p>
                <p style="margin:0;color:#6b7280;font-size:14px;line-height:1.5;">
                  This code expires in 5 minutes. If you did not try to log in, you can ignore this email.
                </p>
              </td></tr>
            </table>
          </td></tr>
        </table>
      </body>
    </html>
    """
