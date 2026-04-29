import logging
import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    def __init__(self, api_token: str, chat_id: str):
        self.api_token = api_token
        self.chat_id = str(chat_id)
        self._url = TELEGRAM_API.format(token=api_token)

    def _send_raw(self, text: str, parse_mode: str = "HTML") -> bool:
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False,
        }
        try:
            resp = requests.post(self._url, json=payload, timeout=15)
            resp.raise_for_status()
            result = resp.json()
            if not result.get("ok"):
                logger.error("Telegram API error: %s", result)
                return False
            return True
        except Exception as exc:
            logger.error("Failed to send Telegram message: %s", exc)
            return False

    def send_announcement(self, subject: str, class_name: str, link: str) -> bool:
        text = (
            "📢 <b>Yeni Duyuru!</b>\n\n"
            f"📚 <b>Ders:</b> {self._escape(class_name)}\n"
            f"📌 <b>Konu:</b> {self._escape(subject)}\n"
            f"🔗 <a href=\"{link}\">Duyuruyu Görüntüle</a>"
        )
        logger.info("Sending announcement notification: '%s' / '%s'", class_name, subject)
        return self._send_raw(text)

    def send_token_expired_alert(self) -> bool:
        text = (
            "⚠️ <b>Canvas Token Geçersiz!</b>\n\n"
            "Access token reddedildi (401 Unauthorized).\n"
            "Canvas → Hesap → Ayarlar → Erişim Jetonları bölümünden "
            "yeni bir jeton oluşturun ve <code>config.json</code> içindeki "
            "<code>access_token</code> değerini güncelleyin."
        )
        logger.warning("Sending token expired alert to Telegram")
        return self._send_raw(text)

    def send_error_alert(self, error_message: str) -> bool:
        text = (
            "🔴 <b>Bot Hatası</b>\n\n"
            f"<code>{self._escape(error_message[:800])}</code>"
        )
        return self._send_raw(text)

    def send_startup_message(self) -> bool:
        text = (
            "✅ <b>ESTÜ OYS Duyuru Botu Başlatıldı</b>\n\n"
            "Duyurular izleniyor. Yeni duyuru geldiğinde buraya bildirim alacaksınız."
        )
        return self._send_raw(text)

    @staticmethod
    def _escape(text: str) -> str:
        """Minimal HTML escaping for Telegram HTML mode."""
        return (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
        )
