import aiohttp
from .config import Config
from .logger import setup_logger

logger = setup_logger("BotSender")

class BotSender:
    def __init__(self):
        self.token = Config.BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    async def send_message(self, chat_id: int, text: str):
        if not self.token:
            logger.warning("Токен бота не указан в .env! Не могу отправить результат.")
            return

        async with aiohttp.ClientSession() as session:
            payload = {
                "chat_id": chat_id,
                "text": text
            }
            try:
                async with session.post(self.base_url, json=payload) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"Ошибка отправки ботом (Status {resp.status}): {error_text}")
                    else:
                        logger.info(f"Результат успешно отправлен в ЛС (ID: {chat_id})")
            except Exception as e:
                logger.error(f"Ошибка связи с Telegram Bot API: {e}")