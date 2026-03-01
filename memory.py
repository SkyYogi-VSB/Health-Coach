import sqlite3
import os
from datetime import datetime

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
            daily_protein_goal INTEGER
        )
    ''')

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
    """Retrieves the most recent messages for a user to provide context to the AI."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Get the most recent messages, ordered by time
    cursor.execute('''
        SELECT role, content, timestamp 
        FROM messages 
        WHERE user_id = ? 
        ORDER BY timestamp DESC 
        LIMIT ?
    ''', (user_id, limit))
    
    # Fetch and reverse so they are in chronological order
    rows = cursor.fetchall()
    conn.close()
    
    rows.reverse()
    
    if not rows:
        return "No previous context."
        
    context_str = "Recent Conversation History:\n"
    for role, content, ts in rows:
        context_str += f"[{ts}] {role.capitalize()}: {content}\n"
        
    return context_str

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

# Initialize the db when the module is imported
init_db()
