import os
import csv
import asyncio
from datetime import datetime
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import logging

logger = logging.getLogger(__name__)

IRAQ_TZ = pytz.timezone('Asia/Baghdad')
BACKUP_DIR = '/tmp/db_backup'

def export_table_to_csv(db, table_name, columns):
    """Export a single table to CSV file"""
    try:
        query = f"SELECT {', '.join(columns)} FROM {table_name}"
        result = db.execute(query)
        rows = result.fetchall() if result else []
        
        filepath = os.path.join(BACKUP_DIR, f"{table_name}.csv")
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            for row in rows:
                writer.writerow(row)
        
        return filepath
    except Exception as e:
        logger.error(f"Failed to export {table_name}: {e}")
        return None

def create_database_backup(db):
    """Create backup files for all tables"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    tables = {
        'users': ['user_id', 'username', 'first_name', 'phone_number', 'is_verified', 
                  'is_blocked', 'is_vip', 'balance_iqd', 'balance_coins', 'language', 
                  'service_type', 'created_at'],
        'cards': ['id', 'user_id', 'pin', 'status', 'amount', 'phone_id', 'created_at', 
                  'processed_at', 'result_message', 'retry_count'],
        'xena_orders': ['id', 'user_id', 'player_id', 'coins', 'price_iqd', 'status', 
                        'severbil_order_id', 'created_at', 'completed_at'],
        'payment_requests': ['id', 'user_id', 'amount', 'payment_method', 'status', 
                             'proof_file_id', 'created_at', 'processed_at', 'transaction_number'],
        'phones': ['phone_id', 'name', 'battery_level', 'last_seen', 'is_active', 
                   'cards_processed', 'cards_success', 'cards_failed'],
    }
    
    files = []
    for table_name, columns in tables.items():
        filepath = export_table_to_csv(db, table_name, columns)
        if filepath:
            files.append(filepath)
    
    return files

async def send_backup_to_admin(bot, admin_id, files):
    """Send backup files to admin via Telegram"""
    try:
        iraq_now = datetime.now(IRAQ_TZ)
        date_str = iraq_now.strftime('%Y-%m-%d %H:%M')
        
        await bot.send_message(
            chat_id=admin_id,
            text=f"📦 نسخة احتياطية من قاعدة البيانات\n"
                 f"📅 التاريخ: {date_str}\n"
                 f"📁 عدد الملفات: {len(files)}"
        )
        
        for filepath in files:
            try:
                if os.path.exists(filepath):
                    with open(filepath, 'rb') as f:
                        await bot.send_document(
                            chat_id=admin_id,
                            document=f,
                            filename=os.path.basename(filepath)
                        )
                    await asyncio.sleep(0.5)
            except Exception as file_err:
                logger.error(f"Failed to send file {filepath}: {file_err}")
                continue
        
        logger.info(f"Backup sent to admin {admin_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to send backup to admin {admin_id}: {e}")
        return False

async def run_daily_backup(bot, db, admin_ids):
    """Run the daily backup job"""
    logger.info("Starting daily database backup...")
    
    try:
        files = create_database_backup(db)
        
        if files:
            for admin_id in admin_ids:
                await send_backup_to_admin(bot, admin_id, files)
        
        for f in files:
            if os.path.exists(f):
                os.remove(f)
                
        logger.info("Daily backup completed successfully")
    except Exception as e:
        logger.error(f"Daily backup failed: {e}")

def setup_backup_scheduler(bot, db, admin_ids):
    """Setup the scheduler to run backup at midnight Iraq time"""
    scheduler = AsyncIOScheduler(timezone=IRAQ_TZ)
    
    scheduler.add_job(
        run_daily_backup,
        CronTrigger(hour=0, minute=0, timezone=IRAQ_TZ),
        args=[bot, db, admin_ids],
        id='daily_backup',
        name='Daily Database Backup',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("Backup scheduler started - will run daily at 00:00 Iraq time")
    return scheduler
