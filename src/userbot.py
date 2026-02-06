import io
import asyncio
import qrcode
import html
import uuid
from telethon import TelegramClient, events, types, functions, utils, Button
from .config import Config
from .transcriber import MistralTranscriber
from .text_fixer import MistralTextFixer
from .bot_sender import BotSender
from .logger import setup_logger

logger = setup_logger("Userbot")

class Userbot:
    def __init__(self):
        self.client = TelegramClient(Config.SESSION_NAME, Config.API_ID, Config.API_HASH)
        self.bot_client = TelegramClient("bot_session", Config.API_ID, Config.API_HASH)
        
        self.transcriber = MistralTranscriber()
        self.fixer = MistralTextFixer()
        self.bot_sender = BotSender()
        
        self.my_id = None
        self.fix_cache = {} 

    async def start(self):
        await self.client.connect()
        if not await self.client.is_user_authorized():
            qr_login = await self.client.qr_login()
            qr = qrcode.QRCode()
            qr.add_data(qr_login.url)
            qr.make(fit=True)
            qr.print_ascii(invert=True)
            await qr_login.wait()

        await self.bot_client.start(bot_token=Config.BOT_TOKEN)
        
        me = await self.client.get_me()
        self.my_id = me.id
        logger.info(f"Система запущена. Аккаунт ID: {self.my_id}")

        # Добавляем обработку разных типов обновлений для реакций
        self.client.add_event_handler(self.reaction_handler, events.Raw())
        self.bot_client.add_event_handler(self.bot_callback_handler, events.CallbackQuery())
        
        await self.client.run_until_disconnected()

    async def reaction_handler(self, event):
        # Ловим любые обновления сообщений (в т.ч. реакции)
        if not isinstance(event, (types.UpdateEditMessage, types.UpdateEditChannelMessage)):
            return
            
        msg_event = event.message
        if not msg_event or not msg_event.reactions:
            return

        # Проверяем, есть ли там ваша триггер-реакция
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
            # Убираем реакцию
            try:
                await self.client(functions.messages.SendReactionRequest(
                    peer=msg_event.peer_id, 
                    msg_id=msg_event.id, 
                    reaction=reactions_to_keep
                ))
            except:
                pass
            
            # ЗАПУСКАЕМ ОБЩИЙ ДИСПЕТЧЕР (он скачает сообщение целиком)
            asyncio.create_task(self._dispatch_message(msg_event.peer_id, msg_event.id))

    async def _dispatch_message(self, peer, msg_id):
        """Метод скачивает полное сообщение и решает: транскрибировать или править текст"""
        try:
            m = await self.client.get_messages(peer, ids=msg_id)
            if not m: return

            # 1. Если это голосовое или кружочек
            if m.voice or m.video_note:
                await self._process_media(m)
            
            # 2. Если это просто текст (и не медиафайл с подписью)
            elif m.text and not (m.audio or m.video or m.document or m.photo):
                await self._process_text_fix(m)
                
            # 3. Если это медиа с текстом (подпись к фото/файлу) - тоже правим текст
            elif m.text:
                await self._process_text_fix(m)

        except Exception as e:
            logger.error(f"Ошибка в диспетчере: {e}")

    async def _process_text_fix(self, m):
        try:
            original_text = m.text
            logger.info(f"Начинаю правку сообщения {m.id}...")
            
            # Ждем результат от фиксера
            fixed = await self.fixer.fix_punctuation(original_text)
            
            logger.info(f"Правка завершена. Сравниваю результаты...")

            if fixed.strip() == original_text.strip():
                logger.info("Изменений не обнаружено.")
                return

            # Дальнейшая логика формирования кнопки и отправки...
            fix_id = str(uuid.uuid4())[:8]
            chat = await m.get_chat()
            
            self.fix_cache[fix_id] = {
                "peer": m.peer_id,
                "msg_id": m.id,
                "text": fixed,
                "link": self._get_link(chat, m.id)
            }

            diff = (
                f"📝 <b>Коррекция пунктуации</b>\n\n"
                f"❌ <b>Было:</b>\n<code>{html.escape(original_text)}</code>\n\n"
                f"✅ <b>Стало:</b>\n<code>{html.escape(fixed)}</code>"
            )

            await self.bot_sender.send_message(
                chat_id=self.my_id,
                text=diff,
                button_text="Применить ✅",
                button_url=f"fix:{fix_id}"
            )
            logger.info(f"Сообщение с правками отправлено в ЛС (ID: {self.my_id})")

        except Exception as e:
            logger.error(f"Ошибка в _process_text_fix: {e}", exc_info=True)

    async def bot_callback_handler(self, event):
        data = event.data.decode()
        if not data.startswith("fix:"): return
        
        fix_id = data.split(":")[1]
        fix_data = self.fix_cache.get(fix_id)
        
        if fix_data:
            try:
                # Юзербот правит сообщение
                await self.client.edit_message(
                    fix_data["peer"], 
                    fix_data["msg_id"], 
                    fix_data["text"]
                )
                
                # Обновляем сообщение бота
                await event.edit(
                    f"✅ <b>Готово!</b>\nСообщение отредактировано.",
                    buttons=[Button.url("🔗 Вернуться к сообщению", fix_data["link"])]
                )
                del self.fix_cache[fix_id]
            except Exception as e:
                logger.error(f"Ошибка применения: {e}")
                await event.answer("Ошибка: сообщение нельзя отредактировать (возможно, оно слишком старое).", alert=True)
        else:
            await event.answer("Данные устарели.", alert=True)

    async def _process_media(self, m):
        """Метод транскрипции (старый проверенный код)"""
        try:
            ext = "video.mp4" if m.video_note else "voice.ogg"
            label = "Кружочек" if m.video_note else "Голосовое"
            
            chat = await m.get_chat()
            sender = await m.get_sender()
            chat_title = getattr(chat, 'title', 'Личные сообщения')
            s_name = utils.get_display_name(sender) if sender else "Неизвестный"

            file_bytes = io.BytesIO()
            await self.client.download_media(m, file=file_bytes)
            
            text = await self.transcriber.transcribe(file_bytes.getvalue(), ext)
            
            # Экранируем и отправляем (с разбиением если надо)
            safe_text = html.escape(text)
            response = (
                f"<b>Чат:</b> {html.escape(chat_title)}\n"
                f"<b>От:</b> {html.escape(s_name)}\n"
                f"<b>Тип:</b> {label}\n"
                f"--------------------\n\n{safe_text}"
            )
            
            await self.bot_sender.send_message(
                self.my_id, response, "🔗 Перейти к сообщению", self._get_link(chat, m.id)
            )
        except Exception as e:
            logger.error(f"Ошибка медиа: {e}")

    def _get_link(self, chat, msg_id):
        try:
            if hasattr(chat, 'username') and chat.username:
                return f"https://t.me/{chat.username}/{msg_id}"
            cid = str(chat.id).replace("-100", "")
            return f"https://t.me/c/{cid}/{msg_id}"
        except: return None