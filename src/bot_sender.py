import aiohttp
import re
import html
from .config import Config
from .logger import setup_logger

logger = setup_logger("BotSender")

class BotSender:
    def __init__(self):
        self.token = Config.BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def _strip_html(self, text):
        """Удаляет все HTML теги из текста"""
        return re.sub(r'<[^>]*>', '', text)

    async def send_message(self, chat_id: int, text: str, buttons: list = None):
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

            async with session.post(self.base_url, json=payload) as resp:
                status = resp.status
                body = await resp.text()

                # Если ошибка в HTML тегах (код 400 и специфичное сообщение)
                if status == 400 and "can't parse entities" in body:
                    logger.warning("Ошибка HTML парсинга. Пробую отправить plain text...")
                    
                    # ФАЛЛБЕК: Чистим текст от тегов и экранируем
                    clean_text = self._strip_html(text)
                    payload["text"] = html.escape(clean_text)
                    payload["parse_mode"] = "HTML" # Теперь это безопасно, так как всё экранировано
                    
                    async with session.post(self.base_url, json=payload) as retry_resp:
                        if retry_resp.status != 200:
                            logger.error(f"Фаллбек тоже не удался: {await retry_resp.text()}")
                
                elif status != 200:
                    logger.error(f"Ошибка Bot API (Status {status}): {body}")