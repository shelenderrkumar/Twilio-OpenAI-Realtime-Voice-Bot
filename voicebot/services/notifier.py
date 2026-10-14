"""Delivery of customer complaints to the support team."""

import base64
import logging
from email.mime.text import MIMEText
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class Notifier(Protocol):
    def send(self, to: str, subject: str, body: str, cc: list[str]) -> str: ...


class LogNotifier:
    """Default: records the e-mail in the server log (useful for demos and tests)."""

    def __init__(self):
        self.sent: list[dict] = []

    def send(self, to: str, subject: str, body: str, cc: list[str]) -> str:
        self.sent.append({"to": to, "subject": subject, "body": body, "cc": cc})
        logger.info("E-mail (dry run) to=%s cc=%s subject=%s\n%s", to, cc, subject, body)
        return "logged"


class GmailNotifier:
    """Sends through the Gmail API. Requires `pip install .[gmail]` and OAuth files."""

    SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

    def __init__(self, sender: str, credentials_file: Path, token_file: Path):
        from langchain_google_community.gmail.utils import (
            build_resource_service,
            get_gmail_credentials,
        )

        credentials = get_gmail_credentials(
            token_file=str(token_file),
            client_secrets_file=str(credentials_file),
            scopes=self.SCOPES,
        )
        self.sender = sender
        self._api = build_resource_service(credentials=credentials)

    def send(self, to: str, subject: str, body: str, cc: list[str]) -> str:
        message = MIMEText(body, "plain")
        message["to"], message["from"], message["subject"] = to, self.sender, subject
        if cc:
            message["cc"] = ", ".join(cc)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        result = self._api.users().messages().send(userId="me", body={"raw": raw}).execute()
        return result.get("id", "sent")


def build_notifier(settings) -> Notifier:
    if settings.gmail_credentials_file.exists():
        try:
            return GmailNotifier(
                settings.complaint_sender,
                settings.gmail_credentials_file,
                settings.gmail_token_file,
            )
        except Exception:
            logger.exception("Gmail unavailable; falling back to log-only notifier")
    return LogNotifier()
