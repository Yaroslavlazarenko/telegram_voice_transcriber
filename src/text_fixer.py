import asyncio
from mistralai import Mistral
from .config import Config
from .logger import setup_logger

logger = setup_logger("TextFixer")

class MistralTextFixer:
    def __init__(self):
        self.client = Mistral(api_key=Config.MISTRAL_API_KEY)
        # nemo — самая стабильная и быстрая модель для простых правок
        self.model = "mistral-medium-latest"

    async def fix_punctuation(self, text: str) -> str:
        # Запускаем синхронную функцию в отдельном потоке, чтобы не вешать бота
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._fix_sync, text)

    def _fix_sync(self, text: str) -> str:
        prompt = (
            "Ты — профессиональный корректор. Твоя единственная задача: расставить знаки препинания (запятые, тире, дефисы, точки). "
            "КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО: менять слова, исправлять ошибки в словах, менять сленг, регистр букв или удалять мат. "
            "Оставляй текст в оригинальном виде, добавляй ТОЛЬКО пунктуацию."
        )
        try:
            logger.info(f"Отправка текста в Mistral ({self.model})...")
            response = self.client.chat.complete(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text}
                ]
            )
            result = response.choices[0].message.content
            logger.info("Ответ от Mistral получен.")
            return result
        except Exception as e:
            logger.error(f"Ошибка в синхронном TextFixer: {e}")
            return text