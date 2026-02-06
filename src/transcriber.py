import io
import asyncio
from mistralai import Mistral
from .config import Config
from .logger import setup_logger

logger = setup_logger("Transcriber")

class MistralTranscriber:
    def __init__(self):
        self.client = Mistral(api_key=Config.MISTRAL_API_KEY)
        self.model = Config.MISTRAL_AUDIO_MODEL

    async def transcribe(self, media_bytes: bytes, filename: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._transcribe_sync, media_bytes, filename)

    def _transcribe_sync(self, media_bytes: bytes, filename: str) -> str:
        try:
            logger.info(f"Транскрипция {filename} через {self.model}...")
            
            # В Audio API инструкции передаются через параметр 'prompt'
            full_prompt = f"{Config.TRANSCRIBE_PROMPT}. Язык: {Config.TARGET_LANGUAGE}."
            
            response = self.client.audio.transcriptions.complete(
                model=self.model,
                file={
                    "content": media_bytes,
                    "file_name": filename,
                },
                prompt=full_prompt # Передаем инструкции здесь
            )

            result = getattr(response, 'text', str(response))
            return result if result.strip() else "<i>(Тишина)</i>"

        except Exception as e:
            logger.error(f"Ошибка Audio API: {e}", exc_info=True)
            return f"❌ Ошибка транскрипции: {str(e)}"