from mistralai import Mistral
from .config import Config
from .logger import setup_logger

logger = setup_logger("TextFixer")

class MistralTextFixer:
    def __init__(self):
        self.client = Mistral(api_key=Config.MISTRAL_API_KEY)
        self.model = "magistral-medium-latest" # Для текста лучше использовать small

    async def fix_punctuation(self, text: str) -> str:
        prompt = (
            "Ты — профессиональный корректор. Твоя единственная задача: расставить знаки препинания (запятые, тире, дефисы, точки). "
            "КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО: менять слова, исправлять ошибки в словах, менять сленг, регистр букв или удалять мат. "
            "Оставляй текст в оригинальном виде, добавляй ТОЛЬКО пунктуацию."
        )
        try:
            response = await self.client.chat.complete_async(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Ошибка TextFixer: {e}")
            return text