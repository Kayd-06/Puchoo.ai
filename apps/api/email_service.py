import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

def get_text_template(otp_code: str) -> str:
    return f"""Pucho.ai - Your Intelligent Database Assistant

Your Verification Code is: {otp_code}

Please use the verification code above to securely log into your account and start getting answers without writing SQL.
This code will expire in 10 minutes.

If you didn't request this code, you can safely ignore this email.
"""

def get_html_template(otp_code: str) -> str:
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Pucho.ai Verification Code</title>
    </head>
    <body style="margin: 0; padding: 0; background-color: #f4f7fb; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f7fb; padding: 40px 0;">
            <tr>
                <td align="center">
                    <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; background-color: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.05);">
                        <tr>
                            <td style="background: linear-gradient(135deg, #FF6B6B 0%, #6B66FF 100%); padding: 40px 20px; text-align: center;">
                                <h1 style="margin: 0; font-size: 32px; font-weight: 800; color: #ffffff; letter-spacing: 1px; text-shadow: 0 2px 4px rgba(0,0,0,0.1);">Pucho.ai</h1>
                                <p style="margin: 15px 0 0 0; color: rgba(255,255,255,0.9); font-size: 16px; font-weight: 500;">Your Intelligent Database Assistant</p>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 40px 30px; text-align: center;">
                                <h2 style="margin: 0 0 20px 0; color: #1a1a1a; font-size: 24px; font-weight: 700;">Verification Code</h2>
                                <p style="margin: 0 0 30px 0; color: #555555; font-size: 16px; line-height: 1.6;">
                                    Please use the verification code below to securely log into your account and start getting answers without writing SQL.
                                </p>
                                
                                <div style="background: linear-gradient(135deg, #f0f4ff 0%, #ffeaf0 100%); border: 2px dashed #6b66ff; padding: 25px; border-radius: 15px; margin: 0 auto; max-width: 300px;">
                                    <span style="font-size: 46px; font-weight: 800; letter-spacing: 12px; color: #1a1a1a; margin-right: -12px; font-family: monospace;">{otp_code}</span>
                                </div>
                                
                                <p style="margin: 30px 0 0 0; color: #888888; font-size: 14px; line-height: 1.5;">
                                    This code will expire in 10 minutes.<br>
                                    If you didn't request this code, you can safely ignore this email.
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

def send_otp_email(to_email: str, otp_code: str) -> bool:
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = os.getenv("SMTP_PORT")
    smtp_user = os.getenv("SMTP_USERNAME")
    smtp_pass = os.getenv("SMTP_PASSWORD")

    if not all([smtp_server, smtp_port, smtp_user, smtp_pass]):
        print("Warning: SMTP credentials are not configured in .env. Email not sent.")
        return False

    try:
        # Using MIMEMultipart('alternative') is critical to avoid spam filters
        msg = MIMEMultipart('alternative')
        msg['From'] = f"Pucho.ai <{smtp_user}>"
        msg['To'] = to_email
        msg['Subject'] = f"{otp_code} is your Pucho.ai verification code"

        text_content = get_text_template(otp_code)
        html_content = get_html_template(otp_code)

        # Attach parts into message container.
        # According to RFC 2046, the last part of a multipart message, in this case
        # the HTML message, is best and preferred.
        part1 = MIMEText(text_content, 'plain')
        part2 = MIMEText(html_content, 'html')

        msg.attach(part1)
        msg.attach(part2)

        with smtplib.SMTP(smtp_server, int(smtp_port)) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
            
        print(f"Successfully sent OTP email to {to_email}")
        return True
    except Exception as e:
        print(f"Failed to send email to {to_email}: {str(e)}")
        return False

