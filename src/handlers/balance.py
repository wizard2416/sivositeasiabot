from telegram import Update
from telegram.ext import ContextTypes

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    user_id = update.effective_user.id
    user_balance = db.get_balance(user_id)
    
    cards = db.get_user_cards(user_id, limit=5)
    
    text = f"💰 رصيدك الحالي:\n\n💵 {user_balance.balance_iqd:,} دينار عراقي\n\n"
    
    if cards:
        text += "📋 آخر الكروت:\n"
        for card in cards:
            status_emoji = "✅" if card.status == "verified" else "⏳" if card.status == "pending" else "❌"
            text += f"{status_emoji} {card.amount:,} د - {card.status}\n"
    
    await update.message.reply_text(text)
