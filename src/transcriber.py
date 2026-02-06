import io
import asyncio
from mistralai import Mistral
from .config import Config
from .logger import setup_logger

logger = setup_logger("Transcriber")

class MistralTranscriber:
    def __init__(self):
        self.client = Mistral(api_key=Config.MISTRAL_API_KEY)
        # Используем проверенную в тестах модель
        self.model = "voxtral-mini-2602"

    async def transcribe(self, media_bytes: bytes, filename: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._transcribe_sync, media_bytes, filename)

    def _transcribe_sync(self, media_bytes: bytes, filename: str) -> str:
        try:
            logger.info(f"Транскрипция {filename} через {self.model}...")
            
            # В этом API передаем только модель и файл. 
            # Параметр 'prompt' здесь не поддерживается SDK Mistral.
            response = self.client.audio.transcriptions.complete(
                model=self.model,
                file={
                    "content": media_bytes,
                    "file_name": filename,
                }
            )

            # Извлекаем текст
            result = getattr(response, 'text', str(response))
            
            if not result or not result.strip():
                return "<i>(Распознано как пустое сообщение или тишина)</i>"

            return result

        except Exception as e:
            logger.error(f"Ошибка Audio API: {e}", exc_info=True)
            return f"❌ Ошибка транскрипции: {str(e)}"