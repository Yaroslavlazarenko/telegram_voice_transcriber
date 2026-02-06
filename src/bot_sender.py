import aiohttp
from .config import Config
from .logger import setup_logger

logger = setup_logger("BotSender")

class BotSender:
    def __init__(self):
        self.token = Config.BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    async def send_message(self, chat_id: int, text: str, buttons: list = None):
        """
        buttons: список кортежей [("Текст", "url_или_callback"), ...]
        """
        async with aiohttp.ClientSession() as session:
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }

            if buttons:
                inline_kb = []
                for b_text, b_val in buttons:
                    kb_item = {"text": b_text}
                    if b_val.startswith("http"):
                        kb_item["url"] = b_val
                    else:
                        kb_item["callback_data"] = b_val
                    inline_kb.append(kb_item)
                
                payload["reply_markup"] = {"inline_keyboard": [inline_kb]}

            await session.post(self.base_url, json=payload)