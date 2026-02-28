import os
import re
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from src.services.lang import get_text, get_btn
from src.handlers.forwarding import copy_bot_reply_to_group
import api
import config

ASK_CARD_NUMBER = 0
CONFIRM_DUPLICATE = 1

ARABIC_TO_ENGLISH = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')

def convert_arabic_numbers(text: str) -> str:
    return text.translate(ARABIC_TO_ENGLISH)

def get_back_keyboard(lang='ar'):
    return ReplyKeyboardMarkup([[get_btn('btn_back', lang)]], resize_keyboard=True)

def get_main_keyboard(lang='ar', is_admin=False, service_type='xena'):
    from src.handlers.start import get_main_keyboard as _get_main_keyboard
    return _get_main_keyboard(lang, is_admin, service_type)

def extract_pins_from_text(text: str) -> list:
    text = convert_arabic_numbers(text)
    text = text.replace("-", "").replace(" ", "")
    
    pins = re.findall(r'\d{13,15}', text)
    
    if not pins:
        digits = re.sub(r'\D', '', text)
        if 13 <= len(digits) <= 15:
            pins = [digits]
    
    return list(dict.fromkeys(pins))

async def begin_recharge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db = context.bot_data["db"]
    user_id = update.effective_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in config.ADMIN_USER_IDS
    is_test_user = user_id in config.TEST_USER_IDS
    
    if api.bot_paused and not is_admin and not is_test_user:
        await update.message.reply_text(
            "🔧 البوت قيد الصيانة...\n\n"
            "سنعود قريباً جداً! ⏳\n"
            "شكراً لصبركم 🙏\n\n"
            "The bot is under maintenance.\n"
            "Coming back soon! 🚀",
            reply_to_message_id=update.message.message_id
        )
        return ConversationHandler.END
    
    if not is_admin and not is_test_user and not db.is_user_verified(user_id):
        await update.message.reply_text(
            "⏳ حسابك قيد المراجعة\n\n"
            "سيتم تفعيل حسابك بعد موافقة المشرف.\n\n"
            "Your account is under review.",
            reply_to_message_id=update.message.message_id
        )
        return ConversationHandler.END
    
    if db.is_user_blocked(user_id):
        await update.message.reply_text(
            "🚫 " + ("تم حظر حسابك. تواصل مع الدعم." if lang == 'ar' else "Your account is blocked. Contact support.")
        )
        return ConversationHandler.END
    
    try:
        with open("assets/asiacell_logo.png", "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=get_text('recharge_prompt', lang),
                reply_markup=get_back_keyboard(lang)
            )
    except FileNotFoundError:
        await update.message.reply_text(
            get_text('recharge_prompt', lang),
            reply_markup=get_back_keyboard(lang)
        )
    return ASK_CARD_NUMBER

MENU_BUTTONS_AR = ["💰 رصيدي", "📋 السجلات", "🎮 Xena Live", "🔋 Asiacell", "📞 الدعم", "📋 سجل", "🌐 اللغة"]
MENU_BUTTONS_EN = ["💰 My Balance", "📋 Records", "🎮 Xena Live", "🔋 Asiacell", "📞 Support", "🎮 Xena History", "🌐 Language"]

async def receive_card_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db = context.bot_data["db"]
    lang = db.get_user_language(update.effective_user.id)
    text = update.message.text.strip()
    
    if text in [get_btn('btn_back', 'ar'), get_btn('btn_back', 'en'), "⬅️ رجوع", "⬅️ Back"]:
        return await cancel_recharge(update, context)
    
    if text in MENU_BUTTONS_AR or text in MENU_BUTTONS_EN:
        await update.message.reply_text(
            "📝 " + ("أنت في وضع الشحن الآن!\nأرسل رقم البطاقة أو اضغط ⬅️ رجوع للخروج." if lang == 'ar' else "You're in recharge mode!\nSend card number or press ⬅️ Back to exit.")
        )
        return ASK_CARD_NUMBER
    
    pins = extract_pins_from_text(text)
    user = update.effective_user
    user_id = user.id
    
    db.get_or_create_user(user_id, user.username or "", user.first_name or "")
    
    if not pins:
        card_number = convert_arabic_numbers(text)
        cleaned = re.sub(r'\D', '', card_number)
        
        if not cleaned:
            await update.message.reply_text(get_text('card_invalid', lang))
            return ASK_CARD_NUMBER
        
        if len(cleaned) < 13:
            await update.message.reply_text(get_text('card_short', lang, len=len(cleaned)))
            return ASK_CARD_NUMBER
        
        if len(cleaned) > 15:
            await update.message.reply_text(get_text('card_long', lang, len=len(cleaned)))
            return ASK_CARD_NUMBER
        
        pins = [cleaned]
    
    created = []
    duplicates = []
    
    for pin in pins:
        dup_info = db.check_duplicate_card(pin)
        if dup_info:
            duplicates.append({'pin': pin, 'info': dup_info})
            continue
        
        card_id = db.create_card(user_id, pin, 0)
        if card_id:
            created.append((card_id, pin))
        else:
            duplicates.append({'pin': pin, 'info': None})
    
    response_parts = []
    
    if created:
        if len(created) == 1:
            response_parts.append(get_text('card_received', lang, card_id=created[0][0]))
        else:
            jobs_list = "\n".join([f"  🎫 #{cid}: {pin[:4]}****{pin[-4:]}" for cid, pin in created])
            response_parts.append(get_text('cards_received', lang, count=len(created), jobs_list=jobs_list))
    
    if duplicates:
        for d in duplicates:
            pin = d['pin']
            info = d.get('info')
            masked_pin = f"{pin[:4]}****{pin[-4:]}"
            if info:
                if info['status'] == 'verified':
                    msg = f"✅ {masked_pin}\n" + ("هذه البطاقة تم شحنها بنجاح سابقاً" if lang == 'ar' else "This card was already redeemed successfully")
                else:
                    msg = f"⚠️ {masked_pin}\n" + ("هذه البطاقة مرسلة مسبقاً. إذا واجهت مشكلة تواصل مع الدعم" if lang == 'ar' else "This card was already sent. If there's an issue, contact support")
                response_parts.append(msg)
            else:
                msg = f"⚠️ {masked_pin}\n" + ("حدث خطأ أثناء إرسال البطاقة. حاول مرة أخرى" if lang == 'ar' else "Error submitting card. Please try again")
                response_parts.append(msg)
    
    if created:
        response_parts.append(get_text('card_wait', lang))
    
    import config
    is_admin = user_id in config.ADMIN_USER_IDS
    service_type = db.get_user_service_type(user_id) if not is_admin else 'both'
    
    if response_parts:
        reply_text = "\n\n".join(response_parts)
        await update.message.reply_text(reply_text, reply_markup=get_main_keyboard(lang, is_admin, service_type))
        await copy_bot_reply_to_group(context, user_id, reply_text)
    else:
        reply_text = "❌ " + ("لم يتم العثور على أرقام صالحة" if lang == 'ar' else "No valid numbers found")
        await update.message.reply_text(reply_text, reply_markup=get_main_keyboard(lang, is_admin, service_type))
        await copy_bot_reply_to_group(context, user_id, reply_text)
    
    return ConversationHandler.END

async def receive_card_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db = context.bot_data["db"]
    user_id = update.effective_user.id
    lang = db.get_user_language(user_id)
    ocr = context.bot_data.get("ocr")
    
    if not ocr:
        await update.message.reply_text(get_text('ocr_not_available', lang))
        return ASK_CARD_NUMBER
    
    await update.message.reply_text(get_text('ocr_reading', lang))
    
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()
    
    image_path = None
    try:
        os.makedirs("data/card_images", exist_ok=True)
        image_path = f"data/card_images/{user_id}_{photo.file_id}.jpg"
        with open(image_path, "wb") as f:
            f.write(image_bytes)
    except Exception:
        image_path = None
    
    result = ocr.extract_multiple_pins(bytes(image_bytes))
    
    if not result.get("success") or not result.get("pins"):
        single_result = ocr.extract_pin_from_image(bytes(image_bytes))
        if single_result.get("success"):
            result = {"success": True, "pins": [single_result["pin"]]}
        else:
            await update.message.reply_text(
                get_text('ocr_failed', lang, error=result.get('error', 'Unknown error'))
            )
            return ASK_CARD_NUMBER
    
    pins = result["pins"]
    
    if len(pins) == 1:
        await update.message.reply_text(get_text('ocr_found', lang, pin=pins[0]))
    else:
        pins_list = "\n".join([f"  • {pin}" for pin in pins])
        await update.message.reply_text(get_text('ocr_found_multi', lang, count=len(pins), pins_list=pins_list))
    
    created = []
    duplicates = []
    
    for pin in pins:
        dup_info = db.check_duplicate_card(pin)
        if dup_info:
            duplicates.append({'pin': pin, 'info': dup_info})
            continue
        
        card_id = db.create_card(user_id, pin, 0, image_path)
        if card_id:
            created.append((card_id, pin))
        else:
            duplicates.append({'pin': pin, 'info': None})
    
    response_parts = []
    
    if created:
        if len(created) == 1:
            response_parts.append(get_text('card_received', lang, card_id=created[0][0]))
        else:
            jobs_list = "\n".join([f"  🎫 #{cid}: {pin[:4]}****{pin[-4:]}" for cid, pin in created])
            response_parts.append(get_text('cards_received', lang, count=len(created), jobs_list=jobs_list))
    
    if duplicates:
        for d in duplicates:
            pin = d['pin']
            info = d.get('info')
            masked_pin = f"{pin[:4]}****{pin[-4:]}"
            if info:
                if info['status'] == 'verified':
                    msg = f"✅ {masked_pin}\n" + ("هذه البطاقة تم شحنها بنجاح سابقاً" if lang == 'ar' else "This card was already redeemed successfully")
                else:
                    msg = f"⚠️ {masked_pin}\n" + ("هذه البطاقة مرسلة مسبقاً. إذا واجهت مشكلة تواصل مع الدعم" if lang == 'ar' else "This card was already sent. If there's an issue, contact support")
                response_parts.append(msg)
            else:
                msg = f"⚠️ {masked_pin}\n" + ("حدث خطأ أثناء إرسال البطاقة. حاول مرة أخرى" if lang == 'ar' else "Error submitting card. Please try again")
                response_parts.append(msg)
    
    if created:
        response_parts.append(get_text('card_wait', lang))
    
    import config
    is_admin = user_id in config.ADMIN_USER_IDS
    service_type = db.get_user_service_type(user_id) if not is_admin else 'both'
    
    if response_parts:
        reply_text = "\n\n".join(response_parts)
        await update.message.reply_text(reply_text, reply_markup=get_main_keyboard(lang, is_admin, service_type))
    else:
        await update.message.reply_text(
            "❌ " + ("جميع البطاقات مستخدمة سابقاً" if lang == 'ar' else "All cards already used"),
            reply_markup=get_main_keyboard(lang, is_admin, service_type)
        )
    
    return ConversationHandler.END

async def cancel_recharge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db = context.bot_data["db"]
    user_id = update.effective_user.id
    lang = db.get_user_language(user_id)
    
    import config
    is_admin = user_id in config.ADMIN_USER_IDS
    service_type = db.get_user_service_type(user_id) if not is_admin else 'both'
    
    await update.message.reply_text(
        get_text('cancelled', lang),
        reply_markup=get_main_keyboard(lang, is_admin, service_type)
    )
    return ConversationHandler.END

