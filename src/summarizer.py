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
            "Ты — мастер краткости. Сделай МАКСИМАЛЬНО сжатую выжимку текста.\n"
            "ТРЕБОВАНИЯ:\n"
            "1. Не более 3-5 коротких пунктов.\n"
            "2. Пиши только самую суть (Bottom Line). Избегай подробностей.\n"
            "3. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО любое форматирование (звездочки, жирный шрифт и т.д.).\n"
            "4. Используй обычное тире (-) для списков.\n"
            "5. Ответ на языке оригинала."
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