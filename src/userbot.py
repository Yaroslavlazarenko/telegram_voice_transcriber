import io
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
        if not isinstance(event, (types.UpdateEditMessage, types.UpdateEditChannelMessage)):
            return
            
        msg_event = event.message
        if not msg_event or not msg_event.reactions:
            return

        target_found = False
        reactions_to_keep = []
        
        if msg_event.reactions.recent_reactions:
            for r in msg_event.reactions.recent_reactions:
                user_id = r.peer_id.user_id if isinstance(r.peer_id, types.PeerUser) else None
                if user_id == self.my_id:
                    emoji = r.reaction.emoticon if isinstance(r.reaction, types.ReactionEmoji) else None
                    if emoji == Config.TRIGGER_EMOJI:
                        target_found = True
                    else:
                        reactions_to_keep.append(r.reaction)

        if target_found:
            # Убираем свою реакцию, чтобы не спамить
            try:
                await self.client(functions.messages.SendReactionRequest(
                    peer=msg_event.peer_id, 
                    msg_id=msg_event.id, 
                    reaction=reactions_to_keep
                ))
            except: pass
            
            # Запускаем обработку в фоне
            asyncio.create_task(self._dispatch_action(msg_event.peer_id, msg_event.id))

    async def _dispatch_action(self, peer, msg_id):
        """Определяет тип контента и вызывает нужный модуль ИИ"""
        try:
            m = await self.client.get_messages(peer, ids=msg_id)
            if not m: return

            if m.voice or m.video_note:
                await self._handle_media(m)
            elif m.text:
                await self._handle_text_fix(m)
        except Exception as e:
            logger.error(f"Ошибка диспетчера: {e}")

    async def _handle_media(self, m):
        """Процесс транскрипции голосовых и кружочков"""
        try:
            is_video = bool(m.video_note)
            ext = "video.mp4" if is_video else "voice.ogg"
            label = "Кружочек" if is_video else "Голосовое"
            
            chat = await m.get_chat()
            sender = await m.get_sender()
            chat_title = getattr(chat, 'title', 'Личные сообщения')
            s_name = utils.get_display_name(sender) if sender else "Неизвестный"
            msg_link = self._get_link(chat, m.id)

            logger.info(f"Транскрипция {label} от {s_name}...")
            
            file_bytes = io.BytesIO()
            await self.client.download_media(m, file=file_bytes)
            
            # Получаем текст от Mistral Audio API
            raw_text = await self.transcriber.transcribe(file_bytes.getvalue(), ext)
            
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
                
                resp = f"📋 <b>Summary сообщения:</b>\n\n{html.escape(summary)}"
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