import sqlite3
import os
from datetime import datetime
import hashlib

# We'll store the database file in the same directory
DB_FILE = os.path.join(os.path.abspath(os.path.dirname(__file__)), "health_coach_v2.db")

def init_db():
    """Initializes the SQLite database with the required tables."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Create users table for profiles (e.g., timezone, goals, macros)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            timezone TEXT,
            daily_calories_goal INTEGER,
            daily_protein_goal INTEGER,
            lunch_time TEXT,
            dinner_time TEXT
        )
    ''')
    
    # Try to add columns for existing users (v1 -> v2 migration)
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN lunch_time TEXT')
        cursor.execute('ALTER TABLE users ADD COLUMN dinner_time TEXT')
    except sqlite3.OperationalError:
        pass # Columns already exist

    # Create messages table for chat history (timestamped)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,           -- 'user' or 'coach'
            content TEXT,        -- The message text
            timestamp TEXT,      -- ISO format timestamp
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    # Create weight tracking table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS weight_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            weight_lbs REAL,
            timestamp TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    # Create API usage tracking table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            request_type TEXT,
            timestamp TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    # Create prompt caching table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS query_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_hash TEXT UNIQUE,
            response TEXT,
            timestamp TEXT
        )
    ''')
    
    # Create context summaries table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS context_summaries (
            user_id INTEGER PRIMARY KEY,
            summary_text TEXT,
            last_message_id INTEGER,
            timestamp TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    conn.commit()
    conn.close()

def save_message(user_id: int, role: str, content: str):
    """Saves a message to the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    timestamp = datetime.now().isoformat()
    cursor.execute('''
        INSERT INTO messages (user_id, role, content, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (user_id, role, content, timestamp))
    
    conn.commit()
    conn.close()

def get_recent_context(user_id: int, limit: int = 20) -> str:
    """Retrieves context including rolling summary + recent unsummarized messages."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Try to get existing summary
    cursor.execute('SELECT summary_text, last_message_id FROM context_summaries WHERE user_id = ?', (user_id,))
    summary_row = cursor.fetchone()
    
    last_id = summary_row[1] if summary_row else 0
    summary_text = summary_row[0] if summary_row else ""
    
    # Get the messages after the summary
    cursor.execute('''
        SELECT role, content, timestamp 
        FROM messages 
        WHERE user_id = ? AND id > ?
        ORDER BY timestamp DESC 
        LIMIT ?
    ''', (user_id, last_id, limit))
    
    rows = cursor.fetchall()
    # Get the latest weights
    cursor.execute('''
        SELECT weight_lbs, timestamp 
        FROM weight_logs 
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT 5
    ''', (user_id,))
    weight_rows = cursor.fetchall()
    
    conn.close()
    
    rows.reverse()
    
    context_str = ""
    if summary_text:
        context_str += f"[Rolling Conversation Summary]:\n{summary_text}\n\n"
        
    if weight_rows:
        weight_rows.reverse()
        context_str += "[Recent Weight Logs]:\n"
        for weight, ts in weight_rows:
            context_str += f"[{ts}] {weight} lbs\n"
        context_str += "\n"
        
    context_str += "Recent Unsummarized Messages:\n"
    if not rows and not summary_text:
        return "No previous context."
    elif not rows:
        context_str += "No new messages."
    
    for role, content, ts in rows:
        context_str += f"[{ts}] {role.capitalize()}: {content}\n"
        
    return context_str

def get_unsummarized_messages(user_id: int) -> tuple:
    """Returns (messages list as string, last_message_id) for unsummarized messages."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Get the last message ID that was summarized
    cursor.execute('SELECT last_message_id FROM context_summaries WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    last_summarized_id = row[0] if row else 0
    
    # Also fetch the most recent messages that came AFTER the last_summarized_id
    cursor.execute('''
        SELECT id, role, content, timestamp 
        FROM messages 
        WHERE user_id = ? AND id > ?
        ORDER BY timestamp ASC
    ''', (user_id, last_summarized_id))
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return "", last_summarized_id
        
    messages_str = ""
    last_id = last_summarized_id
    for msg_id, role, content, ts in rows:
        messages_str += f"[{ts}] {role.capitalize()}: {content}\n"
        last_id = max(last_id, msg_id)
        
    return messages_str, last_id

def update_context_summary(user_id: int, summary_text: str, last_message_id: int):
    """Updates the rolling context summary for a user."""
    timestamp = datetime.now().isoformat()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO context_summaries (user_id, summary_text, last_message_id, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (user_id, summary_text, last_message_id, timestamp))
    
    conn.commit()
    conn.close()

def log_api_request(user_id: int, request_type: str = 'default'):
    """Logs an API request for quota tracking."""
    if not user_id:
        return
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    timestamp = datetime.now().isoformat()
    cursor.execute('''
        INSERT INTO api_usage (user_id, request_type, timestamp)
        VALUES (?, ?, ?)
    ''', (user_id, request_type, timestamp))
    
    conn.commit()
    conn.close()

def can_make_api_call(user_id: int, max_rpm: int = 15, max_rpd: int = 1500) -> bool:
    """Checks if the user has exceeded their request limits."""
    if not user_id:
        return True
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Check RPM (last 1 minute)
    cursor.execute('''
        SELECT COUNT(*) FROM api_usage 
        WHERE user_id = ? AND timestamp >= datetime('now', '-1 minute')
    ''', (user_id,))
    rpm = cursor.fetchone()[0]
    
    # Check RPD (last 24 hours)
    cursor.execute('''
        SELECT COUNT(*) FROM api_usage 
        WHERE user_id = ? AND timestamp >= datetime('now', '-1 day')
    ''', (user_id,))
    rpd = cursor.fetchone()[0]
    
    conn.close()
    
    return rpm < max_rpm and rpd < max_rpd

def get_cached_response(query_text: str) -> str:
    """Retrieves a cached response if available from the past 24 hours."""
    query_hash = hashlib.md5(query_text.encode('utf-8')).hexdigest()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT response FROM query_cache 
        WHERE query_hash = ? AND timestamp >= datetime('now', '-1 day')
    ''', (query_hash,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return row[0]
    return None

def cache_response(query_text: str, response: str):
    """Caches a generic response."""
    query_hash = hashlib.md5(query_text.encode('utf-8')).hexdigest()
    timestamp = datetime.now().isoformat()
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Use REPLACE to update timestamp and response if hash already exists
    cursor.execute('''
        INSERT OR REPLACE INTO query_cache (query_hash, response, timestamp)
        VALUES (?, ?, ?)
    ''', (query_hash, response, timestamp))
    
    conn.commit()
    conn.close()

def get_weekly_logs(user_id: int) -> str:
    """Retrieves the last 7 days of user and coach messages for a weekly summary."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # SQLite datetime functions can calculate 7 days ago
    cursor.execute('''
        SELECT role, content, timestamp 
        FROM messages 
        WHERE user_id = ? AND timestamp >= datetime('now', '-7 days')
        ORDER BY timestamp ASC
    ''', (user_id,))
    
    rows = cursor.fetchall()
    
    # Get weight logs over the last 30 days to see the trend
    cursor.execute('''
        SELECT weight_lbs, timestamp 
        FROM weight_logs 
        WHERE user_id = ? AND timestamp >= datetime('now', '-30 days')
        ORDER BY timestamp ASC
    ''', (user_id,))
    weight_rows = cursor.fetchall()
    
    conn.close()
    
    context_str = "Weight Trend (Past 30 Days):\n"
    if not weight_rows:
        context_str += "No weight logs recorded.\n"
    else:
        for weight, ts in weight_rows:
            context_str += f"[{ts}] Weight: {weight} lbs\n"
            
    context_str += "\nDiet & Activity Logs (Past 7 Days):\n"
    if not rows:
        context_str += "No meal logs in the past week.\n"
    else:
        for role, content, ts in rows:
            context_str += f"[{ts}] {role.capitalize()}: {content}\n"
            
    return context_str

def log_weight(user_id: int, weight: float):
    """Saves a user's weight log."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    timestamp = datetime.now().isoformat()
    cursor.execute('''
        INSERT INTO weight_logs (user_id, weight_lbs, timestamp)
        VALUES (?, ?, ?)
    ''', (user_id, weight, timestamp))
    
    conn.commit()
    conn.close()

def update_user_goals(user_id: int, calories: int, protein: int):
    """Updates the user's daily calorie and protein goals."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, timezone, daily_calories_goal, daily_protein_goal) VALUES (?, 'UTC', 2000, 150)", (user_id,))
    cursor.execute('''
        UPDATE users 
        SET daily_calories_goal = ?, daily_protein_goal = ?
        WHERE user_id = ?
    ''', (calories, protein, user_id))
    conn.commit()
    conn.close()

def update_timezone(user_id: int, timezone: str):
    """Updates the user's timezone."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, timezone, daily_calories_goal, daily_protein_goal) VALUES (?, 'UTC', 2000, 150)", (user_id,))
    cursor.execute('''
        UPDATE users 
        SET timezone = ?
        WHERE user_id = ?
    ''', (timezone, user_id))
    conn.commit()
    conn.close()

def update_meal_times(user_id: int, lunch_time: str, dinner_time: str):
    """Updates the user's preferred lunch and dinner times."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, timezone, daily_calories_goal, daily_protein_goal) VALUES (?, 'UTC', 2000, 150)", (user_id,))
    cursor.execute('''
        UPDATE users 
        SET lunch_time = ?, dinner_time = ?
        WHERE user_id = ?
    ''', (lunch_time, dinner_time, user_id))
    conn.commit()
    conn.close()

def get_user_profile(user_id: int) -> dict:
    """Fetches the user's profile settings."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None

# Initialize the db when the module is imported
init_db()
