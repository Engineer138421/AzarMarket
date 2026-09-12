# database.py

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

DATABASE_NAME = "market_history.db"
TEHRAN_TZ = ZoneInfo("Asia/Tehran")


def get_connection():
    return sqlite3.connect(DATABASE_NAME, timeout=30.0)


def init_database():
    connection = get_connection()
    cursor = connection.cursor()

    # ۱. جدول تاریخچه بازار و بورس
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS market_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            dollar REAL,
            euro REAL,
            tether REAL,
            gold18 REAL,
            gold24 REAL,
            emami REAL,
            half REAL,
            quarter REAL,
            ounce REAL,
            oil REAL,
            bitcoin REAL,
            bourse REAL
        )
        """
    )

    # ارتقای خودکار جدول در صورت نبود ستون‌های جدید
    cursor.execute("PRAGMA table_info(market_history)")
    columns = [column[1] for column in cursor.fetchall()]
    if "tether" not in columns:
        cursor.execute("ALTER TABLE market_history ADD COLUMN tether REAL")
    if "oil" not in columns:
        cursor.execute("ALTER TABLE market_history ADD COLUMN oil REAL")
    if "bourse" not in columns:
        cursor.execute("ALTER TABLE market_history ADD COLUMN bourse REAL")

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_market_history_timestamp
        ON market_history(timestamp)
        """
    )

    # ۲. جدول هشدارهای شخصی کاربران
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            asset TEXT NOT NULL,
            target_price REAL NOT NULL,
            condition TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_alerts_active
        ON user_alerts(is_active)
        """
    )

    # ۳. جدول نظرسنجی‌های ۲۴ ساعته
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_polls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            poll_id TEXT NOT NULL,
            message_id INTEGER NOT NULL,
            chat_id TEXT NOT NULL,
            date_str TEXT NOT NULL,
            status TEXT DEFAULT 'active'
        )
        """
    )

    # ۴. جدول اختصاصی پایش و یادآوری عرضه‌های اولیه
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ipo_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            company_name TEXT,
            ipo_date TEXT NOT NULL,
            price_range TEXT,
            max_shares TEXT,
            cash_needed TEXT,
            notified_days TEXT DEFAULT ''
        )
        """
    )

    connection.commit()
    connection.close()


def save_market_snapshot(data):
    if not data:
        return False

    now = datetime.now(TEHRAN_TZ)
    timestamp = now.isoformat()

    dollar = data.get("dollar", {}).get("price")
    euro = data.get("euro", {}).get("price")
    tether = data.get("tether", {}).get("price")
    gold18 = data.get("gold18", {}).get("price")
    gold24 = data.get("gold24", {}).get("price")
    emami = data.get("emami", {}).get("price")
    half = data.get("half", {}).get("price")
    quarter = data.get("quarter", {}).get("price")
    ounce = data.get("ounce", {}).get("price")
    oil = data.get("oil", {}).get("price")
    bitcoin = data.get("bitcoin", {}).get("price")
    bourse = data.get("bourse", {}).get("price")

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO market_history (
            timestamp, dollar, euro, tether, gold18, gold24,
            emami, half, quarter, ounce, oil, bitcoin, bourse
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            timestamp, dollar, euro, tether, gold18, gold24,
            emami, half, quarter, ounce, oil, bitcoin, bourse,
        ),
    )

    connection.commit()
    connection.close()
    return True


def get_daily_market_history(date_str=None):
    if date_str is None:
        date_str = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d")

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            timestamp, dollar, euro, tether, gold18, gold24,
            emami, half, quarter, ounce, oil, bitcoin, bourse
        FROM market_history
        WHERE timestamp LIKE ?
        ORDER BY timestamp ASC
        """,
        (f"{date_str}%",),
    )

    rows = cursor.fetchall()
    connection.close()
    return rows


def get_daily_summary(date_str=None):
    if date_str is None:
        date_str = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d")

    rows = get_daily_market_history(date_str)
    if not rows:
        return None

    assets = {
        "dollar": 1,
        "euro": 2,
        "tether": 3,
        "gold18": 4,
        "gold24": 5,
        "emami": 6,
        "half": 7,
        "quarter": 8,
        "ounce": 9,
        "oil": 10,
        "bitcoin": 11,
        "bourse": 12,
    }

    summary = {
        "date": date_str,
        "snapshot_count": len(rows),
        "first_timestamp": rows[0][0],
        "last_timestamp": rows[-1][0],
        "assets": {},
    }

    for asset, index in assets.items():
        values = [row[index] for row in rows if len(row) > index and row[index] is not None]

        if not values:
            summary["assets"][asset] = {
                "start": None, "end": None, "high": None,
                "low": None, "change": None, "change_percent": None,
            }
            continue

        start_price = values[0]
        end_price = values[-1]
        high_price = max(values)
        low_price = min(values)
        change = end_price - start_price
        change_percent = (change / start_price * 100) if start_price != 0 else None

        summary["assets"][asset] = {
            "start": start_price,
            "end": end_price,
            "high": high_price,
            "low": low_price,
            "change": change,
            "change_percent": change_percent,
        }

    return summary


def add_user_alert(user_id: int, asset: str, target_price: float, condition: str):
    now_str = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d %H:%M")
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO user_alerts (user_id, asset, target_price, condition, created_at, is_active)
        VALUES (?, ?, ?, ?, ?, 1)
        """,
        (user_id, asset, target_price, condition, now_str),
    )
    connection.commit()
    connection.close()
    return True


def get_active_alerts():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT id, user_id, asset, target_price, condition, created_at
        FROM user_alerts
        WHERE is_active = 1
        """
    )
    rows = cursor.fetchall()
    connection.close()
    return rows


def deactivate_alert(alert_id: int):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("UPDATE user_alerts SET is_active = 0 WHERE id = ?", (alert_id,))
    connection.commit()
    connection.close()


def get_user_alerts(user_id: int):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT id, asset, target_price, condition, created_at
        FROM user_alerts
        WHERE user_id = ? AND is_active = 1
        ORDER BY id DESC
        """,
        (user_id,),
    )
    rows = cursor.fetchall()
    connection.close()
    return rows


def delete_user_alert(alert_id: int, user_id: int):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "DELETE FROM user_alerts WHERE id = ? AND user_id = ?",
        (alert_id, user_id),
    )
    affected = cursor.rowcount
    connection.commit()
    connection.close()
    return affected > 0


def save_daily_poll(poll_id: str, message_id: int, chat_id: str, date_str: str):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO daily_polls (poll_id, message_id, chat_id, date_str, status) VALUES (?, ?, ?, ?, 'active')",
        (poll_id, message_id, chat_id, date_str),
    )
    connection.commit()
    connection.close()


def get_last_active_poll():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT id, poll_id, message_id, chat_id, date_str FROM daily_polls WHERE status = 'active' ORDER BY id DESC LIMIT 1"
    )
    row = cursor.fetchone()
    connection.close()
    return row


def close_poll_record(record_id: int):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("UPDATE daily_polls SET status = 'closed' WHERE id = ?", (record_id,))
    connection.commit()
    connection.close()


# توابع ویژه مدیریت عرضه‌های اولیه
def save_ipo_record(symbol, company_name, ipo_date, price_range, max_shares, cash_needed):
    """ثبت عرضه اولیه جدید در صورتی که قبلاً ذخیره نشده باشد"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM ipo_records WHERE symbol = ? AND ipo_date = ?", (symbol, ipo_date))
    row = cur.fetchone()
    if not row:
        cur.execute(
            """
            INSERT INTO ipo_records (symbol, company_name, ipo_date, price_range, max_shares, cash_needed)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (symbol, company_name, ipo_date, price_range, max_shares, cash_needed),
        )
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False


def get_upcoming_ipos():
    """دریافت تمام عرضه‌های اولیه‌ای که در دیتابیس ثبت شده‌اند"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, symbol, company_name, ipo_date, price_range, max_shares, cash_needed, notified_days FROM ipo_records"
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def update_ipo_notification(record_id, day_tag):
    """ثبت برچسب اطلاع‌رسانی روزشمار (مثلاً day_1 یا day_2) برای جلوگیری از تکرار"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT notified_days FROM ipo_records WHERE id = ?", (record_id,))
    row = cur.fetchone()
    old_tags = row[0] if row and row[0] else ""
    new_tags = f"{old_tags},{day_tag}".strip(",")
    cur.execute("UPDATE ipo_records SET notified_days = ? WHERE id = ?", (new_tags, record_id))
    conn.commit()
    conn.close()