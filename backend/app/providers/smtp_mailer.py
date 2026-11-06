"""Gmail SMTP with an app password (from .env: SMTP_APP_PASSWORD). The body is text/plain only
(no HTML part, no image, no tracking) and the only attachment is the CV PDF. Nothing here
retries: the send queue decides, and logs every attempt."""

from pathlib import Path

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from app.providers.base import OutgoingEmail, SendFailed

HOST, PORT, TIMEOUT = "smtp.gmail.com", 465, 30


def plain_message(email: OutgoingEmail, address: str, from_name: str = "") -> EmailMessage:
    """The one place a message is built: headers, a text/plain body and, when the email
    carries one, the CV PDF."""
    msg = EmailMessage()
    msg["From"] = formataddr((from_name, address)) if from_name else address
    msg["To"] = email.to
    msg["Subject"] = email.subject
    msg["Message-ID"] = make_msgid(domain=address.split("@")[-1] or "localhost")
    msg.set_content(email.body)
    if email.attachment_path:
        path = Path(email.attachment_path)
        msg.add_attachment(path.read_bytes(), maintype="application", subtype="pdf",
                           filename=email.attachment_name or path.name)
    return msg


def payload_problem(msg: EmailMessage) -> str | None:
    """Why this message may not go out: a text/plain body, nothing else but one PDF."""
    body = msg.get_body(preferencelist=("plain", "html"))
    if body is None or body.get_content_type() != "text/plain":
        return "The message is not plain text: the body goes out as text/plain only"
    attachments = list(msg.iter_attachments())
    if len(attachments) > 1 or any(a.get_content_type() != "application/pdf"
                                   for a in attachments):
        return "The only attachment allowed is the CV as one PDF"
    if any(p.get_content_type() == "text/html" for p in msg.walk()):
        return "The message has an HTML part: the body goes out as text/plain only"
    return None


def email_problem(email: OutgoingEmail) -> str | None:
    """The same check on an `OutgoingEmail`, for the send gate (any mailer)."""
    if email.attachment_path and not Path(email.attachment_path).is_file():
        return "The CV file to attach is missing: regenerate or re-render the CV"
    return payload_problem(plain_message(email, "sender@example.invalid"))


class GmailMailer:
    def __init__(self, address: str, password: str, from_name: str = ""):
        self.address, self.password, self.from_name = address, password, from_name

    def build(self, email: OutgoingEmail) -> EmailMessage:
        return plain_message(email, self.address, self.from_name)

    def send(self, email: OutgoingEmail) -> str:
        msg = self.build(email)
        if problem := payload_problem(msg):
            raise SendFailed(problem)
        try:
            with smtplib.SMTP_SSL(HOST, PORT, timeout=TIMEOUT,
                                  context=ssl.create_default_context()) as smtp:
                smtp.login(self.address, self.password)
                refused = smtp.send_message(msg)
        except smtplib.SMTPAuthenticationError as exc:
            raise SendFailed("Gmail refused the login: check the address and the app password "
                             "(SMTP_APP_PASSWORD in .env)", fatal=True) from exc
        except smtplib.SMTPRecipientsRefused as exc:
            raise SendFailed(f"Recipient refused: {email.to}") from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise SendFailed(f"Sending failed: {type(exc).__name__}: {exc}") from exc
        if refused:
            raise SendFailed(f"Recipient refused: {', '.join(refused)}")
        return str(msg["Message-ID"])
