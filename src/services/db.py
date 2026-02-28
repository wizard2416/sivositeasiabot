import psycopg2
import psycopg2.extras
import psycopg2.extensions
import threading
import os
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List

logger = logging.getLogger(__name__)

@dataclass
class User:
    user_id: int
    username: str
    first_name: str
    balance_iqd: int
    language: str
    created_at: str
    is_blocked: bool = False
    is_vip: bool = False
    is_verified: bool = False
    phone_number: str = ""
    approval_notified: bool = False
    is_rejected: bool = False
    balance_coins: int = 0
    service_type: str = "xena"  # 'xena', 'imo', or 'both'

@dataclass
class Card:
    id: int
    user_id: int
    pin: str
    amount: int
    status: str
    retry_count: int
    image_path: Optional[str]
    phone_id: Optional[str]
    created_at: str
    verified_at: Optional[str]

@dataclass
class XenaOrder:
    id: int
    user_id: int
    player_id: str
    coins: int
    price_iqd: int
    severbil_order_id: str
    status: str
    created_at: str

@dataclass
class Phone:
    phone_id: str
    name: str
    battery_level: int
    last_seen: str
    status: str
    jobs_completed: int
    jobs_failed: int

@dataclass
class PaymentRequest:
    id: int
    user_id: int
    payment_type: str
    amount: int
    proof_image_path: Optional[str]
    status: str
    admin_note: Optional[str]
    actual_amount: Optional[int]
    transaction_number: Optional[str]
    created_at: str
    processed_at: Optional[str]

class DictCursor:
    """Wrapper to make cursor results behave like SQLite Row objects."""
    def __init__(self, cursor):
        self._cursor = cursor
        self._columns = None
    
    def execute(self, query, params=None):
        # Convert SQLite placeholders (?) to PostgreSQL (%s)
        query = query.replace('?', '%s')
        if params:
            self._cursor.execute(query, params)
        else:
            self._cursor.execute(query)
        if self._cursor.description:
            self._columns = [desc[0] for desc in self._cursor.description]
        return self
    
    def fetchone(self):
        row = self._cursor.fetchone()
        if row and self._columns:
            return dict(zip(self._columns, row))
        return row
    
    def fetchall(self):
        rows = self._cursor.fetchall()
        if rows and self._columns:
            return [dict(zip(self._columns, row)) for row in rows]
        return rows
    
    def __iter__(self):
        return self
    
    def __next__(self):
        row = self._cursor.fetchone()
        if row is None:
            raise StopIteration
        if self._columns:
            return dict(zip(self._columns, row))
        return row

class Database:
    def __init__(self, db_url: str = None):
        self.db_url = db_url or os.environ.get('DATABASE_URL')
        self._local = threading.local()
        self._init_db()

    def _get_conn(self):
        if not hasattr(self._local, 'conn') or self._local.conn is None or self._local.conn.closed:
            self._local.conn = psycopg2.connect(self.db_url)
            self._local.conn.autocommit = False
        else:
            try:
                if self._local.conn.status == psycopg2.extensions.TRANSACTION_STATUS_INERROR:
                    self._local.conn.rollback()
            except:
                try:
                    self._local.conn.close()
                except:
                    pass
                self._local.conn = psycopg2.connect(self.db_url)
                self._local.conn.autocommit = False
        return self._local.conn
    
    def execute(self, query, params=None):
        """Execute a query with SQLite-compatible syntax."""
        conn = self._get_conn()
        cursor = conn.cursor()
        query = query.replace('?', '%s')
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
        except psycopg2.Error as e:
            conn.rollback()
            raise e
        wrapper = DictCursor(cursor)
        if cursor.description:
            wrapper._columns = [desc[0] for desc in cursor.description]
        return wrapper
    
    def commit(self):
        """Commit current transaction."""
        self._get_conn().commit()

    def _init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                balance_iqd INTEGER DEFAULT 0,
                language TEXT DEFAULT 'ar',
                is_blocked INTEGER DEFAULT 0,
                is_vip INTEGER DEFAULT 0,
                is_verified INTEGER DEFAULT 0,
                phone_number TEXT DEFAULT '',
                approval_notified INTEGER DEFAULT 0,
                is_rejected INTEGER DEFAULT 0,
                balance_coins INTEGER DEFAULT 0,
                service_type TEXT DEFAULT 'xena',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cards (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                pin TEXT UNIQUE,
                amount INTEGER,
                status TEXT DEFAULT 'pending',
                retry_count INTEGER DEFAULT 0,
                image_path TEXT,
                phone_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                verified_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS xena_orders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                player_id TEXT,
                coins INTEGER,
                price_iqd INTEGER,
                severbil_order_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS phones (
                phone_id TEXT PRIMARY KEY,
                name TEXT,
                battery_level INTEGER DEFAULT 100,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'offline',
                jobs_completed INTEGER DEFAULT 0,
                jobs_failed INTEGER DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS message_log (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                direction TEXT,
                message_type TEXT DEFAULT 'text',
                content TEXT,
                media_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payment_requests (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                payment_type TEXT NOT NULL,
                amount INTEGER NOT NULL,
                proof_image_path TEXT,
                status TEXT DEFAULT 'pending',
                admin_note TEXT,
                actual_amount INTEGER,
                transaction_number TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_messages (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                direction TEXT,
                message_type TEXT DEFAULT 'text',
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activity_log (
                id SERIAL PRIMARY KEY,
                action_type TEXT NOT NULL,
                target_type TEXT,
                target_id TEXT,
                details TEXT,
                admin_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS phone_alerts (
                phone_id TEXT PRIMARY KEY,
                last_alert_at TIMESTAMP,
                FOREIGN KEY (phone_id) REFERENCES phones(phone_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pre_approvals (
                user_id BIGINT PRIMARY KEY,
                service_type TEXT DEFAULT 'xena',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                note TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS coin_rates (
                id SERIAL PRIMARY KEY,
                payment_source TEXT UNIQUE NOT NULL,
                source_amount INTEGER NOT NULL,
                coin_amount INTEGER NOT NULL,
                currency_name TEXT DEFAULT 'دينار',
                is_active INTEGER DEFAULT 1,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert default coin rates if not exist
        cursor.execute('''
            INSERT INTO coin_rates (payment_source, source_amount, coin_amount, currency_name) 
            VALUES ('asiacell', 10000, 55000, 'دينار آسيا سيل')
            ON CONFLICT (payment_source) DO NOTHING
        ''')
        cursor.execute('''
            INSERT INTO coin_rates (payment_source, source_amount, coin_amount, currency_name) 
            VALUES ('qi_card', 10000, 60000, 'دينار QI Card')
            ON CONFLICT (payment_source) DO NOTHING
        ''')
        cursor.execute('''
            INSERT INTO coin_rates (payment_source, source_amount, coin_amount, currency_name) 
            VALUES ('zaincash', 10000, 60000, 'دينار ZainCash')
            ON CONFLICT (payment_source) DO NOTHING
        ''')
        cursor.execute('''
            INSERT INTO coin_rates (payment_source, source_amount, coin_amount, currency_name) 
            VALUES ('vodafone', 100, 18500, 'جنيه')
            ON CONFLICT (payment_source) DO NOTHING
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS balance_transactions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                amount INTEGER NOT NULL,
                balance_before INTEGER,
                balance_after INTEGER,
                transaction_type TEXT,
                reference_id TEXT,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Migration: Add service_type column if not exists
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS service_type TEXT DEFAULT 'xena'")
        except Exception as e:
            logger.debug(f"service_type column may already exist: {e}")
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cards_status ON cards(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cards_user ON cards(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_xena_user ON xena_orders(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_payment_user ON payment_requests(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_payment_status ON payment_requests(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_messages(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_log(created_at)')
        
        conn.commit()

    def _row_to_dict(self, cursor, row):
        if row is None:
            return None
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))

    def get_or_create_user(self, user_id: int, username: str = "", first_name: str = "") -> User:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        
        if row:
            data = self._row_to_dict(cursor, row)
            return User(
                user_id=data['user_id'],
                username=data['username'] or '',
                first_name=data['first_name'] or '',
                balance_iqd=data['balance_iqd'] or 0,
                language=data.get('language', 'ar') or 'ar',
                created_at=str(data['created_at']),
                is_blocked=bool(data.get('is_blocked', 0)),
                is_vip=bool(data.get('is_vip', 0)),
                is_verified=bool(data.get('is_verified', 0)),
                phone_number=data.get('phone_number', '') or '',
                approval_notified=bool(data.get('approval_notified', 0)),
                is_rejected=bool(data.get('is_rejected', 0)),
                balance_coins=data.get('balance_coins', 0) or 0,
                service_type=data.get('service_type', 'xena') or 'xena'
            )
        
        # Check for pre-approval
        cursor.execute("SELECT service_type FROM pre_approvals WHERE user_id = %s", (user_id,))
        pre_approval = cursor.fetchone()
        service_type = 'xena'
        is_verified = 0
        if pre_approval:
            service_type = pre_approval[0] or 'xena'
            is_verified = 1  # Pre-approved users are auto-verified
            # Remove from pre_approvals after use
            cursor.execute("DELETE FROM pre_approvals WHERE user_id = %s", (user_id,))
        
        cursor.execute(
            "INSERT INTO users (user_id, username, first_name, language, is_verified, service_type) VALUES (%s, %s, %s, 'ar', %s, %s)",
            (user_id, username or "", first_name or "", is_verified, service_type)
        )
        conn.commit()
        return User(user_id=user_id, username=username or "", first_name=first_name or "", 
                   balance_iqd=0, language='ar', created_at=datetime.now().isoformat(), 
                   is_verified=bool(is_verified), service_type=service_type)

    def get_balance(self, user_id: int) -> User:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        if row:
            data = self._row_to_dict(cursor, row)
            return User(
                user_id=data['user_id'],
                username=data['username'] or '',
                first_name=data['first_name'] or '',
                balance_iqd=data['balance_iqd'] or 0,
                language=data.get('language', 'ar') or 'ar',
                created_at=str(data['created_at']),
                is_blocked=bool(data.get('is_blocked', 0)),
                is_vip=bool(data.get('is_vip', 0)),
                is_verified=bool(data.get('is_verified', 0)),
                phone_number=data.get('phone_number', '') or '',
                approval_notified=bool(data.get('approval_notified', 0)),
                is_rejected=bool(data.get('is_rejected', 0)),
                balance_coins=data.get('balance_coins', 0) or 0
            )
        return User(user_id=user_id, username="", first_name="", balance_iqd=0, language='ar', created_at="")

    def get_user_language(self, user_id: int) -> str:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT language FROM users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        return row[0] if row and row[0] else 'ar'

    def set_user_language(self, user_id: int, language: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET language = %s WHERE user_id = %s", (language, user_id))
        conn.commit()

    def add_balance(self, user_id: int, amount: int, transaction_type: str = None, reference_id: str = None, note: str = None):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT balance_iqd FROM users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        balance_before = row[0] if row else 0
        cursor.execute("UPDATE users SET balance_iqd = balance_iqd + %s WHERE user_id = %s", (amount, user_id))
        balance_after = balance_before + amount
        cursor.execute(
            "INSERT INTO balance_transactions (user_id, amount, balance_before, balance_after, transaction_type, reference_id, note) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (user_id, amount, balance_before, balance_after, transaction_type, reference_id, note)
        )
        conn.commit()
        logger.info(f"Balance change: user={user_id}, amount={amount:+d}, before={balance_before}, after={balance_after}, type={transaction_type}")

    def deduct_balance(self, user_id: int, amount: int, transaction_type: str = None, reference_id: str = None, note: str = None) -> bool:
        """Safely deduct balance - returns False if insufficient funds (prevents negative balance)"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT balance_iqd FROM users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        balance_before = row[0] if row else 0
        if balance_before >= amount:
            cursor.execute("UPDATE users SET balance_iqd = balance_iqd - %s WHERE user_id = %s", (amount, user_id))
            balance_after = balance_before - amount
            cursor.execute(
                "INSERT INTO balance_transactions (user_id, amount, balance_before, balance_after, transaction_type, reference_id, note) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (user_id, -amount, balance_before, balance_after, transaction_type, reference_id, note)
            )
            conn.commit()
            logger.info(f"Balance deducted: user={user_id}, amount=-{amount}, before={balance_before}, after={balance_after}, type={transaction_type}")
            return True
        logger.warning(f"Insufficient balance: user={user_id}, balance={balance_before}, required={amount}, type={transaction_type}")
        return False

    def set_balance(self, user_id: int, amount: int):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance_iqd = %s WHERE user_id = %s", (amount, user_id))
        conn.commit()

    def add_card(self, user_id: int, pin: str, amount: int = 0, image_path: str = None) -> int:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO cards (user_id, pin, amount, image_path) VALUES (%s, %s, %s, %s) RETURNING id",
            (user_id, pin, amount, image_path)
        )
        card_id = cursor.fetchone()[0]
        conn.commit()
        return card_id

    def get_card_by_pin(self, pin: str) -> Optional[Card]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cards WHERE pin = %s", (pin,))
        row = cursor.fetchone()
        if row:
            data = self._row_to_dict(cursor, row)
            return Card(
                id=data['id'],
                user_id=data['user_id'],
                pin=data['pin'],
                amount=data['amount'] or 0,
                status=data['status'],
                retry_count=data.get('retry_count', 0) or 0,
                image_path=data.get('image_path'),
                phone_id=data.get('phone_id'),
                created_at=str(data['created_at']),
                verified_at=str(data['verified_at']) if data.get('verified_at') else None
            )
        return None

    def check_duplicate_card(self, pin: str) -> Optional[dict]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id, status, created_at FROM cards WHERE pin = %s", (pin,))
        row = cursor.fetchone()
        if row:
            data = self._row_to_dict(cursor, row)
            return {
                'id': data['id'],
                'status': data['status'],
                'created_at': str(data['created_at'])
            }
        return None

    def create_card(self, user_id: int, pin: str, amount: int = 0, image_path: str = None) -> Optional[int]:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO cards (user_id, pin, amount, image_path) VALUES (%s, %s, %s, %s) RETURNING id",
                (user_id, pin, amount, image_path)
            )
            card_id = cursor.fetchone()[0]
            conn.commit()
            logger.info(f"Card created: id={card_id}, user={user_id}, pin={pin[:4]}****")
            return card_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Card creation failed: user={user_id}, pin={pin[:4]}****, error={e}")
            return None

    def get_pending_card(self, is_vip_first: bool = True) -> Optional[Card]:
        conn = self._get_conn()
        cursor = conn.cursor()
        if is_vip_first:
            cursor.execute("""
                SELECT c.* FROM cards c 
                LEFT JOIN users u ON c.user_id = u.user_id 
                WHERE c.status = 'pending' 
                ORDER BY COALESCE(u.is_vip, 0) DESC, c.created_at ASC 
                LIMIT 1
            """)
        else:
            cursor.execute("SELECT * FROM cards WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1")
        row = cursor.fetchone()
        if row:
            data = self._row_to_dict(cursor, row)
            return Card(
                id=data['id'],
                user_id=data['user_id'],
                pin=data['pin'],
                amount=data['amount'] or 0,
                status=data['status'],
                retry_count=data.get('retry_count', 0) or 0,
                image_path=data.get('image_path'),
                phone_id=data.get('phone_id'),
                created_at=str(data['created_at']),
                verified_at=str(data['verified_at']) if data.get('verified_at') else None
            )
        return None

    def get_pending_card_vip_priority(self, phone_id: str = None) -> Optional[Card]:
        """Get pending card with VIP priority. Alias for get_pending_card with VIP first."""
        return self.get_pending_card(is_vip_first=True)

    def get_card_by_id(self, card_id: int) -> Optional[Card]:
        """Get card by ID. Alias for get_card."""
        return self.get_card(card_id)

    def toggle_vip(self, user_id: int) -> bool:
        """Toggle VIP status for a user. Returns new VIP status."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT is_vip FROM users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        if row:
            new_vip = 0 if row[0] else 1
            cursor.execute("UPDATE users SET is_vip = %s WHERE user_id = %s", (new_vip, user_id))
            conn.commit()
            return new_vip == 1
        return False

    def update_phone_stats(self, phone_id: str, success: bool):
        """Update phone job statistics."""
        conn = self._get_conn()
        cursor = conn.cursor()
        if success:
            cursor.execute(
                "UPDATE phones SET jobs_completed = jobs_completed + 1 WHERE phone_id = %s",
                (phone_id,)
            )
        else:
            cursor.execute(
                "UPDATE phones SET jobs_failed = jobs_failed + 1 WHERE phone_id = %s",
                (phone_id,)
            )
        conn.commit()

    def update_card_status(self, card_id: int, status: str, amount: int = None, phone_id: str = None):
        conn = self._get_conn()
        cursor = conn.cursor()
        if amount is not None:
            cursor.execute(
                "UPDATE cards SET status = %s, amount = %s, verified_at = CURRENT_TIMESTAMP WHERE id = %s",
                (status, amount, card_id)
            )
        elif phone_id:
            cursor.execute(
                "UPDATE cards SET status = %s, phone_id = %s, verified_at = CURRENT_TIMESTAMP WHERE id = %s",
                (status, phone_id, card_id)
            )
        else:
            cursor.execute(
                "UPDATE cards SET status = %s, verified_at = CURRENT_TIMESTAMP WHERE id = %s",
                (status, card_id)
            )
        conn.commit()

    def mark_card_processing(self, card_id: int, phone_id: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE cards SET status = 'processing', phone_id = %s WHERE id = %s", (phone_id, card_id))
        conn.commit()

    def get_card(self, card_id: int) -> Optional[Card]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cards WHERE id = %s", (card_id,))
        row = cursor.fetchone()
        if row:
            data = self._row_to_dict(cursor, row)
            return Card(
                id=data['id'],
                user_id=data['user_id'],
                pin=data['pin'],
                amount=data['amount'] or 0,
                status=data['status'],
                retry_count=data.get('retry_count', 0) or 0,
                image_path=data.get('image_path'),
                phone_id=data.get('phone_id'),
                created_at=str(data['created_at']),
                verified_at=str(data['verified_at']) if data.get('verified_at') else None
            )
        return None

    def get_user_pending_cards(self, user_id: int) -> List[Card]:
        """Get all pending and processing cards for a user."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM cards WHERE user_id = %s AND status IN ('pending', 'processing') ORDER BY created_at DESC",
            (user_id,)
        )
        cards = []
        for row in cursor.fetchall():
            data = self._row_to_dict(cursor, row)
            cards.append(Card(
                id=data['id'],
                user_id=data['user_id'],
                pin=data['pin'],
                amount=data['amount'] or 0,
                status=data['status'],
                retry_count=data.get('retry_count', 0) or 0,
                image_path=data.get('image_path'),
                phone_id=data.get('phone_id'),
                created_at=data['created_at'],
                verified_at=data.get('verified_at')
            ))
        return cards

    def get_user_cards(self, user_id: int, limit: int = 10) -> List[Card]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cards WHERE user_id = %s ORDER BY created_at DESC LIMIT %s", (user_id, limit))
        cards = []
        for row in cursor.fetchall():
            data = self._row_to_dict(cursor, row)
            cards.append(Card(
                id=data['id'],
                user_id=data['user_id'],
                pin=data['pin'],
                amount=data['amount'] or 0,
                status=data['status'],
                retry_count=data.get('retry_count', 0) or 0,
                image_path=data.get('image_path'),
                phone_id=data.get('phone_id'),
                created_at=str(data['created_at']),
                verified_at=str(data['verified_at']) if data.get('verified_at') else None
            ))
        return cards

    def get_failed_cards(self, user_id: int) -> List[Card]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM cards WHERE user_id = %s AND status = 'failed' AND retry_count < 3 ORDER BY created_at DESC",
            (user_id,)
        )
        cards = []
        for row in cursor.fetchall():
            data = self._row_to_dict(cursor, row)
            cards.append(Card(
                id=data['id'],
                user_id=data['user_id'],
                pin=data['pin'],
                amount=data['amount'] or 0,
                status=data['status'],
                retry_count=data.get('retry_count', 0) or 0,
                image_path=data.get('image_path'),
                phone_id=data.get('phone_id'),
                created_at=str(data['created_at']),
                verified_at=str(data['verified_at']) if data.get('verified_at') else None
            ))
        return cards

    def retry_card(self, card_id: int) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT retry_count FROM cards WHERE id = %s", (card_id,))
        row = cursor.fetchone()
        if row and row[0] < 3:
            cursor.execute(
                "UPDATE cards SET status = 'pending', retry_count = retry_count + 1 WHERE id = %s",
                (card_id,)
            )
            conn.commit()
            return True
        return False

    def get_all_cards(self, status: str = None, limit: int = 100) -> List[Card]:
        conn = self._get_conn()
        cursor = conn.cursor()
        if status:
            cursor.execute("SELECT * FROM cards WHERE status = %s ORDER BY created_at DESC LIMIT %s", (status, limit))
        else:
            cursor.execute("SELECT * FROM cards ORDER BY created_at DESC LIMIT %s", (limit,))
        cards = []
        for row in cursor.fetchall():
            data = self._row_to_dict(cursor, row)
            cards.append(Card(
                id=data['id'],
                user_id=data['user_id'],
                pin=data['pin'],
                amount=data['amount'] or 0,
                status=data['status'],
                retry_count=data.get('retry_count', 0) or 0,
                image_path=data.get('image_path'),
                phone_id=data.get('phone_id'),
                created_at=str(data['created_at']),
                verified_at=str(data['verified_at']) if data.get('verified_at') else None
            ))
        return cards

    def add_xena_order(self, user_id: int, player_id: str, coins: int, price_iqd: int, severbil_order_id: str = "") -> int:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO xena_orders (user_id, player_id, coins, price_iqd, severbil_order_id) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (user_id, player_id, coins, price_iqd, severbil_order_id)
        )
        order_id = cursor.fetchone()[0]
        conn.commit()
        return order_id

    def update_xena_order_status(self, order_id: int, status: str, severbil_order_id: str = None):
        conn = self._get_conn()
        cursor = conn.cursor()
        if severbil_order_id:
            cursor.execute(
                "UPDATE xena_orders SET status = %s, severbil_order_id = %s WHERE id = %s",
                (status, severbil_order_id, order_id)
            )
        else:
            cursor.execute("UPDATE xena_orders SET status = %s WHERE id = %s", (status, order_id))
        conn.commit()

    def get_xena_order(self, order_id: int) -> Optional[XenaOrder]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM xena_orders WHERE id = %s", (order_id,))
        row = cursor.fetchone()
        if row:
            data = self._row_to_dict(cursor, row)
            return XenaOrder(
                id=data['id'],
                user_id=data['user_id'],
                player_id=data['player_id'],
                coins=data['coins'],
                price_iqd=data['price_iqd'],
                severbil_order_id=data['severbil_order_id'] or '',
                status=data['status'],
                created_at=str(data['created_at'])
            )
        return None

    def get_user_xena_orders(self, user_id: int, limit: int = 10) -> List[XenaOrder]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM xena_orders WHERE user_id = %s ORDER BY created_at DESC LIMIT %s", (user_id, limit))
        orders = []
        for row in cursor.fetchall():
            data = self._row_to_dict(cursor, row)
            orders.append(XenaOrder(
                id=data['id'],
                user_id=data['user_id'],
                player_id=data['player_id'],
                coins=data['coins'],
                price_iqd=data['price_iqd'],
                severbil_order_id=data['severbil_order_id'] or '',
                status=data['status'],
                created_at=str(data['created_at'])
            ))
        return orders

    def get_all_xena_orders(self, status: str = None, limit: int = 100) -> List[XenaOrder]:
        conn = self._get_conn()
        cursor = conn.cursor()
        if status:
            cursor.execute("SELECT * FROM xena_orders WHERE status = %s ORDER BY created_at DESC LIMIT %s", (status, limit))
        else:
            cursor.execute("SELECT * FROM xena_orders ORDER BY created_at DESC LIMIT %s", (limit,))
        orders = []
        for row in cursor.fetchall():
            data = self._row_to_dict(cursor, row)
            orders.append(XenaOrder(
                id=data['id'],
                user_id=data['user_id'],
                player_id=data['player_id'],
                coins=data['coins'],
                price_iqd=data['price_iqd'],
                severbil_order_id=data['severbil_order_id'] or '',
                status=data['status'],
                created_at=str(data['created_at'])
            ))
        return orders

    def get_pending_xena_orders(self) -> List[XenaOrder]:
        return self.get_all_xena_orders(status='pending')

    def register_phone(self, phone_id: str, name: str = None, battery_level: int = 100):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO phones (phone_id, name, battery_level, last_seen, status) 
               VALUES (%s, %s, %s, CURRENT_TIMESTAMP, 'online')
               ON CONFLICT (phone_id) DO UPDATE SET 
               name = COALESCE(EXCLUDED.name, phones.name),
               battery_level = EXCLUDED.battery_level,
               last_seen = CURRENT_TIMESTAMP,
               status = 'online'""",
            (phone_id, name, battery_level)
        )
        conn.commit()

    def update_phone_battery(self, phone_id: str, battery_level: int):
        """Update phone battery and return level if low (below 20), else None."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE phones SET battery_level = %s, last_seen = CURRENT_TIMESTAMP WHERE phone_id = %s",
            (battery_level, phone_id)
        )
        conn.commit()
        if battery_level < 20:
            return battery_level
        return None

    def update_phone_heartbeat(self, phone_id: str, battery_level: int = None):
        conn = self._get_conn()
        cursor = conn.cursor()
        if battery_level is not None:
            cursor.execute(
                "UPDATE phones SET last_seen = CURRENT_TIMESTAMP, status = 'online', battery_level = %s WHERE phone_id = %s",
                (battery_level, phone_id)
            )
        else:
            cursor.execute(
                "UPDATE phones SET last_seen = CURRENT_TIMESTAMP, status = 'online' WHERE phone_id = %s",
                (phone_id,)
            )
        conn.commit()

    def get_phone(self, phone_id: str) -> Optional[Phone]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM phones WHERE phone_id = %s", (phone_id,))
        row = cursor.fetchone()
        if row:
            data = self._row_to_dict(cursor, row)
            return Phone(
                phone_id=data['phone_id'],
                name=data['name'] or '',
                battery_level=data['battery_level'] or 100,
                last_seen=str(data['last_seen']),
                status=data['status'],
                jobs_completed=data['jobs_completed'] or 0,
                jobs_failed=data['jobs_failed'] or 0
            )
        return None

    def get_online_phones(self, timeout_minutes: int = 5) -> List[Phone]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM phones WHERE last_seen > NOW() - INTERVAL '%s minutes'",
            (timeout_minutes,)
        )
        phones = []
        for row in cursor.fetchall():
            data = self._row_to_dict(cursor, row)
            phones.append(Phone(
                phone_id=data['phone_id'],
                name=data['name'] or '',
                battery_level=data['battery_level'] or 100,
                last_seen=str(data['last_seen']),
                status=data['status'],
                jobs_completed=data['jobs_completed'] or 0,
                jobs_failed=data['jobs_failed'] or 0
            ))
        return phones

    def get_all_phones(self) -> List[Phone]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM phones ORDER BY last_seen DESC")
        phones = []
        for row in cursor.fetchall():
            data = self._row_to_dict(cursor, row)
            phones.append(Phone(
                phone_id=data['phone_id'],
                name=data['name'] or '',
                battery_level=data['battery_level'] or 100,
                last_seen=str(data['last_seen']),
                status=data['status'],
                jobs_completed=data['jobs_completed'] or 0,
                jobs_failed=data['jobs_failed'] or 0
            ))
        return phones

    def increment_phone_jobs(self, phone_id: str, completed: bool = True):
        conn = self._get_conn()
        cursor = conn.cursor()
        if completed:
            cursor.execute("UPDATE phones SET jobs_completed = jobs_completed + 1 WHERE phone_id = %s", (phone_id,))
        else:
            cursor.execute("UPDATE phones SET jobs_failed = jobs_failed + 1 WHERE phone_id = %s", (phone_id,))
        conn.commit()

    def get_stats(self) -> dict:
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM cards WHERE status = 'pending'")
        pending = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM cards WHERE status = 'verified'")
        verified = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM cards WHERE status = 'failed'")
        failed = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM cards WHERE status = 'processing'")
        processing = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM cards WHERE status = 'verified'")
        total_amount = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM xena_orders WHERE status = 'pending'")
        pending_xena = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM cards")
        total_cards = cursor.fetchone()[0]
        
        return {
            'pending': pending,
            'verified': verified,
            'failed': failed,
            'processing': processing,
            'total_users': total_users,
            'total_amount': total_amount,
            'pending_xena': pending_xena,
            'total_cards': total_cards
        }

    def get_all_users(self, limit: int = 100) -> List[User]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users ORDER BY created_at DESC LIMIT %s", (limit,))
        users = []
        for row in cursor.fetchall():
            data = self._row_to_dict(cursor, row)
            users.append(User(
                user_id=data['user_id'],
                username=data['username'] or '',
                first_name=data['first_name'] or '',
                balance_iqd=data['balance_iqd'] or 0,
                language=data.get('language', 'ar') or 'ar',
                created_at=str(data['created_at']),
                is_blocked=bool(data.get('is_blocked', 0)),
                is_vip=bool(data.get('is_vip', 0)),
                is_verified=bool(data.get('is_verified', 0)),
                phone_number=data.get('phone_number', '') or '',
                approval_notified=bool(data.get('approval_notified', 0)),
                is_rejected=bool(data.get('is_rejected', 0)),
                balance_coins=data.get('balance_coins', 0) or 0
            ))
        return users

    def block_user(self, user_id: int):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_blocked = 1 WHERE user_id = %s", (user_id,))
        conn.commit()

    def unblock_user(self, user_id: int):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_blocked = 0 WHERE user_id = %s", (user_id,))
        conn.commit()

    def is_user_blocked(self, user_id: int) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT is_blocked FROM users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        return bool(row[0]) if row else False

    def set_vip(self, user_id: int, is_vip: bool):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_vip = %s WHERE user_id = %s", (1 if is_vip else 0, user_id))
        conn.commit()

    def is_user_vip(self, user_id: int) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT is_vip FROM users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        return bool(row[0]) if row else False

    def verify_user(self, user_id: int):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_verified = 1, is_rejected = 0 WHERE user_id = %s", (user_id,))
        conn.commit()

    def reject_user(self, user_id: int):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_rejected = 1, is_verified = 0 WHERE user_id = %s", (user_id,))
        conn.commit()

    def unreject_user(self, user_id: int):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_rejected = 0, is_verified = 0 WHERE user_id = %s", (user_id,))
        conn.commit()

    def is_user_verified(self, user_id: int) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT is_verified FROM users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        return bool(row[0]) if row else False

    def is_user_rejected(self, user_id: int) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT is_rejected FROM users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        return bool(row[0]) if row else False

    def get_pending_users(self) -> List[User]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE is_verified = 0 AND is_rejected = 0 ORDER BY created_at DESC")
        users = []
        for row in cursor.fetchall():
            data = self._row_to_dict(cursor, row)
            users.append(User(
                user_id=data['user_id'],
                username=data['username'] or '',
                first_name=data['first_name'] or '',
                balance_iqd=data['balance_iqd'] or 0,
                language=data.get('language', 'ar') or 'ar',
                created_at=str(data['created_at']),
                is_blocked=bool(data.get('is_blocked', 0)),
                is_vip=bool(data.get('is_vip', 0)),
                is_verified=bool(data.get('is_verified', 0)),
                phone_number=data.get('phone_number', '') or '',
                approval_notified=bool(data.get('approval_notified', 0)),
                is_rejected=bool(data.get('is_rejected', 0)),
                balance_coins=data.get('balance_coins', 0) or 0
            ))
        return users

    def mark_approval_notified(self, user_id: int):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET approval_notified = 1 WHERE user_id = %s", (user_id,))
        conn.commit()

    def log_message(self, user_id: int, direction: str, content: str, message_type: str = 'text', media_path: str = None):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO message_log (user_id, direction, content, message_type, media_path) VALUES (%s, %s, %s, %s, %s)",
            (user_id, direction, content, message_type, media_path)
        )
        conn.commit()

    def log_chat_message(self, user_id: int, direction: str, content: str, message_type: str = 'text'):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_messages (user_id, direction, content, message_type) VALUES (%s, %s, %s, %s)",
            (user_id, direction, content, message_type)
        )
        conn.commit()

    def get_chat_messages(self, user_id: int, limit: int = 50) -> list:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM chat_messages WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
            (user_id, limit)
        )
        messages = []
        for row in cursor.fetchall():
            data = self._row_to_dict(cursor, row)
            messages.append({
                'id': data['id'],
                'user_id': data['user_id'],
                'direction': data['direction'],
                'message_type': data['message_type'],
                'content': data['content'],
                'created_at': str(data['created_at'])
            })
        return list(reversed(messages))

    def get_users_with_chats(self) -> list:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT u.user_id, u.username, u.first_name, 
                   (SELECT content FROM chat_messages WHERE user_id = u.user_id ORDER BY created_at DESC LIMIT 1) as last_message,
                   (SELECT created_at FROM chat_messages WHERE user_id = u.user_id ORDER BY created_at DESC LIMIT 1) as last_message_at
            FROM users u
            INNER JOIN chat_messages cm ON u.user_id = cm.user_id
            ORDER BY last_message_at DESC
        """)
        users = []
        for row in cursor.fetchall():
            data = self._row_to_dict(cursor, row)
            users.append({
                'user_id': data['user_id'],
                'username': data['username'] or '',
                'first_name': data['first_name'] or '',
                'last_message': data['last_message'],
                'last_message_at': str(data['last_message_at']) if data['last_message_at'] else ''
            })
        return users

    def get_new_chat_messages(self, user_id: int, after_id: int) -> list:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM chat_messages WHERE user_id = %s AND id > %s ORDER BY created_at ASC",
            (user_id, after_id)
        )
        messages = []
        for row in cursor.fetchall():
            data = self._row_to_dict(cursor, row)
            messages.append({
                'id': data['id'],
                'user_id': data['user_id'],
                'direction': data['direction'],
                'message_type': data['message_type'],
                'content': data['content'],
                'created_at': str(data['created_at'])
            })
        return messages

    def create_payment_request(self, user_id: int, payment_type: str, amount: int) -> int:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO payment_requests (user_id, payment_type, amount, status) VALUES (%s, %s, %s, 'pending') RETURNING id",
            (user_id, payment_type, amount)
        )
        payment_id = cursor.fetchone()[0]
        conn.commit()
        return payment_id

    def update_payment_proof(self, payment_id: int, proof_image_path: str, transaction_number: str = None) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        if transaction_number:
            cursor.execute(
                "UPDATE payment_requests SET proof_image_path = %s, status = 'pending', transaction_number = %s WHERE id = %s",
                (proof_image_path, transaction_number, payment_id)
            )
        else:
            cursor.execute(
                "UPDATE payment_requests SET proof_image_path = %s, status = 'pending' WHERE id = %s",
                (proof_image_path, payment_id)
            )
        conn.commit()
        return True

    def find_payment_by_transaction(self, transaction_number: str) -> Optional[PaymentRequest]:
        if not transaction_number or len(transaction_number) < 15:
            return None
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM payment_requests WHERE transaction_number = %s ORDER BY created_at DESC LIMIT 1",
            (transaction_number,)
        )
        row = cursor.fetchone()
        if row:
            data = self._row_to_dict(cursor, row)
            return PaymentRequest(
                id=data['id'],
                user_id=data['user_id'],
                payment_type=data['payment_type'],
                amount=data['amount'],
                proof_image_path=data.get('proof_image_path'),
                status=data['status'],
                admin_note=data.get('admin_note'),
                actual_amount=data.get('actual_amount'),
                transaction_number=data.get('transaction_number'),
                created_at=str(data['created_at']),
                processed_at=str(data['processed_at']) if data.get('processed_at') else None
            )
        
        cursor.execute(
            "SELECT * FROM payment_requests WHERE transaction_number IS NOT NULL AND LENGTH(transaction_number) > 15 ORDER BY created_at DESC LIMIT 100"
        )
        for row in cursor.fetchall():
            data = self._row_to_dict(cursor, row)
            existing_trans = data.get('transaction_number')
            if existing_trans and self._is_similar_transaction(transaction_number, existing_trans):
                return PaymentRequest(
                    id=data['id'],
                    user_id=data['user_id'],
                    payment_type=data['payment_type'],
                    amount=data['amount'],
                    proof_image_path=data.get('proof_image_path'),
                    status=data['status'],
                    admin_note=data.get('admin_note'),
                    actual_amount=data.get('actual_amount'),
                    transaction_number=data.get('transaction_number'),
                    created_at=str(data['created_at']),
                    processed_at=str(data['processed_at']) if data.get('processed_at') else None
                )
        
        return None
    
    def _is_similar_transaction(self, trans1: str, trans2: str) -> bool:
        if not trans1 or not trans2:
            return False
        
        if abs(len(trans1) - len(trans2)) > 2:
            return False
        
        shorter = trans1 if len(trans1) <= len(trans2) else trans2
        longer = trans2 if len(trans1) <= len(trans2) else trans1
        
        start = len(shorter) // 10
        end = len(shorter) - start
        core = shorter[start:end]
        
        if core in longer:
            return True
        
        matches = sum(1 for a, b in zip(trans1, trans2) if a == b)
        min_len = min(len(trans1), len(trans2))
        
        if min_len > 0 and matches / min_len >= 0.90:
            return True
        
        return False

    def get_payment_request(self, payment_id: int) -> Optional[PaymentRequest]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM payment_requests WHERE id = %s", (payment_id,))
        row = cursor.fetchone()
        if row:
            data = self._row_to_dict(cursor, row)
            return PaymentRequest(
                id=data['id'],
                user_id=data['user_id'],
                payment_type=data['payment_type'],
                amount=data['amount'],
                proof_image_path=data.get('proof_image_path'),
                status=data['status'],
                admin_note=data.get('admin_note'),
                actual_amount=data.get('actual_amount'),
                transaction_number=data.get('transaction_number'),
                created_at=str(data['created_at']),
                processed_at=str(data['processed_at']) if data.get('processed_at') else None
            )
        return None

    def get_pending_payments(self, payment_type: str = None) -> List[PaymentRequest]:
        conn = self._get_conn()
        cursor = conn.cursor()
        if payment_type:
            cursor.execute(
                "SELECT * FROM payment_requests WHERE status = 'pending' AND payment_type = %s ORDER BY created_at ASC",
                (payment_type,)
            )
        else:
            cursor.execute("SELECT * FROM payment_requests WHERE status = 'pending' ORDER BY created_at ASC")
        payments = []
        for row in cursor.fetchall():
            data = self._row_to_dict(cursor, row)
            payments.append(PaymentRequest(
                id=data['id'],
                user_id=data['user_id'],
                payment_type=data['payment_type'],
                amount=data['amount'],
                proof_image_path=data.get('proof_image_path'),
                status=data['status'],
                admin_note=data.get('admin_note'),
                actual_amount=data.get('actual_amount'),
                transaction_number=data.get('transaction_number'),
                created_at=str(data['created_at']),
                processed_at=str(data['processed_at']) if data.get('processed_at') else None
            ))
        return payments

    def get_all_payments(self, status: str = None, payment_type: str = None, limit: int = 100) -> List[PaymentRequest]:
        conn = self._get_conn()
        cursor = conn.cursor()
        query = "SELECT * FROM payment_requests WHERE 1=1"
        params = []
        if status:
            query += " AND status = %s"
            params.append(status)
        if payment_type:
            query += " AND payment_type = %s"
            params.append(payment_type)
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        cursor.execute(query, tuple(params))
        payments = []
        for row in cursor.fetchall():
            data = self._row_to_dict(cursor, row)
            payments.append(PaymentRequest(
                id=data['id'],
                user_id=data['user_id'],
                payment_type=data['payment_type'],
                amount=data['amount'],
                proof_image_path=data.get('proof_image_path'),
                status=data['status'],
                admin_note=data.get('admin_note'),
                actual_amount=data.get('actual_amount'),
                transaction_number=data.get('transaction_number'),
                created_at=str(data['created_at']),
                processed_at=str(data['processed_at']) if data.get('processed_at') else None
            ))
        return payments

    def approve_payment(self, payment_id: int, amount: int) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """UPDATE payment_requests SET status = 'approved', actual_amount = %s, 
                   processed_at = CURRENT_TIMESTAMP WHERE id = %s AND status = 'pending'""",
                (amount, payment_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        except:
            conn.rollback()
            return False

    def reject_payment(self, payment_id: int, note: str = None) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """UPDATE payment_requests SET status = 'rejected', admin_note = %s, 
                   processed_at = CURRENT_TIMESTAMP WHERE id = %s AND status = 'pending'""",
                (note, payment_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        except:
            conn.rollback()
            return False

    def set_payment_different_amount(self, payment_id: int, actual_amount: int, note: str = None) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """UPDATE payment_requests SET status = 'different_amount', actual_amount = %s, 
                   admin_note = %s, processed_at = CURRENT_TIMESTAMP WHERE id = %s AND status = 'pending'""",
                (actual_amount, note, payment_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        except:
            conn.rollback()
            return False

    def get_user_payments(self, user_id: int, limit: int = 10) -> List[PaymentRequest]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM payment_requests WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
            (user_id, limit)
        )
        payments = []
        for row in cursor.fetchall():
            data = self._row_to_dict(cursor, row)
            payments.append(PaymentRequest(
                id=data['id'],
                user_id=data['user_id'],
                payment_type=data['payment_type'],
                amount=data['amount'],
                proof_image_path=data.get('proof_image_path'),
                status=data['status'],
                admin_note=data.get('admin_note'),
                actual_amount=data.get('actual_amount'),
                transaction_number=data.get('transaction_number'),
                created_at=str(data['created_at']),
                processed_at=str(data['processed_at']) if data.get('processed_at') else None
            ))
        return payments

    def get_payment_stats(self) -> dict:
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM payment_requests WHERE status = 'pending'")
        pending = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM payment_requests WHERE payment_type = 'qi_card' AND status = 'pending'")
        pending_qi = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM payment_requests WHERE payment_type = 'zaincash' AND status = 'pending'")
        pending_zaincash = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM payment_requests WHERE status = 'approved'")
        approved = cursor.fetchone()[0]
        
        cursor.execute("SELECT COALESCE(SUM(COALESCE(actual_amount, amount)), 0) FROM payment_requests WHERE status IN ('approved', 'different_amount')")
        total_approved = cursor.fetchone()[0]
        
        return {
            'pending': pending,
            'pending_payments': pending,
            'pending_qi': pending_qi,
            'pending_qi_card': pending_qi,
            'pending_zaincash': pending_zaincash,
            'approved': approved,
            'total_approved': total_approved,
            'total_approved_amount': total_approved or 0
        }

    def get_setting(self, key: str) -> Optional[str]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = %s", (key,))
        row = cursor.fetchone()
        return row[0] if row else None

    def set_setting(self, key: str, value: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO settings (key, value, updated_at) VALUES (%s, %s, CURRENT_TIMESTAMP)
               ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP""",
            (key, value)
        )
        conn.commit()

    def log_activity(self, action_type: str, target_type: str = None, target_id: str = None, details: str = None, admin_id: str = None):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO activity_log (action_type, target_type, target_id, details, admin_id) VALUES (%s, %s, %s, %s, %s)",
            (action_type, target_type, target_id, details, admin_id)
        )
        conn.commit()

    def get_activity_log(self, action_type: str = None, limit: int = 100) -> list:
        conn = self._get_conn()
        cursor = conn.cursor()
        if action_type:
            cursor.execute(
                "SELECT * FROM activity_log WHERE action_type = %s ORDER BY created_at DESC LIMIT %s",
                (action_type, limit)
            )
        else:
            cursor.execute("SELECT * FROM activity_log ORDER BY created_at DESC LIMIT %s", (limit,))
        activities = []
        for row in cursor.fetchall():
            data = self._row_to_dict(cursor, row)
            activities.append({
                'id': data['id'],
                'action_type': data['action_type'],
                'target_type': data['target_type'],
                'target_id': data['target_id'],
                'details': data['details'],
                'admin_id': data['admin_id'],
                'created_at': str(data['created_at'])
            })
        return activities

    def get_offline_phones(self, timeout_minutes: int = 5) -> List[Phone]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM phones WHERE last_seen < NOW() - INTERVAL '%s minutes' AND status = 'online'",
            (timeout_minutes,)
        )
        phones = []
        for row in cursor.fetchall():
            data = self._row_to_dict(cursor, row)
            phones.append(Phone(
                phone_id=data['phone_id'],
                name=data['name'] or '',
                battery_level=data['battery_level'] or 100,
                last_seen=str(data['last_seen']),
                status=data['status'],
                jobs_completed=data['jobs_completed'] or 0,
                jobs_failed=data['jobs_failed'] or 0
            ))
        return phones

    def mark_phone_offline(self, phone_id: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE phones SET status = 'offline' WHERE phone_id = %s", (phone_id,))
        conn.commit()

    def should_alert_phone(self, phone_id: str, cooldown_minutes: int = 30) -> bool:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT last_alert_at FROM phone_alerts WHERE phone_id = %s", (phone_id,))
        row = cursor.fetchone()
        if not row or not row[0]:
            return True
        try:
            last_alert = datetime.fromisoformat(str(row[0]).replace('Z', '+00:00').replace(' ', 'T'))
            if last_alert.tzinfo:
                last_alert = last_alert.replace(tzinfo=None)
            return datetime.now() - last_alert > timedelta(minutes=cooldown_minutes)
        except:
            return True

    def update_phone_alert(self, phone_id: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO phone_alerts (phone_id, last_alert_at) VALUES (%s, CURRENT_TIMESTAMP)
               ON CONFLICT (phone_id) DO UPDATE SET last_alert_at = CURRENT_TIMESTAMP""",
            (phone_id,)
        )
        conn.commit()

    def delete_payment_request(self, payment_id: int):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM payment_requests WHERE id = %s", (payment_id,))
        conn.commit()

    def get_cards_with_images(self, limit: int = 50) -> List[Card]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM cards WHERE image_path IS NOT NULL ORDER BY created_at DESC LIMIT %s",
            (limit,)
        )
        cards = []
        for row in cursor.fetchall():
            data = self._row_to_dict(cursor, row)
            cards.append(Card(
                id=data['id'],
                user_id=data['user_id'],
                pin=data['pin'],
                amount=data['amount'] or 0,
                status=data['status'],
                retry_count=data.get('retry_count', 0) or 0,
                image_path=data.get('image_path'),
                phone_id=data.get('phone_id'),
                created_at=str(data['created_at']),
                verified_at=str(data['verified_at']) if data.get('verified_at') else None
            ))
        return cards

    def get_advanced_stats(self) -> dict:
        conn = self._get_conn()
        cursor = conn.cursor()
        
        stats = self.get_stats()
        
        total = stats['verified'] + stats['failed']
        success_rate = (stats['verified'] / total * 100) if total > 0 else 0
        
        cursor.execute("""
            SELECT EXTRACT(HOUR FROM created_at) as hour, COUNT(*) as count 
            FROM cards 
            WHERE created_at > NOW() - INTERVAL '7 days'
            GROUP BY EXTRACT(HOUR FROM created_at) 
            ORDER BY count DESC 
            LIMIT 3
        """)
        peak_hours = [int(row[0]) for row in cursor.fetchall()]
        
        cursor.execute("SELECT COALESCE(SUM(COALESCE(actual_amount, amount)), 0) FROM payment_requests WHERE status IN ('approved', 'different_amount')")
        total_payments = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COALESCE(SUM(price_iqd), 0) FROM xena_orders WHERE status = 'completed'")
        total_xena = cursor.fetchone()[0] or 0
        
        return {
            **stats,
            'success_rate': round(success_rate, 1),
            'peak_hours': peak_hours,
            'total_payments': total_payments,
            'total_xena_revenue': total_xena
        }

    def export_users_csv(self) -> str:
        import csv
        import io
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, first_name, balance_iqd, language, is_verified, is_blocked, is_vip, created_at FROM users ORDER BY created_at DESC")
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['User ID', 'Username', 'First Name', 'Balance', 'Language', 'Verified', 'Blocked', 'VIP', 'Created At'])
        for row in cursor.fetchall():
            writer.writerow(row)
        return output.getvalue()

    def export_cards_csv(self) -> str:
        import csv
        import io
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id, pin, amount, status, retry_count, phone_id, created_at, verified_at FROM cards ORDER BY created_at DESC")
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'User ID', 'PIN', 'Amount', 'Status', 'Retry Count', 'Phone ID', 'Created At', 'Verified At'])
        for row in cursor.fetchall():
            writer.writerow(row)
        return output.getvalue()

    def export_xena_csv(self) -> str:
        import csv
        import io
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id, player_id, coins, price_iqd, severbil_order_id, status, created_at FROM xena_orders ORDER BY created_at DESC")
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'User ID', 'Player ID', 'Coins', 'Price IQD', 'Severbil Order ID', 'Status', 'Created At'])
        for row in cursor.fetchall():
            writer.writerow(row)
        return output.getvalue()

    # Service Type Management Methods
    def get_user_service_type(self, user_id: int) -> str:
        """Get the service type for a user."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT service_type FROM users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        return row[0] if row and row[0] else 'xena'
    
    def set_user_service_type(self, user_id: int, service_type: str) -> bool:
        """Set the service type for a user. Values: 'xena', 'imo', 'both', 'usd'."""
        if service_type not in ('xena', 'imo', 'both', 'usd'):
            return False
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET service_type = %s WHERE user_id = %s", (service_type, user_id))
        conn.commit()
        return cursor.rowcount > 0
    
    def approve_user_with_service(self, user_id: int, service_type: str = 'xena') -> bool:
        """Approve a user and set their service type."""
        if service_type not in ('xena', 'imo', 'both', 'usd'):
            service_type = 'xena'
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET is_verified = 1, is_rejected = 0, service_type = %s WHERE user_id = %s",
            (service_type, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    
    def pre_approve_user(self, user_id: int, service_type: str = 'xena', note: str = '') -> bool:
        """Pre-approve a user by ID before they register."""
        if service_type not in ('xena', 'imo', 'both'):
            service_type = 'xena'
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            # Check if user already exists
            cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
            if cursor.fetchone():
                # User exists, update their service type directly
                cursor.execute(
                    "UPDATE users SET is_verified = 1, is_rejected = 0, service_type = %s WHERE user_id = %s",
                    (service_type, user_id)
                )
            else:
                # User doesn't exist yet, add to pre-approvals
                cursor.execute(
                    "INSERT INTO pre_approvals (user_id, service_type, note) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET service_type = %s, note = %s",
                    (user_id, service_type, note, service_type, note)
                )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Pre-approve error: {e}")
            conn.rollback()
            return False
    
    def get_pre_approvals(self) -> list:
        """Get all pre-approved users waiting for registration."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, service_type, note, created_at FROM pre_approvals ORDER BY created_at DESC")
        return [{'user_id': row[0], 'service_type': row[1], 'note': row[2], 'created_at': str(row[3])} for row in cursor.fetchall()]
    
    def remove_pre_approval(self, user_id: int) -> bool:
        """Remove a pre-approval entry."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pre_approvals WHERE user_id = %s", (user_id,))
        conn.commit()
        return cursor.rowcount > 0
    
    def get_users_by_service_type(self, service_type: str) -> list:
        """Get all users with a specific service type."""
        conn = self._get_conn()
        cursor = conn.cursor()
        if service_type == 'all':
            cursor.execute("SELECT * FROM users WHERE is_verified = 1 ORDER BY created_at DESC")
        else:
            cursor.execute("SELECT * FROM users WHERE is_verified = 1 AND (service_type = %s OR service_type = 'both') ORDER BY created_at DESC", (service_type,))
        rows = cursor.fetchall()
        result = []
        for row in rows:
            data = self._row_to_dict(cursor, row)
            result.append(data)
        return result

    def get_coin_rates(self) -> list:
        """Get all coin conversion rates."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM coin_rates ORDER BY id")
        rows = cursor.fetchall()
        result = []
        for row in rows:
            data = self._row_to_dict(cursor, row)
            result.append(data)
        return result

    def get_coin_rate(self, payment_source: str) -> dict:
        """Get coin rate for a specific payment source."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM coin_rates WHERE payment_source = %s", (payment_source,))
        row = cursor.fetchone()
        if row:
            return self._row_to_dict(cursor, row)
        return None

    def update_coin_rate(self, payment_source: str, source_amount: int, coin_amount: int, currency_name: str = None) -> bool:
        """Update coin conversion rate."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            if currency_name:
                cursor.execute(
                    "UPDATE coin_rates SET source_amount = %s, coin_amount = %s, currency_name = %s, updated_at = CURRENT_TIMESTAMP WHERE payment_source = %s",
                    (source_amount, coin_amount, currency_name, payment_source)
                )
            else:
                cursor.execute(
                    "UPDATE coin_rates SET source_amount = %s, coin_amount = %s, updated_at = CURRENT_TIMESTAMP WHERE payment_source = %s",
                    (source_amount, coin_amount, payment_source)
                )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Update coin rate error: {e}")
            conn.rollback()
            return False

    def convert_to_coins(self, amount: int, payment_source: str) -> int:
        """Convert amount to coins based on payment source rate."""
        rate = self.get_coin_rate(payment_source)
        if not rate:
            return amount
        return int(amount * rate['coin_amount'] / rate['source_amount'])

    def add_coins(self, user_id: int, coins: int, transaction_type: str = 'deposit', reference_id: str = None) -> bool:
        """Add coins to user balance."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT balance_coins FROM users WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
            balance_before = row[0] if row else 0
            balance_after = balance_before + coins
            
            cursor.execute(
                "UPDATE users SET balance_coins = balance_coins + %s WHERE user_id = %s",
                (coins, user_id)
            )
            
            cursor.execute(
                "INSERT INTO balance_transactions (user_id, amount, balance_before, balance_after, transaction_type, reference_id) VALUES (%s, %s, %s, %s, %s, %s)",
                (user_id, coins, balance_before, balance_after, transaction_type, reference_id)
            )
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Add coins error: {e}")
            conn.rollback()
            return False

    def get_user_coins(self, user_id: int) -> int:
        """Get user's coin balance."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT balance_coins FROM users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else 0

    def deduct_coins(self, user_id: int, coins: int, transaction_type: str = 'purchase', reference_id: str = None) -> bool:
        """Deduct coins from user balance."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT balance_coins FROM users WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
            balance_before = row[0] if row else 0
            
            if balance_before < coins:
                return False
            
            balance_after = balance_before - coins
            
            cursor.execute(
                "UPDATE users SET balance_coins = balance_coins - %s WHERE user_id = %s",
                (coins, user_id)
            )
            
            cursor.execute(
                "INSERT INTO balance_transactions (user_id, amount, balance_before, balance_after, transaction_type, reference_id) VALUES (%s, %s, %s, %s, %s, %s)",
                (user_id, -coins, balance_before, balance_after, transaction_type, reference_id)
            )
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Deduct coins error: {e}")
            conn.rollback()
            return False

    def convert_all_balances_to_coins(self, rate_per_1000_iqd: int = 5500) -> list:
        """Convert all existing IQD balances to coins and return list of users affected."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT user_id, balance_iqd FROM users WHERE balance_iqd > 0")
            rows = cursor.fetchall()
            affected = []
            for row in rows:
                user_id = row[0]
                balance_iqd = row[1]
                coins = int(balance_iqd * rate_per_1000_iqd / 1000)
                cursor.execute(
                    "UPDATE users SET balance_coins = %s, balance_iqd = 0 WHERE user_id = %s",
                    (coins, user_id)
                )
                affected.append({'user_id': user_id, 'balance_iqd': balance_iqd, 'balance_coins': coins})
            conn.commit()
            return affected
        except Exception as e:
            logger.error(f"Convert balances error: {e}")
            conn.rollback()
            return []
