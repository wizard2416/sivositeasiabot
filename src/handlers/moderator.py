from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import config
from src.services.db import Database
from src.services.lang import get_text
from src.handlers.start import get_main_keyboard
import os
import tempfile
import logging
import asyncio

logger = logging.getLogger(__name__)
db = Database()

MODERATOR_WAITING_IMAGE_PROMPT = 100
MODERATOR_WAITING_BROADCAST = 101
MODERATOR_IDS = config.MODERATOR_IDS

def is_moderator(user_id: int) -> bool:
    return user_id in MODERATOR_IDS or user_id in config.ADMIN_USER_IDS

async def moderator_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_moderator(user_id):
        return
    
    user = db.get_or_create_user(user_id)
    lang = user.language or 'ar'
    
    cursor = db.execute("SELECT COUNT(*) as cnt FROM users WHERE is_approved = FALSE")
    pending_count = cursor.fetchone()['cnt']
    
    keyboard = [
        [InlineKeyboardButton(f"{'طلبات الموافقة' if lang == 'ar' else 'Pending Users'} ({pending_count})", callback_data="mod_pending_users")],
        [InlineKeyboardButton("📢 ارسال رسالة للجميع" if lang == 'ar' else "📢 Broadcast Message", callback_data="mod_broadcast_start")],
        [InlineKeyboardButton("انشاء صورة بالذكاء الاصطناعي" if lang == 'ar' else "Generate AI Image", callback_data="mod_generate_image")],
        [InlineKeyboardButton("خروج من لوحة المشرف" if lang == 'ar' else "Exit Moderator Panel", callback_data="mod_exit")]
    ]
    
    text = "لوحة المشرف" if lang == 'ar' else "Moderator Panel"
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def mod_pending_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if not is_moderator(user_id):
        return
    
    user = db.get_or_create_user(user_id)
    lang = user.language or 'ar'
    
    cursor = db.execute("""
        SELECT user_id, username, first_name, created_at 
        FROM users 
        WHERE is_approved = FALSE 
        ORDER BY created_at DESC 
        LIMIT 10
    """)
    pending = cursor.fetchall()
    
    if not pending:
        text = "لا يوجد طلبات معلقة" if lang == 'ar' else "No pending requests"
        keyboard = [[InlineKeyboardButton("رجوع" if lang == 'ar' else "Back", callback_data="mod_menu")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    keyboard = []
    for p in pending:
        name = p['first_name'] or p['username'] or str(p['user_id'])
        keyboard.append([
            InlineKeyboardButton(f"✅ {name}", callback_data=f"mod_approve_{p['user_id']}"),
            InlineKeyboardButton(f"❌", callback_data=f"mod_reject_{p['user_id']}")
        ])
    
    keyboard.append([InlineKeyboardButton("رجوع" if lang == 'ar' else "Back", callback_data="mod_menu")])
    
    text = "المستخدمين المعلقين:" if lang == 'ar' else "Pending Users:"
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def mod_approve_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if not is_moderator(user_id):
        return
    
    target_id = int(query.data.split("_")[2])
    
    db.execute("UPDATE users SET is_approved = TRUE WHERE user_id = %s", (target_id,))
    db.commit()
    
    try:
        await context.bot.send_message(
            target_id,
            "تم الموافقة على حسابك! يمكنك الآن استخدام البوت.\n\nYour account has been approved! You can now use the bot."
        )
    except:
        pass
    
    user = db.get_or_create_user(user_id)
    lang = user.language or 'ar'
    
    await query.message.edit_text(
        f"{'تم الموافقة على المستخدم' if lang == 'ar' else 'User approved'} ✅",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("رجوع" if lang == 'ar' else "Back", callback_data="mod_pending_users")
        ]])
    )

async def mod_reject_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if not is_moderator(user_id):
        return
    
    target_id = int(query.data.split("_")[2])
    
    db.execute("DELETE FROM users WHERE user_id = %s", (target_id,))
    db.commit()
    
    user = db.get_or_create_user(user_id)
    lang = user.language or 'ar'
    
    await query.message.edit_text(
        f"{'تم رفض المستخدم' if lang == 'ar' else 'User rejected'} ❌",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("رجوع" if lang == 'ar' else "Back", callback_data="mod_pending_users")
        ]])
    )

async def mod_generate_image_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if not is_moderator(user_id):
        return
    
    user = db.get_or_create_user(user_id)
    lang = user.language or 'ar'
    
    context.user_data['mod_waiting_image'] = True
    context.user_data['mod_image_prompt'] = ""
    context.user_data['mod_last_generated_image'] = None
    context.user_data['mod_uploaded_photos'] = []
    
    text = """🎨 انشاء صورة بالذكاء الاصطناعي:

📝 ارسل وصف الصورة (نص أو صوت)
📸 أو ارسل صورة/صور لتعديلها مع وصف التعديل

🎨 AI Image Generation:

📝 Send image description (text or voice)
📸 Or send photo(s) with edit description"""
    
    keyboard = [[InlineKeyboardButton("إلغاء" if lang == 'ar' else "Cancel", callback_data="mod_menu")]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return MODERATOR_WAITING_IMAGE_PROMPT

async def mod_handle_text_for_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_moderator(user_id):
        return ConversationHandler.END
    
    if not context.user_data.get('mod_waiting_image'):
        return ConversationHandler.END
    
    prompt = update.message.text.strip()
    user = db.get_or_create_user(user_id)
    lang = user.language or 'ar'
    
    try:
        from src.services.gemini_image import generate_image_from_prompt
        
        await update.message.reply_text("جاري انشاء الصورة..." if lang == 'ar' else "Generating image...")
        image_path = await generate_image_from_prompt(prompt)
        
        if image_path and os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=f"🎨 {'الوصف:' if lang == 'ar' else 'Prompt:'} {prompt}"
                )
        else:
            await update.message.reply_text("فشل انشاء الصورة" if lang == 'ar' else "Failed to generate image")
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        await update.message.reply_text("فشل انشاء الصورة. حاول مرة أخرى." if lang == 'ar' else "Failed to generate image. Please try again.")
    
    context.user_data['mod_waiting_image'] = False
    context.user_data['mod_image_prompt'] = ""
    return ConversationHandler.END

async def mod_handle_voice_for_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_moderator(user_id):
        return ConversationHandler.END
    
    if not context.user_data.get('mod_waiting_image'):
        return ConversationHandler.END
    
    user = db.get_or_create_user(user_id)
    lang = user.language or 'ar'
    
    await update.message.reply_text("جاري تحويل الصوت..." if lang == 'ar' else "Transcribing voice...")
    
    try:
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as tmp:
            await file.download_to_drive(tmp.name)
            voice_path = tmp.name
        
        from src.services.gemini_image import transcribe_arabic_voice, generate_image_from_prompt
        
        prompt = await transcribe_arabic_voice(voice_path)
        os.remove(voice_path)
        
        if not prompt:
            await update.message.reply_text("فشل تحويل الصوت" if lang == 'ar' else "Failed to transcribe voice")
            context.user_data['mod_waiting_image'] = False
            return ConversationHandler.END
        
        await update.message.reply_text(f"{'الوصف:' if lang == 'ar' else 'Prompt:'} {prompt}\n\n{'جاري انشاء الصورة...' if lang == 'ar' else 'Generating image...'}")
        
        image_path = await generate_image_from_prompt(prompt)
        
        if image_path and os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=f"🎨 {'الوصف:' if lang == 'ar' else 'Prompt:'} {prompt}"
                )
        else:
            await update.message.reply_text("فشل انشاء الصورة" if lang == 'ar' else "Failed to generate image")
            
    except Exception as e:
        logger.error(f"Voice image generation error: {e}")
        await update.message.reply_text("فشل معالجة الرسالة الصوتية. حاول مرة أخرى." if lang == 'ar' else "Failed to process voice message. Please try again.")
    
    context.user_data['mod_waiting_image'] = False
    return ConversationHandler.END

async def mod_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['mod_waiting_image'] = False
    context.user_data['mod_waiting_broadcast'] = False
    await moderator_menu(update, context)
    return ConversationHandler.END

async def mod_exit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user = db.get_or_create_user(user_id)
    lang = user.language or 'ar'
    is_admin = user_id in config.ADMIN_USER_IDS
    is_mod = user_id in MODERATOR_IDS
    service_type = db.get_user_service_type(user_id) if not is_admin else 'both'
    
    text = "تم الخروج من لوحة المشرف" if lang == 'ar' else "Exited moderator panel"
    await query.message.edit_text(text)
    await query.message.reply_text(
        "🏠 القائمة الرئيسية" if lang == 'ar' else "🏠 Main Menu",
        reply_markup=get_main_keyboard(lang, is_admin, service_type, is_mod)
    )

async def mod_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if not is_moderator(user_id):
        return
    
    user = db.get_or_create_user(user_id)
    lang = user.language or 'ar'
    
    context.user_data['mod_waiting_broadcast'] = True
    
    text = """📢 ارسل الرسالة التي تريد ارسالها للجميع:
- نص
- صورة
- فيديو
- رسالة صوتية

📢 Send the message you want to broadcast to everyone:
- Text
- Photo
- Video
- Voice message"""
    
    keyboard = [[InlineKeyboardButton("إلغاء" if lang == 'ar' else "Cancel", callback_data="mod_menu")]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return MODERATOR_WAITING_BROADCAST

async def mod_broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_moderator(user_id):
        return ConversationHandler.END
    
    if not context.user_data.get('mod_waiting_broadcast'):
        return ConversationHandler.END
    
    user = db.get_or_create_user(user_id)
    lang = user.language or 'ar'
    
    text = update.message.text
    
    await update.message.reply_text("جاري الارسال..." if lang == 'ar' else "Broadcasting...")
    
    cursor = db.execute("SELECT user_id FROM users WHERE is_approved = TRUE")
    users = cursor.fetchall()
    
    success = 0
    failed = 0
    sent_messages = []
    
    for u in users:
        try:
            msg = await context.bot.send_message(u['user_id'], text)
            sent_messages.append({'chat_id': u['user_id'], 'message_id': msg.message_id})
            success += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            logger.debug(f"Failed to send to {u['user_id']}: {e}")
    
    context.user_data['mod_waiting_broadcast'] = False
    context.user_data['last_broadcast_messages'] = sent_messages
    
    result = f"✅ {'تم الارسال' if lang == 'ar' else 'Broadcast complete'}\n"
    result += f"{'نجح:' if lang == 'ar' else 'Success:'} {success}\n"
    result += f"{'فشل:' if lang == 'ar' else 'Failed:'} {failed}"
    
    keyboard = [[InlineKeyboardButton("🗑️ حذف الرسالة" if lang == 'ar' else "🗑️ Delete Broadcast", callback_data="mod_delete_broadcast")]]
    await update.message.reply_text(result, reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

async def mod_broadcast_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_moderator(user_id):
        return ConversationHandler.END
    
    if not context.user_data.get('mod_waiting_broadcast'):
        return ConversationHandler.END
    
    user = db.get_or_create_user(user_id)
    lang = user.language or 'ar'
    
    photo = update.message.photo[-1]
    caption = update.message.caption or ""
    
    await update.message.reply_text("جاري الارسال..." if lang == 'ar' else "Broadcasting...")
    
    cursor = db.execute("SELECT user_id FROM users WHERE is_approved = TRUE")
    users = cursor.fetchall()
    
    success = 0
    failed = 0
    sent_messages = []
    
    for u in users:
        try:
            msg = await context.bot.send_photo(u['user_id'], photo.file_id, caption=caption)
            sent_messages.append({'chat_id': u['user_id'], 'message_id': msg.message_id})
            success += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            logger.debug(f"Failed to send to {u['user_id']}: {e}")
    
    context.user_data['mod_waiting_broadcast'] = False
    context.user_data['last_broadcast_messages'] = sent_messages
    
    result = f"✅ {'تم الارسال' if lang == 'ar' else 'Broadcast complete'}\n"
    result += f"{'نجح:' if lang == 'ar' else 'Success:'} {success}\n"
    result += f"{'فشل:' if lang == 'ar' else 'Failed:'} {failed}"
    
    keyboard = [[InlineKeyboardButton("🗑️ حذف الرسالة" if lang == 'ar' else "🗑️ Delete Broadcast", callback_data="mod_delete_broadcast")]]
    await update.message.reply_text(result, reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

async def mod_broadcast_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_moderator(user_id):
        return ConversationHandler.END
    
    if not context.user_data.get('mod_waiting_broadcast'):
        return ConversationHandler.END
    
    user = db.get_or_create_user(user_id)
    lang = user.language or 'ar'
    
    video = update.message.video
    caption = update.message.caption or ""
    
    await update.message.reply_text("جاري الارسال..." if lang == 'ar' else "Broadcasting...")
    
    cursor = db.execute("SELECT user_id FROM users WHERE is_approved = TRUE")
    users = cursor.fetchall()
    
    success = 0
    failed = 0
    sent_messages = []
    
    for u in users:
        try:
            msg = await context.bot.send_video(u['user_id'], video.file_id, caption=caption)
            sent_messages.append({'chat_id': u['user_id'], 'message_id': msg.message_id})
            success += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            logger.debug(f"Failed to send to {u['user_id']}: {e}")
    
    context.user_data['mod_waiting_broadcast'] = False
    context.user_data['last_broadcast_messages'] = sent_messages
    
    result = f"✅ {'تم الارسال' if lang == 'ar' else 'Broadcast complete'}\n"
    result += f"{'نجح:' if lang == 'ar' else 'Success:'} {success}\n"
    result += f"{'فشل:' if lang == 'ar' else 'Failed:'} {failed}"
    
    keyboard = [[InlineKeyboardButton("🗑️ حذف الرسالة" if lang == 'ar' else "🗑️ Delete Broadcast", callback_data="mod_delete_broadcast")]]
    await update.message.reply_text(result, reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

async def mod_broadcast_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_moderator(user_id):
        return ConversationHandler.END
    
    if not context.user_data.get('mod_waiting_broadcast'):
        return ConversationHandler.END
    
    user = db.get_or_create_user(user_id)
    lang = user.language or 'ar'
    
    voice = update.message.voice
    
    await update.message.reply_text("جاري الارسال..." if lang == 'ar' else "Broadcasting...")
    
    cursor = db.execute("SELECT user_id FROM users WHERE is_approved = TRUE")
    users = cursor.fetchall()
    
    success = 0
    failed = 0
    sent_messages = []
    
    for u in users:
        try:
            msg = await context.bot.send_voice(u['user_id'], voice.file_id)
            sent_messages.append({'chat_id': u['user_id'], 'message_id': msg.message_id})
            success += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            logger.debug(f"Failed to send to {u['user_id']}: {e}")
    
    context.user_data['mod_waiting_broadcast'] = False
    context.user_data['last_broadcast_messages'] = sent_messages
    
    result = f"✅ {'تم الارسال' if lang == 'ar' else 'Broadcast complete'}\n"
    result += f"{'نجح:' if lang == 'ar' else 'Success:'} {success}\n"
    result += f"{'فشل:' if lang == 'ar' else 'Failed:'} {failed}"
    
    keyboard = [[InlineKeyboardButton("🗑️ حذف الرسالة" if lang == 'ar' else "🗑️ Delete Broadcast", callback_data="mod_delete_broadcast")]]
    await update.message.reply_text(result, reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

async def mod_delete_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if not is_moderator(user_id):
        return
    
    user = db.get_or_create_user(user_id)
    lang = user.language or 'ar'
    
    sent_messages = context.user_data.get('last_broadcast_messages', [])
    
    if not sent_messages:
        await query.message.edit_text("لا توجد رسالة للحذف" if lang == 'ar' else "No broadcast to delete")
        return
    
    await query.message.edit_text("جاري الحذف..." if lang == 'ar' else "Deleting...")
    
    deleted = 0
    failed = 0
    
    for msg in sent_messages:
        try:
            await context.bot.delete_message(msg['chat_id'], msg['message_id'])
            deleted += 1
            await asyncio.sleep(0.03)
        except Exception as e:
            failed += 1
            logger.debug(f"Failed to delete message: {e}")
    
    context.user_data['last_broadcast_messages'] = []
    
    result = f"🗑️ {'تم الحذف' if lang == 'ar' else 'Deleted'}\n"
    result += f"{'نجح:' if lang == 'ar' else 'Success:'} {deleted}\n"
    result += f"{'فشل:' if lang == 'ar' else 'Failed:'} {failed}"
    
    await query.message.edit_text(result)
    await moderator_menu(update, context)
