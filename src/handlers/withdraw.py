from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import config
config.ADMIN_IDS = config.ADMIN_USER_IDS
from src.services.db import Database
from src.services.lang import get_text, get_btn

db = Database()

WITHDRAW_AMOUNT, WITHDRAW_WALLET = range(2)

def get_main_keyboard(lang='ar', is_admin=False, service_type='xena'):
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

def get_withdraw_settings():
    try:
        cursor = db.execute("SELECT key, value FROM settings WHERE key IN ('usd_rate_iqd', 'usd_rate_usd', 'usd_minimum', 'usd_fee_percent')")
        settings = {}
        for row in cursor.fetchall():
            settings[row['key']] = row['value']
        return {
            'rate_iqd': int(settings.get('usd_rate_iqd', 100000)),
            'rate_usd': float(settings.get('usd_rate_usd', 55.50)),
            'minimum': int(settings.get('usd_minimum', 50)),
            'fee_percent': float(settings.get('usd_fee_percent', 0))
        }
    except:
        return {'rate_iqd': 100000, 'rate_usd': 55.50, 'minimum': 50, 'fee_percent': 0}

def iqd_to_usd(iqd_amount, settings):
    return (iqd_amount / settings['rate_iqd']) * settings['rate_usd']

def usd_to_iqd(usd_amount, settings):
    return int((usd_amount / settings['rate_usd']) * settings['rate_iqd'])

async def begin_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user = db.get_or_create_user(user_id)
    lang = user.language or 'ar'
    settings = get_withdraw_settings()
    
    cursor = db.execute("SELECT balance_usd FROM users WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    balance_usd = float(row['balance_usd'] or 0) if row else 0
    balance = int(balance_usd / settings['rate_usd'] * settings['rate_iqd'])
    usd_equivalent = balance_usd
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔶 Binance ID", callback_data="withdraw_binance")],
        [InlineKeyboardButton("💎 USDT TRC20", callback_data="withdraw_trc20")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="withdraw_cancel")]
    ])
    
    fee_percent = settings['fee_percent']
    fee_text = f"\n💸 رسوم السحب: {fee_percent}%" if fee_percent > 0 else ""
    
    msg = get_text('withdraw_menu', lang).format(
        balance=balance,
        usd=usd_equivalent,
        rate_iqd=settings['rate_iqd'],
        rate_usd=settings['rate_usd'],
        minimum=settings['minimum']
    ) + fee_text
    
    await update.message.reply_text(msg, reply_markup=keyboard)
    return WITHDRAW_AMOUNT

async def withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user = db.get_or_create_user(user_id)
    lang = user.language or 'ar'
    balance = user.balance_iqd or 0
    settings = get_withdraw_settings()
    
    action = query.data
    
    if action == "withdraw_cancel":
        is_admin = user_id in config.ADMIN_IDS
        await query.message.edit_text("❌ تم إلغاء عملية السحب")
        return ConversationHandler.END
    
    if action in ["withdraw_binance", "withdraw_trc20"]:
        withdraw_type = "Binance ID" if action == "withdraw_binance" else "USDT TRC20"
        context.user_data['withdraw_type'] = withdraw_type
        
        cursor = db.execute("SELECT balance_usd FROM users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        balance_usd = float(row['balance_usd'] or 0) if row else 0
        balance = int(balance_usd / settings['rate_usd'] * settings['rate_iqd'])
        usd_equivalent = balance_usd
        
        msg = get_text('withdraw_enter_amount', lang).format(
            balance=balance,
            usd=usd_equivalent,
            minimum=settings['minimum']
        )
        
        await query.message.edit_text(msg)
        return WITHDRAW_AMOUNT

async def withdraw_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user = db.get_or_create_user(user_id)
    lang = user.language or 'ar'
    settings = get_withdraw_settings()
    is_admin = user_id in config.ADMIN_IDS
    
    cursor = db.execute("SELECT balance_usd FROM users WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    balance_usd = float(row['balance_usd'] or 0) if row else 0
    
    try:
        amount_usd = float(update.message.text.replace('$', '').strip())
    except:
        await update.message.reply_text("❌ أدخل رقم صحيح")
        return WITHDRAW_AMOUNT
    
    if amount_usd < settings['minimum']:
        msg = get_text('withdraw_minimum', lang).format(minimum=settings['minimum'])
        await update.message.reply_text(msg)
        return WITHDRAW_AMOUNT
    
    if amount_usd > balance_usd:
        balance_iqd_equiv = int(balance_usd / settings['rate_usd'] * settings['rate_iqd'])
        required_iqd = usd_to_iqd(amount_usd, settings)
        msg = get_text('withdraw_insufficient', lang).format(
            balance=balance_iqd_equiv,
            amount=amount_usd,
            iqd=required_iqd
        )
        await update.message.reply_text(msg, reply_markup=get_main_keyboard(lang, is_admin, user.service_type))
        return ConversationHandler.END
    
    context.user_data['withdraw_amount_usd'] = amount_usd
    
    withdraw_type = context.user_data.get('withdraw_type', 'USDT TRC20')
    msg = get_text('withdraw_enter_wallet', lang).format(type=withdraw_type, amount=amount_usd)
    
    await update.message.reply_text(msg)
    return WITHDRAW_WALLET

async def withdraw_wallet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user = db.get_or_create_user(user_id)
    lang = user.language or 'ar'
    is_admin = user_id in config.ADMIN_IDS
    settings = get_withdraw_settings()
    
    wallet = update.message.text.strip()
    amount_usd = context.user_data.get('withdraw_amount_usd', 0)
    withdraw_type = context.user_data.get('withdraw_type', 'USDT TRC20')
    
    fee_percent = settings['fee_percent']
    fee_amount = amount_usd * (fee_percent / 100)
    final_amount_usd = amount_usd - fee_amount
    amount_iqd_equiv = int(amount_usd / settings['rate_usd'] * settings['rate_iqd'])
    
    db.execute(
        "UPDATE users SET balance_usd = balance_usd - %s WHERE user_id = %s",
        (amount_usd, user_id)
    )
    db.commit()
    
    cursor = db.execute(
        """INSERT INTO withdrawals (user_id, amount_iqd, amount_usd, withdrawal_type, wallet_address, status)
           VALUES (%s, %s, %s, %s, %s, 'pending') RETURNING id""",
        (user_id, amount_iqd_equiv, final_amount_usd, withdraw_type, wallet)
    )
    withdrawal_id = cursor.fetchone()['id']
    db.commit()
    
    fee_text = f"\n💸 الرسوم: ${fee_amount:.2f} ({fee_percent}%)" if fee_percent > 0 else ""
    msg = get_text('withdraw_success', lang).format(
        amount=final_amount_usd,
        type=withdraw_type,
        wallet=wallet
    ) + fee_text
    
    await update.message.reply_text(msg, reply_markup=get_main_keyboard(lang, is_admin, user.service_type))
    
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user = db.get_or_create_user(user_id)
    lang = user.language or 'ar'
    is_admin = user_id in config.ADMIN_IDS
    
    context.user_data.clear()
    await update.message.reply_text("❌ تم إلغاء عملية السحب", reply_markup=get_main_keyboard(lang, is_admin, user.service_type))
    return ConversationHandler.END
