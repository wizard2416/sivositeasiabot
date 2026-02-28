import logging
import asyncio
import os
import io
import csv
import threading
import requests
import urllib3
from datetime import datetime, timezone, timedelta
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from flask import Flask, request, jsonify, send_file, render_template, session, redirect, url_for, flash, Response, g
from functools import wraps
import config
from src.services import Database
from src.services.lang import get_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

IRAQ_TZ = timezone(timedelta(hours=3))

app = Flask(__name__, template_folder='templates', static_folder='static', static_url_path='/static')
app.secret_key = os.environ.get('SESSION_SECRET') or os.urandom(24).hex()
db = None
bot_app = None
bot_loop = None
card_processing_paused = False
bot_paused = False
action_counter = 0

# Auto-initialize database for production (gunicorn)
if config.DATABASE_URL and db is None:
    try:
        db = Database(config.DATABASE_URL)
        logger.info("Database auto-initialized for production")
    except Exception as e:
        logger.error(f"Failed to auto-initialize database: {e}")

def trigger_action_backup():
    global action_counter
    action_counter += 1
    if action_counter >= 2:
        action_counter = 0
        if bot_app and bot_loop:
            from main import send_database_backup
            asyncio.run_coroutine_threadsafe(
                send_database_backup(bot_app, f"After 2 admin actions"),
                bot_loop
            )

@app.template_filter('iraq_time')
def iraq_time_filter(dt_str):
    if not dt_str:
        return '-'
    try:
        if isinstance(dt_str, str):
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        else:
            dt = dt_str
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        iraq_dt = dt.astimezone(IRAQ_TZ)
        return iraq_dt.strftime('%Y-%m-%d %H:%M')
    except:
        return dt_str[:16] if len(str(dt_str)) > 16 else str(dt_str)

@app.context_processor
def utility_processor():
    def iraq_now():
        return datetime.now(IRAQ_TZ).strftime('%Y-%m-%d %H:%M:%S')
    return dict(iraq_now=iraq_now)

def format_datetime(dt):
    """Convert datetime object to string for templates."""
    if dt is None:
        return ''
    if hasattr(dt, 'strftime'):
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    return str(dt) if dt else ''

PROXY_MODE = os.environ.get('PROXY_MODE', '').lower() == 'true'
PRODUCTION_URL = os.environ.get('PRODUCTION_URL', 'https://sivoservers.replit.app')

EMPLOYEE_USERNAME = os.environ.get('EMPLOYEE_USERNAME', 'recharge customer support')
EMPLOYEE_PASSWORD = os.environ.get('EMPLOYEE_PASSWORD', 'T2zPXosoYHIfoABv')


def require_admin_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

def require_employee_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('employee_logged_in'):
            return redirect(url_for('employee_login'))
        return f(*args, **kwargs)
    return decorated

def init_api(database: Database, telegram_app=None, event_loop=None):
    global db, bot_app, bot_loop
    db = database
    bot_app = telegram_app
    bot_loop = event_loop

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        valid_tokens = [t for t in [config.PHONE_API_TOKEN] if t]
        if not token or token not in valid_tokens:
            logger.warning("Unauthorized API access attempt")
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

def proxy_to_production(path):
    """Forward request to production server."""
    target_url = f"{PRODUCTION_URL}{path}"
    headers = {k: v for k, v in request.headers if k.lower() not in ('host', 'content-length')}
    
    try:
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=request.get_data(),
            params=request.args,
            timeout=30,
            allow_redirects=False,
            verify=False
        )
        
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        response_headers = [(k, v) for k, v in resp.raw.headers.items() if k.lower() not in excluded_headers]
        
        return Response(resp.content, resp.status_code, response_headers)
    except Exception as e:
        logger.error(f"Proxy error: {e}")
        return jsonify({"error": "Proxy failed"}), 502

def send_telegram_message(user_id: int, text: str):
    """Send a Telegram message to a user via API."""
    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        response = requests.post(url, json={
            "chat_id": user_id,
            "text": text,
            "parse_mode": "HTML"
        }, timeout=10)
        return response.json().get('ok', False)
    except Exception as e:
        logger.error(f"Failed to send Telegram message to {user_id}: {e}")
        return False

@app.route('/', methods=['GET'])
def root():
    try:
        return render_template('landing.html')
    except Exception as e:
        logger.error(f"Error rendering landing page: {e}")
        return f"Welcome to Sivosys Recharge API", 200

@app.route('/download/apk', methods=['GET'])
def download_apk():
    """Download the Android APK zip file."""
    import glob
    zip_files = (glob.glob('static/AsiacellRecharge*.zip') + 
                 glob.glob('static/SivosysRecharge*.zip') +
                 glob.glob('static/downloads/*.zip'))
    if zip_files:
        latest = max(zip_files, key=os.path.getmtime)
        return send_file(latest, as_attachment=True)
    return "APK not found", 404

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    """Download files from static/downloads/."""
    if not filename.endswith('.zip'):
        return "Invalid file type", 400
    filepath = f'static/downloads/{filename}'
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True, download_name=filename)
    return "File not found", 404

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

@app.before_request
def handle_proxy():
    """Intercept API requests and proxy to production when in proxy mode."""
    if PROXY_MODE and request.path.startswith('/api/'):
        logger.info(f"Proxying {request.path} to production")
        return proxy_to_production(request.path)

@app.route('/download/android', methods=['GET'])
def download_android():
    zip_path = os.path.join(os.path.dirname(__file__), 'apk.zip')
    if os.path.exists(zip_path):
        return send_file(zip_path, as_attachment=True, download_name='SystemAsiacell.zip')
    return jsonify({"error": "File not found"}), 404

@app.route('/api/health', methods=['GET'])
def api_health_check():
    """Health check endpoint for monitoring server status"""
    try:
        if db:
            db.execute("SELECT 1")
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "database": "connected" if db else "disconnected"
        }), 200
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500

@app.route('/api/phone/register', methods=['POST'])
@require_auth
def register_phone():
    if not db:
        return jsonify({"error": "Database not initialized"}), 500
    
    data = request.get_json()
    phone_id = data.get('phone_id')
    name = data.get('name')
    battery_level = data.get('battery_level', 100)
    
    if not phone_id:
        return jsonify({"error": "phone_id required"}), 400
    
    phone = db.register_phone(phone_id, name)
    if battery_level:
        db.update_phone_battery(phone_id, battery_level)
    
    logger.info(f"Phone registered: {phone_id} ({name})")
    
    return jsonify({
        "success": True,
        "phone": {
            "phone_id": phone.phone_id,
            "name": phone.name,
            "status": "online"
        }
    })

@app.route('/api/job/pending', methods=['GET'])
@require_auth
def get_pending_job():
    global card_processing_paused
    
    if not db:
        return jsonify({"error": "Database not initialized"}), 500
    
    phone_id = request.headers.get('X-Phone-ID')
    battery_level = request.headers.get('X-Battery-Level')
    
    if phone_id:
        db.register_phone(phone_id)
        if battery_level:
            low_battery = db.update_phone_battery(phone_id, int(battery_level))
            if low_battery is not None:
                notify_admin_battery(phone_id, low_battery)
    
    if card_processing_paused:
        return jsonify({"status": "paused", "job": None})
    
    card = db.get_pending_card_vip_priority(phone_id)
    if not card:
        card = db.get_pending_card(is_vip_first=False)
    if not card:
        return jsonify({"status": "no_job", "job": None})
    
    db.update_card_status(card.id, "processing", phone_id=phone_id)
    
    ussd_code = f"*133*{card.pin}#"
    logger.info(f"Job {card.id} sent to phone {phone_id}, PIN: {card.pin[:4]}****, USSD: *133*****#")
    
    return jsonify({
        "status": "job",
        "job": {
            "id": card.id,
            "pin": card.pin,
            "ussd_code": ussd_code,
            "user_id": card.user_id
        }
    })

@app.route('/api/job/complete', methods=['POST'])
@require_auth
def complete_job():
    if not db:
        return jsonify({"error": "Database not initialized"}), 500
    
    data = request.get_json()
    job_id = data.get('job_id') or data.get('card_id')
    status = data.get('status', '').lower() if data.get('status') else ''
    result_message = data.get('result_message', '') or data.get('response', '') or data.get('message', '')
    amount = data.get('amount', 0)
    phone_id = request.headers.get('X-Phone-ID') or data.get('phone_id')
    card_type = data.get('card_type', 'recharge')
    
    # Determine success from multiple indicators
    success_statuses = ['verified', 'success', 'completed', 'ok', 'done']
    raw_success = data.get('success', False)
    # Handle string "true"/"false" values
    if isinstance(raw_success, str):
        success = raw_success.lower() in ['true', '1', 'yes']
    else:
        success = bool(raw_success)
    if not success and status in success_statuses:
        success = True
    # Also check result_message for success indicators
    if not success and result_message:
        # Arabic, English, and Kurdish success keywords
        success_keywords = [
            'تم', 'نجح', 'success', 'added', 'شحن', 'اضافة', 'رصيدك',  # Arabic/English
            'سەرکەوتوو', 'داخل کرد', 'بالانس', 'دینار'  # Kurdish
        ]
        if any(kw in result_message.lower() for kw in success_keywords):
            success = True
        # Also check for Kurdish patterns with amount (multiple spellings)
        kurdish_patterns = [
            'دینارت به سەرکەوتووی',
            'دینارت بە سەرکەوتوویی',
            'دینارت بە سةرکةوتوویی',
            'سەرکەوتوویی داخل کرد',
            'سةرکةوتوویی داخل کرد'
        ]
        if any(pattern in result_message for pattern in kurdish_patterns):
            success = True
    
    logger.info(f"Job complete request: job_id={job_id}, success={success}, amount={amount}, status={status}")
    logger.info(f"Raw data received: {data}")
    logger.info(f"Result message: {result_message[:300] if result_message else 'empty'}")
    
    if not job_id:
        return jsonify({"error": "job_id required"}), 400
    
    card = db.get_card_by_id(job_id)
    
    if not card:
        return jsonify({"error": "Job not found"}), 404
    
    if amount == 0 and result_message:
        amount = parse_amount_from_response(result_message)
        logger.info(f"Parsed amount from response: {amount}")
    
    if phone_id:
        db.update_phone_stats(phone_id, success)
    
    # Accept success=true even if amount couldn't be parsed
    # This prevents successful cards from being marked as failed
    if success:
        db.update_card_status(job_id, "verified", amount=amount, phone_id=phone_id)
        if amount > 0:
            db.add_balance(card.user_id, amount, transaction_type='card_recharge', reference_id=str(job_id))
        
        logger.info(f"Job {job_id} verified by {phone_id}: +{amount} IQD for user {card.user_id}")
        
        if bot_app and bot_loop:
            try:
                asyncio.run_coroutine_threadsafe(
                    notify_user_success(card.user_id, job_id, amount), 
                    bot_loop
                )
            except Exception as e:
                logger.error(f"Failed to notify user: {e}")
        
        try:
            notify_external_webhook(job_id, "verified", amount, result_message)
        except Exception as e:
            logger.error(f"External webhook notify error: {e}")
        
        return jsonify({
            "success": True,
            "message": f"Verified - Added {amount} IQD" if amount > 0 else "Verified (amount pending)",
            "user_id": card.user_id,
            "new_balance": db.get_balance(card.user_id).balance_iqd
        })
    else:
        db.update_card_status(job_id, "failed", phone_id=phone_id)
        logger.info(f"Job {job_id} failed: {result_message}")
        
        if bot_app and bot_loop:
            try:
                asyncio.run_coroutine_threadsafe(
                    notify_user_failed(card.user_id, job_id), 
                    bot_loop
                )
            except Exception as e:
                logger.error(f"Failed to notify user: {e}")
        
        try:
            notify_external_webhook(job_id, "failed", 0, result_message)
        except Exception as e:
            logger.error(f"External webhook notify error: {e}")
        
        return jsonify({
            "success": False,
            "message": "Card verification failed"
        })

async def notify_user_success(user_id: int, job_id: int, amount: int):
    if bot_app:
        try:
            lang = db.get_user_language(user_id)
            await bot_app.bot.send_message(
                chat_id=user_id,
                text=get_text('card_verified', lang, card_id=job_id, amount=amount, 
                             balance=db.get_balance(user_id).balance_iqd)
            )
        except Exception as e:
            logger.error(f"Failed to send notification to {user_id}: {e}")

async def notify_user_failed(user_id: int, job_id: int):
    if bot_app:
        try:
            lang = db.get_user_language(user_id)
            await bot_app.bot.send_message(
                chat_id=user_id,
                text=get_text('card_failed', lang, card_id=job_id)
            )
        except Exception as e:
            logger.error(f"Failed to send notification to {user_id}: {e}")

def parse_amount_from_response(response: str) -> int:
    """Parse amount from USSD response message."""
    import re
    response = response.replace(',', '').replace('،', '')
    
    logger.debug(f"Parsing amount from response: {response[:200] if response else 'empty'}")
    
    patterns = [
        r'(\d+)\s*(?:IQD|دينار|dinars?)',
        r'(?:added|اضافة|تم اضافة|تمت الاضافة|تم شحن)\s*(\d+)',
        r'(\d+)\s*(?:تم|شحن|اضافة)',
        r'(?:balance|رصيد|الرصيد)\s*[:\s]*(\d+)',
        r'(\d{3,6})\s*(?:balance|رصيد)',
        r'شحن\s*بقيمة\s*(\d+)',
        r'(\d{4,6})'
    ]
    for pattern in patterns:
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            amount = int(match.group(1))
            if 250 <= amount <= 100000:
                logger.debug(f"Parsed amount: {amount}")
                return amount
    
    logger.warning(f"Could not parse amount from response: {response[:200] if response else 'empty'}")
    return 0


def notify_admin_battery(phone_id: str, battery_level: int):
    if bot_app and bot_loop and config.ADMIN_USER_IDS:
        try:
            phone = db.get_all_phones()
            phone_name = phone_id
            for p in phone:
                if p.phone_id == phone_id:
                    phone_name = p.name
                    break
            
            for admin_id in config.ADMIN_USER_IDS:
                asyncio.run_coroutine_threadsafe(
                    send_battery_alert(admin_id, phone_name, battery_level),
                    bot_loop
                )
        except Exception as e:
            logger.error(f"Failed to send battery alert: {e}")

async def send_battery_alert(admin_id: int, phone_name: str, battery_level: int):
    if bot_app:
        try:
            await bot_app.bot.send_message(
                chat_id=admin_id,
                text=f"⚠️ Battery Alert!\n\n"
                     f"📱 {phone_name}\n"
                     f"🪫 {battery_level}%\n\n"
                     f"Please charge the phone!"
            )
        except Exception as e:
            logger.error(f"Failed to send battery alert: {e}")

@app.route('/api/pending', methods=['GET'])
@require_auth
def get_pending_card():
    return get_pending_job()

@app.route('/api/verify', methods=['POST'])
@require_auth
def verify_card():
    return complete_job()

@app.route('/api/stats', methods=['GET'])
@require_auth
def get_stats():
    if not db:
        return jsonify({"error": "Database not initialized"}), 500
    
    stats = db.get_stats()
    online_phones = len(db.get_online_phones())
    stats['online_phones'] = online_phones
    
    return jsonify(stats)

@app.route('/api/phones', methods=['GET'])
@require_auth
def get_phones():
    if not db:
        return jsonify({"error": "Database not initialized"}), 500
    
    phones = db.get_all_phones()
    return jsonify({
        "phones": [
            {
                "phone_id": p.phone_id,
                "name": p.name,
                "battery_level": p.battery_level,
                "status": p.status,
                "last_seen": p.last_seen,
                "jobs_completed": p.jobs_completed,
                "jobs_failed": p.jobs_failed
            }
            for p in phones
        ]
    })

@app.route('/api/phone/heartbeat', methods=['POST'])
@require_auth
def phone_heartbeat():
    if not db:
        return jsonify({"error": "Database not initialized"}), 500
    
    data = request.get_json()
    phone_id = data.get('phone_id') or request.headers.get('X-Phone-ID')
    battery_level = data.get('battery_level', 100)
    
    if phone_id:
        db.register_phone(phone_id)
        low_battery = db.update_phone_battery(phone_id, battery_level)
        if low_battery is not None:
            notify_admin_battery(phone_id, low_battery)
    
    logger.info(f"Phone heartbeat: {phone_id}, battery={battery_level}%")
    return jsonify({"success": True})

@app.route('/api/phone/settings', methods=['GET'])
@require_auth
def phone_settings():
    return jsonify({
        "active_sim_slot": 1,
        "poll_interval_ms": 3000
    })


@app.route('/status', methods=['GET'])
def phone_status_page():
    """Public status page showing phone stats - only active phones from last 24 hours"""
    try:
        if not db:
            return "Database not initialized", 500
        
        all_phones = db.get_all_phones() or []
        twenty_four_hours_ago = datetime.now(IRAQ_TZ) - timedelta(hours=24)
        phones = []
        for p in all_phones:
            if p.last_seen:
                try:
                    last_seen = p.last_seen
                    if last_seen.tzinfo is None:
                        last_seen = last_seen.replace(tzinfo=timezone.utc)
                    last_seen_iraq = last_seen.astimezone(IRAQ_TZ)
                    if last_seen_iraq > twenty_four_hours_ago:
                        phones.append(p)
                except:
                    pass
        stats = db.get_stats() if hasattr(db, 'get_stats') else {}
    except Exception as e:
        logger.error(f"Status page error: {e}")
        phones = []
        stats = {}
    
    html = """
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>حالة الأجهزة</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: linear-gradient(135deg, #0a1929 0%, #132f4c 100%); min-height: 100vh; color: #fff; padding: 20px; }
            .container { max-width: 800px; margin: 0 auto; }
            h1 { text-align: center; margin-bottom: 30px; font-size: 28px; color: #4fc3f7; }
            .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-bottom: 30px; }
            .stat-card { background: rgba(255,255,255,0.1); border-radius: 12px; padding: 20px; text-align: center; }
            .stat-value { font-size: 32px; font-weight: bold; color: #4fc3f7; }
            .stat-label { font-size: 14px; color: #90caf9; margin-top: 5px; }
            .phone-card { background: rgba(255,255,255,0.1); border-radius: 12px; padding: 20px; margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center; }
            .phone-info { flex: 1; }
            .phone-name { font-size: 18px; font-weight: bold; margin-bottom: 5px; }
            .phone-stats { font-size: 14px; color: #90caf9; }
            .battery { display: flex; align-items: center; gap: 10px; }
            .battery-bar { width: 60px; height: 24px; background: #333; border-radius: 4px; overflow: hidden; position: relative; }
            .battery-bar::after { content: ''; position: absolute; right: -4px; top: 6px; width: 4px; height: 12px; background: #333; border-radius: 0 2px 2px 0; }
            .battery-level { height: 100%; transition: width 0.3s; }
            .battery-high { background: linear-gradient(90deg, #4caf50, #8bc34a); }
            .battery-medium { background: linear-gradient(90deg, #ff9800, #ffc107); }
            .battery-low { background: linear-gradient(90deg, #f44336, #ff5722); }
            .status-badge { padding: 4px 12px; border-radius: 20px; font-size: 12px; }
            .status-online { background: rgba(76, 175, 80, 0.3); color: #4caf50; }
            .status-offline { background: rgba(244, 67, 54, 0.3); color: #f44336; }
            .refresh { text-align: center; margin-top: 20px; }
            .refresh a { color: #4fc3f7; text-decoration: none; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📱 حالة الأجهزة</h1>
            <div class="stats">
    """
    
    total_completed = sum(p.jobs_completed for p in phones)
    total_failed = sum(p.jobs_failed for p in phones)
    online_count = len([p for p in phones if p.status == 'online'])
    
    html += f"""
                <div class="stat-card">
                    <div class="stat-value">{online_count}</div>
                    <div class="stat-label">أجهزة متصلة</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{total_completed}</div>
                    <div class="stat-label">بطاقات ناجحة</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{total_failed}</div>
                    <div class="stat-label">بطاقات فاشلة</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{total_completed + total_failed}</div>
                    <div class="stat-label">المجموع</div>
                </div>
            </div>
    """
    
    for phone in phones:
        battery = phone.battery_level or 0
        battery_class = 'battery-high' if battery > 50 else ('battery-medium' if battery > 20 else 'battery-low')
        status_class = 'status-online' if phone.status == 'online' else 'status-offline'
        status_text = 'متصل' if phone.status == 'online' else 'غير متصل'
        name = phone.name or phone.phone_id[:8]
        
        html += f"""
            <div class="phone-card">
                <div class="phone-info">
                    <div class="phone-name">📱 {name}</div>
                    <div class="phone-stats">✅ {phone.jobs_completed} ناجحة | ❌ {phone.jobs_failed} فاشلة</div>
                </div>
                <div class="battery">
                    <div class="battery-bar">
                        <div class="battery-level {battery_class}" style="width: {battery}%"></div>
                    </div>
                    <span>{battery}%</span>
                </div>
                <span class="status-badge {status_class}">{status_text}</span>
            </div>
        """
    
    html += """
            <div class="refresh">
                <a href="/status">🔄 تحديث</a>
            </div>
        </div>
        <script>setTimeout(() => location.reload(), 30000);</script>
    </body>
    </html>
    """
    
    return html


# ============ EXTERNAL API ============

def _validate_webhook_url(url):
    if not url:
        return True
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False
        if not parsed.hostname:
            return False
        blocked = ['localhost', '127.0.0.1', '0.0.0.0', '169.254.169.254', '10.', '192.168.', '172.16.']
        host = parsed.hostname.lower()
        for b in blocked:
            if host == b or host.startswith(b):
                return False
        return True
    except Exception:
        return False


def require_external_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key', '') or request.args.get('api_key', '')
        if not api_key or not db:
            return jsonify({"error": "Unauthorized"}), 401
        
        try:
            cursor = db.execute(
                "SELECT id, key_name, webhook_url, is_active FROM external_api_keys WHERE api_key = %s",
                (api_key,)
            )
            row = cursor.fetchone()
            if not row:
                return jsonify({"error": "Invalid API key"}), 401
            if not row['is_active']:
                return jsonify({"error": "API key disabled"}), 403
            
            g.ext_api_key_id = row['id']
            g.ext_api_key_name = row['key_name']
            g.ext_api_webhook_url = row.get('webhook_url', '') or ''
        except Exception as e:
            logger.error(f"External API auth error: {e}")
            try:
                db.rollback()
            except Exception:
                pass
            return jsonify({"error": "Authentication failed"}), 500
        
        return f(*args, **kwargs)
    return decorated


@app.route('/api/external/submit-card', methods=['POST'])
@require_external_api_key
def external_submit_card():
    if not db:
        return jsonify({"error": "Database not initialized"}), 500
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400
    
    pin = data.get('pin', '').strip()
    external_ref = data.get('external_ref', '') or data.get('reference', '') or ''
    webhook_url = data.get('webhook_url', '') or g.ext_api_webhook_url
    
    if not pin:
        return jsonify({"error": "pin is required"}), 400
    
    if not pin.isdigit() or len(pin) < 10:
        return jsonify({"error": "Invalid PIN format"}), 400
    
    if webhook_url and not _validate_webhook_url(webhook_url):
        return jsonify({"error": "Invalid webhook URL"}), 400
    
    try:
        external_user_id = 0
        card_id = db.add_card(external_user_id, pin, 0)
        
        pin_masked = pin[:4] + '*' * (len(pin) - 4) if len(pin) > 4 else '****'
        
        db.execute("""
            INSERT INTO external_cards (external_ref, card_id, pin, source, api_key_name, webhook_url, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'pending')
        """, (external_ref, card_id, pin_masked, g.ext_api_key_name, g.ext_api_key_name, webhook_url))
        db.commit()
        
        logger.info(f"External card submitted: card_id={card_id}, ref={external_ref}, source={g.ext_api_key_name}")
        
        return jsonify({
            "success": True,
            "card_id": card_id,
            "external_ref": external_ref,
            "status": "pending",
            "message": "Card submitted for processing"
        }), 201
    
    except Exception as e:
        logger.error(f"External submit card error: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return jsonify({"error": "Failed to submit card"}), 500


@app.route('/api/external/submit-cards', methods=['POST'])
@require_external_api_key
def external_submit_cards_batch():
    if not db:
        return jsonify({"error": "Database not initialized"}), 500
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400
    
    cards = data.get('cards', [])
    webhook_url = data.get('webhook_url', '') or g.ext_api_webhook_url
    
    if not cards or not isinstance(cards, list):
        return jsonify({"error": "cards array is required"}), 400
    
    if len(cards) > 50:
        return jsonify({"error": "Maximum 50 cards per batch"}), 400
    
    results = []
    try:
        for card_data in cards:
            pin = str(card_data.get('pin', '')).strip()
            external_ref = card_data.get('external_ref', '') or card_data.get('reference', '') or ''
            
            if not pin or not pin.isdigit() or len(pin) < 10:
                results.append({"pin": pin[:4] + "****", "success": False, "error": "Invalid PIN"})
                continue
            
            external_user_id = 0
            card_id = db.add_card(external_user_id, pin, 0)
            
            pin_masked = pin[:4] + '*' * (len(pin) - 4) if len(pin) > 4 else '****'
            db.execute("""
                INSERT INTO external_cards (external_ref, card_id, pin, source, api_key_name, webhook_url, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'pending')
            """, (external_ref, card_id, pin_masked, g.ext_api_key_name, g.ext_api_key_name, webhook_url))
            
            results.append({
                "card_id": card_id,
                "external_ref": external_ref,
                "success": True,
                "status": "pending"
            })
        
        db.commit()
        logger.info(f"External batch: {len(results)} cards from {g.ext_api_key_name}")
        
        return jsonify({
            "success": True,
            "total": len(results),
            "submitted": sum(1 for r in results if r.get('success')),
            "results": results
        }), 201
    
    except Exception as e:
        logger.error(f"External batch submit error: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return jsonify({"error": "Failed to submit cards"}), 500


@app.route('/api/external/card-status/<int:card_id>', methods=['GET'])
@require_external_api_key
def external_card_status(card_id):
    if not db:
        return jsonify({"error": "Database not initialized"}), 500
    
    try:
        cursor = db.execute("""
            SELECT ec.id, ec.external_ref, ec.card_id, ec.status, ec.amount, ec.result_message,
                   ec.created_at, ec.processed_at,
                   c.status as card_status, c.amount as card_amount
            FROM external_cards ec
            LEFT JOIN cards c ON ec.card_id = c.id
            WHERE ec.card_id = %s AND ec.api_key_name = %s
        """, (card_id, g.ext_api_key_name))
        row = cursor.fetchone()
        
        if not row:
            return jsonify({"error": "Card not found"}), 404
        
        return jsonify({
            "card_id": row['card_id'],
            "external_ref": row['external_ref'] or '',
            "status": row['status'],
            "amount": row['amount'] or row['card_amount'] or 0,
            "result_message": row['result_message'] or '',
            "created_at": str(row['created_at']) if row['created_at'] else '',
            "processed_at": str(row['processed_at']) if row['processed_at'] else ''
        })
    
    except Exception as e:
        logger.error(f"External card status error: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return jsonify({"error": "Failed to get status"}), 500


@app.route('/api/external/cards', methods=['GET'])
@require_external_api_key
def external_list_cards():
    if not db:
        return jsonify({"error": "Database not initialized"}), 500
    
    try:
        status_filter = request.args.get('status', '')
        limit = min(int(request.args.get('limit', 50)), 200)
        offset = int(request.args.get('offset', 0))
        
        query = """
            SELECT ec.id, ec.external_ref, ec.card_id, ec.status, ec.amount, ec.result_message,
                   ec.created_at, ec.processed_at,
                   c.status as card_status, c.amount as card_amount
            FROM external_cards ec
            LEFT JOIN cards c ON ec.card_id = c.id
            WHERE ec.api_key_name = %s
        """
        params = [g.ext_api_key_name]
        
        if status_filter:
            query += " AND ec.status = %s"
            params.append(status_filter)
        
        query += " ORDER BY ec.created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        cursor = db.execute(query, tuple(params))
        rows = cursor.fetchall()
        
        cards = []
        for row in rows:
            cards.append({
                "card_id": row['card_id'],
                "external_ref": row['external_ref'] or '',
                "status": row['status'],
                "amount": row['amount'] or row['card_amount'] or 0,
                "result_message": row['result_message'] or '',
                "created_at": str(row['created_at']) if row['created_at'] else '',
                "processed_at": str(row['processed_at']) if row['processed_at'] else ''
            })
        
        return jsonify({
            "cards": cards,
            "total": len(cards),
            "limit": limit,
            "offset": offset
        })
    
    except Exception as e:
        logger.error(f"External list cards error: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return jsonify({"error": "Failed to list cards"}), 500


def notify_external_webhook(card_id: int, status: str, amount: int, result_message: str):
    try:
        cursor = db.execute("""
            SELECT ec.id, ec.external_ref, ec.webhook_url, ec.api_key_name
            FROM external_cards ec
            WHERE ec.card_id = %s
        """, (card_id,))
        row = cursor.fetchone()
        
        if not row or not row['webhook_url']:
            return
        
        db.execute("""
            UPDATE external_cards 
            SET status = %s, amount = %s, result_message = %s, processed_at = CURRENT_TIMESTAMP
            WHERE card_id = %s
        """, (status, amount, result_message, card_id))
        db.commit()
        
        webhook_data = {
            "card_id": card_id,
            "external_ref": row['external_ref'] or '',
            "status": status,
            "amount": amount,
            "result_message": result_message,
            "source": row['api_key_name']
        }
        
        try:
            resp = requests.post(
                row['webhook_url'],
                json=webhook_data,
                timeout=10,
                headers={"Content-Type": "application/json"}
            )
            logger.info(f"External webhook sent for card {card_id}: {resp.status_code}")
        except Exception as e:
            logger.error(f"External webhook failed for card {card_id}: {e}")
    
    except Exception as e:
        logger.error(f"notify_external_webhook error: {e}")
        try:
            db.rollback()
        except Exception:
            pass


# ============ XPARTY WEBHOOK ============

@app.route('/api/xparty/webhook', methods=['POST'])
def xparty_webhook():
    """
    Webhook endpoint for Xparty recharge results.
    Receives POST with: state, err, id, ammount, order_number
    """
    if not db:
        return jsonify({"error": "Database not initialized"}), 500
    
    try:
        data = request.get_json() or {}
        logger.info(f"Xparty webhook received: {data}")
        
        order_number = data.get("order_number", "")
        state = data.get("state", False)
        err = data.get("err", False)
        player_id = data.get("id", "")
        amount = data.get("ammount", "")
        
        if not order_number:
            return jsonify({"error": "Missing order_number"}), 400
        
        # Find order by order_number (stored as xparty_order_id)
        cursor = db.execute("""
            SELECT id, user_id, player_id, coins, price_iqd, status, player_nickname, player_country, player_avatar 
            FROM xena_orders 
            WHERE xparty_order_id = %s
            LIMIT 1
        """, (order_number,))
        row = cursor.fetchone()
        
        if not row:
            logger.warning(f"Xparty webhook: Order not found for order_number={order_number}")
            return jsonify({"error": "Order not found"}), 404
        
        order_id = row['id']
        user_id = row['user_id']
        player_id_db = row['player_id']
        coins = row['coins']
        price_iqd = row['price_iqd']
        current_status = row['status']
        player_nickname = row.get('player_nickname', '') or ''
        player_country = row.get('player_country', '') or ''
        player_avatar = row.get('player_avatar', '') or ''
        
        # Skip if already processed
        if current_status in ('completed', 'failed'):
            logger.info(f"Xparty webhook: Order #{order_id} already {current_status}")
            return jsonify({"status": "already_processed"})
        
        nickname_line = f"🏷️ الاسم: {player_nickname}\n" if player_nickname else ""
        country_line = f"🌍 الدولة: {player_country}\n" if player_country else ""
        
        # Get avatar URL
        avatar_base_url = os.environ.get("XENA_AVATAR_BASE_URL", "")
        avatar_url = f"{avatar_base_url.rstrip('/')}/{player_avatar}" if avatar_base_url and player_avatar else ""
        
        if state == True:
            # Success - mark completed
            db.update_xena_order_status(order_id, "completed")
            
            if bot_app and bot_loop:
                success_text = (
                    f"✅ تم إرسال العملات بنجاح!\n\n"
                    f"🎫 رقم الطلب: #{order_id}\n"
                    f"👤 ايدي اللاعب: {player_id_db}\n"
                    f"{nickname_line}"
                    f"{country_line}"
                    f"💎 العملات: {coins:,}\n\n"
                    f"شكراً لاستخدامك!"
                )
                
                if avatar_url:
                    asyncio.run_coroutine_threadsafe(
                        bot_app.bot.send_photo(
                            chat_id=user_id,
                            photo=avatar_url,
                            caption=success_text
                        ),
                        bot_loop
                    )
                else:
                    asyncio.run_coroutine_threadsafe(
                        bot_app.bot.send_message(
                            chat_id=user_id,
                            text=success_text
                        ),
                        bot_loop
                    )
            
            logger.info(f"Xparty webhook: Order #{order_id} completed successfully")
        else:
            # Failed - refund user
            db.add_balance(user_id, price_iqd, transaction_type='xena_refund', reference_id=str(order_id))
            db.update_xena_order_status(order_id, "failed")
            
            if bot_app and bot_loop:
                new_balance = db.get_balance(user_id).balance_iqd
                error_msg = str(err) if err else "Unknown error"
                fail_text = (
                    f"❌ فشل إرسال العملات!\n\n"
                    f"🎫 رقم الطلب: #{order_id}\n"
                    f"👤 ايدي اللاعب: {player_id_db}\n"
                    f"{nickname_line}"
                    f"{country_line}"
                    f"💎 العملات: {coins:,}\n\n"
                    f"💰 تم استرداد {price_iqd:,} دينار إلى رصيدك.\n"
                    f"💵 رصيدك الحالي: {new_balance:,} دينار"
                )
                
                if avatar_url:
                    asyncio.run_coroutine_threadsafe(
                        bot_app.bot.send_photo(
                            chat_id=user_id,
                            photo=avatar_url,
                            caption=fail_text
                        ),
                        bot_loop
                    )
                else:
                    asyncio.run_coroutine_threadsafe(
                        bot_app.bot.send_message(
                            chat_id=user_id,
                            text=fail_text
                        ),
                        bot_loop
                    )
            
            logger.info(f"Xparty webhook: Order #{order_id} failed, user refunded. Error: {err}")
        
        return jsonify({"status": "processed"})
        
    except Exception as e:
        logger.error(f"Xparty webhook error: {e}")
        return jsonify({"error": str(e)}), 500


# ============ END XENA WORKER BOT API ============


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        session['admin_logged_in'] = True
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Logged out', 'info')
    return redirect(url_for('root'))

@app.route('/admin')
@require_admin_login
def dashboard():
    global card_processing_paused
    if not db:
        return "Database not initialized", 500
    
    stats = db.get_stats()
    stats['online_phones'] = len(db.get_online_phones())
    stats['verified_cards'] = stats.get('verified', 0)
    stats['pending_cards'] = stats.get('pending', 0)
    phones = db.get_all_phones()
    
    all_orders = []
    
    users_cache = {}
    try:
        users_cursor = db.execute("SELECT user_id, username, first_name FROM users")
        for u in users_cursor.fetchall():
            users_cache[u['user_id']] = u['username'] or u['first_name'] or str(u['user_id'])
    except:
        pass
    
    phones_cache = {}
    try:
        phones_cursor = db.execute("SELECT phone_id, name FROM phones")
        for p in phones_cursor.fetchall():
            phones_cache[p['phone_id']] = p['name'] or p['phone_id'][:8]
    except:
        pass
    
    cursor = db.execute("SELECT * FROM cards ORDER BY id DESC")
    for row in cursor.fetchall():
        created = row['created_at']
        if hasattr(created, 'strftime'):
            created = created.strftime('%Y-%m-%d %H:%M:%S')
        pin = row['pin'] or ''
        phone_name = phones_cache.get(row.get('phone_id', ''), '-')
        username = users_cache.get(row['user_id'], str(row['user_id']))
        all_orders.append({
            'product': 'Asiacell',
            'user_id': row['user_id'],
            'username': username,
            'details': pin,
            'full_pin': pin,
            'amount': f"IQD {row['amount']:,}" if row['amount'] else '-',
            'raw_amount': row['amount'] or 0,
            'status': row['status'],
            'phone': phone_name,
            'result': row.get('result', ''),
            'retries': row.get('retries', 0),
            'created_at': str(created) if created else ''
        })
    
    cursor2 = db.execute("SELECT * FROM xena_orders ORDER BY id DESC")
    for row in cursor2.fetchall():
        created = row['created_at']
        if hasattr(created, 'strftime'):
            created = created.strftime('%Y-%m-%d %H:%M:%S')
        username = users_cache.get(row['user_id'], str(row['user_id']))
        all_orders.append({
            'product': 'Xena Live',
            'user_id': row['user_id'],
            'username': username,
            'details': f"{row['player_id']} ({row['coins']:,} coins)",
            'full_pin': row['player_id'],
            'amount': f"IQD {row['price_iqd']:,}",
            'raw_amount': row['price_iqd'],
            'status': row['status'],
            'phone': '-',
            'result': '',
            'retries': 0,
            'created_at': str(created) if created else ''
        })
    
    all_orders.sort(key=lambda x: x['created_at'] or '', reverse=True)
    
    orders_page = request.args.get('orders_page', 1, type=int)
    orders_offset = (orders_page - 1) * 8
    total_orders = len(all_orders)
    total_orders_pages = (total_orders + 7) // 8 if total_orders > 0 else 1
    recent_orders = all_orders[orders_offset:orders_offset + 8]
    
    for i, order in enumerate(recent_orders):
        order['order_num'] = orders_offset + i + 1
    
    try:
        pending_users_cursor = db.execute("SELECT COUNT(*) as count FROM users WHERE is_verified = FALSE AND is_rejected = FALSE AND is_blocked = FALSE")
        stats['pending_users'] = pending_users_cursor.fetchone()['count']
    except:
        stats['pending_users'] = 0
    
    try:
        pending_payments_cursor = db.execute("SELECT COUNT(*) as count FROM payment_requests WHERE status = 'pending'")
        stats['pending_payments'] = pending_payments_cursor.fetchone()['count']
    except:
        stats['pending_payments'] = 0
    
    try:
        offline_phones = [p for p in phones if p.status != 'online']
        stats['offline_phones'] = len(offline_phones)
    except:
        stats['offline_phones'] = 0
    
    return render_template('dashboard_simple.html', 
                         stats=stats, 
                         phones=phones, 
                         recent_orders=recent_orders,
                         orders_page=orders_page,
                         total_orders_pages=total_orders_pages,
                         processing_paused=card_processing_paused,
                         bot_paused=bot_paused)

@app.route('/admin/api/chart-data')
@require_admin_login
def admin_chart_data():
    """API endpoint for dashboard charts data"""
    if not db:
        return jsonify({'error': 'Database not initialized'}), 500
    
    today = datetime.now(IRAQ_TZ).date()
    yesterday = today - timedelta(days=1)
    
    daily_data = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_str = day.strftime('%Y-%m-%d')
        
        try:
            cards_cursor = db.execute(
                "SELECT COUNT(*) as count, COALESCE(SUM(CASE WHEN amount IS NOT NULL THEN amount ELSE 0 END), 0) as total FROM cards WHERE DATE(created_at) = %s",
                (day_str,)
            )
            cards_row = cards_cursor.fetchone()
            cards_count = cards_row['count'] if cards_row else 0
            cards_amount = int(cards_row['total']) if cards_row else 0
        except:
            cards_count = 0
            cards_amount = 0
        
        try:
            verified_cursor = db.execute(
                "SELECT COUNT(*) as count FROM cards WHERE DATE(created_at) = %s AND status = 'verified'",
                (day_str,)
            )
            verified_count = verified_cursor.fetchone()['count']
        except:
            verified_count = 0
        
        try:
            xena_cursor = db.execute(
                "SELECT COUNT(*) as count, COALESCE(SUM(price_iqd), 0) as total FROM xena_orders WHERE DATE(created_at) = %s",
                (day_str,)
            )
            xena_row = xena_cursor.fetchone()
            xena_count = xena_row['count'] if xena_row else 0
            xena_amount = int(xena_row['total']) if xena_row else 0
        except:
            xena_count = 0
            xena_amount = 0
        
        daily_data.append({
            'date': day.strftime('%m/%d'),
            'day_name_ar': ['الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت'][day.weekday()],
            'day_name_en': day.strftime('%a'),
            'cards': cards_count,
            'cards_verified': verified_count,
            'cards_amount': cards_amount,
            'xena': xena_count,
            'xena_amount': xena_amount,
            'total_amount': cards_amount + xena_amount
        })
    
    try:
        status_cursor = db.execute(
            "SELECT status, COUNT(*) as count FROM cards GROUP BY status"
        )
        status_data = {row['status']: row['count'] for row in status_cursor.fetchall()}
    except:
        status_data = {}
    
    try:
        payment_cursor = db.execute(
            "SELECT payment_type, COUNT(*) as count FROM payment_requests GROUP BY payment_type"
        )
        payment_data = {row['payment_type']: row['count'] for row in payment_cursor.fetchall()}
    except:
        payment_data = {}
    
    today_cards = daily_data[-1]['cards'] if daily_data else 0
    yesterday_cards = daily_data[-2]['cards'] if len(daily_data) > 1 else 0
    today_amount = daily_data[-1]['total_amount'] if daily_data else 0
    yesterday_amount = daily_data[-2]['total_amount'] if len(daily_data) > 1 else 0
    
    cards_change = ((today_cards - yesterday_cards) / yesterday_cards * 100) if yesterday_cards > 0 else 0
    amount_change = ((today_amount - yesterday_amount) / yesterday_amount * 100) if yesterday_amount > 0 else 0
    
    return jsonify({
        'daily': daily_data,
        'status': status_data,
        'payments': payment_data,
        'comparison': {
            'today_cards': today_cards,
            'yesterday_cards': yesterday_cards,
            'cards_change': round(cards_change, 1),
            'today_amount': today_amount,
            'yesterday_amount': yesterday_amount,
            'amount_change': round(amount_change, 1)
        }
    })

@app.route('/admin/users')
@require_admin_login
def admin_users():
    if not db:
        return "Database not initialized", 500
    
    status_filter = request.args.get('status', 'all')
    sort_by = request.args.get('sort', 'newest')
    
    order_clause = "u.created_at DESC"
    if sort_by == 'balance_high':
        order_clause = "u.balance_iqd DESC"
    elif sort_by == 'balance_low':
        order_clause = "u.balance_iqd ASC"
    elif sort_by == 'cards':
        order_clause = "card_count DESC"
    elif sort_by == 'oldest':
        order_clause = "u.created_at ASC"
    
    cursor = db.execute(f"""
        SELECT u.*, COUNT(c.id) as card_count 
        FROM users u 
        LEFT JOIN cards c ON u.user_id = c.user_id 
        GROUP BY u.user_id 
        ORDER BY {order_clause}
    """)
    users = []
    for row in cursor.fetchall():
        is_verified = row['is_verified'] if 'is_verified' in row.keys() else 1
        is_blocked = row['is_blocked'] if 'is_blocked' in row.keys() else False
        is_rejected = row['is_rejected'] if 'is_rejected' in row.keys() else False
        
        if is_blocked:
            approval_status = 'blocked'
        elif is_rejected:
            approval_status = 'rejected'
        elif is_verified:
            approval_status = 'approved'
        else:
            approval_status = 'pending'
        
        if status_filter != 'all' and approval_status != status_filter:
            continue
            
        users.append({
            'user_id': row['user_id'],
            'username': row['username'],
            'first_name': row['first_name'] if 'first_name' in row.keys() else '',
            'balance_iqd': row['balance_iqd'],
            'balance_coins': row['balance_coins'] if 'balance_coins' in row.keys() else 0,
            'card_count': row['card_count'],
            'is_blocked': is_blocked,
            'is_rejected': is_rejected,
            'is_vip': row['is_vip'] if 'is_vip' in row.keys() else False,
            'is_verified': is_verified,
            'approval_status': approval_status,
            'created_at': format_datetime(row['created_at']) if 'created_at' in row.keys() else ''
        })
    
    counts = {'all': 0, 'pending': 0, 'approved': 0, 'rejected': 0, 'blocked': 0}
    cursor2 = db.execute("SELECT is_verified, is_blocked, is_rejected FROM users")
    for row in cursor2.fetchall():
        counts['all'] += 1
        is_v = row['is_verified'] if 'is_verified' in row.keys() else 1
        is_b = row['is_blocked'] if 'is_blocked' in row.keys() else 0
        is_r = row['is_rejected'] if 'is_rejected' in row.keys() else 0
        if is_b:
            counts['blocked'] += 1
        elif is_r:
            counts['rejected'] += 1
        elif is_v:
            counts['approved'] += 1
        else:
            counts['pending'] += 1
    
    return render_template('users.html', users=users, status_filter=status_filter, sort_by=sort_by, counts=counts)

@app.route('/admin/user/<int:user_id>')
@require_admin_login
def admin_user_detail(user_id):
    if not db:
        return "Database not initialized", 500
    
    user = db.get_or_create_user(user_id)
    
    cursor = db.execute("SELECT * FROM cards WHERE user_id = ? ORDER BY id DESC", (user_id,))
    cards = []
    for row in cursor.fetchall():
        cards.append({
            'id': row['id'],
            'pin': row['pin'],
            'amount': row['amount'],
            'status': row['status'],
            'created_at': format_datetime(row['created_at'])
        })
    
    cursor = db.execute("SELECT * FROM xena_orders WHERE user_id = ? ORDER BY id DESC", (user_id,))
    xena_orders = []
    for row in cursor.fetchall():
        xena_orders.append({
            'id': row['id'],
            'player_id': row['player_id'],
            'coins': row['coins'],
            'price_iqd': row['price_iqd'],
            'status': row['status'],
            'created_at': format_datetime(row['created_at'])
        })
    
    return render_template('user_detail.html', user=user, cards=cards, xena_orders=xena_orders)

@app.route('/admin/user/<int:user_id>/balance', methods=['GET', 'POST'])
@require_admin_login
def admin_user_balance(user_id):
    if not db:
        return "Database not initialized", 500
    
    user = db.get_or_create_user(user_id)
    
    if request.method == 'POST':
        operation = request.form.get('operation', 'add')
        amount = int(request.form.get('amount', 0))
        lang = user.language if user else 'ar'
        
        if operation == 'add':
            db.add_balance(user_id, amount)
            new_balance = user.balance_iqd + amount
            if lang == 'ar':
                msg = f"💰 تم إضافة {amount:,} IQD إلى رصيدك من قبل الإدارة.\n\n💳 رصيدك الجديد: {new_balance:,} IQD"
            else:
                msg = f"💰 {amount:,} IQD has been added to your balance by admin.\n\n💳 New balance: {new_balance:,} IQD"
            send_telegram_message(user_id, msg)
            db.log_activity('balance_add', 'user', str(user_id), f'Added {amount:,} IQD to user balance')
            flash(f'Added {amount:,} IQD and notified user', 'success')
        elif operation == 'subtract':
            db.add_balance(user_id, -amount)
            new_balance = user.balance_iqd - amount
            if lang == 'ar':
                msg = f"💸 تم خصم {amount:,} IQD من رصيدك من قبل الإدارة.\n\n💳 رصيدك الجديد: {new_balance:,} IQD"
            else:
                msg = f"💸 {amount:,} IQD has been deducted from your balance by admin.\n\n💳 New balance: {new_balance:,} IQD"
            send_telegram_message(user_id, msg)
            db.log_activity('balance_subtract', 'user', str(user_id), f'Subtracted {amount:,} IQD from user balance')
            flash(f'Subtracted {amount:,} IQD and notified user', 'success')
        elif operation == 'set':
            current = user.balance_iqd
            db.add_balance(user_id, amount - current)
            if lang == 'ar':
                msg = f"💳 تم تعديل رصيدك إلى {amount:,} IQD من قبل الإدارة."
            else:
                msg = f"💳 Your balance has been set to {amount:,} IQD by admin."
            send_telegram_message(user_id, msg)
            db.log_activity('balance_set', 'user', str(user_id), f'Set user balance to {amount:,} IQD')
            flash(f'Set balance to {amount:,} IQD and notified user', 'success')
        
        return redirect(url_for('admin_user_detail', user_id=user_id))
    
    return render_template('user_balance.html', user=user)

@app.route('/admin/user/<int:user_id>/block')
@require_admin_login
def admin_block_user(user_id):
    if not db:
        return "Database not initialized", 500
    db.block_user(user_id)
    user = db.get_or_create_user(user_id)
    lang = user.language if user else 'ar'
    if lang == 'ar':
        msg = "⛔ تم حظر حسابك من استخدام الخدمة.\n\nللاستفسار تواصل مع الدعم."
    else:
        msg = "⛔ Your account has been blocked from using this service.\n\nContact support for inquiries."
    send_telegram_message(user_id, msg)
    db.log_activity('user_block', 'user', str(user_id), f'User blocked')
    flash(f'User {user_id} blocked and notified', 'warning')
    return redirect(url_for('admin_user_detail', user_id=user_id))

@app.route('/admin/user/<int:user_id>/unblock')
@require_admin_login
def admin_unblock_user(user_id):
    if not db:
        return "Database not initialized", 500
    db.unblock_user(user_id)
    user = db.get_or_create_user(user_id)
    lang = user.language if user else 'ar'
    if lang == 'ar':
        msg = "✅ تم إلغاء حظر حسابك. يمكنك الآن استخدام الخدمة."
    else:
        msg = "✅ Your account has been unblocked. You can now use the service."
    send_telegram_message(user_id, msg)
    db.log_activity('user_unblock', 'user', str(user_id), f'User unblocked')
    flash(f'User {user_id} unblocked and notified', 'success')
    return redirect(url_for('admin_user_detail', user_id=user_id))

@app.route('/admin/user/<int:user_id>/toggle-vip')
@require_admin_login
def admin_toggle_vip(user_id):
    if not db:
        return "Database not initialized", 500
    db.toggle_vip(user_id)
    user = db.get_or_create_user(user_id)
    is_vip = user.is_vip if user else False
    lang = user.language if user else 'ar'
    if is_vip:
        if lang == 'ar':
            msg = "⭐ مبروك! تم ترقيتك إلى عضوية VIP.\n\nستحصل على أولوية في معالجة البطاقات."
        else:
            msg = "⭐ Congratulations! You have been upgraded to VIP membership.\n\nYou will get priority card processing."
    else:
        if lang == 'ar':
            msg = "ℹ️ تم إلغاء عضوية VIP الخاصة بك."
        else:
            msg = "ℹ️ Your VIP membership has been removed."
    send_telegram_message(user_id, msg)
    status_str = 'granted' if is_vip else 'removed'
    db.log_activity('vip_toggle', 'user', str(user_id), f'VIP status {status_str}')
    flash(f'VIP status toggled for user {user_id} and notified', 'success')
    return redirect(url_for('admin_user_detail', user_id=user_id))

@app.route('/admin/users/pending')
@require_admin_login
def admin_pending_users():
    if not db:
        return "Database not initialized", 500
    
    pending_users = db.get_pending_users()
    return render_template('pending_users.html', users=pending_users)

@app.route('/admin/user/<int:user_id>/approve')
@require_admin_login
def admin_approve_user(user_id):
    if not db:
        return "Database not initialized", 500
    service_type = request.args.get('service_type', 'xena')
    if service_type not in ('xena', 'imo', 'both'):
        service_type = 'xena'
    db.approve_user_with_service(user_id, service_type)
    service_name = {'xena': 'Xena Live', 'imo': 'IMO', 'both': 'Xena Live + IMO'}[service_type]
    send_telegram_message(user_id, f"✅ تم تفعيل حسابك!\n\nخدمتك: {service_name}\nيمكنك الآن استخدام البوت.\nاضغط /start للبدء.\n\n✅ Your account has been approved!\nService: {service_name}\nPress /start to begin.")
    db.log_activity('user_approve', 'user', str(user_id), f'User approved with service: {service_type}')
    flash(f'User {user_id} approved for {service_name} and notified', 'success')
    return redirect(url_for('admin_pending_users'))

@app.route('/admin/user/<int:user_id>/service-type')
@require_admin_login
def admin_set_service_type(user_id):
    if not db:
        return "Database not initialized", 500
    new_service_type = request.args.get('type', 'xena')
    if new_service_type not in ('xena', 'imo', 'both', 'usd'):
        flash('Invalid service type', 'error')
        return redirect(url_for('admin_user_detail', user_id=user_id))
    
    cursor = db.execute("SELECT service_type, balance_iqd, balance_usd FROM users WHERE user_id = %s", (user_id,))
    user_row = cursor.fetchone()
    old_service_type = user_row['service_type'] if user_row else 'xena'
    balance_iqd = user_row['balance_iqd'] or 0 if user_row else 0
    balance_usd = float(user_row['balance_usd'] or 0) if user_row else 0
    
    cursor = db.execute("SELECT key, value FROM settings WHERE key IN ('usd_rate_iqd', 'usd_rate_usd')")
    settings = {}
    for row in cursor.fetchall():
        settings[row['key']] = row['value']
    rate_iqd = int(settings.get('usd_rate_iqd', 100000))
    rate_usd = float(settings.get('usd_rate_usd', 55.50))
    
    conversion_msg = ""
    if old_service_type != 'usd' and new_service_type == 'usd' and balance_iqd > 0:
        converted_usd = (balance_iqd / rate_iqd) * rate_usd
        db.execute("UPDATE users SET balance_usd = %s, balance_iqd = 0 WHERE user_id = %s", (converted_usd, user_id))
        db.commit()
        conversion_msg = f" | Converted {balance_iqd:,} IQD → ${converted_usd:.2f}"
    elif old_service_type == 'usd' and new_service_type != 'usd' and balance_usd > 0:
        converted_iqd = int((balance_usd / rate_usd) * rate_iqd)
        db.execute("UPDATE users SET balance_iqd = %s, balance_usd = 0 WHERE user_id = %s", (converted_iqd, user_id))
        db.commit()
        conversion_msg = f" | Converted ${balance_usd:.2f} → {converted_iqd:,} IQD"
    
    db.set_user_service_type(user_id, new_service_type)
    service_name = {'xena': 'Xena Live', 'imo': 'IMO', 'both': 'Xena Live + IMO', 'usd': 'USD Withdrawal'}[new_service_type]
    db.log_activity('service_type_change', 'user', str(user_id), f'Service type changed to: {new_service_type}{conversion_msg}')
    flash(f'Service type changed to {service_name}{conversion_msg}', 'success')
    return redirect(url_for('admin_user_detail', user_id=user_id))

@app.route('/admin/user/<int:user_id>/reject')
@require_admin_login
def admin_reject_user(user_id):
    if not db:
        return "Database not initialized", 500
    db.reject_user(user_id)
    send_telegram_message(user_id, "❌ تم رفض طلب تفعيل حسابك.\n\n❌ Your account approval request has been rejected.")
    db.log_activity('user_reject', 'user', str(user_id), f'User rejected')
    flash(f'User {user_id} rejected and notified', 'warning')
    return redirect(url_for('admin_users'))

@app.route('/admin/user/<int:user_id>/unreject')
@require_admin_login
def admin_unreject_user(user_id):
    if not db:
        return "Database not initialized", 500
    db.unreject_user(user_id)
    flash(f'User {user_id} moved back to pending', 'info')
    return redirect(url_for('admin_users'))

@app.route('/admin/pre-approvals')
@require_admin_login
def admin_pre_approvals():
    if not db:
        return "Database not initialized", 500
    pre_approvals = db.get_pre_approvals()
    return render_template('pre_approvals.html', pre_approvals=pre_approvals)

@app.route('/admin/pre-approvals/add', methods=['POST'])
@require_admin_login
def admin_add_pre_approval():
    if not db:
        return "Database not initialized", 500
    user_id = request.form.get('user_id', '').strip()
    service_type = request.form.get('service_type', 'xena')
    note = request.form.get('note', '').strip()
    
    if not user_id or not user_id.isdigit():
        flash('Please enter a valid Telegram User ID', 'error')
        return redirect(url_for('admin_pre_approvals'))
    
    user_id = int(user_id)
    if service_type not in ('xena', 'imo', 'both'):
        service_type = 'xena'
    
    if db.pre_approve_user(user_id, service_type, note):
        service_name = {'xena': 'Xena Live', 'imo': 'IMO', 'both': 'Xena Live + IMO'}[service_type]
        db.log_activity('pre_approve', 'user', str(user_id), f'Pre-approved for {service_type}')
        flash(f'User {user_id} pre-approved for {service_name}', 'success')
    else:
        flash('Failed to add pre-approval', 'error')
    return redirect(url_for('admin_pre_approvals'))

@app.route('/admin/pre-approvals/<int:user_id>/remove')
@require_admin_login
def admin_remove_pre_approval(user_id):
    if not db:
        return "Database not initialized", 500
    if db.remove_pre_approval(user_id):
        db.log_activity('remove_pre_approval', 'user', str(user_id), 'Pre-approval removed')
        flash(f'Pre-approval for user {user_id} removed', 'success')
    else:
        flash('Pre-approval not found', 'warning')
    return redirect(url_for('admin_pre_approvals'))

@app.route('/admin/cards')
@require_admin_login
def admin_cards():
    if not db:
        return "Database not initialized", 500
    
    
    cursor = db.execute("SELECT * FROM cards ORDER BY id DESC LIMIT 500")
    cards = []
    for row in cursor.fetchall():
        cards.append({
            'id': row['id'],
            'user_id': row['user_id'],
            'pin': row['pin'],
            'amount': row['amount'],
            'status': row['status'],
            'phone_id': row['phone_id'],
            'created_at': format_datetime(row['created_at'])
        })
    
    return render_template('cards.html', cards=cards)

@app.route('/admin/card/confirm/<int:card_id>', methods=['POST'])
@require_admin_login
def admin_card_confirm(card_id):
    if not db:
        flash('Database not initialized', 'danger')
        return redirect(url_for('admin_cards'))
    
    
    db.execute("UPDATE cards SET status = 'verified' WHERE id = ?", (card_id,))
    db.commit()
    
    cursor = db.execute("SELECT user_id, amount FROM cards WHERE id = ?", (card_id,))
    card = cursor.fetchone()
    if card and bot_app and bot_loop:
        asyncio.run_coroutine_threadsafe(
            notify_user_card_verified(card['user_id'], card['amount'], card_id),
            bot_loop
        )
    
    db.log_activity('card_confirm', 'card', str(card_id), f'Card confirmed as verified')
    trigger_action_backup()
    flash(f'Card #{card_id} confirmed as verified', 'success')
    return redirect(url_for('admin_cards'))

@app.route('/admin/card/reject/<int:card_id>', methods=['POST'])
@require_admin_login
def admin_card_reject(card_id):
    if not db:
        flash('Database not initialized', 'danger')
        return redirect(url_for('admin_cards'))
    
    
    cursor = db.execute("SELECT user_id, amount, status FROM cards WHERE id = ?", (card_id,))
    card = cursor.fetchone()
    
    if not card:
        flash('Card not found', 'danger')
        return redirect(url_for('admin_cards'))
    
    if card['status'] == 'rejected':
        flash('Card already rejected', 'warning')
        return redirect(url_for('admin_cards'))
    
    user_id = card['user_id']
    refund_amount = card['amount']
    
    db.execute("UPDATE cards SET status = 'rejected' WHERE id = ?", (card_id,))
    db.execute("UPDATE users SET balance_iqd = balance_iqd + ? WHERE user_id = ?", (refund_amount, user_id))
    db.commit()
    
    if bot_app and bot_loop:
        asyncio.run_coroutine_threadsafe(
            notify_user_card_refund(user_id, refund_amount, card_id),
            bot_loop
        )
    
    db.log_activity('card_reject', 'card', str(card_id), f'Card rejected, {refund_amount:,} IQD refunded to user {user_id}')
    trigger_action_backup()
    flash(f'Card #{card_id} rejected. {refund_amount:,} IQD refunded to user', 'success')
    return redirect(url_for('admin_cards'))

@app.route('/admin/card/retry/<int:card_id>', methods=['POST'])
@require_admin_login
def admin_card_retry(card_id):
    if not db:
        flash('Database not initialized', 'danger')
        return redirect(url_for('admin_cards'))
    
    
    db.execute("UPDATE cards SET status = 'pending', phone_id = NULL, retry_count = retry_count + 1 WHERE id = ?", (card_id,))
    db.commit()
    
    db.log_activity('card_retry', 'card', str(card_id), f'Card set to pending for retry')
    flash(f'Card #{card_id} set to pending for retry', 'success')
    return redirect(url_for('admin_cards'))

async def notify_user_card_verified(user_id, amount, card_id):
    if bot_app:
        try:
            await bot_app.bot.send_message(
                chat_id=user_id,
                text=f"✅ تم التحقق من البطاقة!\n\n"
                     f"بطاقة #{card_id} تم التحقق منها\n"
                     f"المبلغ: {amount:,} IQD\n\n"
                     f"✅ Card verified!\n"
                     f"Card #{card_id} has been verified\n"
                     f"Amount: {amount:,} IQD"
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_id} about card verification: {e}")

async def notify_user_card_refund(user_id, amount, card_id):
    if bot_app:
        try:
            await bot_app.bot.send_message(
                chat_id=user_id,
                text=f"💰 تم استرداد رصيدك!\n\n"
                     f"بطاقة #{card_id} تم رفضها\n"
                     f"تم إضافة {amount:,} IQD إلى رصيدك\n\n"
                     f"💰 Your balance has been refunded!\n"
                     f"Card #{card_id} was rejected\n"
                     f"{amount:,} IQD added to your balance"
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_id} about card refund: {e}")

@app.route('/admin/cards/gallery')
@require_admin_login
def admin_gallery():
    images = []
    image_dir = 'data/card_images'
    if os.path.exists(image_dir):
        for filename in os.listdir(image_dir):
            if filename.endswith(('.jpg', '.jpeg', '.png')):
                images.append({'filename': filename})
    
    return render_template('gallery.html', images=images)

@app.route('/admin/payments')
@app.route('/admin/payments/<payment_type>')
@require_admin_login
def admin_payments(payment_type=None):
    if not db:
        return "Database not initialized", 500
    
    status_filter = request.args.get('status', 'pending')
    
    payments = db.get_all_payments(payment_type=payment_type, status=status_filter if status_filter != 'all' else None, limit=100)
    
    payment_list = []
    for p in payments:
        user = db.get_or_create_user(p.user_id)
        payment_list.append({
            'id': p.id,
            'user_id': p.user_id,
            'username': user.username if user else '',
            'first_name': user.first_name if user else '',
            'payment_type': p.payment_type,
            'amount': p.amount,
            'actual_amount': p.actual_amount,
            'status': p.status,
            'proof_image_path': p.proof_image_path,
            'admin_note': p.admin_note,
            'created_at': p.created_at,
            'processed_at': p.processed_at
        })
    
    stats = db.get_payment_stats()
    
    return render_template('payments.html', 
                          payments=payment_list, 
                          payment_type=payment_type,
                          status_filter=status_filter,
                          stats=stats)

@app.route('/admin/payments/proof/<int:payment_id>')
@require_admin_login
def admin_payment_proof(payment_id):
    if not db:
        return "Database not initialized", 500
    
    payment = db.get_payment_request(payment_id)
    if payment and payment.proof_image_path and os.path.exists(payment.proof_image_path):
        return send_file(payment.proof_image_path)
    return "Image not found", 404

@app.route('/admin/payments/<int:payment_id>/approve', methods=['POST'])
@require_admin_login
def admin_approve_payment(payment_id):
    if not db:
        return "Database not initialized", 500
    
    payment = db.get_payment_request(payment_id)
    if not payment:
        flash('Payment not found', 'danger')
        return redirect(url_for('admin_payments'))
    
    if payment.status != 'pending':
        flash('Payment already processed', 'warning')
        return redirect(url_for('admin_payments'))
    
    if not db.approve_payment(payment_id, payment.amount):
        flash('Payment already processed', 'warning')
        return redirect(url_for('admin_payments'))
    
    db.add_balance(payment.user_id, payment.amount)
    
    user = db.get_or_create_user(payment.user_id)
    lang = user.language if user else 'ar'
    type_name = "QI Card" if payment.payment_type == 'qi_card' else "ZainCash"
    new_balance = db.get_balance(payment.user_id).balance_iqd
    
    if lang == 'ar':
        msg = f"✅ تم تأكيد الدفع #{payment_id}\n\n💳 {type_name}\n💰 المبلغ: {payment.amount:,} دينار\n💵 رصيدك الجديد: {new_balance:,} دينار"
    else:
        msg = f"✅ Payment #{payment_id} confirmed\n\n💳 {type_name}\n💰 Amount: {payment.amount:,} IQD\n💵 New balance: {new_balance:,} IQD"
    
    send_telegram_message(payment.user_id, msg)
    flash(f'Payment #{payment_id} approved and user notified', 'success')
    return redirect(url_for('admin_payments'))

@app.route('/admin/payments/<int:payment_id>/reject', methods=['POST'])
@require_admin_login
def admin_reject_payment(payment_id):
    if not db:
        return "Database not initialized", 500
    
    payment = db.get_payment_request(payment_id)
    if not payment:
        flash('Payment not found', 'danger')
        return redirect(url_for('admin_payments'))
    
    if payment.status != 'pending':
        flash('Payment already processed', 'warning')
        return redirect(url_for('admin_payments'))
    
    note = request.form.get('note', '')
    if not db.reject_payment(payment_id, note):
        flash('Payment already processed', 'warning')
        return redirect(url_for('admin_payments'))
    
    user = db.get_or_create_user(payment.user_id)
    lang = user.language if user else 'ar'
    type_name = "QI Card" if payment.payment_type == 'qi_card' else "ZainCash"
    
    if lang == 'ar':
        msg = f"❌ تم رفض طلب الدفع #{payment_id}\n\n💳 {type_name}\n\nالسبب: الإيصال غير صالح أو لم يتم التحويل"
    else:
        msg = f"❌ Payment request #{payment_id} rejected\n\n💳 {type_name}\n\nReason: Invalid receipt or transfer not found"
    
    send_telegram_message(payment.user_id, msg)
    flash(f'Payment #{payment_id} rejected and user notified', 'warning')
    return redirect(url_for('admin_payments'))

@app.route('/admin/payments/<int:payment_id>/different-amount', methods=['POST'])
@require_admin_login
def admin_different_amount_payment(payment_id):
    if not db:
        return "Database not initialized", 500
    
    payment = db.get_payment_request(payment_id)
    if not payment:
        flash('Payment not found', 'danger')
        return redirect(url_for('admin_payments'))
    
    if payment.status != 'pending':
        flash('Payment already processed', 'warning')
        return redirect(url_for('admin_payments'))
    
    actual_amount = int(request.form.get('actual_amount', 0))
    if actual_amount <= 0:
        flash('Invalid amount', 'danger')
        return redirect(url_for('admin_payments'))
    
    note = f"المبلغ المدعى: {payment.amount:,}, الفعلي: {actual_amount:,}"
    if not db.set_payment_different_amount(payment_id, actual_amount, note):
        flash('Payment already processed', 'warning')
        return redirect(url_for('admin_payments'))
    
    db.add_balance(payment.user_id, actual_amount)
    
    user = db.get_or_create_user(payment.user_id)
    lang = user.language if user else 'ar'
    type_name = "QI Card" if payment.payment_type == 'qi_card' else "ZainCash"
    new_balance = db.get_balance(payment.user_id).balance_iqd
    
    if lang == 'ar':
        msg = f"⚠️ طلب الدفع #{payment_id}\n\n💳 {type_name}\n💰 المبلغ المدعى: {payment.amount:,} دينار\n💰 المبلغ الفعلي: {actual_amount:,} دينار\n\n✅ تم إضافة {actual_amount:,} دينار\n💵 رصيدك الجديد: {new_balance:,} دينار"
    else:
        msg = f"⚠️ Payment request #{payment_id}\n\n💳 {type_name}\n💰 Claimed amount: {payment.amount:,} IQD\n💰 Actual amount: {actual_amount:,} IQD\n\n✅ Added {actual_amount:,} IQD\n💵 New balance: {new_balance:,} IQD"
    
    send_telegram_message(payment.user_id, msg)
    flash(f'Payment #{payment_id} approved with different amount ({actual_amount:,} IQD) and user notified', 'success')
    return redirect(url_for('admin_payments'))

@app.route('/admin/cards/image/<filename>')
@require_admin_login
def admin_card_image(filename):
    image_path = os.path.join('data/card_images', filename)
    if os.path.exists(image_path):
        return send_file(image_path)
    return "Image not found", 404

@app.route('/admin/phones')
@require_admin_login
def admin_phones():
    if not db:
        return "Database not initialized", 500
    
    phones = db.get_all_phones()
    return render_template('phones.html', phones=phones)

@app.route('/admin/chats')
@app.route('/admin/chats/<int:user_id>')
@require_admin_login
def admin_chats(user_id=None):
    if not db:
        return "Database not initialized", 500
    
    
    cursor = db.execute("""
        SELECT m.user_id, u.username, COUNT(*) as message_count, MAX(m.created_at) as last_message
        FROM chat_messages m
        LEFT JOIN users u ON m.user_id = u.user_id
        GROUP BY m.user_id, u.username
        ORDER BY last_message DESC
    """)
    users_with_chats = []
    for row in cursor.fetchall():
        users_with_chats.append({
            'user_id': row['user_id'],
            'username': row['username'],
            'message_count': row['message_count']
        })
    
    messages = []
    selected_username = None
    if user_id:
        cursor = db.execute(
            "SELECT * FROM chat_messages WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,)
        )
        for row in cursor.fetchall():
            messages.append({
                'content': row['content'],
                'direction': row['direction'],
                'created_at': format_datetime(row['created_at'])
            })
        user = db.get_or_create_user(user_id)
        selected_username = user.username
    
    return render_template('admin_chats.html', 
                         users_with_chats=users_with_chats,
                         messages=messages,
                         selected_user=user_id,
                         selected_username=selected_username)

@app.route('/admin/chats/api/<int:user_id>')
@require_admin_login
def admin_chats_api(user_id):
    if not db:
        return jsonify({'error': 'Database not initialized'}), 500
    
    
    cursor = db.execute(
        "SELECT * FROM chat_messages WHERE user_id = ? ORDER BY created_at ASC",
        (user_id,)
    )
    messages = []
    for row in cursor.fetchall():
        messages.append({
            'id': row['id'],
            'content': row['content'],
            'direction': row['direction'],
            'created_at': format_datetime(row['created_at'])[:16] if row['created_at'] else ''
        })
    
    return jsonify({'messages': messages})

@app.route('/admin/activity')
@require_admin_login
def admin_activity():
    if not db:
        return "Database not initialized", 500
    
    action_filter = request.args.get('action', '')
    activities = db.get_activity_log(limit=200, action_type=action_filter if action_filter else None)
    
    return render_template('activity_log.html', activities=activities, action_filter=action_filter)

@app.route('/admin/settings')
@require_admin_login
def admin_settings():
    global card_processing_paused, bot_paused
    if not db:
        return "Database not initialized", 500
    
    stats = db.get_stats()
    stats['online_phones'] = len(db.get_online_phones())
    stats['verified_cards'] = stats.get('verified', 0)
    stats['total_cards'] = stats.get('total_cards', 0)
    
    qi_card_number = db.get_setting('qi_card_number') or os.environ.get('QI_CARD_ADDRESS', '')
    zaincash_number = db.get_setting('zaincash_number') or os.environ.get('ZAINCASH_ADDRESS', '')
    
    your_api_key = db.get_setting('your_api_key')
    if not your_api_key:
        import secrets
        your_api_key = 'sivosys_' + secrets.token_hex(16)
        db.set_setting('your_api_key', your_api_key)
    
    api_config = {
        'your_api_key': your_api_key,
        'webhook_url': db.get_setting('webhook_url') or '',
        'webhook_secret': db.get_setting('webhook_secret') or '',
        'rate_limit': db.get_setting('rate_limit') or '60',
        'allowed_origins': db.get_setting('allowed_origins') or '*',
    }
    
    try:
        pending_users_cursor = db.execute("SELECT COUNT(*) as count FROM users WHERE is_verified = FALSE AND is_rejected = FALSE AND is_blocked = FALSE")
        stats['pending_users'] = pending_users_cursor.fetchone()['count']
    except:
        stats['pending_users'] = 0
    
    try:
        pending_payments_cursor = db.execute("SELECT COUNT(*) as count FROM payment_requests WHERE status = 'pending'")
        stats['pending_payments'] = pending_payments_cursor.fetchone()['count']
    except:
        stats['pending_payments'] = 0
    
    return render_template('settings_new.html', 
                         stats=stats, 
                         processing_paused=card_processing_paused,
                         bot_paused=bot_paused,
                         qi_card_number=qi_card_number,
                         zaincash_number=zaincash_number,
                         api_config=api_config)

@app.route('/admin/settings/toggle-processing', methods=['POST'])
@require_admin_login
def admin_toggle_processing():
    global card_processing_paused
    card_processing_paused = not card_processing_paused
    status = 'paused' if card_processing_paused else 'resumed'
    flash(f'Card processing {status}', 'success')
    return redirect(url_for('admin_settings'))

@app.route('/admin/api-settings')
@require_admin_login
def admin_api_settings():
    if not db:
        flash('Database not initialized', 'error')
        return redirect(url_for('admin_dashboard'))
    
    your_api_key = db.get_setting('your_api_key')
    if not your_api_key:
        import secrets
        your_api_key = 'sivosys_' + secrets.token_hex(16)
        db.set_setting('your_api_key', your_api_key)
    
    api_config = {
        'your_api_key': your_api_key,
        'webhook_url': db.get_setting('webhook_url') or '',
        'webhook_secret': db.get_setting('webhook_secret') or '',
        'rate_limit': db.get_setting('rate_limit') or '60',
        'allowed_origins': db.get_setting('allowed_origins') or '*',
    }
    
    return render_template('api_settings.html', api_config=api_config)

@app.route('/admin/settings/api-config', methods=['POST'])
@require_admin_login
def admin_save_api_config():
    if not db:
        flash('Database not initialized', 'error')
        return redirect(url_for('admin_settings'))
    
    api_fields = [
        'webhook_url', 'webhook_secret',
        'rate_limit', 'allowed_origins'
    ]
    
    for field in api_fields:
        value = request.form.get(field, '').strip()
        db.set_setting(field, value)
    
    flash('تم حفظ إعدادات API بنجاح', 'success')
    return redirect(url_for('admin_settings'))

@app.route('/admin/settings/regenerate-api-key', methods=['POST'])
@require_admin_login
def admin_regenerate_api_key():
    if not db:
        return jsonify({'error': 'Database not initialized'}), 500
    
    import secrets
    new_key = 'sivosys_' + secrets.token_hex(16)
    db.set_setting('your_api_key', new_key)
    
    return jsonify({'new_key': new_key})

@app.route('/admin/external-api')
@require_admin_login
def admin_external_api():
    if not db:
        flash('Database not initialized', 'error')
        return redirect(url_for('admin_dashboard'))
    
    try:
        cursor = db.execute("SELECT * FROM external_api_keys ORDER BY created_at DESC")
        api_keys = cursor.fetchall()
    except Exception:
        api_keys = []
        try:
            db.rollback()
        except Exception:
            pass
    
    try:
        cursor = db.execute("""
            SELECT ec.*, c.status as card_status, c.amount as card_amount
            FROM external_cards ec
            LEFT JOIN cards c ON ec.card_id = c.id
            ORDER BY ec.created_at DESC
            LIMIT 100
        """)
        recent_cards = cursor.fetchall()
    except Exception:
        recent_cards = []
        try:
            db.rollback()
        except Exception:
            pass
    
    stats = {
        'total_keys': len(api_keys),
        'active_keys': sum(1 for k in api_keys if k['is_active']),
        'total_cards': len(recent_cards),
        'pending_cards': sum(1 for c in recent_cards if c['status'] == 'pending'),
        'verified_cards': sum(1 for c in recent_cards if c['status'] == 'verified'),
        'failed_cards': sum(1 for c in recent_cards if c['status'] == 'failed'),
    }
    
    return render_template('external_api.html', 
                          api_keys=api_keys, 
                          recent_cards=recent_cards,
                          stats=stats)


@app.route('/admin/external-api/create-key', methods=['POST'])
@require_admin_login
def admin_create_external_api_key():
    if not db:
        flash('Database not initialized', 'error')
        return redirect(url_for('admin_external_api'))
    
    key_name = request.form.get('key_name', '').strip()
    webhook_url = request.form.get('webhook_url', '').strip()
    
    if not key_name:
        flash('Key name is required', 'danger')
        return redirect(url_for('admin_external_api'))
    
    try:
        import secrets
        api_key = f"ext_{secrets.token_hex(24)}"
        
        db.execute("""
            INSERT INTO external_api_keys (key_name, api_key, webhook_url, is_active)
            VALUES (%s, %s, %s, TRUE)
        """, (key_name, api_key, webhook_url))
        db.commit()
        
        flash(f'API key created: {api_key}', 'success')
    except Exception as e:
        logger.error(f"Create external API key error: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        flash('Failed to create API key', 'danger')
    
    return redirect(url_for('admin_external_api'))


@app.route('/admin/external-api/toggle-key/<int:key_id>', methods=['POST'])
@require_admin_login
def admin_toggle_external_api_key(key_id):
    if not db:
        return redirect(url_for('admin_external_api'))
    
    try:
        db.execute("""
            UPDATE external_api_keys SET is_active = NOT is_active WHERE id = %s
        """, (key_id,))
        db.commit()
        flash('API key status updated', 'success')
    except Exception as e:
        logger.error(f"Toggle external API key error: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        flash('Failed to update key', 'danger')
    
    return redirect(url_for('admin_external_api'))


@app.route('/admin/external-api/delete-key/<int:key_id>', methods=['POST'])
@require_admin_login
def admin_delete_external_api_key(key_id):
    if not db:
        return redirect(url_for('admin_external_api'))
    
    try:
        db.execute("DELETE FROM external_api_keys WHERE id = %s", (key_id,))
        db.commit()
        flash('API key deleted', 'success')
    except Exception as e:
        logger.error(f"Delete external API key error: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        flash('Failed to delete key', 'danger')
    
    return redirect(url_for('admin_external_api'))


@app.route('/admin/coin-rates')
@require_admin_login
def admin_coin_rates():
    if not db:
        flash('Database not initialized', 'error')
        return redirect(url_for('admin_settings'))
    
    rates = db.get_coin_rates()
    return render_template('coin_rates.html', rates=rates)

@app.route('/admin/coin-rates/update', methods=['POST'])
@require_admin_login
def admin_update_coin_rate():
    if not db:
        return jsonify({'error': 'Database not initialized'}), 500
    
    payment_source = request.form.get('payment_source')
    source_amount = int(request.form.get('source_amount', 0))
    coin_amount = int(request.form.get('coin_amount', 0))
    currency_name = request.form.get('currency_name', '')
    
    if db.update_coin_rate(payment_source, source_amount, coin_amount, currency_name):
        flash('تم تحديث سعر التحويل بنجاح', 'success')
    else:
        flash('فشل في تحديث سعر التحويل', 'error')
    
    return redirect(url_for('admin_coin_rates'))

@app.route('/admin/convert-balances', methods=['POST'])
@require_admin_login
def admin_convert_balances():
    if not db:
        return jsonify({'error': 'Database not initialized'}), 500
    
    rate = int(request.form.get('rate', 5500))
    affected = db.convert_all_balances_to_coins(rate)
    
    if bot_app and bot_loop:
        for user_data in affected:
            try:
                msg = f"🔄 تم تحويل رصيدك!\n\n💰 الرصيد السابق: {user_data['balance_iqd']:,} دينار\n🪙 رصيدك الجديد: {user_data['balance_coins']:,} عملة"
                asyncio.run_coroutine_threadsafe(
                    bot_app.bot.send_message(chat_id=user_data['user_id'], text=msg),
                    bot_loop
                )
            except Exception as e:
                logger.error(f"Failed to notify user {user_data['user_id']}: {e}")
    
    flash(f'تم تحويل رصيد {len(affected)} مستخدم إلى عملات', 'success')
    return redirect(url_for('admin_coin_rates'))

@app.route('/admin/settings/toggle-bot', methods=['POST'])
@require_admin_login
def admin_toggle_bot():
    global bot_paused
    bot_paused = not bot_paused
    status = 'paused (maintenance mode)' if bot_paused else 'resumed'
    flash(f'Bot {status}', 'success')
    return redirect(url_for('admin_settings'))

@app.route('/admin/settings/payment-numbers', methods=['POST'])
@require_admin_login
def admin_save_payment_numbers():
    if not db:
        flash('Database not initialized', 'danger')
        return redirect(url_for('admin_settings'))
    
    qi_card_number = request.form.get('qi_card_number', '').strip()
    zaincash_number = request.form.get('zaincash_number', '').strip()
    
    if qi_card_number:
        db.set_setting('qi_card_number', qi_card_number)
    if zaincash_number:
        db.set_setting('zaincash_number', zaincash_number)
    
    flash('تم حفظ أرقام الدفع', 'success')
    return redirect(url_for('admin_settings'))


@app.route('/admin/settings/broadcast', methods=['POST'])
@require_admin_login
def admin_broadcast():
    message = request.form.get('message', '').strip()
    media_file = request.files.get('media')
    
    media_data = None
    media_type = None
    
    if media_file and media_file.filename:
        media_data = media_file.read()
        filename = media_file.filename.lower()
        content_type = media_file.content_type or ''
        
        if content_type.startswith('image/') or filename.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
            media_type = 'photo'
        elif content_type.startswith('video/') or filename.endswith(('.mp4', '.mov', '.avi', '.mkv')):
            media_type = 'video'
        elif content_type.startswith('audio/') or filename.endswith(('.ogg', '.mp3', '.wav', '.m4a', '.oga')):
            media_type = 'voice'
    
    if not message and not media_data:
        flash('Message or media is required', 'danger')
        return redirect(url_for('admin_settings'))
    
    if not db or not bot_app or not bot_loop:
        flash('Bot not initialized', 'danger')
        return redirect(url_for('admin_settings'))
    
    
    cursor = db.execute("SELECT user_id FROM users")
    user_ids = [row['user_id'] for row in cursor.fetchall()]
    
    asyncio.run_coroutine_threadsafe(
        broadcast_message(user_ids, message, media_data, media_type),
        bot_loop
    )
    
    media_info = f' with {media_type}' if media_type else ''
    db.log_activity('broadcast', 'users', str(len(user_ids)), f'Broadcast sent to {len(user_ids)} users{media_info}')
    flash(f'Broadcast sent to {len(user_ids)} users', 'success')
    return redirect(url_for('admin_settings'))

async def broadcast_message(user_ids, message, media_data=None, media_type=None):
    if bot_app:
        for user_id in user_ids:
            try:
                if media_data and media_type:
                    import io
                    media_bytes = io.BytesIO(media_data)
                    if media_type == 'photo':
                        await bot_app.bot.send_photo(chat_id=user_id, photo=media_bytes, caption=message or None)
                    elif media_type == 'video':
                        await bot_app.bot.send_video(chat_id=user_id, video=media_bytes, caption=message or None)
                    elif media_type == 'voice':
                        await bot_app.bot.send_voice(chat_id=user_id, voice=media_bytes, caption=message or None)
                elif message:
                    await bot_app.bot.send_message(chat_id=user_id, text=message)
            except Exception as e:
                logger.error(f"Failed to broadcast to {user_id}: {e}")

@app.route('/admin/export/users')
@require_admin_login
def export_users():
    if not db:
        return "Database not initialized", 500
    
    
    cursor = db.execute("SELECT * FROM users ORDER BY user_id")
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['user_id', 'username', 'first_name', 'balance_iqd', 'language', 'created_at'])
    
    for row in cursor.fetchall():
        writer.writerow([row['user_id'], row['username'], row['first_name'], 
                        row['balance_iqd'], row['language'], format_datetime(row['created_at'])])
    
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv',
                   headers={'Content-Disposition': 'attachment; filename=users.csv'})

@app.route('/admin/export/cards')
@require_admin_login
def export_cards():
    if not db:
        return "Database not initialized", 500
    
    
    cursor = db.execute("SELECT * FROM cards ORDER BY id")
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id', 'user_id', 'pin', 'amount', 'status', 'phone_id', 'created_at'])
    
    for row in cursor.fetchall():
        writer.writerow([row['id'], row['user_id'], row['pin'], 
                        row['amount'], row['status'], row['phone_id'], format_datetime(row['created_at'])])
    
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv',
                   headers={'Content-Disposition': 'attachment; filename=cards.csv'})

@app.route('/admin/xena')
@require_admin_login
def admin_xena():
    if not db:
        return "Database not initialized", 500
    
    
    cursor = db.execute("""
        SELECT x.*, u.username, u.first_name 
        FROM xena_orders x 
        LEFT JOIN users u ON x.user_id = u.user_id 
        ORDER BY x.id DESC
    """)
    orders = []
    for row in cursor.fetchall():
        orders.append({
            'id': row['id'],
            'user_id': row['user_id'],
            'username': row['username'],
            'first_name': row['first_name'],
            'player_id': row['player_id'],
            'coins': row['coins'],
            'price_iqd': row['price_iqd'],
            'status': row['status'],
            'created_at': format_datetime(row['created_at'])
        })
    
    return render_template('xena_history.html', orders=orders)

@app.route('/admin/xena/confirm/<int:order_id>', methods=['POST'])
@require_admin_login
def admin_xena_confirm(order_id):
    if not db:
        flash('Database not initialized', 'danger')
        return redirect(url_for('admin_xena'))
    
    
    db.execute("UPDATE xena_orders SET status = 'completed' WHERE id = ?", (order_id,))
    db.commit()
    
    db.log_activity('xena_confirm', 'xena', str(order_id), f'Xena order confirmed')
    trigger_action_backup()
    flash(f'Order #{order_id} confirmed', 'success')
    return redirect(url_for('admin_xena'))

@app.route('/admin/xena/reject/<int:order_id>', methods=['POST'])
@require_admin_login
def admin_xena_reject(order_id):
    if not db:
        flash('Database not initialized', 'danger')
        return redirect(url_for('admin_xena'))
    
    
    cursor = db.execute("SELECT user_id, price_iqd, status FROM xena_orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    
    if not order:
        flash('Order not found', 'danger')
        return redirect(url_for('admin_xena'))
    
    if order['status'] == 'rejected':
        flash('Order already rejected', 'warning')
        return redirect(url_for('admin_xena'))
    
    user_id = order['user_id']
    refund_amount = order['price_iqd']
    
    db.execute("UPDATE xena_orders SET status = 'rejected' WHERE id = ?", (order_id,))
    db.execute("UPDATE users SET balance_iqd = balance_iqd + ? WHERE user_id = ?", (refund_amount, user_id))
    db.commit()
    
    if bot_app and bot_loop:
        asyncio.run_coroutine_threadsafe(
            notify_user_refund(user_id, refund_amount, order_id),
            bot_loop
        )
    
    db.log_activity('xena_reject', 'xena', str(order_id), f'Xena order rejected, {refund_amount:,} IQD refunded to user {user_id}')
    trigger_action_backup()
    flash(f'Order #{order_id} rejected. {refund_amount:,} IQD refunded to user', 'success')
    return redirect(url_for('admin_xena'))

@app.route('/admin/xena/remove/<int:order_id>', methods=['POST'])
@require_admin_login
def admin_xena_remove(order_id):
    if not db:
        flash('Database not initialized', 'danger')
        return redirect(url_for('admin_xena'))
    
    cursor = db.execute("SELECT user_id, price_iqd, status FROM xena_orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    
    if not order:
        flash('Order not found', 'danger')
        return redirect(url_for('admin_xena'))
    
    db.execute("DELETE FROM xena_orders WHERE id = ?", (order_id,))
    db.commit()
    
    db.log_activity('xena_remove', 'xena', str(order_id), f'Xena order removed without refund (was {order["price_iqd"]:,} IQD)')
    trigger_action_backup()
    flash(f'Order #{order_id} removed (no refund)', 'success')
    return redirect(url_for('admin_xena'))

@app.route('/admin/xena/clear_pending', methods=['POST'])
@require_admin_login
def admin_xena_clear_pending():
    if not db:
        flash('Database not initialized', 'danger')
        return redirect(url_for('admin_xena'))
    
    try:
        cursor = db.execute("SELECT COUNT(*) as cnt FROM xena_orders WHERE status = 'pending'")
        row = cursor.fetchone()
        count = row['cnt'] if row else 0
        
        if count == 0:
            flash('No pending orders to clear', 'info')
            return redirect(url_for('admin_xena'))
        
        db.execute("DELETE FROM xena_orders WHERE status = 'pending'")
        db.commit()
        db.log_activity('xena_clear_pending', 'xena', str(count), f'Cleared {count} pending Xena orders')
        
        flash(f'Cleared {count} pending Xena orders', 'success')
    except Exception as e:
        logger.error(f"Error clearing pending orders: {e}")
        flash(f'Error: {str(e)}', 'danger')
    
    return redirect(url_for('admin_xena'))

@app.route('/admin/xena/complete/<int:order_id>', methods=['POST'])
@require_admin_login
def admin_xena_complete(order_id):
    if not db:
        flash('Database not initialized', 'danger')
        return redirect(url_for('admin_xena'))
    
    cursor = db.execute("SELECT user_id, player_id, coins, status FROM xena_orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    
    if not order:
        flash('Order not found', 'danger')
        return redirect(url_for('admin_xena'))
    
    db.execute("UPDATE xena_orders SET status = 'completed' WHERE id = ?", (order_id,))
    db.commit()
    db.log_activity('xena_complete', 'xena', str(order_id), f'Xena order marked as completed by admin')
    
    # Notify user via Telegram
    if bot_app and bot_loop:
        user_id = order['user_id']
        player_id = order['player_id']
        coins = order['coins']
        asyncio.run_coroutine_threadsafe(
            notify_xena_complete(user_id, order_id, player_id, coins),
            bot_loop
        )
    
    flash(f'Order #{order_id} marked as completed!', 'success')
    return redirect(url_for('admin_xena'))

async def notify_xena_complete(user_id, order_id, player_id, coins):
    if bot_app:
        try:
            await bot_app.bot.send_message(
                chat_id=user_id,
                text=f"✅ تم اكتمال طلبك!\n\n"
                     f"🎫 رقم الطلب: #{order_id}\n"
                     f"👤 ايدي اللاعب: {player_id}\n"
                     f"💎 العملات: {coins:,}\n\n"
                     f"✅ تم إرسال العملات إلى حسابك في Xena Live!\n"
                     f"شكراً لاستخدامك!"
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_id} about xena completion: {e}")

async def notify_user_refund(user_id, amount, order_id):
    if bot_app:
        try:
            await bot_app.bot.send_message(
                chat_id=user_id,
                text=f"💰 تم استرداد رصيدك!\n\n"
                     f"طلب Xena #{order_id} تم رفضه\n"
                     f"تم إضافة {amount:,} IQD إلى رصيدك\n\n"
                     f"💰 Your balance has been refunded!\n"
                     f"Xena order #{order_id} was rejected\n"
                     f"{amount:,} IQD added to your balance"
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_id} about refund: {e}")

@app.route('/admin/usd')
@require_admin_login
def admin_usd():
    if not db:
        return "Database not initialized", 500
    
    cursor = db.execute("""
        SELECT u.*, 
               (SELECT COUNT(*) FROM withdrawals w WHERE w.user_id = u.user_id) as withdrawal_count,
               (SELECT COALESCE(SUM(amount_usd), 0) FROM withdrawals w WHERE w.user_id = u.user_id AND w.status = 'approved') as total_withdrawn
        FROM users u 
        WHERE u.service_type = 'usd'
        ORDER BY u.user_id DESC
    """)
    users = []
    for row in cursor.fetchall():
        users.append({
            'user_id': row['user_id'],
            'first_name': row['first_name'],
            'username': row['username'],
            'balance_iqd': row['balance_iqd'] or 0,
            'is_verified': row['is_verified'],
            'withdrawal_count': row['withdrawal_count'],
            'total_withdrawn': float(row['total_withdrawn']) if row['total_withdrawn'] else 0
        })
    
    cursor = db.execute("SELECT key, value FROM settings WHERE key IN ('usd_rate_iqd', 'usd_rate_usd', 'usd_minimum', 'usd_fee_percent')")
    settings = {}
    for row in cursor.fetchall():
        settings[row['key']] = row['value']
    
    cursor = db.execute("SELECT COUNT(*) as pending FROM withdrawals WHERE status = 'pending'")
    pending_count = cursor.fetchone()['pending']
    
    cursor = db.execute("SELECT COALESCE(SUM(amount_usd), 0) as total FROM withdrawals WHERE status = 'approved'")
    total_paid = float(cursor.fetchone()['total'])
    
    return render_template('usd.html', users=users, settings=settings, pending_count=pending_count, total_paid=total_paid)

@app.route('/admin/usd/settings', methods=['POST'])
@require_admin_login
def admin_usd_settings():
    rate_iqd = request.form.get('rate_iqd', '100000')
    rate_usd = request.form.get('rate_usd', '55.50')
    minimum = request.form.get('minimum', '50')
    fee_percent = request.form.get('fee_percent', '0')
    
    db.execute("UPDATE settings SET value = ? WHERE key = 'usd_rate_iqd'", (rate_iqd,))
    db.execute("UPDATE settings SET value = ? WHERE key = 'usd_rate_usd'", (rate_usd,))
    db.execute("UPDATE settings SET value = ? WHERE key = 'usd_minimum'", (minimum,))
    db.execute("UPDATE settings SET value = ? WHERE key = 'usd_fee_percent'", (fee_percent,))
    db.commit()
    
    db.log_activity('usd_settings_update', 'settings', '', f'Rate: {rate_iqd} IQD = ${rate_usd}, Min: ${minimum}, Fee: {fee_percent}%')
    flash('USD settings updated', 'success')
    return redirect(url_for('admin_usd'))

@app.route('/admin/withdrawals')
@require_admin_login
def admin_withdrawals():
    if not db:
        return "Database not initialized", 500
    
    cursor = db.execute("""
        SELECT w.*, u.first_name, u.username 
        FROM withdrawals w 
        LEFT JOIN users u ON w.user_id = u.user_id 
        ORDER BY w.id DESC
    """)
    withdrawals = []
    for row in cursor.fetchall():
        withdrawals.append({
            'id': row['id'],
            'user_id': row['user_id'],
            'first_name': row['first_name'],
            'username': row['username'],
            'amount_iqd': row['amount_iqd'],
            'amount_usd': float(row['amount_usd']),
            'withdrawal_type': row['withdrawal_type'],
            'wallet_address': row['wallet_address'],
            'status': row['status'],
            'created_at': format_datetime(row['created_at']),
            'processed_at': format_datetime(row['processed_at']) if row['processed_at'] else None
        })
    
    cursor = db.execute("SELECT key, value FROM settings WHERE key IN ('usd_rate_iqd', 'usd_rate_usd', 'usd_minimum')")
    settings = {}
    for row in cursor.fetchall():
        settings[row['key']] = row['value']
    
    return render_template('withdrawals.html', withdrawals=withdrawals, settings=settings)

@app.route('/admin/withdrawal/approve/<int:withdrawal_id>', methods=['POST'])
@require_admin_login
def admin_withdrawal_approve(withdrawal_id):
    if not db:
        flash('Database not initialized', 'danger')
        return redirect(url_for('admin_withdrawals'))
    
    cursor = db.execute("SELECT * FROM withdrawals WHERE id = ?", (withdrawal_id,))
    withdrawal = cursor.fetchone()
    
    if not withdrawal:
        flash('Withdrawal not found', 'danger')
        return redirect(url_for('admin_withdrawals'))
    
    if withdrawal['status'] != 'pending':
        flash('Withdrawal already processed', 'warning')
        return redirect(url_for('admin_withdrawals'))
    
    db.execute("UPDATE withdrawals SET status = 'approved', processed_at = NOW() WHERE id = ?", (withdrawal_id,))
    db.commit()
    
    if bot_app and bot_loop:
        asyncio.run_coroutine_threadsafe(
            notify_withdrawal_approved(withdrawal['user_id'], withdrawal['amount_usd'], withdrawal['wallet_address']),
            bot_loop
        )
    
    db.log_activity('withdrawal_approve', 'withdrawal', str(withdrawal_id), 
                   f'Approved ${withdrawal["amount_usd"]} to {withdrawal["wallet_address"]}')
    flash(f'Withdrawal #{withdrawal_id} approved', 'success')
    return redirect(url_for('admin_withdrawals'))

@app.route('/admin/withdrawal/reject/<int:withdrawal_id>', methods=['POST'])
@require_admin_login
def admin_withdrawal_reject(withdrawal_id):
    if not db:
        flash('Database not initialized', 'danger')
        return redirect(url_for('admin_withdrawals'))
    
    cursor = db.execute("SELECT * FROM withdrawals WHERE id = ?", (withdrawal_id,))
    withdrawal = cursor.fetchone()
    
    if not withdrawal:
        flash('Withdrawal not found', 'danger')
        return redirect(url_for('admin_withdrawals'))
    
    if withdrawal['status'] != 'pending':
        flash('Withdrawal already processed', 'warning')
        return redirect(url_for('admin_withdrawals'))
    
    cursor = db.execute("SELECT value FROM settings WHERE key = 'usd_fee_percent'")
    fee_row = cursor.fetchone()
    fee_percent = float(fee_row['value']) if fee_row else 0
    
    refund_usd = float(withdrawal['amount_usd']) / (1 - fee_percent/100) if fee_percent > 0 else float(withdrawal['amount_usd'])
    db.execute("UPDATE users SET balance_usd = balance_usd + ? WHERE user_id = ?", 
              (refund_usd, withdrawal['user_id']))
    db.execute("UPDATE withdrawals SET status = 'rejected', processed_at = NOW() WHERE id = ?", (withdrawal_id,))
    db.commit()
    
    if bot_app and bot_loop:
        asyncio.run_coroutine_threadsafe(
            notify_withdrawal_rejected(withdrawal['user_id'], withdrawal['amount_usd'], withdrawal['amount_iqd']),
            bot_loop
        )
    
    db.log_activity('withdrawal_reject', 'withdrawal', str(withdrawal_id), 
                   f'Rejected ${withdrawal["amount_usd"]}, refunded {withdrawal["amount_iqd"]:,} IQD')
    flash(f'Withdrawal #{withdrawal_id} rejected, balance refunded', 'success')
    return redirect(url_for('admin_withdrawals'))

@app.route('/admin/withdrawal/settings', methods=['POST'])
@require_admin_login
def admin_withdrawal_settings():
    rate_iqd = request.form.get('rate_iqd', '100000')
    rate_usd = request.form.get('rate_usd', '55.50')
    minimum = request.form.get('minimum', '50')
    
    db.execute("UPDATE settings SET value = ? WHERE key = 'usd_rate_iqd'", (rate_iqd,))
    db.execute("UPDATE settings SET value = ? WHERE key = 'usd_rate_usd'", (rate_usd,))
    db.execute("UPDATE settings SET value = ? WHERE key = 'usd_minimum'", (minimum,))
    db.commit()
    
    flash('Withdrawal settings updated', 'success')
    return redirect(url_for('admin_withdrawals'))

async def notify_withdrawal_approved(user_id, amount_usd, wallet):
    if bot_app:
        try:
            await bot_app.bot.send_message(
                chat_id=user_id,
                text=f"✅ تم تحويل طلب السحب!\n\n"
                     f"💵 المبلغ: ${amount_usd}\n"
                     f"💳 العنوان: {wallet}\n\n"
                     f"✅ Withdrawal completed!\n"
                     f"💵 Amount: ${amount_usd}\n"
                     f"💳 Address: {wallet}"
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_id} about withdrawal: {e}")

async def notify_withdrawal_rejected(user_id, amount_usd, amount_iqd):
    if bot_app:
        try:
            await bot_app.bot.send_message(
                chat_id=user_id,
                text=f"❌ تم رفض طلب السحب\n\n"
                     f"💵 المبلغ: ${amount_usd}\n"
                     f"💰 تم إرجاع {amount_iqd:,} IQD لرصيدك\n\n"
                     f"❌ Withdrawal rejected\n"
                     f"💵 Amount: ${amount_usd}\n"
                     f"💰 {amount_iqd:,} IQD refunded to balance"
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_id} about withdrawal rejection: {e}")

@app.route('/admin/export/xena')
@require_admin_login
def export_xena():
    if not db:
        return "Database not initialized", 500
    
    
    cursor = db.execute("SELECT * FROM xena_orders ORDER BY id")
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id', 'user_id', 'player_id', 'coins', 'price_iqd', 'status', 'created_at'])
    
    for row in cursor.fetchall():
        writer.writerow([row['id'], row['user_id'], row['player_id'], 
                        row['coins'], row['price_iqd'], row['status'], format_datetime(row['created_at'])])
    
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv',
                   headers={'Content-Disposition': 'attachment; filename=xena_orders.csv'})

@app.route('/employee/login', methods=['GET', 'POST'])
def employee_login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if username == EMPLOYEE_USERNAME and password == EMPLOYEE_PASSWORD:
            session['employee_logged_in'] = True
            flash('Logged in successfully', 'success')
            return redirect(url_for('employee_dashboard'))
        else:
            flash('Invalid credentials', 'danger')
    return render_template('employee_login.html')

@app.route('/employee/logout')
def employee_logout():
    session.pop('employee_logged_in', None)
    flash('Logged out', 'info')
    return redirect(url_for('employee_login'))

@app.route('/employee')
@require_employee_login
def employee_dashboard():
    if not db:
        return "Database not initialized", 500
    
    phones = db.get_all_phones()
    
    
    cursor = db.execute("SELECT * FROM cards ORDER BY id DESC LIMIT 100")
    cards = []
    for row in cursor.fetchall():
        cards.append({
            'id': row['id'],
            'user_id': row['user_id'],
            'pin': row['pin'],
            'amount': row['amount'],
            'status': row['status'],
            'phone_id': row['phone_id'],
            'created_at': format_datetime(row['created_at'])
        })
    
    phone_list = []
    online_count = 0
    for p in phones:
        status = getattr(p, 'status', 'offline')
        if status == 'online':
            online_count += 1
        phone_list.append({
            'phone_id': getattr(p, 'phone_id', 'Unknown'),
            'name': getattr(p, 'name', 'System'),
            'battery_level': getattr(p, 'battery_level', 0),
            'status': status,
            'last_seen': format_datetime(getattr(p, 'last_seen', '')),
            'jobs_completed': getattr(p, 'jobs_completed', 0),
            'jobs_failed': getattr(p, 'jobs_failed', 0)
        })
    
    stats = {
        'pending': sum(1 for c in cards if c['status'] == 'pending'),
        'verified': sum(1 for c in cards if c['status'] == 'verified'),
        'failed': sum(1 for c in cards if c['status'] == 'failed'),
        'online_phones': online_count
    }
    
    return render_template('employee_dashboard.html', cards=cards, phones=phone_list, stats=stats)

@app.route('/employee/api/live-feed')
@require_employee_login
def employee_live_feed():
    if not db:
        return jsonify({"error": "Database not initialized"}), 500
    
    
    cursor = db.execute("SELECT * FROM cards ORDER BY id DESC LIMIT 20")
    cards = []
    for row in cursor.fetchall():
        cards.append({
            'id': row['id'],
            'user_id': row['user_id'],
            'pin': row['pin'],
            'amount': row['amount'],
            'status': row['status'],
            'phone_id': row['phone_id'],
            'created_at': format_datetime(row['created_at'])
        })
    
    phones = db.get_all_phones()
    phone_list = []
    for p in phones:
        phone_list.append({
            'phone_id': getattr(p, 'phone_id', 'Unknown'),
            'name': getattr(p, 'name', 'System'),
            'battery_level': getattr(p, 'battery_level', 0),
            'status': getattr(p, 'status', 'offline'),
            'last_seen': format_datetime(getattr(p, 'last_seen', '')),
            'jobs_completed': getattr(p, 'jobs_completed', 0),
            'jobs_failed': getattr(p, 'jobs_failed', 0)
        })
    
    return jsonify({
        'cards': cards,
        'phones': phone_list
    })

def run_api():
    logger.info(f"Starting API server on {config.API_HOST}:{config.API_PORT}")
    app.run(host=config.API_HOST, port=config.API_PORT, debug=False, use_reloader=False)
