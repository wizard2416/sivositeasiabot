from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from src.services.lang import get_btn
from src.services import xparty
import api
import config
import os
import logging

logger = logging.getLogger(__name__)

WEBHOOK_BASE_URL = os.environ.get("REPLIT_DOMAINS", "").split(",")[0] if os.environ.get("REPLIT_DOMAINS") else ""

# Xena Live conversion rate: 10,000 IQD = 55,000 coins
XENA_RATE_IQD = 10000
XENA_RATE_COINS = 55000

def calculate_price_iqd(coins: int) -> int:
    """Calculate price in IQD. 10,000 IQD = 55,000 coins"""
    return int(coins * XENA_RATE_IQD / XENA_RATE_COINS)

ASK_PLAYER_ID = 1
ASK_COINS = 2
CONFIRM_PURCHASE = 3

MIN_COINS = 3000
MAX_COINS = 50000000

def get_confirm_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تأكيد", callback_data="xena_confirm")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="xena_cancel")]
    ])

def get_back_keyboard(lang='ar'):
    return ReplyKeyboardMarkup([[get_btn('btn_back', lang)]], resize_keyboard=True)

def get_main_keyboard(lang='ar', is_admin=False, service_type='xena'):
    from src.handlers.start import get_main_keyboard as start_get_main_keyboard
    return start_get_main_keyboard(lang, is_admin=is_admin, service_type=service_type)

XENA_IMAGE_PATH = "data/images/xena_live.png"

async def begin_xena(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db = context.bot_data["db"]
    user_id = update.effective_user.id
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
    
    # Check service type authorization
    if not is_admin and not is_test_user:
        service_type = db.get_user_service_type(user_id)
        if service_type not in ('xena', 'both'):
            lang = db.get_user_language(user_id)
            if lang == 'ar':
                msg = "❌ هذه الخدمة غير متوفرة لحسابك.\n\nتواصل مع الدعم لتفعيل خدمة Xena Live."
            else:
                msg = "❌ This service is not available for your account.\n\nContact support to enable Xena Live."
            await update.message.reply_text(msg, reply_to_message_id=update.message.message_id)
            return ConversationHandler.END
    
    user_balance = db.get_balance(user_id)
    lang = db.get_user_language(user_id)
    
    balance_iqd = user_balance.balance_iqd if hasattr(user_balance, 'balance_iqd') else 0
    context.user_data['xena_balance'] = balance_iqd
    context.user_data['xena_lang'] = lang
    
    import os
    if os.path.exists(XENA_IMAGE_PATH):
        msg = await update.message.reply_photo(
            photo=open(XENA_IMAGE_PATH, 'rb'),
            caption=f"🎮 Xena Live\n"
                    f"💰 رصيدك: {balance_iqd:,} IQD\n\n"
                    f"👤 أدخل معرف اللاعب:",
            reply_markup=get_back_keyboard(lang),
            reply_to_message_id=update.message.message_id
        )
    else:
        msg = await update.message.reply_text(
            f"🎮 Xena Live\n"
            f"💰 رصيدك: {balance_iqd:,} IQD\n\n"
            f"👤 أدخل معرف اللاعب:",
            reply_markup=get_back_keyboard(lang),
            reply_to_message_id=update.message.message_id
        )
    context.user_data['xena_last_msg_id'] = msg.message_id
    
    return ASK_PLAYER_ID

MENU_BUTTONS = ["💰 رصيدي", "📋 السجلات", "🎮 Xena Live", "🔋 Asiacell", "📞 الدعم", "📋 سجل", "⬅️ رجوع", "⬅️ Back"]

async def receive_player_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    player_id = update.message.text.strip()
    
    if player_id.startswith("⬅️") or "رجوع" in player_id or "Back" in player_id:
        return await cancel_xena(update, context)
    
    if player_id in MENU_BUTTONS:
        await update.message.reply_text(
            "👤 أنت في وضع شراء Xena!\n\n"
            "ادخل ايدي اللاعب أو اضغط ⬅️ رجوع للخروج.",
            reply_to_message_id=update.message.message_id
        )
        return ASK_PLAYER_ID
    
    if not player_id or len(player_id) < 3:
        await update.message.reply_text(
            "❌ ايدي غير صالح\n"
            "👤 ادخل ايدي اللاعب (أرقام فقط):",
            reply_to_message_id=update.message.message_id
        )
        return ASK_PLAYER_ID
    
    if not player_id.isdigit():
        await update.message.reply_text(
            "❌ ايدي اللاعب يجب أن يكون أرقام فقط!\n"
            "👤 ادخل ايدي اللاعب:",
            reply_to_message_id=update.message.message_id
        )
        return ASK_PLAYER_ID
    
    context.user_data['xena_player_id'] = player_id
    lang = context.user_data.get('xena_lang', 'ar')
    
    # Fetch nickname via Xparty API
    loading_msg = await update.message.reply_text(
        "⏳ جاري التحقق من الايدي...",
        reply_to_message_id=update.message.message_id
    )
    
    nickname_result = xparty.get_nickname_by_id(player_id)
    
    if nickname_result.get("success"):
        nickname = nickname_result.get("nickname", "")
        country = nickname_result.get("country", "")
        avatar = nickname_result.get("avatar", "")
        avatar_url = xparty.get_avatar_url(avatar)
        
        context.user_data['xena_player_nickname'] = nickname
        context.user_data['xena_player_country'] = country
        context.user_data['xena_player_avatar'] = avatar
        
        caption = (
            f"✅ تم التحقق!\n\n"
            f"👤 ايدي اللاعب: {player_id}\n"
            f"🏷️ الاسم: {nickname}\n"
            f"🌍 الدولة: {country}\n\n"
            f"💎 ادخل عدد العملات:\n"
            f"(الحد الأدنى: {MIN_COINS:,} عملة)"
        )
        
        if avatar_url:
            try:
                await loading_msg.delete()
                await update.message.reply_photo(
                    photo=avatar_url,
                    caption=caption,
                    reply_markup=get_back_keyboard(context.user_data.get('xena_lang', 'ar'))
                )
            except Exception:
                await loading_msg.edit_text(caption)
        else:
            await loading_msg.edit_text(caption)
    else:
        error = nickname_result.get("error", "Unknown error")
        if "expired" in error.lower():
            await loading_msg.edit_text(
                "❌ خطأ: الجلسة منتهية الصلاحية\n\n"
                "يرجى التواصل مع الدعم."
            )
            return ConversationHandler.END
        
        context.user_data['xena_player_nickname'] = ""
        context.user_data['xena_player_country'] = ""
        context.user_data['xena_player_avatar'] = ""
        await loading_msg.edit_text(
            f"⚠️ تعذر التحقق من الايدي\n\n"
            f"👤 ايدي اللاعب: {player_id}\n\n"
            f"💎 ادخل عدد العملات:\n"
            f"(الحد الأدنى: {MIN_COINS:,} عملة)"
        )
    
    context.user_data['xena_last_msg_id'] = loading_msg.message_id
    return ASK_COINS

async def receive_coins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    db = context.bot_data["db"]
    user_id = update.effective_user.id
    
    if text.startswith("⬅️") or "رجوع" in text or "Back" in text:
        return await cancel_xena(update, context)
    
    if text in MENU_BUTTONS:
        await update.message.reply_text(
            "💎 أنت في وضع شراء Xena!\n\n"
            "ادخل عدد العملات أو اضغط ⬅️ رجوع للخروج.",
            reply_to_message_id=update.message.message_id
        )
        return ASK_COINS
    
    text = text.replace(",", "")
    
    if not text.isdigit():
        await update.message.reply_text(
            "❌ ادخل رقم صحيح\n"
            "💎 عدد العملات:",
            reply_to_message_id=update.message.message_id
        )
        return ASK_COINS
    
    coins = int(text)
    
    if coins < MIN_COINS:
        await update.message.reply_text(
            f"❌ الحد الأدنى {MIN_COINS:,} عملة\n"
            "💎 عدد العملات:",
            reply_to_message_id=update.message.message_id
        )
        return ASK_COINS
    
    if coins > MAX_COINS:
        await update.message.reply_text(
            f"❌ الحد الأقصى {MAX_COINS:,} عملة\n"
            "💎 عدد العملات:",
            reply_to_message_id=update.message.message_id
        )
        return ASK_COINS
    
    price_iqd = calculate_price_iqd(coins)
    
    if price_iqd is None or price_iqd <= 0:
        lang = db.get_user_language(user_id)
        service_type = db.get_user_service_type(user_id)
        is_admin = user_id in config.ADMIN_USER_IDS
        await update.message.reply_text(
            "❌ تعذر جلب الأسعار حالياً\n"
            "يرجى المحاولة لاحقاً",
            reply_markup=get_main_keyboard(lang, is_admin, service_type),
            reply_to_message_id=update.message.message_id
        )
        return ConversationHandler.END
    
    context.user_data['xena_coins'] = coins
    context.user_data['xena_price'] = price_iqd
    
    player_id = context.user_data.get('xena_player_id', '')
    user_balance = context.user_data.get('xena_balance', 0)
    
    if user_balance < price_iqd:
        lang = db.get_user_language(user_id)
        service_type = db.get_user_service_type(user_id)
        is_admin = user_id in config.ADMIN_USER_IDS
        await update.message.reply_text(
            f"❌ رصيدك غير كافي!\n\n"
            f"💰 رصيدك: {user_balance:,} IQD\n"
            f"💎 السعر: {price_iqd:,} IQD",
            reply_markup=get_main_keyboard(lang, is_admin, service_type),
            reply_to_message_id=update.message.message_id
        )
        return ConversationHandler.END
    
    balance_after = user_balance - price_iqd
    await update.message.reply_text(
        f"📋 ملخص الطلب:\n\n"
        f"👤 الايدي: {player_id}\n"
        f"💎 العملات: {coins:,}\n"
        f"💰 السعر: {price_iqd:,} IQD\n\n"
        f"💰 رصيدك قبل: {user_balance:,} IQD\n"
        f"💰 رصيدك بعد: {balance_after:,} IQD\n\n"
        f"تأكيد الشراء؟",
        reply_markup=get_confirm_keyboard(),
        reply_to_message_id=update.message.message_id
    )
    return CONFIRM_PURCHASE

async def xena_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    action = query.data
    
    if action == "xena_cancel":
        await query.edit_message_text("❌ تم الإلغاء")
        return ConversationHandler.END
    
    if action == "xena_confirm":
        db = context.bot_data["db"]
        user_id = query.from_user.id
        
        try:
            coins = context.user_data.get('xena_coins', 0)
            price_iqd = context.user_data.get('xena_price', 0)
            player_id = str(context.user_data.get('xena_player_id', '')).replace('\x00', '')
            player_nickname = (context.user_data.get('xena_player_nickname', '') or '').replace('\x00', '')
            player_country = (context.user_data.get('xena_player_country', '') or '').replace('\x00', '')
            player_avatar = (context.user_data.get('xena_player_avatar', '') or '').replace('\x00', '')
            
            # Re-fetch player info if missing (handles bot restart case)
            if player_id and not player_nickname:
                nickname_result = xparty.get_nickname_by_id(player_id)
                if nickname_result.get("success"):
                    player_nickname = (nickname_result.get("nickname", "") or "").replace('\x00', '')
                    player_country = (nickname_result.get("country", "") or "").replace('\x00', '')
                    player_avatar = (nickname_result.get("avatar", "") or "").replace('\x00', '')
            
            user_bal = db.get_balance(user_id)
            balance_before = user_bal.balance_iqd if hasattr(user_bal, 'balance_iqd') else 0
            if balance_before < price_iqd:
                await query.edit_message_text("❌ رصيدك غير كافي!")
                return ConversationHandler.END
            
            # Deduct IQD balance
            if not db.deduct_balance(user_id, price_iqd, transaction_type='xena_purchase', reference_id='pending'):
                await query.edit_message_text("❌ رصيدك غير كافي!")
                return ConversationHandler.END
            
            user_bal_after = db.get_balance(user_id)
            balance_after = user_bal_after.balance_iqd if hasattr(user_bal_after, 'balance_iqd') else 0
            
            # Generate unique order number for Xparty
            import uuid
            xparty_order_id = f"xena_{user_id}_{uuid.uuid4().hex[:8]}"
            
            # Create order in database
            order_id = db.add_xena_order(user_id, player_id, coins, price_iqd, "")
            
            # Update order with xparty_order_id, nickname, country and avatar
            db.execute("""
                UPDATE xena_orders 
                SET xparty_order_id = %s, player_nickname = %s, player_country = %s, player_avatar = %s
                WHERE id = %s
            """, (xparty_order_id, player_nickname, player_country, player_avatar, order_id))
            db.commit()
            
            # Submit to Xparty API - get domain at runtime
            webhook_base = os.environ.get("WEBHOOK_BASE_URL", "")
            if not webhook_base:
                replit_domains = os.environ.get("REPLIT_DOMAINS", "")
                webhook_base = replit_domains.split(",")[0] if replit_domains else ""
            webhook_url = f"https://{webhook_base}/api/xparty/webhook" if webhook_base else ""
            
            if xparty.is_configured() and webhook_url:
                logger.info(f"Submitting order #{order_id} to Xparty: player={player_id}, coins={coins}, webhook={webhook_url}")
                recharge_result = xparty.recharge_by_id(
                    player_id=player_id,
                    amount=coins,
                    order_number=xparty_order_id,
                    webhook_url=webhook_url
                )
                
                if recharge_result.get("success"):
                    db.update_xena_order_status(order_id, "processing")
                    logger.info(f"Order #{order_id} submitted successfully to Xparty")
                    status_msg = "⏳ جاري إرسال العملات..."
                else:
                    error = recharge_result.get("error", "Unknown error")
                    logger.error(f"Xparty recharge failed for order #{order_id}: {error}")
                    status_msg = "⏳ تم استلام طلبك، سيتم معالجته قريباً"
            else:
                logger.warning(f"Xparty not configured or webhook missing. configured={xparty.is_configured()}, webhook={webhook_url}")
                status_msg = "⏳ سيتم معالجة طلبك قريباً"
            
            nickname_line = f"🏷️ الاسم: {player_nickname}\n" if player_nickname else ""
            country_line = f"🌍 الدولة: {player_country}\n" if player_country else ""
            
            caption = (
                f"✅ تم استلام طلبك!\n\n"
                f"🎫 رقم الطلب: #{order_id}\n"
                f"👤 ايدي اللاعب: {player_id}\n"
                f"{nickname_line}"
                f"{country_line}"
                f"💎 العملات: {coins:,}\n"
                f"💰 السعر: {price_iqd:,} IQD\n\n"
                f"💰 رصيدك قبل: {balance_before:,} IQD\n"
                f"💰 رصيدك بعد: {balance_after:,} IQD\n\n"
                f"{status_msg}\n"
                f"شكراً لاستخدامك!"
            )
            
            avatar_url = xparty.get_avatar_url(player_avatar)
            if avatar_url:
                try:
                    await query.message.delete()
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=avatar_url,
                        caption=caption
                    )
                except Exception:
                    await query.edit_message_text(caption)
            else:
                await query.edit_message_text(caption)
            
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"Xena confirm error for user {user_id}: {e}", exc_info=True)
            try:
                db.rollback()
            except Exception:
                pass
            await query.edit_message_text(
                "❌ حدث خطأ أثناء معالجة طلبك.\n"
                "يرجى المحاولة مرة أخرى."
            )
            return ConversationHandler.END
    
    return ASK_COINS

async def cancel_xena(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db = context.bot_data["db"]
    user_id = update.effective_user.id
    lang = db.get_user_language(user_id)
    service_type = db.get_user_service_type(user_id)
    is_admin = user_id in config.ADMIN_USER_IDS
    await update.message.reply_text(
        "تم الإلغاء. اختر من القائمة 👇",
        reply_markup=get_main_keyboard(lang, is_admin, service_type),
        reply_to_message_id=update.message.message_id
    )
    return ConversationHandler.END
