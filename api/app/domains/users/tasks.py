import asyncio

from celery import shared_task
from loguru import logger
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType

from app.core.config import settings

conf = ConnectionConfig(
    MAIL_USERNAME=settings.SMTP_USER,
    MAIL_PASSWORD=settings.SMTP_PASSWORD,
    MAIL_FROM=settings.SMTP_USER,
    MAIL_PORT=settings.SMTP_PORT,
    MAIL_SERVER=settings.SMTP_HOST,
    MAIL_FROM_NAME=settings.EMAILS_FROM_NAME,
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)


async def send_async_email(email_to: str, otp: str):
    html_content = f"""
    <div style="font-family: Arial, sans-serif; padding: 20px;">
        <h2>Відновлення пароля - Mess&Gags</h2>
        <p>Ваш код підтвердження:</p>
        <h1 style="color: #4CAF50; letter-spacing: 5px;">{otp}</h1>
        <p style="color: red; font-size: 12px;">
            Увага: відновлення пароля скине ваші старі E2E ключі.
        </p>
    </div>
    """

    message = MessageSchema(
        subject="Відновлення пароля",
        recipients=[email_to],
        body=html_content,
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    await fm.send_message(message)


@shared_task
def send_reset_password_email(email_to: str, otp: str):
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning(f"SMTP is not configured! Simulated email to {email_to}. OTP: {otp}")
        return False

    try:
        asyncio.run(send_async_email(email_to, otp))
        logger.info(f"Successfully sent reset HTML-email to {email_to}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {email_to}: {e}")
        return False
