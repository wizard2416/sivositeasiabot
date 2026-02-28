import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from src.services.lang import get_text
from src.handlers.forwarding import copy_bot_reply_to_group
import config

logger = logging.getLogger(__name__)

ASK_PAYMENT_AMOUNT = 1
ASK_PAYMENT_PROOF = 2

def get_payment_address(payment_type: str, db=None) -> str:
    if payment_type == 'qi_card':
        if db:
            db_value = db.get_setting('qi_card_number')
            if db_value:
                return db_value
        return os.environ.get('QI_CARD_ADDRESS', '')
    elif payment_type == 'zaincash':
        if db:
            db_value = db.get_setting('zaincash_number')
            if db_value:
                return db_value
        return os.environ.get('ZAINCASH_ADDRESS', '')
    return ''

COMING_SOON_QI = """🚧 قريباً 🚧

💳 QI Card

⏳ هذه الخدمة ستكون متاحة قريباً!

شكراً لصبركم 🙏"""

COMING_SOON_ZAINCASH = """🚧 قريباً 🚧

💜 ZainCash

⏳ هذه الخدمة ستكون متاحة قريباً!

شكراً لصبركم 🙏"""

COMING_SOON_VODAFONE = """🚧 قريباً 🚧

🔴 Vodafone Cash

⏳ هذه الخدمة ستكون متاحة قريباً!

شكراً لصبركم 🙏"""

async def begin_qi_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(COMING_SOON_QI)
    return ConversationHandler.END

async def begin_zaincash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(COMING_SOON_ZAINCASH)
    return ConversationHandler.END

async def begin_vodafone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(COMING_SOON_VODAFONE)
    return ConversationHandler.END

async def receive_payment_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    user_id = update.effective_user.id
    lang = db.get_user_language(user_id)
    
    text = update.message.text.strip()
    text = text.replace(',', '').replace(' ', '')
    
    if not text.isdigit():
        await update.message.reply_text(get_text('payment_invalid_amount', lang))
        return ASK_PAYMENT_AMOUNT
    
    amount = int(text)
    if amount < 1000:
        await update.message.reply_text(get_text('payment_amount_too_low', lang))
        return ASK_PAYMENT_AMOUNT
    
    if amount > 10000000:
        await update.message.reply_text(get_text('payment_amount_too_high', lang))
        return ASK_PAYMENT_AMOUNT
    
    payment_type = context.user_data.get('payment_type', 'qi_card')
    
    address = get_payment_address(payment_type)
    if not address:
        await update.message.reply_text(get_text('payment_not_configured', lang))
        return ConversationHandler.END
    
    payment_id = db.create_payment_request(user_id, payment_type, amount)
    
    context.user_data['payment_id'] = payment_id
    context.user_data['payment_amount'] = amount
    
    type_name = "QI Card" if payment_type == 'qi_card' else "ZainCash"
    
    reply_text = get_text('payment_send_to_address', lang, 
                          type_name=type_name, 
                          address=address, 
                          amount=amount)
    await update.message.reply_text(reply_text)
    return ASK_PAYMENT_PROOF

async def receive_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    ocr = context.bot_data.get("ocr")
    user_id = update.effective_user.id
    lang = db.get_user_language(user_id)
    
    if not update.message.photo:
        await update.message.reply_text(get_text('payment_need_photo', lang))
        return ASK_PAYMENT_PROOF
    
    payment_id = context.user_data.get('payment_id')
    payment_type = context.user_data.get('payment_type', 'qi_card')
    
    if not payment_id:
        await update.message.reply_text(get_text('payment_error', lang))
        return ConversationHandler.END
    
    os.makedirs("data/payment_proofs", exist_ok=True)
    
    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_path = f"data/payment_proofs/{payment_id}_{user_id}.jpg"
    await file.download_to_drive(file_path)
    
    # Extract transaction info using OCR
    transaction_number = None
    ocr_amount = None
    if ocr:
        try:
            with open(file_path, 'rb') as f:
                image_bytes = f.read()
            ocr_result = ocr.extract_payment_info(image_bytes)
            if ocr_result.get("success"):
                transaction_number = ocr_result.get("transaction_number")
                ocr_amount = ocr_result.get("amount")
                logger.info(f"OCR extracted: trans={transaction_number}, amount={ocr_amount}")
        except Exception as e:
            logger.error(f"OCR failed for payment proof: {e}")
    
    # Check for duplicate transaction
    if transaction_number:
        existing = db.find_payment_by_transaction(transaction_number)
        if existing:
            # Show status of existing payment
            status_text = {
                'pending': '⏳ قيد المراجعة',
                'approved': '✅ تم قبولها',
                'rejected': '❌ مرفوضة',
                'different_amount': '✅ تم قبولها (بمبلغ مختلف)'
            }.get(existing.status, existing.status)
            
            if lang == 'en':
                status_text = {
                    'pending': '⏳ Pending review',
                    'approved': '✅ Approved',
                    'rejected': '❌ Rejected',
                    'different_amount': '✅ Approved (different amount)'
                }.get(existing.status, existing.status)
            
            # Delete the new payment request since this is a duplicate
            db.delete_payment_request(payment_id)
            
            if lang == 'ar':
                msg = f"⚠️ هذا الإيصال مستخدم مسبقاً\n\n"
                msg += f"🆔 رقم الطلب السابق: #{existing.id}\n"
                msg += f"📊 الحالة: {status_text}\n"
                if existing.actual_amount:
                    msg += f"💰 المبلغ: {existing.actual_amount:,} د.ع"
            else:
                msg = f"⚠️ This receipt has already been used\n\n"
                msg += f"🆔 Previous request ID: #{existing.id}\n"
                msg += f"📊 Status: {status_text}\n"
                if existing.actual_amount:
                    msg += f"💰 Amount: {existing.actual_amount:,} IQD"
            
            await update.message.reply_text(msg)
            context.user_data.clear()
            return ConversationHandler.END
    
    db.update_payment_proof(payment_id, file_path, transaction_number)
    
    type_name = "QI Card" if payment_type == 'qi_card' else "ZainCash"
    
    for admin_id in config.ADMIN_USER_IDS:
        try:
            user_data = db.get_balance(user_id)
            caption = f"💳 طلب دفع جديد\n\n"
            caption += f"📋 النوع: {type_name}\n"
            caption += f"🆔 رقم الطلب: #{payment_id}\n"
            caption += f"👤 المستخدم: {user_data.first_name} (@{user_data.username})\n"
            caption += f"🆔 الايدي: {user_id}"
            if ocr_amount:
                caption += f"\n💰 المبلغ (OCR): {ocr_amount:,} د.ع"
            if transaction_number:
                caption += f"\n📝 رقم الحركة: {transaction_number[:15]}..."
            
            await context.bot.send_photo(
                chat_id=admin_id,
                photo=open(file_path, 'rb'),
                caption=caption,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💰 تحديد المبلغ والتأكيد", callback_data=f"payment_diff_{payment_id}")],
                    [InlineKeyboardButton("❌ رفض", callback_data=f"payment_reject_{payment_id}")]
                ])
            )
        except Exception as e:
            pass
    
    await update.message.reply_text(get_text('payment_proof_received', lang, id=payment_id))
    
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    lang = db.get_user_language(update.effective_user.id)
    context.user_data.clear()
    await update.message.reply_text(get_text('cancelled', lang))
    return ConversationHandler.END

async def payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data["db"]
    data = query.data
    
    if data.startswith("payment_approve_"):
        payment_id = int(data.replace("payment_approve_", ""))
        payment = db.get_payment_request(payment_id)
        
        if not payment:
            await query.edit_message_caption("❌ الطلب غير موجود")
            return
        
        if payment.status != 'pending':
            await query.edit_message_caption("⚠️ تم معالجة هذا الطلب مسبقاً")
            return
        
        if not db.approve_payment(payment_id, payment.amount):
            await query.edit_message_caption("⚠️ تم معالجة هذا الطلب مسبقاً")
            return
        
        db.add_balance(payment.user_id, payment.amount)
        
        user_lang = db.get_user_language(payment.user_id)
        type_name = "QI Card" if payment.payment_type == 'qi_card' else "ZainCash"
        
        try:
            new_balance = db.get_balance(payment.user_id).balance_iqd
            await context.bot.send_message(
                chat_id=payment.user_id,
                text=get_text('payment_approved', user_lang, 
                             id=payment_id, 
                             amount=payment.amount,
                             balance=new_balance,
                             type_name=type_name)
            )
        except:
            pass
        
        await query.edit_message_caption(
            f"✅ تم تأكيد الطلب #{payment_id}\n"
            f"💰 المبلغ: {payment.amount:,} دينار\n"
            f"👤 المستخدم: {payment.user_id}"
        )
    
    elif data.startswith("payment_reject_"):
        payment_id = int(data.replace("payment_reject_", ""))
        payment = db.get_payment_request(payment_id)
        
        if not payment:
            await query.edit_message_caption("❌ الطلب غير موجود")
            return
        
        if payment.status != 'pending':
            await query.edit_message_caption("⚠️ تم معالجة هذا الطلب مسبقاً")
            return
        
        if not db.reject_payment(payment_id):
            await query.edit_message_caption("⚠️ تم معالجة هذا الطلب مسبقاً")
            return
        
        user_lang = db.get_user_language(payment.user_id)
        type_name = "QI Card" if payment.payment_type == 'qi_card' else "ZainCash"
        
        try:
            await context.bot.send_message(
                chat_id=payment.user_id,
                text=get_text('payment_rejected', user_lang, id=payment_id, type_name=type_name)
            )
        except:
            pass
        
        await query.edit_message_caption(
            f"❌ تم رفض الطلب #{payment_id}\n"
            f"👤 المستخدم: {payment.user_id}"
        )
    
    elif data.startswith("payment_diff_"):
        payment_id = int(data.replace("payment_diff_", ""))
        payment = db.get_payment_request(payment_id)
        
        if not payment:
            await query.edit_message_caption("❌ الطلب غير موجود")
            return
        
        if payment.status != 'pending':
            await query.edit_message_caption("⚠️ تم معالجة هذا الطلب مسبقاً")
            return
        
        context.user_data['diff_payment_id'] = payment_id
        
        await query.edit_message_caption(
            f"💰 طلب #{payment_id}\n\n"
            f"أدخل المبلغ المستلم:"
        )
        return

ASK_DIFF_AMOUNT = 10

async def receive_diff_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    
    payment_id = context.user_data.get('diff_payment_id')
    if not payment_id:
        return
    
    text = update.message.text.strip().replace(',', '').replace(' ', '')
    if not text.isdigit():
        await update.message.reply_text("❌ أدخل رقم صحيح")
        return
    
    actual_amount = int(text)
    payment = db.get_payment_request(payment_id)
    
    if not payment:
        await update.message.reply_text("❌ الطلب غير موجود")
        context.user_data.pop('diff_payment_id', None)
        return
    
    if payment.status != 'pending':
        await update.message.reply_text("⚠️ تم معالجة هذا الطلب مسبقاً")
        context.user_data.pop('diff_payment_id', None)
        return
    
    if not db.set_payment_different_amount(payment_id, actual_amount, f"المبلغ المدعى: {payment.amount}, الفعلي: {actual_amount}"):
        await update.message.reply_text("⚠️ تم معالجة هذا الطلب مسبقاً")
        context.user_data.pop('diff_payment_id', None)
        return
    
    db.add_balance(payment.user_id, actual_amount)
    
    user_lang = db.get_user_language(payment.user_id)
    type_name = "QI Card" if payment.payment_type == 'qi_card' else "ZainCash"
    
    try:
        new_balance = db.get_balance(payment.user_id).balance_iqd
        await context.bot.send_message(
            chat_id=payment.user_id,
            text=get_text('payment_different_amount', user_lang,
                         id=payment_id,
                         claimed=payment.amount,
                         actual=actual_amount,
                         balance=new_balance,
                         type_name=type_name)
        )
    except:
        pass
    
    await update.message.reply_text(
        f"✅ تم تأكيد الطلب #{payment_id} بمبلغ مختلف\n"
        f"💰 المبلغ المدعى: {payment.amount:,}\n"
        f"💰 المبلغ الفعلي: {actual_amount:,}\n"
        f"👤 المستخدم: {payment.user_id}"
    )
    
    context.user_data.pop('diff_payment_id', None)
