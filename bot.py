import logging
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    ConversationHandler,
    filters
)
import config
from src.services import Database, OCRService
from src.handlers.start import (
    start_command, help_command, contact_command, menu_callback,
    balance_handler, records_handler, xena_history_handler, support_handler,
    language_handler, language_callback, retry_handler, retry_callback,
    settings_handler, settings_back_handler, imo_handler, payment_methods_handler,
    track_orders_handler,
    BTN_RECHARGE, BTN_BALANCE, BTN_RECORDS, BTN_XENA, BTN_SUPPORT, BTN_XENA_HISTORY,
    BTN_LANGUAGE, BTN_RETRY, BTN_QI_CARD, BTN_ZAINCASH, BTN_SETTINGS, BTN_PAYMENT_METHODS, BTN_VODAFONE,
    BTN_WITHDRAW, BTN_BINANCE, BTN_TRC20
)
from src.handlers.withdraw import (
    begin_withdraw, withdraw_callback, withdraw_amount_handler, withdraw_wallet_handler, cancel_withdraw,
    WITHDRAW_AMOUNT, WITHDRAW_WALLET
)
from src.handlers.recharge import (
    begin_recharge, receive_card_number, receive_card_photo, cancel_recharge,
    ASK_CARD_NUMBER
)
from src.handlers.payment import (
    begin_qi_card, begin_zaincash, begin_vodafone, receive_payment_proof,
    cancel_payment, payment_callback, receive_diff_amount,
    ASK_PAYMENT_PROOF
)
from src.handlers.xena import (
    begin_xena, receive_player_id, receive_coins, xena_callback, cancel_xena,
    ASK_PLAYER_ID, ASK_COINS, CONFIRM_PURCHASE
)
from src.handlers.admin import (
    admin_command, receive_user_id, receive_amount, stats_command,
    broadcast_command, receive_broadcast_message, cancel_admin,
    admin_callback, gallery_callback, user_callback, export_callback,
    chat_search_handler, receive_ai_image_prompt,
    ASK_USER_ID, ASK_AMOUNT, ASK_MESSAGE, ASK_AI_IMAGE_PROMPT
)
from src.handlers.forwarding import forward_to_admin
from src.handlers.group_admin import (
    group_chats_command, group_viewchat_command, group_search_command, 
    group_callback, group_searchmsg_command, pause_command, resume_command, status_command
)
from src.handlers.moderator import (
    moderator_menu, mod_pending_users, mod_approve_user, mod_reject_user,
    mod_generate_image_start, mod_handle_text_for_image, mod_handle_voice_for_image,
    mod_cancel, mod_exit, is_moderator, MODERATOR_WAITING_IMAGE_PROMPT,
    mod_broadcast_start, mod_broadcast_text, mod_broadcast_photo, 
    mod_broadcast_video, mod_broadcast_voice, MODERATOR_WAITING_BROADCAST,
    mod_delete_broadcast
)
from src.services.backup import setup_backup_scheduler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

withdraw_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("withdraw", begin_withdraw),
        MessageHandler(filters.Regex("^💵.*سحب"), begin_withdraw)
    ],
    states={
        WITHDRAW_AMOUNT: [
            CallbackQueryHandler(withdraw_callback, pattern="^withdraw_"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount_handler)
        ],
        WITHDRAW_WALLET: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_wallet_handler)
        ]
    },
    fallbacks=[
        CommandHandler("start", start_command),
        CommandHandler("cancel", cancel_withdraw),
        MessageHandler(filters.Regex("^⬅️"), cancel_withdraw)
    ],
    name="withdraw",
    persistent=False
)

recharge_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("recharge", begin_recharge),
        MessageHandler(filters.Regex("^💳.*إضافة رصيد|^📱.*آسيا"), begin_recharge)
    ],
    states={
        ASK_CARD_NUMBER: [
            MessageHandler(filters.PHOTO, receive_card_photo),
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_card_number)
        ]
    },
    fallbacks=[
        CommandHandler("start", start_command),
        MessageHandler(filters.Regex("^(/start|start|Start|START)$"), start_command),
        CommandHandler("cancel", cancel_recharge),
        MessageHandler(filters.Regex("^⬅️"), cancel_recharge)
    ],
    name="recharge",
    persistent=False
)

xena_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("xena", begin_xena),
        MessageHandler(filters.Regex("^🪙"), begin_xena)
    ],
    states={
        ASK_PLAYER_ID: [
            MessageHandler(filters.Regex("^🪙"), begin_xena),
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_player_id)
        ],
        ASK_COINS: [
            MessageHandler(filters.Regex("^🪙"), begin_xena),
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_coins)
        ],
        CONFIRM_PURCHASE: [CallbackQueryHandler(xena_callback, pattern="^xena_")]
    },
    fallbacks=[
        CommandHandler("start", start_command),
        MessageHandler(filters.Regex("^(/start|start|Start|START)$"), start_command),
        CommandHandler("cancel", cancel_xena),
        MessageHandler(filters.Regex("^⬅️"), cancel_xena)
    ],
    name="xena",
    persistent=False
)

admin_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("admin", admin_command),
        MessageHandler(filters.Regex("^🎛️"), admin_command),
        CallbackQueryHandler(admin_callback, pattern="^admin_")
    ],
    states={
        ASK_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user_id)],
        ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_amount)],
        ASK_AI_IMAGE_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ai_image_prompt)]
    },
    fallbacks=[
        CommandHandler("start", start_command),
        MessageHandler(filters.Regex("^(/start|start|Start|START)$"), start_command),
        CommandHandler("cancel", cancel_admin),
        CallbackQueryHandler(admin_callback, pattern="^admin_")
    ],
    name="admin",
    persistent=False
)

broadcast_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("broadcast", broadcast_command)],
    states={
        ASK_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_broadcast_message)]
    },
    fallbacks=[
        CommandHandler("start", start_command),
        MessageHandler(filters.Regex("^(/start|start|Start|START)$"), start_command),
        CommandHandler("cancel", cancel_admin)
    ],
    name="broadcast",
    persistent=False
)

qi_card_conv_handler = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex("^💳 QI"), begin_qi_card)
    ],
    states={
        ASK_PAYMENT_PROOF: [MessageHandler(filters.PHOTO, receive_payment_proof)]
    },
    fallbacks=[
        CommandHandler("start", start_command),
        MessageHandler(filters.Regex("^(/start|start|Start|START)$"), start_command),
        CommandHandler("cancel", cancel_payment),
        MessageHandler(filters.Regex("^⬅️"), cancel_payment)
    ],
    name="qi_card",
    persistent=False
)

zaincash_conv_handler = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex("^💜 Zain"), begin_zaincash)
    ],
    states={
        ASK_PAYMENT_PROOF: [MessageHandler(filters.PHOTO, receive_payment_proof)]
    },
    fallbacks=[
        CommandHandler("start", start_command),
        MessageHandler(filters.Regex("^(/start|start|Start|START)$"), start_command),
        CommandHandler("cancel", cancel_payment),
        MessageHandler(filters.Regex("^⬅️"), cancel_payment)
    ],
    name="zaincash",
    persistent=False
)

vodafone_conv_handler = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex("^🔴 Vodafone"), begin_vodafone)
    ],
    states={
        ASK_PAYMENT_PROOF: [MessageHandler(filters.PHOTO, receive_payment_proof)]
    },
    fallbacks=[
        CommandHandler("start", start_command),
        MessageHandler(filters.Regex("^(/start|start|Start|START)$"), start_command),
        CommandHandler("cancel", cancel_payment),
        MessageHandler(filters.Regex("^⬅️"), cancel_payment)
    ],
    name="vodafone",
    persistent=False
)

moderator_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(mod_generate_image_start, pattern="^mod_generate_image$")
    ],
    states={
        MODERATOR_WAITING_IMAGE_PROMPT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, mod_handle_text_for_image),
            MessageHandler(filters.VOICE, mod_handle_voice_for_image),
            CallbackQueryHandler(mod_cancel, pattern="^mod_menu$")
        ]
    },
    fallbacks=[
        CommandHandler("start", start_command),
        CallbackQueryHandler(mod_cancel, pattern="^mod_menu$")
    ],
    name="moderator_image",
    persistent=False
)

moderator_broadcast_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(mod_broadcast_start, pattern="^mod_broadcast_start$")
    ],
    states={
        MODERATOR_WAITING_BROADCAST: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, mod_broadcast_text),
            MessageHandler(filters.PHOTO, mod_broadcast_photo),
            MessageHandler(filters.VIDEO, mod_broadcast_video),
            MessageHandler(filters.VOICE, mod_broadcast_voice),
            CallbackQueryHandler(mod_cancel, pattern="^mod_menu$")
        ]
    },
    fallbacks=[
        CommandHandler("start", start_command),
        CallbackQueryHandler(mod_cancel, pattern="^mod_menu$")
    ],
    name="moderator_broadcast",
    persistent=False
)

def create_bot(db: Database, ocr: OCRService) -> Application:
    if not config.TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set")
    
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    
    application.bot_data["db"] = db
    application.bot_data["ocr"] = ocr
    
    application.add_handler(MessageHandler(filters.ALL, forward_to_admin), group=-1)
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("contact", contact_command))
    application.add_handler(CommandHandler("balance", balance_handler))
    application.add_handler(CommandHandler("stats", stats_command))
    
    application.add_handler(recharge_conv_handler)
    application.add_handler(xena_conv_handler)
    application.add_handler(withdraw_conv_handler)
    application.add_handler(qi_card_conv_handler)
    application.add_handler(zaincash_conv_handler)
    application.add_handler(vodafone_conv_handler)
    application.add_handler(admin_conv_handler)
    application.add_handler(broadcast_conv_handler)
    application.add_handler(moderator_conv_handler)
    application.add_handler(moderator_broadcast_conv_handler)
    
    application.add_handler(MessageHandler(filters.Regex("^💰"), balance_handler))
    application.add_handler(MessageHandler(filters.Regex("^📋 سجل$|^📋 History$"), xena_history_handler))
    application.add_handler(MessageHandler(filters.Regex("^📋 السجلات|^📋 سجل|^📋 Records"), records_handler))
    application.add_handler(MessageHandler(filters.Regex("^📞"), support_handler))
    application.add_handler(MessageHandler(filters.Regex("^🌐"), language_handler))
    application.add_handler(MessageHandler(filters.Regex("^🔄"), retry_handler))
    application.add_handler(MessageHandler(filters.Regex("^⚙️"), settings_handler))
    application.add_handler(MessageHandler(filters.Regex("^💳 طرق الدفع"), payment_methods_handler))
    application.add_handler(MessageHandler(filters.Regex("^📦"), track_orders_handler))
    application.add_handler(MessageHandler(filters.Regex("^⬅️"), settings_back_handler))
    application.add_handler(MessageHandler(filters.Regex("^📱 (IMO|ايمو)"), imo_handler))
    
    application.add_handler(CallbackQueryHandler(language_callback, pattern="^lang_"))
    application.add_handler(CallbackQueryHandler(retry_callback, pattern="^retry_"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^approve_"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^reject_"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^chat"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^noop"))
    application.add_handler(CallbackQueryHandler(gallery_callback, pattern="^gallery_"))
    application.add_handler(CallbackQueryHandler(export_callback, pattern="^export_"))
    application.add_handler(CallbackQueryHandler(user_callback, pattern="^user_"))
    application.add_handler(CallbackQueryHandler(user_callback, pattern="^bal_"))
    application.add_handler(CallbackQueryHandler(user_callback, pattern="^toggle_"))
    application.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    application.add_handler(CallbackQueryHandler(payment_callback, pattern="^payment_"))
    
    application.add_handler(CallbackQueryHandler(moderator_menu, pattern="^mod_menu$"))
    application.add_handler(CallbackQueryHandler(mod_pending_users, pattern="^mod_pending_users$"))
    application.add_handler(CallbackQueryHandler(mod_approve_user, pattern="^mod_approve_"))
    application.add_handler(CallbackQueryHandler(mod_reject_user, pattern="^mod_reject_"))
    application.add_handler(CallbackQueryHandler(mod_exit, pattern="^mod_exit$"))
    application.add_handler(CallbackQueryHandler(mod_delete_broadcast, pattern="^mod_delete_broadcast$"))
    
    application.add_handler(CommandHandler("chats", group_chats_command))
    application.add_handler(CommandHandler("viewchat", group_viewchat_command))
    application.add_handler(CommandHandler("search", group_search_command))
    application.add_handler(CommandHandler("searchmsg", group_searchmsg_command))
    application.add_handler(CommandHandler("pause", pause_command))
    application.add_handler(CommandHandler("resume", resume_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CallbackQueryHandler(group_callback, pattern="^g"))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_search_handler), group=2)
    
    return application

async def error_handler(update, context):
    """Log errors caused by updates."""
    error_msg = str(context.error)[:200] if context.error else "Unknown error"
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(f"❌ خطأ: {error_msg}")
        except:
            pass

async def run_bot(db: Database, ocr: OCRService):
    application = create_bot(db, ocr)
    application.add_error_handler(error_handler)
    logger.info("Starting Telegram bot...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    
    # Backup scheduler disabled for now
    # setup_backup_scheduler(application.bot, db, config.ADMIN_USER_IDS)
    
    return application
