import aiohttp
from .config import Config
from .logger import setup_logger

logger = setup_logger("BotSender")

class BotSender:
    def __init__(self):
        self.token = Config.BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    async def send_message(self, chat_id: int, text: str, button_text: str = None, button_url: str = None):
        if not self.token:
            logger.warning("Токен бота не указан!")
            return

        async with aiohttp.ClientSession() as session:
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }

            if button_text and button_url:
                payload["reply_markup"] = {
                    "inline_keyboard": [[{"text": button_text, "url": button_url}]]
                }

            try:
                async with session.post(self.base_url, json=payload) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        logger.error(f"Ошибка отправки (Status {resp.status}): {err_text}")
            except Exception as e:
                logger.error(f"Ошибка связи с Bot API: {e}")