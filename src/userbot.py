import io
import os
import time
import tempfile
import subprocess
import asyncio
import qrcode
import html
import uuid
from telethon import TelegramClient, events, types, functions, utils, Button
from .config import Config
from .transcriber import MistralTranscriber
from .text_fixer import MistralTextFixer
from .summarizer import MistralSummarizer  # Не забудьте создать этот файл
from .bot_sender import BotSender
from .logger import setup_logger

logger = setup_logger("Userbot")

class Userbot:
    def __init__(self):
        # Два клиента: ваш аккаунт и вспомогательный бот для кнопок
        self.client = TelegramClient(Config.SESSION_NAME, Config.API_ID, Config.API_HASH)
        self.bot_client = TelegramClient("bot_session", Config.API_ID, Config.API_HASH)
        
        # Модули ИИ
        self.transcriber = MistralTranscriber()
        self.fixer = MistralTextFixer()
        self.summarizer = MistralSummarizer()
        
        self.bot_sender = BotSender()
        self.my_id = None
        
        # Общий кэш для правок текста и транскрипций (для саммари)
        # {id: {"text": str, "peer": obj, "msg_id": int, "link": str}}
        self.data_cache = {}
        self.recent_handled = {}
        self.MAX_MSG_LEN = 4000

    async def start(self):
        # Авторизация Юзербота
        await self.client.connect()
        if not await self.client.is_user_authorized():
            logger.info("Требуется авторизация Юзербота...")
            qr_login = await self.client.qr_login()
            qr = qrcode.QRCode()
            qr.add_data(qr_login.url)
            qr.make(fit=True)
            qr.print_ascii(invert=True)
            await qr_login.wait()

        # Авторизация Бота
        await self.bot_client.start(bot_token=Config.BOT_TOKEN)
        
        me = await self.client.get_me()
        self.my_id = me.id
        logger.info(f"Система запущена. Аккаунт: {me.first_name} (ID: {self.my_id})")

        # Регистрация обработчиков
        self.client.add_event_handler(self.reaction_handler, events.Raw())
        self.bot_client.add_event_handler(self.bot_callback_handler, events.CallbackQuery())
        
        await self.client.run_until_disconnected()

    async def reaction_handler(self, event):
        """Ловит вашу реакцию-триггер на сообщениях"""
        peer = None
        msg_id = None
        reactions_obj = None

        if isinstance(event, (types.UpdateEditMessage, types.UpdateEditChannelMessage)):
            msg_event = event.message
            if msg_event and msg_event.reactions:
                peer = msg_event.peer_id
                msg_id = msg_event.id
                reactions_obj = msg_event.reactions
        elif isinstance(event, types.UpdateMessageReactions):
            peer = event.peer
            msg_id = event.msg_id
            reactions_obj = event.reactions
        else:
            return

        if not peer or not msg_id or not reactions_obj:
            return

        target_found = False
        reactions_to_keep = []

        # 1. Проверяем в results (в группах, супергруппах и каналах Telegram передает реакцию текущего пользователя через chosen_order)
        if reactions_obj.results:
            for rc in reactions_obj.results:
                if getattr(rc, "chosen_order", None) is not None:
                    emoji = rc.reaction.emoticon if isinstance(rc.reaction, types.ReactionEmoji) else None
                    if emoji == Config.TRIGGER_EMOJI:
                        target_found = True
                    else:
                        reactions_to_keep.append(rc.reaction)

        # 2. Также проверяем в recent_reactions (в ЛС и малых группах, где есть список peer_id)
        if not target_found and reactions_obj.recent_reactions:
            for r in reactions_obj.recent_reactions:
                user_id = r.peer_id.user_id if isinstance(r.peer_id, types.PeerUser) else None
                if user_id == self.my_id:
                    emoji = r.reaction.emoticon if isinstance(r.reaction, types.ReactionEmoji) else None
                    if emoji == Config.TRIGGER_EMOJI:
                        target_found = True
                    else:
                        if r.reaction not in reactions_to_keep:
                            reactions_to_keep.append(r.reaction)

        if target_found:
            # Дедупликация (Telegram может прислать и UpdateMessageReactions, и UpdateEditMessage)
            now = time.time()
            clean_cutoff = now - 60
            self.recent_handled = {k: v for k, v in self.recent_handled.items() if v > clean_cutoff}
            try:
                p_id = utils.get_peer_id(peer)
            except Exception:
                p_id = str(peer)
            dedup_key = (p_id, msg_id)
            if dedup_key in self.recent_handled and now - self.recent_handled[dedup_key] < 15:
                return
            self.recent_handled[dedup_key] = now

            # Убираем свою реакцию, чтобы не спамить в чате
            try:
                await self.client(functions.messages.SendReactionRequest(
                    peer=peer, 
                    msg_id=msg_id, 
                    reaction=reactions_to_keep
                ))
            except Exception as e:
                logger.debug(f"SendReactionRequest failed: {e}")
            
            # Запускаем обработку в фоне
            asyncio.create_task(self._dispatch_action(peer, msg_id))

    async def _dispatch_action(self, peer, msg_id):
        """Определяет тип контента и вызывает нужный модуль ИИ"""
        try:
            m = await self.client.get_messages(peer, ids=msg_id)
            if not m: return

            is_media = (
                bool(m.voice or m.video_note or m.audio or m.video)
                or bool(m.document and getattr(m.document, "mime_type", "").startswith(("audio/", "video/")))
            )

            if is_media:
                await self._handle_media(m)
            elif m.text:
                await self._handle_text_fix(m)
        except Exception as e:
            logger.error(f"Ошибка диспетчера: {e}")

    @staticmethod
    def _extract_audio_sync(media_bytes: bytes, in_ext: str = ".mp4"):
        """Извлекает аудиодорожку из видео или перекодирует в легкий моно MP3 16kHz."""
        with tempfile.NamedTemporaryFile(suffix=in_ext, delete=False) as in_f:
            in_f.write(media_bytes)
            in_path = in_f.name
        out_path = in_path + ".mp3"
        try:
            cmd = [
                "ffmpeg", "-y", "-i", in_path,
                "-vn",
                "-ac", "1",
                "-ar", "16000",
                "-b:a", "48k",
                out_path
            ]
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if res.returncode == 0 and os.path.exists(out_path):
                with open(out_path, "rb") as f:
                    return f.read(), "extracted_voice.mp3", None
            err_msg = res.stderr.decode("utf-8", errors="ignore")
            if "does not contain any stream" in err_msg or "Output file is empty" in err_msg:
                return None, in_ext, "no_audio"
        except Exception as e:
            logger.error(f"FFmpeg extraction error: {e}")
        finally:
            for p in (in_path, out_path):
                if os.path.exists(p):
                    try: os.remove(p)
                    except: pass
        return media_bytes, in_ext, None

    async def _handle_media(self, m):
        """Процесс транскрипции голосовых и кружочков"""
        try:
            is_video_note = bool(m.video_note)
            is_voice = bool(m.voice)
            is_audio = bool(m.audio or (m.document and getattr(m.document, "mime_type", "").startswith("audio/")))
            is_video = bool(m.video or (m.document and getattr(m.document, "mime_type", "").startswith("video/")))

            if is_video_note:
                label = "Кружочек"
                ext = "video.mp4"
            elif is_voice:
                label = "Голосовое"
                ext = "voice.ogg"
            elif is_audio:
                label = "Аудио"
                ext = "audio.mp3"
            elif is_video:
                label = "Видео"
                ext = "video.mp4"
            else:
                label = "Медиа"
                ext = "media.ogg"
            
            chat = await m.get_chat()
            sender = await m.get_sender()
            chat_title = getattr(chat, 'title', None) or getattr(chat, 'first_name', 'Личные сообщения')
            s_name = utils.get_display_name(sender) if sender else "Неизвестный"
            msg_link = self._get_link(chat, m.id)

            file_size = getattr(m, 'file', None) and getattr(m.file, 'size', 0)
            if file_size and file_size > 50 * 1024 * 1024:
                size_mb = round(file_size / 1024 / 1024, 1)
                logger.warning(f"Файл слишком большой ({size_mb} МБ)")
                await self.bot_sender.send_message(
                    chat_id=self.my_id,
                    text=f"⚠️ Файл в чате <b>{html.escape(chat_title)}</b> слишком большой ({size_mb} МБ). Лимит для распознавания — 50 МБ.",
                    buttons=[("🔗 Перейти", msg_link)]
                )
                return

            logger.info(f"Транскрипция {label} от {s_name} в '{chat_title}'...")
            
            file_bytes = io.BytesIO()
            await self.client.download_media(m, file=file_bytes)
            raw_media = file_bytes.getvalue()
            
            # Извлекаем аудиодорожку через ffmpeg для видео, кружочков и тяжелых файлов
            if is_video or is_video_note or len(raw_media) > 10 * 1024 * 1024:
                loop = asyncio.get_running_loop()
                dot_ext = "." + ext.split(".")[-1]
                extracted_data, audio_ext, err = await loop.run_in_executor(
                    None, self._extract_audio_sync, raw_media, dot_ext
                )
                if err == "no_audio" or not extracted_data:
                    raw_text = "<i>(В видео отсутствует звуковая дорожка)</i>"
                else:
                    raw_text = await self.transcriber.transcribe(extracted_data, audio_ext)
            else:
                raw_text = await self.transcriber.transcribe(raw_media, ext)
            
            # Кэшируем для возможного саммари
            item_id = str(uuid.uuid4())[:8]
            self.data_cache[item_id] = {"text": raw_text, "link": msg_link}

            # Подготовка HTML
            header = (
                f"<b>Чат:</b> {html.escape(chat_title)}\n"
                f"<b>От:</b> {html.escape(s_name)}\n"
                f"<b>Тип:</b> {label}\n"
                f"--------------------\n\n"
            )
            safe_text = html.escape(raw_text)
            
            # Разбивка на части если текст длинный
            parts = []
            if len(header + safe_text) <= self.MAX_MSG_LEN:
                parts.append(header + safe_text)
            else:
                first_part_limit = self.MAX_MSG_LEN - len(header)
                parts.append(header + safe_text[:first_part_limit])
                remaining = safe_text[first_part_limit:]
                for i in range(0, len(remaining), self.MAX_MSG_LEN):
                    parts.append(remaining[i : i + self.MAX_MSG_LEN])

            # Отправка
            for i, part_content in enumerate(parts):
                is_last = (i == len(parts) - 1)
                btns = []
                if is_last:
                    btns = [
                        ("🔗 Перейти", msg_link),
                        ("📝 Summary", f"summ:{item_id}")
                    ]
                
                await self.bot_sender.send_message(
                    chat_id=self.my_id,
                    text=part_content,
                    buttons=btns
                )
                if not is_last: await asyncio.sleep(0.4)

        except Exception as e:
            logger.error(f"Ошибка медиа: {e}", exc_info=True)

    async def _handle_text_fix(self, m):
        """Процесс исправления пунктуации"""
        try:
            original = m.text
            fixed = await self.fixer.fix_punctuation(original)
            
            if fixed.strip() == original.strip():
                return # Нет изменений — нет сообщения

            item_id = str(uuid.uuid4())[:8]
            chat = await m.get_chat()
            msg_link = self._get_link(chat, m.id)

            self.data_cache[item_id] = {
                "peer": m.peer_id,
                "msg_id": m.id,
                "text": fixed,
                "link": msg_link
            }

            diff_msg = (
                f"📝 <b>Коррекция пунктуации</b>\n\n"
                f"❌ <b>Было:</b>\n<code>{html.escape(original)}</code>\n\n"
                f"✅ <b>Стало:</b>\n<code>{html.escape(fixed)}</code>"
            )

            await self.bot_sender.send_message(
                chat_id=self.my_id,
                text=diff_msg,
                buttons=[("Применить ✅", f"fix:{item_id}")]
            )
        except Exception as e:
            logger.error(f"Ошибка фикса текста: {e}")

    async def bot_callback_handler(self, event):
        """Обработка нажатий на кнопки Summary и Применить"""
        data = event.data.decode()
        
        # 1. Логика ПРИМЕНИТЬ ПРАВКУ ТЕКСТА
        if data.startswith("fix:"):
            item_id = data.split(":")[1]
            cached = self.data_cache.get(item_id)
            if cached:
                try:
                    await self.client.edit_message(cached["peer"], cached["msg_id"], cached["text"])
                    await event.edit(
                        "✅ <b>Сообщение отредактировано!</b>",
                        buttons=[Button.url("🔗 Вернуться к сообщению", cached["link"])],
                        parse_mode='html'
                    )
                    del self.data_cache[item_id]
                except Exception as e:
                    logger.error(f"Ошибка редактирования: {e}")
                    await event.answer("Ошибка: не удалось отредактировать.", alert=True)
            else:
                await event.answer("Данные устарели.", alert=True)

        # 2. Логика СОЗДАТЬ SUMMARY
        elif data.startswith("summ:"):
            item_id = data.split(":")[1]
            cached = self.data_cache.get(item_id)
            if cached:
                await event.answer("Генерирую Summary... 🧠")
                summary = await self.summarizer.summarize(cached["text"])
                
                safe_summary = html.escape(summary)
                resp = f"📋 <b>Summary сообщения:</b>\n\n{safe_summary}"
                
                await self.bot_sender.send_message(
                    chat_id=self.my_id,
                    text=resp,
                    buttons=[("🔗 К сообщению", cached["link"])]
                )
            else:
                await event.answer("Текст транскрипции не найден в кэше.", alert=True)

    def _get_link(self, chat, msg_id):
        try:
            if hasattr(chat, 'username') and chat.username:
                return f"https://t.me/{chat.username}/{msg_id}"
            cid = str(chat.id).replace("-100", "")
            return f"https://t.me/c/{cid}/{msg_id}"
        except: return None