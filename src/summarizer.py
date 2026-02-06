import asyncio
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
        prompt = (
            "Ты — аналитик. Твоя задача: сделать краткую выжимку (summary) предоставленного текста. "
            "Выдели только самые важные факты, цифры и принятые решения. Используй маркированный список. "
            "Ответ дай на языке оригинала."
        )
        try:
            response = self.client.chat.complete(
                model=self.model,
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}]
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Ошибка при создании саммари: {e}"