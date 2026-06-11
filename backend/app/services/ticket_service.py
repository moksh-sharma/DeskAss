"""Support ticket emails from chat sessions."""
from __future__ import annotations

import smtplib
import socket
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from app.core.config import Settings
from app.core.exceptions import FeatureUnavailableError
from app.core.logging import get_logger
from app.models.schemas import DiagnosisResult
from app.utils.diagnosis_format import format_diagnosis_plain_text

logger = get_logger(__name__)

_GRAPH_SCOPE = "https://graph.microsoft.com/.default"
_GRAPH_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_GRAPH_SEND_URL = "https://graph.microsoft.com/v1.0/users/{user}/sendMail"

_SMTP_AUTH_DISABLED_HINT = (
    "Microsoft 365 has SMTP AUTH disabled for your organization. "
    "Ask IT to either enable SMTP AUTH for the sender mailbox, or set "
    "TICKET_EMAIL_TRANSPORT=graph with AZURE_TENANT_ID, AZURE_CLIENT_ID, "
    "and AZURE_CLIENT_SECRET (app needs Mail.Send application permission)."
)


class TicketService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _assistant_reply_text(
        self,
        diagnosis: DiagnosisResult | None,
        assistant_reply: str | None,
    ) -> str:
        if diagnosis is not None:
            return format_diagnosis_plain_text(diagnosis)
        if assistant_reply and assistant_reply.strip():
            return assistant_reply.strip()
        raise FeatureUnavailableError(
            "No assistant reply was provided for this ticket.",
            status_code=422,
            error_code="validation_error",
        )

    def _build_ticket_content(
        self,
        *,
        user_issue: str,
        reply_text: str,
        session_id: int | None,
    ) -> tuple[str, str]:
        hostname = socket.gethostname()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        subject_parts = [f"{self.settings.app_name} ticket"]
        if session_id is not None:
            subject_parts.append(f"session #{session_id}")
        subject_parts.append(hostname)
        subject = " — ".join(subject_parts)

        body_lines = [
            f"A user raised a support ticket from {self.settings.app_name}.",
            "",
            f"Time: {now}",
            f"Machine: {hostname}",
        ]
        if session_id is not None:
            body_lines.append(f"Session ID: {session_id}")
        body_lines.extend(
            [
                "",
                "=" * 60,
                "USER ISSUE",
                "=" * 60,
                "",
                user_issue.strip(),
                "",
                "=" * 60,
                "ASSISTANT REPLY",
                "=" * 60,
                "",
                reply_text,
                "",
            ]
        )
        return subject, "\n".join(body_lines)

    def _sender_address(self) -> str:
        return (
            (self.settings.graph_send_as_user or "").strip()
            or (self.settings.smtp_from or "").strip()
            or (self.settings.smtp_user or "").strip()
        )

    def _transport(self) -> str:
        mode = (self.settings.ticket_email_transport or "auto").strip().lower()
        if mode in {"graph", "microsoft_graph", "msgraph"}:
            return "graph"
        if mode == "smtp":
            return "smtp"
        if self._graph_configured():
            return "graph"
        return "smtp"

    def _graph_configured(self) -> bool:
        return bool(
            (self.settings.azure_tenant_id or "").strip()
            and (self.settings.azure_client_id or "").strip()
            and (self.settings.azure_client_secret or "").strip()
            and self._sender_address()
        )

    def _graph_access_token(self) -> str:
        tenant = (self.settings.azure_tenant_id or "").strip()
        client_id = (self.settings.azure_client_id or "").strip()
        client_secret = (self.settings.azure_client_secret or "").strip()
        if not tenant or not client_id or not client_secret:
            raise FeatureUnavailableError(
                "Microsoft Graph is not configured. Set AZURE_TENANT_ID, "
                "AZURE_CLIENT_ID, and AZURE_CLIENT_SECRET in backend/.env.",
                error_code="feature_unavailable",
            )

        url = _GRAPH_TOKEN_URL.format(tenant=tenant)
        try:
            resp = httpx.post(
                url,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": _GRAPH_SCOPE,
                    "grant_type": "client_credentials",
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            token = resp.json().get("access_token")
            if not token:
                raise FeatureUnavailableError(
                    "Microsoft Graph token response did not include access_token.",
                    error_code="feature_unavailable",
                )
            return token
        except httpx.HTTPError as exc:
            logger.exception("Microsoft Graph token request failed")
            raise FeatureUnavailableError(
                f"Could not authenticate with Microsoft Graph: {exc}",
                error_code="feature_unavailable",
            ) from exc

    def _send_via_graph(
        self,
        *,
        to_addr: str,
        from_addr: str,
        subject: str,
        body: str,
        session_id: int | None,
    ) -> None:
        token = self._graph_access_token()
        url = _GRAPH_SEND_URL.format(user=from_addr)
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": to_addr}}],
            },
            "saveToSentItems": True,
        }
        logger.info(
            "Sending support ticket via Microsoft Graph: %s -> %s (session=%s)",
            from_addr,
            to_addr,
            session_id,
        )
        try:
            resp = httpx.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30.0,
            )
            if resp.status_code >= 400:
                detail = resp.text[:500]
                logger.error("Graph sendMail failed (%s): %s", resp.status_code, detail)
                raise FeatureUnavailableError(
                    f"Microsoft Graph could not send email ({resp.status_code}). "
                    "Ensure the Azure app has Mail.Send application permission and "
                    "admin consent, and that GRAPH_SEND_AS_USER is a valid mailbox.",
                    error_code="feature_unavailable",
                )
        except httpx.HTTPError as exc:
            logger.exception("Microsoft Graph send failed")
            raise FeatureUnavailableError(
                f"Could not send email via Microsoft Graph: {exc}",
                error_code="feature_unavailable",
            ) from exc

    def _send_via_smtp(
        self,
        *,
        to_addr: str,
        from_addr: str,
        subject: str,
        body: str,
        session_id: int | None,
    ) -> None:
        host = (self.settings.smtp_host or "").strip()
        if not host:
            raise FeatureUnavailableError(
                "SMTP is not configured. Set SMTP_HOST in backend/.env, or use "
                "TICKET_EMAIL_TRANSPORT=graph with Azure credentials.",
                error_code="feature_unavailable",
            )

        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg.attach(MIMEText(body, "plain", "utf-8"))

        port = self.settings.smtp_port
        use_tls = self.settings.smtp_use_tls
        user = (self.settings.smtp_user or "").strip()
        password = (self.settings.smtp_password or "").strip()

        logger.info("Sending support ticket via SMTP to %s (session=%s)", to_addr, session_id)

        try:
            if use_tls:
                with smtplib.SMTP(host, port, timeout=30) as smtp:
                    smtp.ehlo()
                    smtp.starttls()
                    smtp.ehlo()
                    if user and password:
                        smtp.login(user, password)
                    smtp.sendmail(from_addr, [to_addr], msg.as_string())
            else:
                with smtplib.SMTP(host, port, timeout=30) as smtp:
                    if user and password:
                        smtp.login(user, password)
                    smtp.sendmail(from_addr, [to_addr], msg.as_string())
        except smtplib.SMTPAuthenticationError as exc:
            logger.exception("SMTP authentication failed")
            message = f"SMTP login failed: {exc}"
            if "SmtpClientAuthentication is disabled" in str(exc) or "5.7.139" in str(exc):
                message = _SMTP_AUTH_DISABLED_HINT
            raise FeatureUnavailableError(message, error_code="feature_unavailable") from exc
        except OSError as exc:
            logger.exception("SMTP connection failed")
            raise FeatureUnavailableError(
                f"Could not send email: {exc}",
                error_code="feature_unavailable",
            ) from exc
        except smtplib.SMTPException as exc:
            logger.exception("SMTP send failed")
            raise FeatureUnavailableError(
                f"Email delivery failed: {exc}",
                error_code="feature_unavailable",
            ) from exc

    def send_ticket_email(
        self,
        *,
        user_issue: str,
        diagnosis: DiagnosisResult | None = None,
        assistant_reply: str | None = None,
        session_id: int | None = None,
    ) -> None:
        to_addr = (self.settings.ticket_email_to or "").strip()
        if not to_addr:
            raise FeatureUnavailableError(
                "Support email is not configured. Set TICKET_EMAIL_TO in backend/.env.",
                error_code="feature_unavailable",
            )

        from_addr = self._sender_address()
        if not from_addr:
            raise FeatureUnavailableError(
                "Sender address is not configured. Set SMTP_FROM or GRAPH_SEND_AS_USER.",
                error_code="feature_unavailable",
            )

        reply_text = self._assistant_reply_text(diagnosis, assistant_reply)
        subject, body = self._build_ticket_content(
            user_issue=user_issue,
            reply_text=reply_text,
            session_id=session_id,
        )

        transport = self._transport()
        if transport == "graph":
            self._send_via_graph(
                to_addr=to_addr,
                from_addr=from_addr,
                subject=subject,
                body=body,
                session_id=session_id,
            )
        else:
            self._send_via_smtp(
                to_addr=to_addr,
                from_addr=from_addr,
                subject=subject,
                body=body,
                session_id=session_id,
            )

        logger.info("Support ticket email sent to %s", to_addr)
