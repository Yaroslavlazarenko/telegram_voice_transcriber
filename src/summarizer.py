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

    async def summarize(self, text: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._summarize_sync, text)

    def _summarize_sync(self, text: str) -> str:
        # Максимально строгий промпт для обычного текста
        prompt = (
            "Ты — аналитик. Твоя задача: сделать краткую выжимку (summary) предоставленного текста. "
            "Выбери наиболее подходящую структуру (абзацы или список) для максимальной ясности. "
            "ВАЖНО: КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать любое форматирование: жирный шрифт, курсив, "
            "Markdown-звездочки (**), решетки (#) или HTML-теги. Пиши только ОБЫЧНЫМ ТЕКСТОМ. "
            "Ответ дай на языке оригинала."
        )
        try:
            logger.info("Запрос к Mistral для создания Plain Text саммари...")
            response = self.client.chat.complete(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text}
                ]
            )
            result = response.choices[0].message.content
            
            # --- ПРИНУДИТЕЛЬНАЯ ОЧИСТКА ---
            # Удаляем звездочки, нижние подчеркивания и решетки (Markdown)
            result = result.replace("**", "").replace("__", "").replace("*", "").replace("#", "")
            
            # Удаляем любые HTML-теги, если они проскочили
            result = re.sub(r'<[^>]*>', '', result)
            
            logger.info("Саммари готово (чистый текст).")
            return result.strip()
            
        except Exception as e:
            logger.error(f"Ошибка в Summarizer: {e}")
            return f"Ошибка при создании саммари: {e}"