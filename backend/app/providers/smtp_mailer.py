"""Gmail SMTP with an app password (from .env: SMTP_APP_PASSWORD). Plain text plus an optional
HTML alternative (signature photo), the CV as a PDF attachment. Nothing here retries: the send
queue decides, and logs every attempt."""

import mimetypes
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

from app.providers.base import OutgoingEmail, SendFailed

HOST, PORT, TIMEOUT = "smtp.gmail.com", 465, 30


class GmailMailer:
    def __init__(self, address: str, password: str, from_name: str = ""):
        self.address, self.password, self.from_name = address, password, from_name

    def build(self, email: OutgoingEmail) -> EmailMessage:
        msg = EmailMessage()
        msg["From"] = formataddr((self.from_name, self.address)) if self.from_name else self.address
        msg["To"] = email.to
        msg["Subject"] = email.subject
        msg["Message-ID"] = make_msgid(domain=self.address.split("@")[-1])
        msg.set_content(email.body)
        if email.html:
            msg.add_alternative(email.html, subtype="html")
            html_part = msg.get_payload()[-1]
            for cid, path in email.inline_images.items():
                data = Path(path).read_bytes()
                kind = (mimetypes.guess_type(path)[0] or "image/png").split("/")
                html_part.add_related(data, maintype=kind[0], subtype=kind[1], cid=f"<{cid}>")
        if email.attachment_path:
            data = Path(email.attachment_path).read_bytes()
            msg.add_attachment(data, maintype="application", subtype="pdf",
                               filename=email.attachment_name or Path(email.attachment_path).name)
        return msg

    def send(self, email: OutgoingEmail) -> str:
        msg = self.build(email)
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
