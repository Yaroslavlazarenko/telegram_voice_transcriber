import asyncio
from mistralai import Mistral
from .config import Config
from .logger import setup_logger

logger = setup_logger("TextFixer")

class MistralTextFixer:
    def __init__(self):
        self.client = Mistral(api_key=Config.MISTRAL_API_KEY)
        self.model = "mistral-medium-latest"

    async def fix_punctuation(self, text: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._fix_sync, text)

    def _fix_sync(self, text: str) -> str:
        prompt = (
            "Ты — профессиональный корректор для чатов. Твоя задача: расставить знаки препинания (запятые, дефисы).\n"
            "ПРАВИЛА:\n"
            "1. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО: менять слова, исправлять ошибки в словах, менять сленг, регистр букв или удалять мат.\n"
            "2. Используй ТОЛЬКО короткие дефисы (-) вместо длинных тире (—).\n"
            "3. НЕ СТАВЬ точку в самом конце всего сообщения.\n"
            "4. Оставляй текст максимально оригинальным, добавляй только пунктуацию."
        )
        try:
            logger.info(f"Отправка в Mistral ({self.model})...")
            response = self.client.chat.complete(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text}
                ]
            )
            result = response.choices[0].message.content
            
            result = result.replace(" — ", " - ").replace("—", "-")
            
            result = result.strip()
            if result.endswith('.') and not text.endswith('.'):
                result = result[:-1]
            
            logger.info("Ответ от Mistral получен и обработан.")
            return result
        except Exception as e:
            logger.error(f"Ошибка в TextFixer: {e}")
            return text