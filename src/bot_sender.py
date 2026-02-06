import aiohttp
from .config import Config
from .logger import setup_logger

logger = setup_logger("BotSender")

class BotSender:
    def __init__(self):
        self.token = Config.BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    # Добавили button_text и button_url как необязательные аргументы
    async def send_message(self, chat_id: int, text: str, button_text: str = None, button_url: str = None):
        if not self.token:
            logger.warning("Токен бота не указан в .env! Не могу отправить результат.")
            return

        async with aiohttp.ClientSession() as session:
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }

            # Если передана ссылка, добавляем inline-клавиатуру
            if button_url and button_text:
                payload["reply_markup"] = {
                    "inline_keyboard": [[
                        {
                            "text": button_text,
                            "url": button_url
                        }
                    ]]
                }

            try:
                # Библиотека aiohttp сама преобразует словари внутри json=payload в нужный формат
                async with session.post(self.base_url, json=payload) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"Ошибка отправки ботом (Status {resp.status}): {error_text}")
                    else:
                        logger.info(f"Результат успешно отправлен в ЛС (ID: {chat_id})")
            except Exception as e:
                logger.error(f"Ошибка связи с Telegram Bot API: {e}")