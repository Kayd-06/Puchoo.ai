"""Send the login verification code. The code is never written to logs."""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from backend.config import settings


class EmailDeliveryError(RuntimeError):
    pass


def send_otp_email(to_email: str, otp_code: str) -> None:
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

    message = MIMEMultipart("alternative")
    sender = settings.smtp_from or settings.smtp_username
    message["From"] = f"Puchoo.ai <{sender}>"
    message["To"] = to_email
    message["Subject"] = f"{otp_code} is your Puchoo.ai verification code"
    message.attach(MIMEText(_text(otp_code), "plain", "utf-8"))
    message.attach(MIMEText(_html(otp_code), "html", "utf-8"))

    try:
        smtp_class = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
        with smtp_class(settings.smtp_server, settings.smtp_port, timeout=20) as smtp:
            smtp.ehlo()
            if settings.smtp_use_tls:
                smtp.starttls()
                smtp.ehlo()
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except (OSError, ValueError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError("delivery failed") from exc


def _text(otp_code: str) -> str:
    return (
        "Puchoo.ai\n\n"
        f"Your verification code is {otp_code}.\n\n"
        "Enter it to finish logging in. This code expires in 10 minutes.\n"
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
                <p style="margin:0;color:#6b7280;font-size:13px;">Puchoo.ai</p>
                <h1 style="margin:12px 0 0;color:#111827;font-size:22px;font-weight:600;">Your verification code</h1>
                <p style="margin:24px 0;letter-spacing:0.3em;font-size:32px;color:#111827;">{otp_code}</p>
                <p style="margin:0;color:#6b7280;font-size:14px;line-height:1.5;">
                  This code expires in 10 minutes. If you did not try to log in, you can ignore this email.
                </p>
              </td></tr>
            </table>
          </td></tr>
        </table>
      </body>
    </html>
    """
