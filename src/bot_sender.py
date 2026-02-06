import aiohttp
from .config import Config
from .logger import setup_logger

logger = setup_logger("BotSender")

class BotSender:
    def __init__(self):
        self.token = Config.BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    async def send_message(self, chat_id: int, text: str, button_text: str = None, button_url: str = None):
        async with aiohttp.ClientSession() as session:
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }

            if button_text and button_url:
                # Если button_url начинается на http - это ссылка, иначе - данные для кнопки
                kb_item = {"text": button_text}
                if button_url.startswith("http"):
                    kb_item["url"] = button_url
                else:
                    kb_item["callback_data"] = button_url
                
                payload["reply_markup"] = {"inline_keyboard": [[kb_item]]}

            async with session.post(self.base_url, json=payload) as resp:
                if resp.status != 200:
                    logger.error(f"Ошибка Bot API: {await resp.text()}")