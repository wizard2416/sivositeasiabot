import os
from telegram import Update, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from datetime import datetime
import config
import api

ASK_USER_ID = 10
ASK_AMOUNT = 11
ASK_MESSAGE = 20
ASK_AI_IMAGE_PROMPT = 30

def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_USER_IDS

def is_moderator(user_id: int) -> bool:
    return user_id in getattr(config, 'MODERATOR_IDS', [])

def get_admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏳ طلبات التفعيل", callback_data="admin_pending")],
        [InlineKeyboardButton("👤 رصيد المستخدمين", callback_data="admin_balance")],
        [InlineKeyboardButton("💬 محادثات المستخدمين", callback_data="admin_chats")],
        [InlineKeyboardButton("📱 حالة الأنظمة", callback_data="admin_phones")],
        [InlineKeyboardButton("🖼️ معرض البطاقات", callback_data="admin_gallery")],
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton("📈 إحصائيات متقدمة", callback_data="admin_advanced_stats")],
        [InlineKeyboardButton("📥 تصدير البيانات", callback_data="admin_export")],
        [InlineKeyboardButton("📢 إرسال رسالة جماعية", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🎨 إنشاء صورة بالذكاء الاصطناعي", callback_data="admin_ai_image")],
    ])

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    
    if is_moderator(user_id) and not is_admin(user_id):
        from src.handlers.moderator import moderator_menu
        await moderator_menu(update, context)
        return ConversationHandler.END
    
    if not is_admin(user_id):
        await update.message.reply_text("⛔ غير مصرح")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "🎛️ لوحة التحكم\n\nاختر خياراً:",
        reply_markup=get_admin_keyboard()
    )
    return ConversationHandler.END

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action = query.data
    user_id = query.from_user.id
    
    # Moderators can ONLY approve/reject users - nothing else
    moderator_allowed_actions = ["approve_", "reject_", "admin_back", "admin_pending", "pending_"]
    
    is_mod_allowed = any(action.startswith(a) or action == a for a in moderator_allowed_actions)
    
    if is_moderator(user_id) and not is_admin(user_id):
        if not is_mod_allowed:
            await query.edit_message_text("⛔ غير مصرح - صلاحيات المشرف محدودة")
            return
    elif not is_admin(user_id):
        await query.edit_message_text("⛔ غير مصرح")
        return
    
    db = context.bot_data["db"]
    
    if action == "admin_pending":
        pending_users = db.get_pending_users()
        
        if not pending_users:
            await query.edit_message_text(
                "⏳ طلبات التفعيل\n\nلا توجد طلبات جديدة.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="admin_back")]])
            )
            return
        
        buttons = []
        for user in pending_users[:15]:
            name = user.first_name or user.username or str(user.user_id)[:10]
            buttons.append([InlineKeyboardButton(
                f"👤 {name} - {user.user_id}",
                callback_data=f"pending_{user.user_id}"
            )])
        
        buttons.append([InlineKeyboardButton("⬅️ رجوع", callback_data="admin_back")])
        
        await query.edit_message_text(
            f"⏳ طلبات التفعيل ({len(pending_users)} طلب)\n\nاختر مستخدم للمراجعة:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return
    
    elif action.startswith("pending_"):
        user_id = int(action.replace("pending_", ""))
        user = db.get_balance(user_id)
        
        await query.edit_message_text(
            f"👤 طلب تفعيل جديد\n\n"
            f"🆔 الايدي: {user_id}\n"
            f"📝 الاسم: {user.first_name or 'غير متوفر'}\n"
            f"👤 المستخدم: @{user.username or 'غير متوفر'}\n\n"
            f"اختر إجراء:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ قبول", callback_data=f"approve_{user_id}")],
                [InlineKeyboardButton("❌ رفض", callback_data=f"reject_{user_id}")],
                [InlineKeyboardButton("⬅️ رجوع", callback_data="admin_pending")]
            ])
        )
        return
    
    elif action.startswith("approve_"):
        user_id = int(action.replace("approve_", ""))
        db.approve_user(user_id)
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="✅ تم تفعيل حسابك!\n\nيمكنك الآن استخدام البوت.\nاضغط /start للبدء."
            )
        except:
            pass
        
        await query.edit_message_text(
            f"✅ تم قبول المستخدم {user_id}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="admin_pending")]])
        )
        return
    
    elif action.startswith("reject_"):
        user_id = int(action.replace("reject_", ""))
        db.reject_user(user_id)
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ تم رفض طلب تفعيل حسابك."
            )
        except:
            pass
        
        await query.edit_message_text(
            f"❌ تم رفض المستخدم {user_id}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="admin_pending")]])
        )
        return
    
    elif action == "admin_balance":
        users = db.get_all_users()
        
        if not users:
            await query.edit_message_text(
                "👤 إدارة الأرصدة\n\nلا يوجد مستخدمين.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="admin_back")]])
            )
            return
        
        users_sorted = sorted(users, key=lambda u: u.balance_iqd, reverse=True)[:15]
        
        buttons = []
        for user in users_sorted:
            name = user.first_name or user.username or str(user.user_id)[:10]
            buttons.append([InlineKeyboardButton(
                f"👤 {name} - 💰 {user.balance_iqd:,} د.ع",
                callback_data=f"user_{user.user_id}"
            )])
        
        buttons.append([InlineKeyboardButton("⬅️ رجوع", callback_data="admin_back")])
        
        text = f"👤 أرصدة المستخدمين ({len(users)} مستخدم)\n\nاختر مستخدم للإدارة:"
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return
    
    elif action == "admin_phones":
        phones = db.get_all_phones()
        
        if not phones:
            await query.edit_message_text(
                "📱 حالة الأنظمة\n\nلا توجد هواتف مسجلة.\n\nتسجل الهواتف تلقائياً عند الاتصال.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="admin_back")]])
            )
            return
        
        text = "📱 حالة الأنظمة\n\n"
        for phone in phones:
            last_seen = format_time_ago(phone.last_seen)
            status_icon = "🟢" if phone.status == 'online' else "🔴"
            battery_icon = "🔋" if phone.battery_level > 20 else "🪫"
            
            text += f"{status_icon} {phone.name}\n"
            text += f"{battery_icon} {phone.battery_level}%\n"
            text += f"📊 ✅{phone.jobs_completed} ❌{phone.jobs_failed}\n"
            text += f"⏰ {last_seen}\n\n"
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="admin_back")]])
        )
    
    elif action == "admin_gallery":
        cards = db.get_cards_with_images(limit=10)
        
        if not cards:
            await query.edit_message_text(
                "🖼️ معرض البطاقات\n\nلا توجد صور بطاقات محفوظة.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="admin_back")]])
            )
            return
        
        buttons = []
        for card in cards:
            pin_display = f"{card.pin[:4]}****{card.pin[-4:]}" if len(card.pin) >= 8 else card.pin
            status_icon = "✅" if card.status == "verified" else "❌" if card.status == "failed" else "⏳"
            buttons.append([InlineKeyboardButton(
                f"{status_icon} #{card.id} - {pin_display}",
                callback_data=f"gallery_{card.id}"
            )])
        
        buttons.append([InlineKeyboardButton("🗑️ حذف الصور القديمة", callback_data="gallery_cleanup")])
        buttons.append([InlineKeyboardButton("⬅️ رجوع", callback_data="admin_back")])
        
        await query.edit_message_text(
            "🖼️ معرض البطاقات\n\nاختر بطاقة لعرض صورتها:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    
    elif action == "admin_stats":
        stats = db.get_stats()
        online_phones = len(db.get_online_phones())
        
        text = f"📊 إحصائيات البوت\n\n"
        text += f"👥 المستخدمين: {stats['total_users']}\n"
        text += f"✅ مكتملة: {stats['verified_cards']}\n"
        text += f"❌ فاشلة: {stats['failed_cards']}\n"
        text += f"⏳ قيد الانتظار: {stats['pending_cards']}\n"
        text += f"💰 إجمالي الرصيد: {stats['total_balance_added']:,} د.ع\n"
        text += f"🎮 طلبات Xena: {stats['xena_orders']}\n"
        text += f"💵 إيرادات Xena: {stats['xena_revenue']:,} د.ع\n"
        text += f"📱 الهواتف المتصلة: {online_phones}"
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="admin_back")]])
        )
    
    elif action == "admin_broadcast":
        await query.edit_message_text("📢 إرسال رسالة جماعية")
        await query.message.reply_text(
            "أرسل الرسالة التي تريد إرسالها للجميع:",
            reply_markup=ForceReply(selective=True, input_field_placeholder="الرسالة...")
        )
        context.user_data['admin_action'] = 'broadcast'
        return ASK_MESSAGE
    
    elif action == "admin_ai_image":
        from src.services.ai_image import is_available
        if not is_available():
            await query.edit_message_text(
                "❌ خدمة توليد الصور غير متاحة حالياً",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="admin_back")]])
            )
            return
        
        await query.edit_message_text("🎨 إنشاء صورة بالذكاء الاصطناعي")
        await query.message.reply_text(
            "🎨 أرسل وصف الصورة التي تريد إنشاءها:\n\n"
            "مثال: قطة لطيفة تجلس على سحابة\n"
            "Example: A cute cat sitting on a cloud",
            reply_markup=ForceReply(selective=True, input_field_placeholder="وصف الصورة...")
        )
        context.user_data['admin_action'] = 'ai_image'
        return ASK_AI_IMAGE_PROMPT
    
    elif action == "admin_advanced_stats":
        success_rate = db.get_card_success_rate()
        peak_hours = db.get_peak_hours()[:5]
        profit = db.get_profit_stats(days=7)
        
        text = "📈 إحصائيات متقدمة\n\n"
        text += f"📊 نسبة نجاح البطاقات\n"
        text += f"  ✅ ناجحة: {success_rate['verified']}\n"
        text += f"  ❌ فاشلة: {success_rate['failed']}\n"
        text += f"  📈 النسبة: {success_rate['success_rate']}%\n\n"
        
        text += f"⏰ ساعات الذروة (أعلى 5)\n"
        for h in peak_hours:
            text += f"  {h['hour']}:00 - {h['count']} بطاقة\n"
        
        text += f"\n💰 الإيرادات (آخر 7 أيام)\n"
        text += f"  🔋 البطاقات: {profit['cards_revenue']:,} د.ع\n"
        text += f"  🎮 Xena: {profit['xena_revenue']:,} د.ع\n"
        text += f"  💵 الإجمالي: {profit['total_revenue']:,} د.ع"
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="admin_back")]])
        )
    
    elif action == "admin_chats":
        data = db.get_users_with_messages(page=1, per_page=10)
        await show_chat_users_list(query, data, 1)
    
    elif action.startswith("chats_page_"):
        page = int(action.replace("chats_page_", ""))
        data = db.get_users_with_messages(page=page, per_page=10)
        await show_chat_users_list(query, data, page)
    
    elif action == "chat_search":
        context.user_data['awaiting_chat_search'] = True
        await query.edit_message_text(
            "🔍 بحث في المحادثات\n\nأرسل رقم المستخدم أو اسمه للبحث:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ إلغاء", callback_data="admin_chats")]])
        )
    
    elif action.startswith("chatsearch_"):
        search_term = action.replace("chatsearch_", "")
        data = db.get_users_with_messages(search=search_term, page=1, per_page=10)
        await show_chat_users_list(query, data, 1)
    
    elif action.startswith("chat_"):
        parts = action.split("_")
        user_id = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 1
        data = db.get_user_messages(user_id, page=page, per_page=10)
        await show_user_chat(query, data, user_id, page)
    
    elif action == "admin_export":
        buttons = [
            [InlineKeyboardButton("👥 تصدير المستخدمين", callback_data="export_users")],
            [InlineKeyboardButton("🎴 تصدير البطاقات", callback_data="export_cards")],
            [InlineKeyboardButton("🎮 تصدير طلبات Xena", callback_data="export_xena")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="admin_back")],
        ]
        await query.edit_message_text(
            "📥 تصدير البيانات\n\nاختر البيانات للتصدير كملف CSV:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    
    elif action == "admin_back":
        # Moderators get redirected to their limited menu
        if is_moderator(user_id) and not is_admin(user_id):
            from src.handlers.moderator import moderator_menu
            await moderator_menu(update, context)
            return
        
        await query.edit_message_text(
            "🎛️ لوحة التحكم\n\nاختر خياراً:",
            reply_markup=get_admin_keyboard()
        )

async def user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    db = context.bot_data["db"]
    action = query.data
    
    if action.startswith("user_"):
        user_id = int(action.replace("user_", ""))
        user = db.get_balance(user_id)
        is_blocked = db.is_user_blocked(user_id)
        is_vip = db.is_user_vip(user_id)
        
        buttons = [
            [
                InlineKeyboardButton("➕ إضافة 1000", callback_data=f"bal_add_{user_id}_1000"),
                InlineKeyboardButton("➕ إضافة 5000", callback_data=f"bal_add_{user_id}_5000"),
            ],
            [
                InlineKeyboardButton("➕ إضافة 10000", callback_data=f"bal_add_{user_id}_10000"),
                InlineKeyboardButton("➕ إضافة 25000", callback_data=f"bal_add_{user_id}_25000"),
            ],
            [
                InlineKeyboardButton("➖ خصم 1000", callback_data=f"bal_sub_{user_id}_1000"),
                InlineKeyboardButton("➖ خصم 5000", callback_data=f"bal_sub_{user_id}_5000"),
            ],
            [InlineKeyboardButton("🗑️ تصفير الرصيد", callback_data=f"bal_set_{user_id}_0")],
            [
                InlineKeyboardButton("🔓 إلغاء الحظر" if is_blocked else "🚫 حظر", callback_data=f"toggle_block_{user_id}"),
                InlineKeyboardButton("⭐ إلغاء VIP" if is_vip else "⭐ تعيين VIP", callback_data=f"toggle_vip_{user_id}"),
            ],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="admin_balance")],
        ]
        
        status_icons = []
        if is_blocked: status_icons.append("🚫 محظور")
        if is_vip: status_icons.append("⭐ VIP")
        status_str = " | ".join(status_icons) if status_icons else ""
        
        await query.edit_message_text(
            f"👤 المستخدم: {user.first_name or user.username or user_id}\n"
            f"🆔 الايدي: {user_id}\n"
            f"💰 الرصيد: {user.balance_iqd:,} د.ع\n"
            f"{status_str}\n\n"
            f"اختر إجراء:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    
    elif action.startswith("bal_add_"):
        parts = action.split("_")
        user_id = int(parts[2])
        amount = int(parts[3])
        new_balance = db.add_balance(user_id, amount)
        
        await query.edit_message_text(
            f"✅ تم إضافة {amount:,} د.ع\n\n"
            f"👤 المستخدم: {user_id}\n"
            f"💰 الرصيد الجديد: {new_balance:,} د.ع",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👤 رجوع للمستخدم", callback_data=f"user_{user_id}")],
                [InlineKeyboardButton("📋 رجوع للقائمة", callback_data="admin_balance")],
            ])
        )
    
    elif action.startswith("bal_sub_"):
        parts = action.split("_")
        user_id = int(parts[2])
        amount = int(parts[3])
        new_balance = db.add_balance(user_id, -amount)
        
        await query.edit_message_text(
            f"✅ تم خصم {amount:,} د.ع\n\n"
            f"👤 المستخدم: {user_id}\n"
            f"💰 الرصيد الجديد: {new_balance:,} د.ع",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👤 رجوع للمستخدم", callback_data=f"user_{user_id}")],
                [InlineKeyboardButton("📋 رجوع للقائمة", callback_data="admin_balance")],
            ])
        )
    
    elif action.startswith("bal_set_"):
        parts = action.split("_")
        user_id = int(parts[2])
        amount = int(parts[3])
        new_balance = db.set_balance(user_id, amount)
        
        await query.edit_message_text(
            f"✅ تم تعيين الرصيد إلى {amount:,} د.ع\n\n"
            f"👤 المستخدم: {user_id}\n"
            f"💰 الرصيد الجديد: {new_balance:,} د.ع",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👤 رجوع للمستخدم", callback_data=f"user_{user_id}")],
                [InlineKeyboardButton("📋 رجوع للقائمة", callback_data="admin_balance")],
            ])
        )
    
    elif action.startswith("toggle_block_"):
        user_id = int(action.replace("toggle_block_", ""))
        is_blocked = db.is_user_blocked(user_id)
        if is_blocked:
            db.unblock_user(user_id)
            await query.answer("✅ تم إلغاء الحظر")
        else:
            db.block_user(user_id)
            await query.answer("🚫 تم حظر المستخدم")
        
        user = db.get_balance(user_id)
        is_blocked = db.is_user_blocked(user_id)
        is_vip = db.is_user_vip(user_id)
        
        buttons = [
            [
                InlineKeyboardButton("➕ إضافة 1000", callback_data=f"bal_add_{user_id}_1000"),
                InlineKeyboardButton("➕ إضافة 5000", callback_data=f"bal_add_{user_id}_5000"),
            ],
            [
                InlineKeyboardButton("➕ إضافة 10000", callback_data=f"bal_add_{user_id}_10000"),
                InlineKeyboardButton("➕ إضافة 25000", callback_data=f"bal_add_{user_id}_25000"),
            ],
            [
                InlineKeyboardButton("➖ خصم 1000", callback_data=f"bal_sub_{user_id}_1000"),
                InlineKeyboardButton("➖ خصم 5000", callback_data=f"bal_sub_{user_id}_5000"),
            ],
            [InlineKeyboardButton("🗑️ تصفير الرصيد", callback_data=f"bal_set_{user_id}_0")],
            [
                InlineKeyboardButton("🔓 إلغاء الحظر" if is_blocked else "🚫 حظر", callback_data=f"toggle_block_{user_id}"),
                InlineKeyboardButton("⭐ إلغاء VIP" if is_vip else "⭐ تعيين VIP", callback_data=f"toggle_vip_{user_id}"),
            ],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="admin_balance")],
        ]
        
        status_icons = []
        if is_blocked: status_icons.append("🚫 محظور")
        if is_vip: status_icons.append("⭐ VIP")
        status_str = " | ".join(status_icons) if status_icons else ""
        
        await query.edit_message_text(
            f"👤 المستخدم: {user.first_name or user.username or user_id}\n"
            f"🆔 الايدي: {user_id}\n"
            f"💰 الرصيد: {user.balance_iqd:,} د.ع\n"
            f"{status_str}\n\n"
            f"اختر إجراء:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    
    elif action.startswith("toggle_vip_"):
        user_id = int(action.replace("toggle_vip_", ""))
        is_vip = db.is_user_vip(user_id)
        db.set_user_vip(user_id, not is_vip)
        await query.answer("⭐ تم تحديث حالة VIP")
        
        user = db.get_balance(user_id)
        is_blocked = db.is_user_blocked(user_id)
        is_vip = db.is_user_vip(user_id)
        
        buttons = [
            [
                InlineKeyboardButton("➕ إضافة 1000", callback_data=f"bal_add_{user_id}_1000"),
                InlineKeyboardButton("➕ إضافة 5000", callback_data=f"bal_add_{user_id}_5000"),
            ],
            [
                InlineKeyboardButton("➕ إضافة 10000", callback_data=f"bal_add_{user_id}_10000"),
                InlineKeyboardButton("➕ إضافة 25000", callback_data=f"bal_add_{user_id}_25000"),
            ],
            [
                InlineKeyboardButton("➖ خصم 1000", callback_data=f"bal_sub_{user_id}_1000"),
                InlineKeyboardButton("➖ خصم 5000", callback_data=f"bal_sub_{user_id}_5000"),
            ],
            [InlineKeyboardButton("🗑️ تصفير الرصيد", callback_data=f"bal_set_{user_id}_0")],
            [
                InlineKeyboardButton("🔓 إلغاء الحظر" if is_blocked else "🚫 حظر", callback_data=f"toggle_block_{user_id}"),
                InlineKeyboardButton("⭐ إلغاء VIP" if is_vip else "⭐ تعيين VIP", callback_data=f"toggle_vip_{user_id}"),
            ],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="admin_balance")],
        ]
        
        status_icons = []
        if is_blocked: status_icons.append("🚫 محظور")
        if is_vip: status_icons.append("⭐ VIP")
        status_str = " | ".join(status_icons) if status_icons else ""
        
        await query.edit_message_text(
            f"👤 المستخدم: {user.first_name or user.username or user_id}\n"
            f"🆔 الايدي: {user_id}\n"
            f"💰 الرصيد: {user.balance_iqd:,} د.ع\n"
            f"{status_str}\n\n"
            f"اختر إجراء:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

async def export_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    db = context.bot_data["db"]
    action = query.data
    
    if action == "export_users":
        csv_data = db.export_users_csv()
        filename = f"users_{datetime.now().strftime('%Y%m%d')}.csv"
        os.makedirs("data/exports", exist_ok=True)
        filepath = f"data/exports/{filename}"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(csv_data)
        
        with open(filepath, "rb") as f:
            await context.bot.send_document(
                chat_id=query.from_user.id,
                document=f,
                filename=filename,
                caption="👥 تصدير المستخدمين"
            )
    
    elif action == "export_cards":
        csv_data = db.export_cards_csv()
        filename = f"cards_{datetime.now().strftime('%Y%m%d')}.csv"
        os.makedirs("data/exports", exist_ok=True)
        filepath = f"data/exports/{filename}"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(csv_data)
        
        with open(filepath, "rb") as f:
            await context.bot.send_document(
                chat_id=query.from_user.id,
                document=f,
                filename=filename,
                caption="🎴 تصدير البطاقات"
            )
    
    elif action == "export_xena":
        csv_data = db.export_xena_orders_csv()
        filename = f"xena_orders_{datetime.now().strftime('%Y%m%d')}.csv"
        os.makedirs("data/exports", exist_ok=True)
        filepath = f"data/exports/{filename}"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(csv_data)
        
        with open(filepath, "rb") as f:
            await context.bot.send_document(
                chat_id=query.from_user.id,
                document=f,
                filename=filename,
                caption="🎮 تصدير طلبات Xena"
            )

async def gallery_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    db = context.bot_data["db"]
    action = query.data
    
    if action == "gallery_cleanup":
        deleted = db.cleanup_old_images(days=7)
        await query.edit_message_text(
            f"🗑️ اكتمل التنظيف\n\nتم حذف {deleted} صورة قديمة.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="admin_gallery")]])
        )
        return
    
    card_id = int(action.replace("gallery_", ""))
    card = db.get_card_by_id(card_id)
    
    if not card or not card.image_path:
        await query.edit_message_text(
            "❌ الصورة غير موجودة أو محذوفة.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="admin_gallery")]])
        )
        return
    
    if os.path.exists(card.image_path):
        try:
            with open(card.image_path, "rb") as f:
                await context.bot.send_photo(
                    chat_id=query.from_user.id,
                    photo=f,
                    caption=f"🎴 البطاقة #{card.id}\n"
                            f"👤 المستخدم: {card.user_id}\n"
                            f"📝 الرقم: {card.pin}\n"
                            f"💰 المبلغ: {card.amount:,}\n"
                            f"📊 الحالة: {card.status}\n"
                            f"📅 التاريخ: {card.created_at[:10]}"
                )
        except Exception as e:
            await query.message.reply_text(f"❌ خطأ في تحميل الصورة: {e}")
    else:
        await query.message.reply_text("❌ ملف الصورة غير موجود.")

async def receive_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    
    text = update.message.text.strip()
    
    if not text.isdigit():
        await update.message.reply_text(
            "❌ Enter a valid number\nUser ID:",
            reply_markup=ForceReply(selective=True, input_field_placeholder="User ID...")
        )
        return ASK_USER_ID
    
    user_id = int(text)
    context.user_data['admin_target_user'] = user_id
    
    db = context.bot_data["db"]
    user = db.get_balance(user_id)
    
    await update.message.reply_text(
        f"👤 User: {user_id}\n"
        f"💰 Balance: {user.balance_iqd:,} IQD\n\n"
        f"Enter new amount (or +/- to add/subtract):",
        reply_markup=ForceReply(selective=True, input_field_placeholder="Amount...")
    )
    return ASK_AMOUNT

async def receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    
    text = update.message.text.strip()
    user_id = context.user_data.get('admin_target_user', 0)
    db = context.bot_data["db"]
    
    current = db.get_balance(user_id).balance_iqd
    
    try:
        if text.startswith('+'):
            amount = int(text[1:].replace(",", ""))
            new_balance = db.add_balance(user_id, amount)
            action = f"Added {amount:,}"
        elif text.startswith('-'):
            amount = int(text[1:].replace(",", ""))
            new_balance = db.add_balance(user_id, -amount)
            action = f"Subtracted {amount:,}"
        else:
            amount = int(text.replace(",", ""))
            new_balance = db.set_balance(user_id, amount)
            action = f"Set to {amount:,}"
    except ValueError:
        await update.message.reply_text("Invalid amount. Try again:")
        return ASK_AMOUNT
    
    await update.message.reply_text(
        f"✅ {action}\n\n"
        f"👤 User: {user_id}\n"
        f"💰 Previous: {current:,} IQD\n"
        f"💰 New: {new_balance:,} IQD"
    )
    
    return ConversationHandler.END

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Access denied")
        return
    
    db = context.bot_data["db"]
    stats = db.get_stats()
    online_phones = len(db.get_online_phones())
    
    await update.message.reply_text(
        f"📊 Bot Statistics\n\n"
        f"👥 Users: {stats['total_users']}\n"
        f"✅ Verified: {stats['verified_cards']}\n"
        f"❌ Failed: {stats['failed_cards']}\n"
        f"⏳ Pending: {stats['pending_cards']}\n"
        f"💰 Total Balance: {stats['total_balance_added']:,} IQD\n"
        f"🎮 Xena Orders: {stats['xena_orders']}\n"
        f"💵 Xena Revenue: {stats['xena_revenue']:,} IQD\n"
        f"📱 Online Phones: {online_phones}"
    )

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Access denied")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📢 Broadcast Message\n\nEnter your message:",
        reply_markup=ForceReply(selective=True, input_field_placeholder="Message...")
    )
    return ASK_MESSAGE

async def receive_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    
    message = update.message.text
    db = context.bot_data["db"]
    users = db.get_all_users()
    
    sent = 0
    failed = 0
    
    await update.message.reply_text(f"⏳ Sending to {len(users)} users...")
    
    for user in users:
        try:
            await context.bot.send_message(user.user_id, message)
            sent += 1
        except Exception:
            failed += 1
    
    await update.message.reply_text(
        f"✅ Broadcast Complete!\n\n"
        f"📤 Sent: {sent}\n"
        f"❌ Failed: {failed}"
    )
    
    return ConversationHandler.END

async def receive_ai_image_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    
    prompt = update.message.text.strip()
    
    if not prompt or len(prompt) < 3:
        await update.message.reply_text(
            "❌ الوصف قصير جداً\n\nأرسل وصف أطول للصورة:",
            reply_markup=ForceReply(selective=True, input_field_placeholder="وصف الصورة...")
        )
        return ASK_AI_IMAGE_PROMPT
    
    progress_msg = await update.message.reply_text("⏳ جاري إنشاء الصورة...\n\nقد يستغرق هذا بضع ثوان...")
    
    try:
        from src.services.ai_image import generate_image
        success, message, file_path = generate_image(prompt)
        
        if success and file_path:
            await progress_msg.delete()
            with open(file_path, 'rb') as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=f"🎨 الصورة المُنشأة\n\n📝 الوصف: {prompt[:200]}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🎨 إنشاء صورة أخرى", callback_data="admin_ai_image")],
                        [InlineKeyboardButton("⬅️ رجوع للقائمة", callback_data="admin_back")]
                    ])
                )
        else:
            await progress_msg.edit_text(
                f"❌ {message}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 حاول مرة أخرى", callback_data="admin_ai_image")],
                    [InlineKeyboardButton("⬅️ رجوع", callback_data="admin_back")]
                ])
            )
    except Exception as e:
        await progress_msg.edit_text(
            f"❌ حدث خطأ: {str(e)[:100]}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 حاول مرة أخرى", callback_data="admin_ai_image")],
                [InlineKeyboardButton("⬅️ رجوع", callback_data="admin_back")]
            ])
        )
    
    return ConversationHandler.END

async def cancel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Cancelled")
    return ConversationHandler.END

async def chat_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    if not context.user_data.get('awaiting_chat_search'):
        return
    
    context.user_data['awaiting_chat_search'] = False
    search_term = update.message.text.strip()
    
    db = context.bot_data["db"]
    data = db.get_users_with_messages(search=search_term, page=1, per_page=10)
    
    users = data.get('users', [])
    total = data.get('total', 0)
    
    if not users:
        await update.message.reply_text(
            f"🔍 لم يتم العثور على نتائج لـ: {search_term}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="admin_chats")]])
        )
        return
    
    text = f"🔍 نتائج البحث عن '{search_term}' ({total} نتيجة)\n\n"
    
    buttons = []
    for u in users:
        name = u.get('first_name') or u.get('username') or str(u.get('user_id', ''))[:10]
        msg_count = u.get('msg_count', 0)
        buttons.append([InlineKeyboardButton(
            f"👤 {name} ({msg_count} رسالة)",
            callback_data=f"chat_{u['user_id']}_1"
        )])
    
    buttons.append([InlineKeyboardButton("⬅️ رجوع للمستخدمين", callback_data="admin_chats")])
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

def format_time_ago(dt_str: str) -> str:
    try:
        dt = datetime.fromisoformat(dt_str.replace(' ', 'T'))
        diff = datetime.now() - dt
        
        if diff.total_seconds() < 60:
            return "الآن"
        elif diff.total_seconds() < 3600:
            mins = int(diff.total_seconds() / 60)
            return f"منذ {mins} دقيقة"
        elif diff.total_seconds() < 86400:
            hours = int(diff.total_seconds() / 3600)
            return f"منذ {hours} ساعة"
        else:
            days = int(diff.total_seconds() / 86400)
            return f"منذ {days} يوم"
    except:
        return dt_str[:16] if dt_str else "غير معروف"

async def show_chat_users_list(query, data: dict, current_page: int):
    users = data.get('users', [])
    total_pages = data.get('total_pages', 1)
    total = data.get('total', 0)
    
    if not users:
        await query.edit_message_text(
            "💬 محادثات المستخدمين\n\nلا توجد رسائل بعد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="admin_back")]])
        )
        return
    
    text = f"💬 محادثات المستخدمين ({total} مستخدم)\n\nاختر مستخدم لعرض المحادثة:\n\n"
    
    buttons = []
    for u in users:
        name = u.get('first_name') or u.get('username') or str(u.get('user_id', ''))[:10]
        msg_count = u.get('msg_count', 0)
        last_msg = format_time_ago(u.get('last_msg', '')) if u.get('last_msg') else 'لا رسائل'
        buttons.append([InlineKeyboardButton(
            f"👤 {name} ({msg_count} رسالة) - {last_msg}",
            callback_data=f"chat_{u['user_id']}_1"
        )])
    
    nav_buttons = []
    if current_page > 1:
        nav_buttons.append(InlineKeyboardButton("◀️ السابق", callback_data=f"chats_page_{current_page - 1}"))
    nav_buttons.append(InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="noop"))
    if current_page < total_pages:
        nav_buttons.append(InlineKeyboardButton("التالي ▶️", callback_data=f"chats_page_{current_page + 1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton("🔍 بحث عن مستخدم", callback_data="chat_search")])
    buttons.append([InlineKeyboardButton("⬅️ رجوع", callback_data="admin_back")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def show_user_chat(query, data: dict, user_id: int, current_page: int):
    messages = data.get('messages', [])
    user_info = data.get('user', {})
    total_pages = data.get('total_pages', 1)
    total = data.get('total', 0)
    
    name = user_info.get('first_name') or user_info.get('username') or str(user_id)
    
    text = f"💬 محادثة مع {name}\n"
    text += f"🆔 الايدي: {user_id}\n"
    text += f"📊 {total} رسالة (صفحة {current_page}/{total_pages})\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    if not messages:
        text += "لا توجد رسائل بعد."
    else:
        for msg in messages:
            direction = msg.get('direction', 'user')
            content = msg.get('content', '')[:100]
            if len(msg.get('content', '')) > 100:
                content += "..."
            time_str = format_time_ago(msg.get('created_at', ''))
            
            if direction == 'user':
                text += f"👤 {content}\n   ⏰ {time_str}\n\n"
            else:
                text += f"🤖 {content}\n   ⏰ {time_str}\n\n"
    
    if len(text) > 4000:
        text = text[:3997] + "..."
    
    nav_buttons = []
    if current_page > 1:
        nav_buttons.append(InlineKeyboardButton("◀️ السابق", callback_data=f"chat_{user_id}_{current_page - 1}"))
    if current_page < total_pages:
        nav_buttons.append(InlineKeyboardButton("التالي ▶️", callback_data=f"chat_{user_id}_{current_page + 1}"))
    
    buttons = []
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton("⬅️ رجوع للمستخدمين", callback_data="admin_chats")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
