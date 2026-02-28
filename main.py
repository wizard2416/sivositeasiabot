import asyncio
import threading
import logging
import signal
import sys
import os
from datetime import datetime

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

import config
from src.services import Database, OCRService
from api import app, init_api

action_counter = 0

async def send_database_backup(bot_app, db, reason="scheduled"):
    """Send PostgreSQL database backup as CSV files to admins"""
    if not bot_app or not config.ADMIN_USER_IDS:
        return
    
    try:
        from src.services.backup import create_database_backup, send_backup_to_admin
        
        files = create_database_backup(db)
        if files:
            for admin_id in config.ADMIN_USER_IDS:
                await send_backup_to_admin(bot_app.bot, admin_id, files)
            
            for f in files:
                if os.path.exists(f):
                    os.remove(f)
            
            logger.info(f"Database backup sent - reason: {reason}")
        else:
            logger.warning("No backup files created")
    except Exception as e:
        logger.error(f"Error creating database backup: {e}")

async def periodic_backup(bot_app, db):
    while True:
        try:
            await asyncio.sleep(12 * 60 * 60)
            await send_database_backup(bot_app, db, "12-hour scheduled backup")
        except Exception as e:
            logger.error(f"Error in periodic backup: {e}")

async def check_offline_phones(db, bot_app):
    while True:
        try:
            await asyncio.sleep(120)
            
            if not bot_app or not config.ADMIN_USER_IDS:
                continue
            
            offline_phones = db.get_offline_phones(minutes=5)
            
            for phone in offline_phones:
                phone_id = phone['phone_id']
                phone_name = phone.get('name', phone_id)
                last_seen = phone.get('last_seen', 'Unknown')
                
                if db.should_alert_phone(phone_id, cooldown_minutes=30):
                    alert_msg = (
                        f"⚠️ Phone Offline Alert\n\n"
                        f"📱 Phone: {phone_name}\n"
                        f"🆔 ID: {phone_id}\n"
                        f"🕐 Last seen: {last_seen}\n\n"
                        f"The phone has been offline for more than 5 minutes."
                    )
                    
                    for admin_id in config.ADMIN_USER_IDS:
                        try:
                            await bot_app.bot.send_message(chat_id=admin_id, text=alert_msg)
                        except Exception as e:
                            logger.error(f"Failed to alert admin {admin_id} about phone {phone_id}: {e}")
                    
                    db.update_phone_alert(phone_id)
                    db.log_activity('phone_offline_alert', 'phone', phone_id, 
                                   f'Phone {phone_name} offline alert sent to admins')
                    logger.info(f"Sent offline alert for phone {phone_id} to admins")
        except Exception as e:
            logger.error(f"Error in offline phone check: {e}")


API_ONLY_MODE = os.environ.get("API_ONLY", "").lower() in ("1", "true", "yes") or \
                os.environ.get("DISABLE_BOT_POLLING", "").lower() in ("1", "true", "yes")

def run_flask():
    logger.info(f"Starting Flask API on port {config.API_PORT}")
    app.run(host=config.API_HOST, port=config.API_PORT, debug=False, use_reloader=False)

async def main():
    if API_ONLY_MODE:
        logger.info("Starting in API-ONLY mode (no Telegram bot)")
    else:
        logger.info("Initializing Asiacell Telegram Bot...")
    
    db = Database(config.DATABASE_URL)
    logger.info("Database initialized")
    
    ocr = OCRService()
    logger.info("OCR service initialized")
    
    loop = asyncio.get_running_loop()
    init_api(db, event_loop=loop)
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask API started in background thread")
    
    if API_ONLY_MODE or not config.TELEGRAM_BOT_TOKEN:
        if API_ONLY_MODE:
            logger.info("Running in API-ONLY mode (development)")
        else:
            logger.warning("TELEGRAM_BOT_TOKEN not set - bot will not start")
        logger.info("API server is running.")
        
        try:
            while True:
                await asyncio.sleep(60)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        return
    
    from bot import run_bot
    
    application = await run_bot(db, ocr)
    logger.info("Telegram bot started")
    
    init_api(db, application, loop)
    
    asyncio.create_task(check_offline_phones(db, application))
    logger.info("Phone offline monitoring started")
    
    asyncio.create_task(periodic_backup(application, db))
    logger.info("12-hour periodic backup started")
    
    
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
