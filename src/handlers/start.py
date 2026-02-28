import os
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime
import config
from src.services.lang import get_text, get_btn
from src.handlers.forwarding import copy_bot_reply_to_group
import api

def get_main_keyboard(lang='ar', is_admin=False, service_type='xena', is_moderator=False):
    if service_type == 'usd':
        if is_admin:
            return ReplyKeyboardMarkup([
                [get_btn('btn_recharge', lang), get_btn('btn_withdraw', lang)],
                [get_btn('btn_settings', lang), get_btn('btn_payment_methods', lang)],
                [get_btn('btn_admin', lang)]
            ], resize_keyboard=True)
        return ReplyKeyboardMarkup([
            [get_btn('btn_recharge', lang), get_btn('btn_withdraw', lang)],
            [get_btn('btn_settings', lang), get_btn('btn_payment_methods', lang)]
        ], resize_keyboard=True)
    
    if is_admin:
        return ReplyKeyboardMarkup([
            [get_btn('btn_xena', lang), get_btn('btn_recharge', lang)],
            [get_btn('btn_settings', lang), get_btn('btn_payment_methods', lang)],
            [get_btn('btn_admin', lang)]
        ], resize_keyboard=True)
    
    return ReplyKeyboardMarkup([
        [get_btn('btn_xena', lang), get_btn('btn_recharge', lang)],
        [get_btn('btn_settings', lang), get_btn('btn_payment_methods', lang)]
    ], resize_keyboard=True)

def get_settings_keyboard(lang='ar'):
    return ReplyKeyboardMarkup([
        [get_btn('btn_balance', lang), get_btn('btn_records', lang)],
        [get_btn('btn_track_orders', lang), get_btn('btn_language', lang)],
        [get_btn('btn_back', lang)]
    ], resize_keyboard=True)

def get_payment_methods_keyboard(lang='ar'):
    return ReplyKeyboardMarkup([
        [get_btn('btn_qi_card', lang), get_btn('btn_zaincash', lang)],
        [get_btn('btn_vodafone', lang)],
        [get_btn('btn_back', lang)]
    ], resize_keyboard=True)

BTN_RECHARGE = "💳 إضافة رصيد آسيا"
BTN_BALANCE = "💰 رصيدي"
BTN_RECORDS = "📋 سجل الطلبات"
BTN_XENA = "🪙 زینە لایڤ"
BTN_SUPPORT = "📞 الدعم"
BTN_XENA_HISTORY = "📋 سجل"
BTN_LANGUAGE = "🌐 تغيير اللغة"
BTN_RETRY = "🔄 إعادة المحاولة"
BTN_QI_CARD = "💳 QI Card"
BTN_ZAINCASH = "💜 ZainCash"
BTN_SETTINGS = "⚙️ إعدادات"
BTN_PAYMENT_METHODS = "💳 طرق الدفع"
BTN_VODAFONE = "🔴 Vodafone Cash"
BTN_WITHDRAW = "💵 سحب"
BTN_BINANCE = "🔶 Binance ID"
BTN_TRC20 = "💎 USDT TRC20"

def get_admin_contact_keyboard():
    admin_tg = config.ADMIN_TELEGRAM.replace('@', '') if config.ADMIN_TELEGRAM else ""
    admin_wa = config.ADMIN_WHATSAPP.replace('+', '').replace(' ', '') if config.ADMIN_WHATSAPP else ""
    
    buttons = []
    if admin_tg:
        buttons.append([InlineKeyboardButton("📱 Telegram", url=f"https://t.me/{admin_tg}")])
    if admin_wa:
        buttons.append([InlineKeyboardButton("💬 WhatsApp", url=f"https://wa.me/{admin_wa}")])
    
    return InlineKeyboardMarkup(buttons) if buttons else None

COMING_SOON_MESSAGE = (
    "🚀 ترقبوا... المفاجأة الأضخم قادمة! 🚀\n\n"
    "🔥 الحصري والجديد:\n"
    "إضافة الرصيد ستكون متاحة عبر:\n"
    "🟠 زين كاش (ZainCash)\n"
    "🟡 كي كارد (Qi Card)\n\n"
    "⚠️ نصيحة: لا تغادر وتفوت الفرصة!\n"
    "سنعود للعمل قريباً جداً وبقوة أكبر. خليك قريب... القادم مذهل! 😉🔥"
)

async def coming_soon_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in config.ADMIN_USER_IDS or user_id in config.TEST_USER_IDS:
        return
    if update.message:
        await update.message.reply_text(COMING_SOON_MESSAGE, reply_to_message_id=update.message.message_id)
    elif update.callback_query:
        await update.callback_query.answer(show_alert=False)
        await update.callback_query.message.reply_text(COMING_SOON_MESSAGE)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        db = context.bot_data["db"]
        user = update.effective_user
        user_id = user.id
        
        is_user_admin = user_id in config.ADMIN_USER_IDS
        is_user_moderator = user_id in getattr(config, 'MODERATOR_IDS', [])
        is_test_user = user_id in config.TEST_USER_IDS
    except Exception as e:
        logger.error(f"Start command init error: {e}")
        await update.message.reply_text(f"❌ خطأ: {str(e)[:100]}")
        return
    
    if api.bot_paused and not is_user_admin and not is_test_user:
        await update.message.reply_text(
            "🔧 البوت قيد الصيانة...\n\n"
            "سنعود قريباً جداً! ⏳\n"
            "شكراً لصبركم 🙏\n\n"
            "The bot is under maintenance.\n"
            "Coming back soon! 🚀",
            reply_to_message_id=update.message.message_id
        )
        return
    
    db.get_or_create_user(user_id, user.username or "", user.first_name or "")
    user_data = db.get_balance(user_id)
    if not user_data:
        await update.message.reply_text("❌ خطأ في قاعدة البيانات. حاول مرة أخرى.")
        return
    lang = db.get_user_language(user_id)
    
    is_private = update.effective_chat.type == "private"
    is_admin = is_user_admin and is_private
    
    if not is_user_admin and not is_test_user and not db.is_user_verified(user_id):
        await update.message.reply_text(
            "⏳ حسابك قيد المراجعة\n\n"
            "سيتم تفعيل حسابك بعد موافقة المشرف.\n"
            "شكراً لانتظارك! 🙏\n\n"
            "Your account is under review.\n"
            "Please wait for admin approval.",
            reply_to_message_id=update.message.message_id
        )
        if not db.is_approval_notified(user_id):
            db.set_approval_notified(user_id)
            notify_ids = list(config.ADMIN_USER_IDS) + list(getattr(config, 'MODERATOR_IDS', []))
            for notify_id in notify_ids:
                try:
                    await context.bot.send_message(
                        chat_id=notify_id,
                        text=f"👤 طلب تفعيل جديد:\n\n"
                             f"🆔 الايدي: {user_id}\n"
                             f"📝 الاسم: {user.first_name or 'غير متوفر'}\n"
                             f"👤 المستخدم: @{user.username or 'غير متوفر'}",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("✅ قبول", callback_data=f"approve_{user_id}")],
                            [InlineKeyboardButton("❌ رفض", callback_data=f"reject_{user_id}")]
                        ])
                    )
                except:
                    pass
        return
    
    service_type = db.get_user_service_type(user_id) if not is_admin else 'both'
    balance_iqd = user_data.balance_iqd if hasattr(user_data, 'balance_iqd') else 0
    reply_text = get_text('welcome', lang, name=user.first_name, user_id=user_id, balance=balance_iqd)
    is_mod = user_id in getattr(config, 'MODERATOR_IDS', [])
    await update.message.reply_text(
        reply_text, 
        reply_markup=get_main_keyboard(lang, is_admin, service_type, is_mod),
        reply_to_message_id=update.message.message_id
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ Asiacell Fast Recharge Bot ⚡\n\n"
        "🚀 Recharge in seconds!\n"
        "🤖 Fully automatic\n"
        "📱 Asiacell cards only\n"
        "🔒 100% safe and trusted\n"
        "⏰ Available 24/7\n\n"
        "✨ Try it now!"
    )

async def settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    user_id = update.effective_user.id
    lang = db.get_user_language(user_id)
    
    settings_text = "⚙️ إعدادات\n\nاختر من القائمة 👇"
    await update.message.reply_text(
        settings_text,
        reply_markup=get_settings_keyboard(lang)
    )

async def payment_methods_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    user_id = update.effective_user.id
    lang = db.get_user_language(user_id)
    
    payment_text = "💳 طرق الدفع\n\nاختر طريقة الدفع 👇"
    await update.message.reply_text(
        payment_text,
        reply_markup=get_payment_methods_keyboard(lang)
    )

async def settings_back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    user_id = update.effective_user.id
    lang = db.get_user_language(user_id)
    is_admin = user_id in config.ADMIN_USER_IDS
    is_mod = user_id in getattr(config, 'MODERATOR_IDS', [])
    service_type = db.get_user_service_type(user_id) if not is_admin else 'both'
    
    back_text = "🏠 القائمة الرئيسية" if lang == 'ar' else "🏠 Main Menu"
    await update.message.reply_text(
        back_text,
        reply_markup=get_main_keyboard(lang, is_admin, service_type, is_mod)
    )

async def contact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    lang = db.get_user_language(update.effective_user.id)
    keyboard = get_admin_contact_keyboard()
    await update.message.reply_text(
        get_text('support_title', lang),
        reply_markup=keyboard
    )

async def balance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    user_id = update.effective_user.id
    user_balance = db.get_balance(user_id)
    lang = db.get_user_language(user_id)
    
    balance_iqd = user_balance.balance_iqd if hasattr(user_balance, 'balance_iqd') else 0
    reply_text = f"💰 رصيدك الحالي:\n\n💵 {balance_iqd:,} IQD"
    await update.message.reply_text(reply_text)
    await copy_bot_reply_to_group(context, user_id, reply_text)

async def track_orders_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    user_id = update.effective_user.id
    lang = db.get_user_language(user_id)
    
    pending_cards = db.get_user_pending_cards(user_id)
    
    if not pending_cards:
        if lang == 'ar':
            reply_text = "📦 تتبع الطلبات\n\n✅ لا توجد طلبات قيد المعالجة حالياً"
        else:
            reply_text = "📦 Track Orders\n\n✅ No pending orders at the moment"
        await update.message.reply_text(reply_text)
        return
    
    if lang == 'ar':
        reply_text = "📦 تتبع الطلبات\n\n"
    else:
        reply_text = "📦 Track Orders\n\n"
    
    for card in pending_cards:
        status_icon = "⏳" if card.status == "pending" else "🔄"
        status_text = "قيد الانتظار" if card.status == "pending" else "قيد المعالجة"
        if lang == 'en':
            status_text = "Pending" if card.status == "pending" else "Processing"
        
        created_at = card.created_at.strftime('%H:%M') if card.created_at else ""
        pin_masked = f"{card.pin[:4]}****{card.pin[-4:]}" if len(card.pin) > 8 else card.pin[:4] + "****"
        
        reply_text += f"{status_icon} #{card.id}\n"
        reply_text += f"🎴 {pin_masked}\n"
        reply_text += f"📊 {status_text}\n"
        reply_text += f"⏰ {created_at}\n\n"
    
    await update.message.reply_text(reply_text)

async def language_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇮🇶 العربية", callback_data="lang_ar")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")]
    ])
    await update.message.reply_text(
        "🌐 اختر اللغة / Choose Language",
        reply_markup=keyboard
    )

async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    user_id = query.from_user.id
    
    new_lang = query.data.replace("lang_", "")
    db.set_user_language(user_id, new_lang)
    
    is_admin = user_id in config.ADMIN_USER_IDS
    is_mod = user_id in getattr(config, 'MODERATOR_IDS', [])
    service_type = db.get_user_service_type(user_id) if not is_admin else 'both'
    
    await query.edit_message_text(get_text('language_changed', new_lang))
    user_balance = db.get_balance(user_id)
    balance_iqd = user_balance.balance_iqd if hasattr(user_balance, 'balance_iqd') else 0
    await query.message.reply_text(
        get_text('welcome', new_lang, name=query.from_user.first_name, 
                user_id=user_id, balance=balance_iqd),
        reply_markup=get_main_keyboard(new_lang, is_admin, service_type, is_mod)
    )

async def retry_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    user_id = update.effective_user.id
    lang = db.get_user_language(user_id)
    
    failed_cards = db.get_user_failed_cards(user_id)
    
    if not failed_cards:
        await update.message.reply_text(get_text('retry_empty', lang))
        return
    
    buttons = []
    for card in failed_cards[:5]:
        pin_display = f"{card.pin[:4]}****{card.pin[-4:]}" if len(card.pin) >= 8 else card.pin
        retry_count = card.retry_count if card.retry_count else 0
        buttons.append([InlineKeyboardButton(
            f"❌ #{card.id} - {pin_display} ({retry_count}/3)",
            callback_data=f"retry_{card.id}"
        )])
    
    await update.message.reply_text(
        get_text('retry_title', lang),
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def retry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    user_id = query.from_user.id
    lang = db.get_user_language(user_id)
    
    card_id = int(query.data.replace("retry_", ""))
    
    card = db.get_card_by_id(card_id)
    if not card or card.user_id != user_id:
        await query.edit_message_text(get_text('retry_not_found', lang))
        return
    
    if db.retry_card(card_id):
        await query.edit_message_text(get_text('retry_success', lang, id=card_id))
    else:
        await query.edit_message_text(get_text('retry_failed', lang))

def format_date_short(dt_str: str) -> str:
    try:
        dt = datetime.fromisoformat(dt_str.replace(' ', 'T'))
        return dt.strftime("%m/%d")
    except:
        return dt_str[:5] if dt_str else ""

async def records_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    user_id = update.effective_user.id
    lang = db.get_user_language(user_id)
    
    cards = db.get_user_cards(user_id, limit=10)
    
    if not cards:
        await update.message.reply_text(get_text('records_empty', lang))
        return
    
    text = get_text('records_title', lang)
    total_success = 0
    total_amount = 0
    
    for card in cards:
        date_str = format_date_short(card.created_at)
        pin_display = f"{card.pin[:4]}****{card.pin[-4:]}" if len(card.pin) >= 8 else card.pin
        
        if card.status == "verified":
            text += get_text('records_verified', lang, id=card.id, amount=card.amount, date=date_str, pin=pin_display)
            total_success += 1
            total_amount += card.amount
        elif card.status == "failed":
            text += get_text('records_failed', lang, id=card.id, date=date_str, pin=pin_display)
        elif card.status == "processing":
            text += get_text('records_processing', lang, id=card.id, date=date_str, pin=pin_display)
        else:
            text += get_text('records_pending', lang, id=card.id, date=date_str, pin=pin_display)
    
    if total_success > 0:
        text += get_text('records_summary', lang, success=total_success, amount=total_amount)
    else:
        text += get_text('records_no_complete', lang)
    
    await update.message.reply_text(text)

async def xena_history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    user_id = update.effective_user.id
    lang = db.get_user_language(user_id)
    
    orders = db.get_user_xena_orders(user_id, limit=10)
    
    if not orders:
        await update.message.reply_text(get_text('xena_history_empty', lang))
        return
    
    text = get_text('xena_history_title', lang)
    total_coins = 0
    total_amount = 0
    
    for order in orders:
        date_str = format_date_short(order.created_at)
        status_icon = "✅" if order.status == 'completed' else "⏳"
        
        text += f"{status_icon} #{order.id}\n"
        text += f"👤 {order.player_id}\n"
        text += f"💎 {order.coins:,}\n"
        text += f"💰 {order.price_iqd:,}\n"
        text += f"📅 {date_str}\n\n"
        
        if order.status == 'completed':
            total_coins += order.coins
            total_amount += order.price_iqd
    
    text += "───────────────\n"
    if total_coins > 0:
        text += f"💎 {total_coins:,}\n"
        text += f"💰 {total_amount:,}"
    
    await update.message.reply_text(text)

async def support_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    lang = db.get_user_language(update.effective_user.id)
    keyboard = get_admin_contact_keyboard()
    await update.message.reply_text(
        get_text('support_title', lang),
        reply_markup=keyboard
    )

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    lang = db.get_user_language(query.from_user.id)
    action = query.data
    
    if action == "menu_balance":
        user_balance = db.get_balance(query.from_user.id)
        await query.edit_message_text(
            get_text('balance_msg', lang, balance=user_balance.balance_iqd)
        )
    
    elif action == "menu_contact":
        keyboard = get_admin_contact_keyboard()
        await query.edit_message_text(
            get_text('support_title', lang),
            reply_markup=keyboard
        )

async def imo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    user_id = update.effective_user.id
    lang = db.get_user_language(user_id)
    
    # Check service type authorization
    is_admin = user_id in config.ADMIN_USER_IDS
    is_test_user = user_id in config.TEST_USER_IDS
    if not is_admin and not is_test_user:
        service_type = db.get_user_service_type(user_id)
        if service_type not in ('imo', 'both'):
            if lang == 'ar':
                msg = "❌ هذه الخدمة غير متوفرة لحسابك.\n\nتواصل مع الدعم لتفعيل خدمة IMO."
            else:
                msg = "❌ This service is not available for your account.\n\nContact support to enable IMO."
            await update.message.reply_text(msg, reply_to_message_id=update.message.message_id)
            return
    
    if lang == 'ar':
        msg = (
            "📱 IMO - قريباً!\n\n"
            "🚀 نعمل على إضافة خدمة IMO.\n"
            "ستتوفر قريباً جداً!\n\n"
            "ترقبوا... 🔥"
        )
    else:
        msg = (
            "📱 IMO - Coming Soon!\n\n"
            "🚀 We are working on adding IMO service.\n"
            "It will be available very soon!\n\n"
            "Stay tuned... 🔥"
        )
    
    await update.message.reply_text(msg, reply_to_message_id=update.message.message_id)

