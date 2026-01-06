import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_ID = int(os.getenv("API_ID", 0))
    API_HASH = os.getenv("API_HASH")
    SESSION_NAME = os.getenv("SESSION_NAME")
    
    MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
    MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "voxtral-mini-latest")
    
    TARGET_LANGUAGE = os.getenv("TARGET_LANGUAGE", "")
    SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT")
    TRANSCRIBE_PROMPT = os.getenv("TRANSCRIBE_PROMPT")

    BOT_TOKEN = os.getenv("BOT_TOKEN")
    TRIGGER_EMOJI = os.getenv("TRIGGER_EMOJI")