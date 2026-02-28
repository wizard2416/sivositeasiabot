import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import config
from datetime import datetime, timedelta
import api

logger = logging.getLogger(__name__)

MONITOR_GROUP_ID = -1003505287913

sent_message_ids = {}

def is_monitor_group(chat_id: int) -> bool:
    return chat_id == MONITOR_GROUP_ID

def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_USER_IDS

async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    api.card_processing_paused = True
    await update.message.reply_text(
        "⏸️ Card processing PAUSED\n\n"
        "The Android app will not receive any new cards.\n"
        "Use /resume to start receiving cards again."
    )

async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    api.card_processing_paused = False
    await update.message.reply_text(
        "▶️ Card processing RESUMED\n\n"
        "The Android app will now receive pending cards."
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    status = "⏸️ PAUSED" if api.card_processing_paused else "▶️ RUNNING"
    
    db = context.bot_data["db"]
    pending = db.get_pending_cards_count() if hasattr(db, 'get_pending_cards_count') else "?"
    phones = db.get_online_phones()
    
    text = f"📊 System Status\n\n"
    text += f"Card Processing: {status}\n"
    text += f"Online Phones: {len(phones)}\n"
    text += f"\nUse /pause or /resume to control"
    
    await update.message.reply_text(text)

def format_time(dt_str: str) -> str:
    try:
        dt = datetime.fromisoformat(dt_str.replace(' ', 'T'))
        return dt.strftime("%Y-%m-%d %H:%M")
    except:
        return dt_str[:16] if dt_str else ""

async def group_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_monitor_group(update.effective_chat.id):
        return
    
    if not is_admin(update.effective_user.id):
        return
    
    db = context.bot_data["db"]
    data = db.get_users_with_messages(page=1, per_page=8)
    
    users = data.get('users', [])
    total = data.get('total', 0)
    total_pages = data.get('total_pages', 1)
    
    if not users:
        await update.message.reply_text("💬 No user conversations yet.")
        return
    
    text = f"💬 User Conversations ({total} users)\n\nClick to view full chat:"
    
    buttons = []
    for u in users:
        name = u.get('first_name') or u.get('username') or str(u.get('user_id', ''))[:12]
        user_id = u.get('user_id')
        msg_count = u.get('msg_count', 0)
        buttons.append([InlineKeyboardButton(
            f"👤 {name} ({msg_count})",
            callback_data=f"gopen_{user_id}"
        )])
    
    nav_row = []
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(f"1/{total_pages}", callback_data="gnoop"))
        nav_row.append(InlineKeyboardButton("▶️", callback_data="glist_2"))
    if nav_row:
        buttons.append(nav_row)
    
    buttons.append([
        InlineKeyboardButton("🔍 Search", callback_data="gsearchmenu"),
        InlineKeyboardButton("📅 Filter", callback_data="gdatemenu")
    ])
    
    msg = await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    chat_id = update.effective_chat.id
    if chat_id not in sent_message_ids:
        sent_message_ids[chat_id] = []
    sent_message_ids[chat_id].append(msg.message_id)

async def group_viewchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_monitor_group(update.effective_chat.id):
        return
    
    if not is_admin(update.effective_user.id):
        return
    
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Usage: /viewchat <user_id>")
        return
    
    user_id = int(args[0])
    await send_full_chat(update.effective_chat.id, user_id, context)

async def group_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_monitor_group(update.effective_chat.id):
        return
    
    if not is_admin(update.effective_user.id):
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /search <keyword or user name>")
        return
    
    search_term = " ".join(args)
    db = context.bot_data["db"]
    
    data = db.get_users_with_messages(search=search_term, page=1, per_page=8)
    users = data.get('users', [])
    
    if not users:
        await update.message.reply_text(f"🔍 No users found for: {search_term}")
        return
    
    text = f"🔍 Results for '{search_term}':\n\nClick to view chat:"
    
    buttons = []
    for u in users:
        name = u.get('first_name') or u.get('username') or str(u.get('user_id', ''))[:12]
        user_id = u.get('user_id')
        msg_count = u.get('msg_count', 0)
        buttons.append([InlineKeyboardButton(
            f"👤 {name} ({msg_count})",
            callback_data=f"gopen_{user_id}"
        )])
    
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="glist_1")])
    
    msg = await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    chat_id = update.effective_chat.id
    if chat_id not in sent_message_ids:
        sent_message_ids[chat_id] = []
    sent_message_ids[chat_id].append(msg.message_id)

async def send_full_chat(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE, keyword: str = None, date_filter: str = None):
    db = context.bot_data["db"]
    
    date_from = None
    if date_filter == "today":
        date_from = datetime.now().replace(hour=0, minute=0, second=0).isoformat()
    elif date_filter == "yesterday":
        date_from = (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0).isoformat()
    elif date_filter == "week":
        date_from = (datetime.now() - timedelta(days=7)).isoformat()
    elif date_filter == "month":
        date_from = (datetime.now() - timedelta(days=30)).isoformat()
    
    data = db.get_user_messages_filtered(user_id, keyword=keyword, date_from=date_from)
    
    messages = data.get('messages', [])
    user_info = data.get('user', {})
    total = data.get('total', 0)
    
    name = user_info.get('first_name') or user_info.get('username') or str(user_id) if user_info else str(user_id)
    
    header = f"💬 Chat with {name} (ID: {user_id})\n"
    if keyword:
        header += f"🔍 Keyword: {keyword}\n"
    if date_filter:
        header += f"📅 Filter: {date_filter}\n"
    header += f"📊 {total} messages\n"
    header += "━━━━━━━━━━━━━━━━━━━━"
    
    msg = await context.bot.send_message(chat_id=chat_id, text=header)
    if chat_id not in sent_message_ids:
        sent_message_ids[chat_id] = []
    sent_message_ids[chat_id].append(msg.message_id)
    
    if not messages:
        msg = await context.bot.send_message(chat_id=chat_id, text="No messages found.")
        sent_message_ids[chat_id].append(msg.message_id)
    else:
        chunk = ""
        for m in messages:
            direction = "👤" if m.get('direction') == 'user' else "🤖"
            content = m.get('content', '')
            time_str = format_time(m.get('created_at', ''))
            
            line = f"{direction} [{time_str}]\n{content}\n\n"
            
            if len(chunk) + len(line) > 3500:
                msg = await context.bot.send_message(chat_id=chat_id, text=chunk)
                sent_message_ids[chat_id].append(msg.message_id)
                chunk = line
            else:
                chunk += line
        
        if chunk:
            msg = await context.bot.send_message(chat_id=chat_id, text=chunk)
            sent_message_ids[chat_id].append(msg.message_id)
    
    buttons = [
        [
            InlineKeyboardButton("🔍 Search in Chat", callback_data=f"gkeyword_{user_id}"),
            InlineKeyboardButton("📅 Filter Date", callback_data=f"gfilter_{user_id}")
        ],
        [
            InlineKeyboardButton("🗑️ Delete All Above", callback_data="gdeleteall"),
            InlineKeyboardButton("⬅️ Back", callback_data="glist_1")
        ]
    ]
    
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text="━━━━━━━━━━━━━━━━━━━━\nEnd of chat",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    sent_message_ids[chat_id].append(msg.message_id)

async def group_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat.id
    
    if not is_monitor_group(chat_id):
        return
    
    if not is_admin(query.from_user.id):
        await query.answer("Access denied", show_alert=True)
        return
    
    action = query.data
    db = context.bot_data["db"]
    
    if action == "gnoop":
        return
    
    elif action.startswith("gopen_"):
        user_id = int(action.replace("gopen_", ""))
        await query.message.delete()
        await send_full_chat(chat_id, user_id, context)
    
    elif action.startswith("glist_"):
        page = int(action.replace("glist_", ""))
        data = db.get_users_with_messages(page=page, per_page=8)
        
        users = data.get('users', [])
        total = data.get('total', 0)
        total_pages = data.get('total_pages', 1)
        
        if not users:
            await query.edit_message_text("💬 No users yet.")
            return
        
        text = f"💬 User Conversations ({total} users)\n\nClick to view full chat:"
        
        buttons = []
        for u in users:
            name = u.get('first_name') or u.get('username') or str(u.get('user_id', ''))[:12]
            user_id = u.get('user_id')
            msg_count = u.get('msg_count', 0)
            buttons.append([InlineKeyboardButton(
                f"👤 {name} ({msg_count})",
                callback_data=f"gopen_{user_id}"
            )])
        
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton("◀️", callback_data=f"glist_{page - 1}"))
        nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="gnoop"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton("▶️", callback_data=f"glist_{page + 1}"))
        if nav_row:
            buttons.append(nav_row)
        
        buttons.append([
            InlineKeyboardButton("🔍 Search", callback_data="gsearchmenu"),
            InlineKeyboardButton("📅 Filter", callback_data="gdatemenu")
        ])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    
    elif action == "gsearchmenu":
        await query.edit_message_text(
            "🔍 Search Options:\n\n"
            "Use /search <keyword> to find users\n"
            "Example: /search Ahmed",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="glist_1")]])
        )
    
    elif action == "gdatemenu":
        buttons = [
            [InlineKeyboardButton("📅 Today", callback_data="gdatefilter_today")],
            [InlineKeyboardButton("📅 Yesterday", callback_data="gdatefilter_yesterday")],
            [InlineKeyboardButton("📅 Last 7 Days", callback_data="gdatefilter_week")],
            [InlineKeyboardButton("📅 Last 30 Days", callback_data="gdatefilter_month")],
            [InlineKeyboardButton("⬅️ Back", callback_data="glist_1")]
        ]
        await query.edit_message_text(
            "📅 Filter by Date:\n\nSelect a time period:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    
    elif action.startswith("gdatefilter_"):
        date_filter = action.replace("gdatefilter_", "")
        context.user_data['date_filter'] = date_filter
        
        data = db.get_users_with_messages(page=1, per_page=8)
        users = data.get('users', [])
        
        text = f"📅 Filter: {date_filter}\n\nSelect user to view filtered chat:"
        
        buttons = []
        for u in users:
            name = u.get('first_name') or u.get('username') or str(u.get('user_id', ''))[:12]
            user_id = u.get('user_id')
            buttons.append([InlineKeyboardButton(
                f"👤 {name}",
                callback_data=f"gopenfiltered_{user_id}_{date_filter}"
            )])
        
        buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="glist_1")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    
    elif action.startswith("gopenfiltered_"):
        parts = action.split("_")
        user_id = int(parts[1])
        date_filter = parts[2] if len(parts) > 2 else None
        await query.message.delete()
        await send_full_chat(chat_id, user_id, context, date_filter=date_filter)
    
    elif action.startswith("gkeyword_"):
        user_id = action.replace("gkeyword_", "")
        context.user_data['search_user_id'] = user_id
        await query.edit_message_text(
            f"🔍 Search in chat with user {user_id}:\n\n"
            f"Use /searchmsg <keyword>\n"
            f"Example: /searchmsg hello",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Cancel", callback_data="glist_1")]])
        )
    
    elif action.startswith("gfilter_"):
        user_id = action.replace("gfilter_", "")
        buttons = [
            [InlineKeyboardButton("Today", callback_data=f"gopenfiltered_{user_id}_today")],
            [InlineKeyboardButton("Yesterday", callback_data=f"gopenfiltered_{user_id}_yesterday")],
            [InlineKeyboardButton("Last 7 Days", callback_data=f"gopenfiltered_{user_id}_week")],
            [InlineKeyboardButton("Last 30 Days", callback_data=f"gopenfiltered_{user_id}_month")],
            [InlineKeyboardButton("⬅️ Back", callback_data="glist_1")]
        ]
        await query.edit_message_text(
            f"📅 Filter chat with user {user_id}:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    
    elif action == "gdeleteall":
        if chat_id in sent_message_ids and sent_message_ids[chat_id]:
            deleted = 0
            for msg_id in sent_message_ids[chat_id]:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                    deleted += 1
                except Exception as e:
                    logger.debug(f"Could not delete message {msg_id}: {e}")
            
            sent_message_ids[chat_id] = []
            
            msg = await context.bot.send_message(chat_id=chat_id, text=f"🗑️ Deleted {deleted} messages.")
            sent_message_ids[chat_id].append(msg.message_id)
        else:
            await query.answer("No messages to delete", show_alert=True)

async def group_searchmsg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_monitor_group(update.effective_chat.id):
        return
    
    if not is_admin(update.effective_user.id):
        return
    
    user_id = context.user_data.get('search_user_id')
    if not user_id:
        await update.message.reply_text("First use /chats and click on a user, then use 🔍 Search in Chat")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /searchmsg <keyword>")
        return
    
    keyword = " ".join(args)
    await send_full_chat(update.effective_chat.id, int(user_id), context, keyword=keyword)
