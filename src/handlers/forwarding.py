import logging
from telegram import Update, Message
from telegram.ext import ContextTypes
import config

logger = logging.getLogger(__name__)

MONITOR_GROUP_ID = -1003505287913

async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    
    user = update.effective_user
    user_id = user.id
    chat_type = update.effective_chat.type
    
    if chat_type in ['group', 'supergroup']:
        return
    
    if user_id in config.ADMIN_USER_IDS:
        return
    
    db = context.bot_data.get("db")
    if db:
        message = update.message
        content = message.text or message.caption or "[media]"
        msg_type = 'text'
        if message.photo:
            msg_type = 'photo'
        elif message.document:
            msg_type = 'document'
        try:
            db.log_message(user_id, 'user', content, msg_type)
            logger.info(f"Logged message from user {user_id}")
        except Exception as e:
            logger.error(f"Failed to log user message: {e}")

async def copy_bot_reply_to_group(context: ContextTypes.DEFAULT_TYPE, user_id: int, text: str = None, photo = None, document = None):
    if user_id in config.ADMIN_USER_IDS:
        return
    
    db = context.bot_data.get("db")
    if db:
        try:
            content = text or "[media]"
            msg_type = 'text' if text else ('photo' if photo else 'document')
            db.log_message(user_id, 'bot', content, msg_type)
        except Exception as e:
            logger.error(f"Failed to log bot reply: {e}")
