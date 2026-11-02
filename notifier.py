import logging
import time

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MESSAGE_CHARS = 4000  # Telegram hard limit is 4096


class TelegramNotifier:
    def __init__(self, api_token: str, chat_id: str):
        self.api_token = api_token
        self.chat_id = str(chat_id)
        self._url = TELEGRAM_API.format(token=api_token)

    def _send_raw(self, text: str, parse_mode: str = "HTML", attempts: int = 3) -> bool:
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        for attempt in range(1, attempts + 1):
            try:
                resp = requests.post(self._url, json=payload, timeout=20)
                if resp.status_code == 429 and attempt < attempts:
                    wait = min(resp.json().get("parameters", {}).get("retry_after", 5), 30)
                    logger.warning("Telegram rate limit, retrying in %ss", wait)
                    time.sleep(wait)
                    continue
                if resp.status_code >= 500 and attempt < attempts:
                    time.sleep(2 * attempt)
                    continue
                if not resp.ok:
                    # Log Telegram's own explanation (e.g. "can't parse entities"), not just the status.
                    logger.error("Telegram HTTP %s: %s", resp.status_code, resp.text[:300])
                    return False
                if not resp.json().get("ok"):
                    logger.error("Telegram API error: %s", resp.text[:300])
                    return False
                return True
            except requests.RequestException as exc:
                logger.error("Failed to send Telegram message (try %d/%d): %s", attempt, attempts, exc)
                if attempt < attempts:
                    time.sleep(2 * attempt)
        return False

    def _build_announcement(self, subject: str, class_name: str, link: str,
                            content: str = "", posted_at: str = "") -> str:
        date_line = f"\n🕐 <b>Tarih:</b> {self._escape(posted_at)}" if posted_at else ""
        while True:
            content_line = f"\n\n📄 <i>{self._escape(content)}</i>" if content else ""
            text = (
                "📢 <b>Yeni Duyuru!</b>\n\n"
                f"📚 <b>Kaynak:</b> {self._escape(class_name)}\n"
                f"📌 <b>Konu:</b> {self._escape(subject)}"
                f"{date_line}"
                f"{content_line}\n\n"
                f"🔗 <a href=\"{self._escape(link)}\">{self._escape(link)}</a>"
            )
            if len(text) <= MAX_MESSAGE_CHARS or not content:
                return text
            content = content[: int(len(content) * 0.8)].rstrip() + "…"

    def send_announcement(self, subject: str, class_name: str, link: str,
                          content: str = "", posted_at: str = "") -> bool:
        logger.info("Sending: [%s] %s", class_name, subject)
        return self._send_raw(self._build_announcement(subject, class_name, link, content, posted_at))

    def send_token_expired_alert(self) -> bool:
        text = (
            "⚠️ <b>Canvas Token Geçersiz!</b>\n\n"
            "Access token reddedildi (401 Unauthorized).\n"
            "Canvas → Hesap → Ayarlar → Erişim Jetonları bölümünden "
            "yeni bir jeton oluşturun ve GitHub'daki <code>CANVAS_TOKEN</code> secret'ını "
            "(yerel çalışıyorsa <code>config.json</code> içindeki <code>access_token</code>) güncelleyin."
        )
        logger.warning("Sending token expired alert")
        return self._send_raw(text)

    def send_error_alert(self, error_message: str) -> bool:
        text = (
            "🔴 <b>Bot Hatası</b>\n\n"
            f"<code>{self._escape(error_message[:800])}</code>"
        )
        return self._send_raw(text)

    def send_startup_message(self) -> bool:
        text = (
            "✅ <b>ESTÜ Duyuru Botu Başlatıldı</b>\n\n"
            "Canvas dersleri + Bilgisayar Mühendisliği bölüm sitesi izleniyor.\n"
            "Yeni duyuru geldiğinde tam içerikle buraya bildirim alacaksınız."
        )
        return self._send_raw(text)

    @staticmethod
    def _escape(text: str) -> str:
        return (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
        )
