import asyncio
import re
from mistralai import Mistral
from .config import Config
from .logger import setup_logger

logger = setup_logger("Summarizer")

class MistralSummarizer:
    def __init__(self):
        self.client = Mistral(api_key=Config.MISTRAL_API_KEY)
        self.model = "mistral-medium-latest"

    def _balance_tags(self, text):
        """Простейшая проверка: на каждый <b> должен быть </b>"""
        open_tags = len(re.findall(r'<b>', text, re.IGNORECASE))
        close_tags = len(re.findall(r'</b>', text, re.IGNORECASE))
        
        # Если открытых больше, добавляем закрывающие в конец
        if open_tags > close_tags:
            text += '</b>' * (open_tags - close_tags)
        return text

    async def summarize(self, text: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._summarize_sync, text)

    def _summarize_sync(self, text: str) -> str:
        prompt = (
            "Ты — аналитик. Сделай краткое саммари текста в виде списка.\n"
            "ПРАВИЛА:\n"
            "1. Используй <b>текст</b> для жирного шрифта.\n"
            "2. ВСЕГДА закрывай теги </b>.\n"
            "3. Не используй другие HTML теги.\n"
            "4. Ответ на языке оригинала."
        )
        try:
            response = self.client.chat.complete(
                model=self.model,
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}]
            )
            result = response.choices[0].message.content
            
            # Балансируем теги перед возвратом
            return self._balance_tags(result)
        except Exception as e:
            return f"Ошибка при создании саммари: {e}"