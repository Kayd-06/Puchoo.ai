"""Send the login verification code. The code is never written to logs."""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


class EmailDeliveryError(RuntimeError):
    pass


def send_otp_email(to_email: str, otp_code: str) -> None:
    server = os.getenv("SMTP_SERVER")
    port = os.getenv("SMTP_PORT")
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    if not all([server, port, username, password]):
        raise EmailDeliveryError("SMTP is not configured")

    message = MIMEMultipart("alternative")
    message["From"] = f"Puchoo.ai <{username}>"
    message["To"] = to_email
    message["Subject"] = f"{otp_code} is your Puchoo.ai verification code"
    message.attach(MIMEText(_text(otp_code), "plain", "utf-8"))
    message.attach(MIMEText(_html(otp_code), "html", "utf-8"))

    try:
        with smtplib.SMTP(server, int(port), timeout=20) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
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
