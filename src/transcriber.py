import asyncio
from mistralai import Mistral
from .config import Config
from .logger import setup_logger

logger = setup_logger("Transcriber")

class MistralTranscriber:
    def __init__(self):
        self.client = Mistral(api_key=Config.MISTRAL_API_KEY)
        # Оставляем лучшую модель из тестов
        self.model = "voxtral-mini-2602"

    async def transcribe(self, audio_bytes: bytes) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._transcribe_sync, audio_bytes)

    def _transcribe_sync(self, audio_bytes: bytes) -> str:
        try:
            logger.info(f"Запуск транскрипции через Audio API (Model: {self.model})...")
            
            # Передаем аудио_bytes напрямую в поле content. 
            # SDK Mistral умеет принимать тип bytes.
            response = self.client.audio.transcriptions.complete(
                model=self.model,
                file={
                    "content": audio_bytes, 
                    "file_name": "voice.ogg",
                }
            )

            if hasattr(response, 'text'):
                result = response.text
            else:
                result = str(response)

            if not result or not result.strip():
                return "Голосовое сообщение распознано как пустое."

            logger.info(f"Транскрипция успешно завершена.")
            return result

        except Exception as e:
            # Чтобы избежать ошибок HTML в Telegram, логируем полную ошибку здесь,
            # а пользователю отправляем краткий текст.
            logger.error(f"Ошибка Audio API: {e}")
            return f"❌ Ошибка при распознавании аудио. Проверьте логи сервера."