STRINGS = {
    'ar': {
        'btn_recharge': '💳 إضافة رصيد آسيا',
        'btn_balance': '💰 رصيدي',
        'btn_records': '📋 سجل الطلبات',
        'btn_xena': '🪙 زینە لایڤ',
        'btn_support': '📞 الدعم',
        'btn_xena_history': '📋 سجل',
        'btn_language': '🌐 تغيير اللغة',
        'btn_retry': '🔄 إعادة المحاولة',
        'btn_back': '⬅️ رجوع',
        'btn_settings': '⚙️ إعدادات',
        'btn_admin': '🎛️ لوحة التحكم',
        'btn_phones': '📱 حالة الهواتف',
        'btn_gallery': '🖼️ صور البطاقات',
        'btn_payment_methods': '💳 طرق الدفع',
        'btn_vodafone': '🔴 Vodafone Cash',
        'btn_track_orders': '📦 تتبع الطلبات',
        
        'welcome': '💎✨ أهلاً {name}!\nفي بوت شحن آسياسيل السريع 🚀\n\n🆔 الآيدي ⤝ {user_id}\n💵 الرصيد ⤝ {balance:,} IQD\n\nيمكنك التحكم بحسابك من خلال الأزرار في الأسفل 👇',
        'balance_msg': '💰 رصيدك الحالي:\n\n💵 {balance:,} IQD',
        
        'recharge_prompt': '🔋 إضافة رصيد آسياسيل\n\n📝 أرسل رقم بطاقة الشحن (13-15 رقم)\n📝 يمكنك إرسال عدة أرقام (كل رقم بسطر)\n\n📷 أو أرسل صورة للبطاقة وسنقرأ الرقم تلقائياً!',
        'card_received': '✅ تم استلام البطاقة\n🎫 رقم العملية: {card_id}',
        'cards_received': '✅ تم استلام {count} بطاقات:\n{jobs_list}',
        'cards_duplicate': '⚠️ بطاقات مستخدمة سابقاً:\n{dup_list}',
        'card_wait': '\nسيتم إشعارك عند اكتمال الشحن 👇',
        'card_verified': '✅ تم شحن البطاقة #{card_id}\n\n💰 المبلغ: {amount:,} دينار\n💵 رصيدك الجديد: {balance:,} دينار',
        'card_failed': '❌ فشل شحن البطاقة #{card_id}\n\nالسبب: رقم البطاقة خاطئ أو مستخدم',
        'card_invalid': '❌ رقم البطاقة غير صالح\n\nأرسل أرقام فقط (13-15 رقم).',
        'card_short': '❌ رقم البطاقة قصير جداً\n\nأدخلت {len} رقم.\nرقم البطاقة يجب أن يكون بين 13-15 رقم.',
        'card_long': '❌ رقم البطاقة طويل جداً\n\nأدخلت {len} رقم.\nرقم البطاقة يجب أن يكون بين 13-15 رقم.',
        
        'ocr_reading': '📷 جاري قراءة الصورة...',
        'ocr_found': '✅ تم قراءة الرقم: {pin}\n\nجاري المعالجة...',
        'ocr_found_multi': '✅ تم قراءة {count} أرقام:\n{pins_list}\n\nجاري المعالجة...',
        'ocr_failed': '❌ فشل قراءة الصورة\n\n{error}\n\n📝 حاول مرة أخرى أو أدخل الرقم يدوياً:',
        'ocr_not_available': '❌ خدمة قراءة الصور غير متوفرة حالياً\n\n📝 الرجاء إدخال الرقم يدوياً:',
        
        'records_title': '📋 سجلاتي\n\n',
        'records_empty': '📋 سجلاتي\n\nلا توجد عمليات سابقة.\n\n🔋 اضغط على \'إضافة رصيد\' للبدء!',
        'records_verified': '✅ #{id}\n💰 {amount:,} دينار\n📅 {date}\n🎴 {pin}\n\n',
        'records_failed': '❌ #{id}\n📅 {date}\n🎴 {pin}\n⚠️ رقم البطاقة خاطئ\n\n',
        'records_processing': '🔄 #{id} جاري المعالجة\n📅 {date}\n🎴 {pin}\n\n',
        'records_pending': '⏳ #{id} قيد الانتظار\n📅 {date}\n🎴 {pin}\n\n',
        'records_summary': '───────────────\n✅ {success} ناجحة\n💰 {amount:,} دينار',
        'records_no_complete': '───────────────\nلا توجد عمليات مكتملة',
        
        'xena_history_title': '📋 سجل المشتريات\n\n',
        'xena_history_empty': '📋 سجل المشتريات\n\nلا توجد عمليات شراء سابقة.\n\n🎮 اضغط على \'Xena Live\' للبدء!',
        
        'retry_title': '🔄 إعادة المحاولة\n\nالبطاقات الفاشلة التي يمكن إعادتها:',
        'retry_empty': '🔄 إعادة المحاولة\n\nلا توجد بطاقات فاشلة يمكن إعادتها.',
        'retry_card': '❌ #{id} - {pin} ({retries}/3)',
        'retry_success': '✅ تم إعادة البطاقة #{id} للمعالجة',
        'retry_failed': '❌ لا يمكن إعادة هذه البطاقة (تجاوزت 3 محاولات)',
        'retry_not_found': '❌ البطاقة غير موجودة',
        
        'language_title': '🌐 اختر اللغة / Choose Language',
        'language_changed': '✅ تم تغيير اللغة إلى العربية',
        
        'support_title': '📞 خدمة العملاء\n\nللتواصل معنا اختر إحدى الطرق:',
        
        'cancelled': 'تم الإلغاء. اختر من القائمة 👇',
        
        'admin_phones_title': '📱 حالة الهواتف\n\n',
        'admin_phones_empty': '📱 لا توجد هواتف مسجلة',
        'admin_phone_info': '{status} {name}\n🔋 {battery}%\n📊 ✅{completed} ❌{failed}\n⏰ {last_seen}\n\n',
        'admin_battery_alert': '⚠️ تنبيه البطارية!\n\n📱 {phone}\n🔋 {battery}%\n\nيرجى شحن الهاتف!',
        
        'admin_gallery_title': '🖼️ صور البطاقات\n\n',
        'admin_gallery_empty': '🖼️ لا توجد صور محفوظة',
        
        'btn_qi_card': '💳 QI Card',
        'btn_zaincash': '💜 ZainCash',
        
        'payment_ask_amount': '💰 كم المبلغ الذي تريد إيداعه؟\n\nأرسل المبلغ بالدينار العراقي (أرقام فقط)',
        'payment_invalid_amount': '❌ المبلغ غير صالح\n\nأرسل أرقام فقط',
        'payment_amount_too_low': '❌ الحد الأدنى للإيداع 1,000 دينار',
        'payment_amount_too_high': '❌ الحد الأقصى للإيداع 10,000,000 دينار',
        'payment_send_to_address': '💳 {type_name}\n\n📍 أرسل المبلغ إلى:\n\n📱 الرقم: {address}\n\n💰 المبلغ: {amount:,} دينار\n\n📷 بعد الإرسال، أرسل صورة إيصال التحويل كدليل',
        'payment_send_proof': '💳 {type_name}\n\n📍 أرسل المبلغ إلى:\n\n📱 الرقم: {address}\n\n📷 بعد الإرسال، أرسل صورة إيصال التحويل كدليل',
        'payment_need_photo': '📷 الرجاء إرسال صورة إيصال التحويل',
        'payment_proof_received': '✅ تم استلام إثبات الدفع\n\n🎫 رقم الطلب: #{id}\n\n⏳ سيتم مراجعة طلبك وإشعارك بالنتيجة',
        'payment_error': '❌ حدث خطأ، حاول مرة أخرى',
        'payment_approved': '✅ تم تأكيد الدفع #{id}\n\n💳 {type_name}\n💰 المبلغ: {amount:,} دينار\n💵 رصيدك الجديد: {balance:,} دينار',
        'payment_rejected': '❌ تم رفض طلب الدفع #{id}\n\n💳 {type_name}\n\nالسبب: الإيصال غير صالح أو لم يتم التحويل',
        'payment_different_amount': '⚠️ طلب الدفع #{id}\n\n💳 {type_name}\n💰 المبلغ المدعى: {claimed:,} دينار\n💰 المبلغ الفعلي: {actual:,} دينار\n\n✅ تم إضافة {actual:,} دينار\n💵 رصيدك الجديد: {balance:,} دينار',
        
        'not_verified': '⏳ حسابك قيد المراجعة\n\nالرجاء الانتظار حتى تتم الموافقة على حسابك',
        'user_blocked': '🚫 حسابك محظور\n\nتواصل مع الدعم للمساعدة',
        'payment_not_configured': '❌ طريقة الدفع غير متوفرة حالياً\n\nيرجى التواصل مع الدعم',
        
        'btn_withdraw': '💵 سحب',
        'btn_binance': '🔶 Binance ID',
        'btn_trc20': '💎 USDT TRC20',
        'withdraw_menu': '💵 سحب الرصيد\n\n💰 رصيدك: {balance:,} IQD\n💵 ما يعادل: ${usd:.2f}\n\n📊 السعر: {rate_iqd:,} IQD = ${rate_usd}\n⚠️ الحد الأدنى: ${minimum}\n\nاختر طريقة السحب:',
        'withdraw_enter_amount': '💵 أدخل المبلغ بالدولار:\n\n💰 رصيدك: {balance:,} IQD\n💵 ما يعادل: ${usd:.2f}\n⚠️ الحد الأدنى: ${minimum}',
        'withdraw_enter_wallet': '💳 أدخل عنوان {type}:\n\n💵 المبلغ: ${amount}',
        'withdraw_insufficient': '❌ رصيدك غير كافي\n\n💰 رصيدك: {balance:,} IQD\n💵 المطلوب: ${amount} ({iqd:,} IQD)',
        'withdraw_minimum': '❌ الحد الأدنى للسحب ${minimum}',
        'withdraw_success': '✅ تم إرسال طلب السحب\n\n💵 المبلغ: ${amount}\n💳 {type}: {wallet}\n\nسيتم معالجة طلبك قريباً',
        'withdraw_approved': '✅ تم تحويل ${amount} إلى {wallet}\n\n💵 رصيدك الجديد: {balance:,} IQD',
        'withdraw_rejected': '❌ تم رفض طلب السحب ${amount}\n\n💵 تم إرجاع المبلغ لرصيدك',
    },
    'en': {
        'btn_recharge': '💳 Add Asiacell Balance',
        'btn_balance': '💰 My Balance',
        'btn_records': '📋 Records',
        'btn_xena': '🎮 Xena Live',
        'btn_support': '📞 Support',
        'btn_xena_history': '📋 History',
        'btn_language': '🌐 Language',
        'btn_retry': '🔄 Retry',
        'btn_back': '⬅️ Back',
        'btn_settings': '⚙️ Settings',
        'btn_admin': '🎛️ Admin Panel',
        'btn_phones': '📱 Phone Status',
        'btn_gallery': '🖼️ Card Gallery',
        'btn_payment_methods': '💳 Payment Methods',
        'btn_vodafone': '🔴 Vodafone Cash',
        'btn_track_orders': '📦 Track Orders',
        
        'welcome': '💎✨ Welcome {name}!\nAsiacell Fast Recharge Bot 🚀\n\n🆔 ID ⤝ {user_id}\n💵 Balance ⤝ {balance:,} IQD\n\nUse the buttons below to navigate 👇',
        'balance_msg': '💰 Your Balance:\n\n💵 {balance:,} IQD',
        
        'recharge_prompt': '🔋 Add Asiacell Balance\n\n📝 Send card number (13-15 digits)\n📝 You can send multiple numbers (one per line)\n\n📷 Or send a photo and we\'ll read it automatically!',
        'card_received': '✅ Card received\n🎫 Job ID: {card_id}',
        'cards_received': '✅ Received {count} cards:\n{jobs_list}',
        'cards_duplicate': '⚠️ Previously used cards:\n{dup_list}',
        'card_wait': '\nYou will be notified when complete 👇',
        'card_verified': '✅ Card #{card_id} verified\n\n💰 Amount: {amount:,} IQD\n💵 New balance: {balance:,} IQD',
        'card_failed': '❌ Card #{card_id} failed\n\nReason: Invalid or used card',
        'card_invalid': '❌ Invalid card number\n\nSend digits only (13-15 digits).',
        'card_short': '❌ Card number too short\n\nYou entered {len} digits.\nCard number must be 13-15 digits.',
        'card_long': '❌ Card number too long\n\nYou entered {len} digits.\nCard number must be 13-15 digits.',
        
        'ocr_reading': '📷 Reading image...',
        'ocr_found': '✅ Found number: {pin}\n\nProcessing...',
        'ocr_found_multi': '✅ Found {count} numbers:\n{pins_list}\n\nProcessing...',
        'ocr_failed': '❌ Failed to read image\n\n{error}\n\n📝 Try again or enter manually:',
        'ocr_not_available': '❌ Image reading not available\n\n📝 Please enter number manually:',
        
        'records_title': '📋 My Records\n\n',
        'records_empty': '📋 My Records\n\nNo previous transactions.\n\n🔋 Press \'Add Balance\' to start!',
        'records_verified': '✅ #{id}\n💰 {amount:,} IQD\n📅 {date}\n🎴 {pin}\n\n',
        'records_failed': '❌ #{id}\n📅 {date}\n🎴 {pin}\n⚠️ Invalid card number\n\n',
        'records_processing': '🔄 #{id} Processing\n📅 {date}\n🎴 {pin}\n\n',
        'records_pending': '⏳ #{id} Pending\n📅 {date}\n🎴 {pin}\n\n',
        'records_summary': '───────────────\n✅ {success} successful\n💰 {amount:,} IQD',
        'records_no_complete': '───────────────\nNo completed transactions',
        
        'xena_history_title': '📋 Purchase History\n\n',
        'xena_history_empty': '📋 Purchase History\n\nNo previous purchases.\n\n🎮 Press \'Xena Live\' to start!',
        
        'retry_title': '🔄 Retry Cards\n\nFailed cards that can be retried:',
        'retry_empty': '🔄 Retry Cards\n\nNo failed cards to retry.',
        'retry_card': '❌ #{id} - {pin} ({retries}/3)',
        'retry_success': '✅ Card #{id} queued for retry',
        'retry_failed': '❌ Cannot retry this card (exceeded 3 attempts)',
        'retry_not_found': '❌ Card not found',
        
        'language_title': '🌐 اختر اللغة / Choose Language',
        'language_changed': '✅ Language changed to English',
        
        'support_title': '📞 Customer Support\n\nContact us:',
        
        'cancelled': 'Cancelled. Choose from menu 👇',
        
        'admin_phones_title': '📱 Phone Status\n\n',
        'admin_phones_empty': '📱 No registered phones',
        'admin_phone_info': '{status} {name}\n🔋 {battery}%\n📊 ✅{completed} ❌{failed}\n⏰ {last_seen}\n\n',
        'admin_battery_alert': '⚠️ Battery Alert!\n\n📱 {phone}\n🔋 {battery}%\n\nPlease charge the phone!',
        
        'admin_gallery_title': '🖼️ Card Images\n\n',
        'admin_gallery_empty': '🖼️ No saved images',
        
        'btn_qi_card': '💳 QI Card',
        'btn_zaincash': '💜 ZainCash',
        
        'payment_ask_amount': '💰 How much do you want to deposit?\n\nSend the amount in IQD (numbers only)',
        'payment_invalid_amount': '❌ Invalid amount\n\nSend numbers only',
        'payment_amount_too_low': '❌ Minimum deposit is 1,000 IQD',
        'payment_amount_too_high': '❌ Maximum deposit is 10,000,000 IQD',
        'payment_send_to_address': '💳 {type_name}\n\n📍 Send amount to:\n\n📱 {address}\n\n💰 Amount: {amount:,} IQD\n\n📷 After sending, send a photo of the transfer receipt as proof',
        'payment_send_proof': '💳 {type_name}\n\n📍 Send amount to:\n\n📱 {address}\n\n📷 After sending, send a photo of the transfer receipt as proof',
        'payment_need_photo': '📷 Please send a photo of the transfer receipt',
        'payment_proof_received': '✅ Payment proof received\n\n🎫 Request ID: #{id}\n\n⏳ Your request will be reviewed and you will be notified',
        'payment_error': '❌ An error occurred, please try again',
        'payment_approved': '✅ Payment #{id} confirmed\n\n💳 {type_name}\n💰 Amount: {amount:,} IQD\n💵 New balance: {balance:,} IQD',
        'payment_rejected': '❌ Payment request #{id} rejected\n\n💳 {type_name}\n\nReason: Invalid receipt or transfer not found',
        'payment_different_amount': '⚠️ Payment request #{id}\n\n💳 {type_name}\n💰 Claimed amount: {claimed:,} IQD\n💰 Actual amount: {actual:,} IQD\n\n✅ Added {actual:,} IQD\n💵 New balance: {balance:,} IQD',
        
        'not_verified': '⏳ Your account is under review\n\nPlease wait for approval',
        'user_blocked': '🚫 Your account is blocked\n\nContact support for help',
        'payment_not_configured': '❌ This payment method is not available\n\nPlease contact support',
        
        'btn_withdraw': '💵 Withdraw',
        'btn_binance': '🔶 Binance ID',
        'btn_trc20': '💎 USDT TRC20',
        'withdraw_menu': '💵 Withdraw Balance\n\n💰 Balance: {balance:,} IQD\n💵 Equivalent: ${usd:.2f}\n\n📊 Rate: {rate_iqd:,} IQD = ${rate_usd}\n⚠️ Minimum: ${minimum}\n\nChoose withdrawal method:',
        'withdraw_enter_amount': '💵 Enter amount in USD:\n\n💰 Balance: {balance:,} IQD\n💵 Equivalent: ${usd:.2f}\n⚠️ Minimum: ${minimum}',
        'withdraw_enter_wallet': '💳 Enter {type} address:\n\n💵 Amount: ${amount}',
        'withdraw_insufficient': '❌ Insufficient balance\n\n💰 Balance: {balance:,} IQD\n💵 Required: ${amount} ({iqd:,} IQD)',
        'withdraw_minimum': '❌ Minimum withdrawal is ${minimum}',
        'withdraw_success': '✅ Withdrawal request submitted\n\n💵 Amount: ${amount}\n💳 {type}: {wallet}\n\nYour request will be processed soon',
        'withdraw_approved': '✅ ${amount} sent to {wallet}\n\n💵 New balance: {balance:,} IQD',
        'withdraw_rejected': '❌ Withdrawal request ${amount} rejected\n\n💵 Amount refunded to balance',
    }
}

def get_text(key: str, lang: str = 'ar', **kwargs) -> str:
    text = STRINGS.get(lang, STRINGS['ar']).get(key, STRINGS['ar'].get(key, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except:
            return text
    return text

def get_btn(key: str, lang: str = 'ar') -> str:
    return get_text(key, lang)
