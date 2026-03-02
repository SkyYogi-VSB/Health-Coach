import os
import logging
import re
import uuid
import datetime
import pytz
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

from ai_coach import get_coach_response, get_coach_summary
import memory

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Explicit Security Allowlist (From .env for Git Safety)
allowed_users_env = os.getenv("ALLOWED_TELEGRAM_USER_IDS", "")
ALLOWED_USER_IDS = [int(x.strip()) for x in allowed_users_env.split(",")] if allowed_users_env else []

async def check_allowed(update: Update) -> bool:
    """Security check to ensure only you can communicate with your bot."""
    if update.effective_user.id not in ALLOWED_USER_IDS:
        await update.effective_message.reply_text("⛔️ Unauthorized access. This is a personal Health Coach bot.")
        return False
    return True

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    if not await check_allowed(update): return
    
    user_id = update.effective_user.id
    # Create the user profile in the DB (for a simple setup, just an entry)
    conn = memory.sqlite3.connect(memory.DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, timezone, daily_calories_goal, daily_protein_goal)
        VALUES (?, 'UTC', 2000, 150)
    ''', (user_id,))
    conn.commit()
    conn.close()

    welcome_msg = (
        "ALRIGHT LISTEN UP! I'm your new AI Health Coach built with Gemini.\n\n"
        "To get started, tell me a little bit about yourself:\n"
        "1. What is your primary goal (e.g. lose weight, build muscle)?\n"
        "2. What timezone or city are you in?\n"
        "3. What times do you usually eat lunch and dinner? (e.g. 12:30 PM and 7:00 PM)\n\n"
        "Once you tell me, I'll automatically update your profile and we can get to work tracking meals!"
    )
    
    # Save bot's welcome message
    memory.save_message(user_id, "coach", welcome_msg)
    
    await context.bot.send_message(chat_id=update.effective_chat.id, text=welcome_msg)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_allowed(update): return
    
    user_id = update.effective_user.id
    user_msg = update.message.text
    
    memory.save_message(user_id, "user", user_msg)
    context_str = memory.get_recent_context(user_id, limit=10)
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    
    coach_reply = get_coach_response(user_id, user_msg, context_str)
    
    memory.save_message(user_id, "coach", coach_reply)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=coach_reply)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_allowed(update): return
    
    user_id = update.effective_user.id
    caption = update.message.caption or "Here's my meal."
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    
    photo_file = await update.message.photo[-1].get_file()
    download_path = os.path.join(os.path.dirname(__file__), f"temp_{user_id}_{uuid.uuid4().hex[:8]}.jpg")
    await photo_file.download_to_drive(download_path)
    
    try:
        memory.save_message(user_id, "user", f"[Sent a photo]: {caption}")
        context_str = memory.get_recent_context(user_id, limit=10)
        coach_reply = get_coach_response(user_id, caption, context_str, image_path=download_path)
        memory.save_message(user_id, "coach", coach_reply)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=coach_reply)
    finally:
        if os.path.exists(download_path):
            try: os.remove(download_path)
            except Exception: pass

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_allowed(update): return
    
    user_id = update.effective_user.id
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    
    voice_file = await update.message.voice.get_file()
    download_path = os.path.join(os.path.dirname(__file__), f"temp_voice_{user_id}_{uuid.uuid4().hex[:8]}.ogg")
    await voice_file.download_to_drive(download_path)
    
    try:
        memory.save_message(user_id, "user", "[Sent an Audio Voice Note]")
        context_str = memory.get_recent_context(user_id, limit=10)
        coach_reply = get_coach_response(user_id, "Transcribe this audio, parse the meal or workout inside it, and reply.", context_str, audio_path=download_path)
        memory.save_message(user_id, "coach", coach_reply)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=coach_reply)
    finally:
        if os.path.exists(download_path):
            try: os.remove(download_path)
            except Exception: pass

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_allowed(update): return
    user_id = update.effective_user.id
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    weekly_logs_str = memory.get_weekly_logs(user_id)
    coach_reply = get_coach_summary(weekly_logs_str)
    
    memory.save_message(user_id, "user", "[Requested Weekly Summary]")
    memory.save_message(user_id, "coach", coach_reply)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=coach_reply)

# ---- NEW PROACTIVE JOBS ----

# Memory cache to prevent duplicate prompts in the same day (resets if day changes)
PROMPT_STATE = {} # dict of user_id -> {'last_morning': 'YYYY-MM-DD', 'last_lunch': 'YYYY-MM-DD', 'last_dinner': 'YYYY-MM-DD'}

async def proactive_prompts_job(context: ContextTypes.DEFAULT_TYPE):
    """Runs every 15 minutes. Checks user's local time and sends contextual prompts."""
    conn = memory.sqlite3.connect(memory.DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = cursor.fetchall()
    conn.close()
    
    for (user_id,) in users:
        profile = memory.get_user_profile(user_id) or {}
        tz_str = profile.get('timezone') or 'UTC'
        lunch_time_str = profile.get('lunch_time') or '12:30'
        dinner_time_str = profile.get('dinner_time') or '18:30'
        
        try:
            user_tz = pytz.timezone(tz_str)
        except pytz.UnknownTimeZoneError:
            user_tz = pytz.utc
            
        local_now = datetime.datetime.now(user_tz)
        local_date = local_now.strftime("%Y-%m-%d")
        
        if user_id not in PROMPT_STATE:
            PROMPT_STATE[user_id] = {'last_morning': '', 'last_lunch': '', 'last_dinner': ''}
            
        state = PROMPT_STATE[user_id]
        
        # 1. Morning Plan (approx 08:00 AM)
        if local_now.hour == 8 and state['last_morning'] != local_date:
            state['last_morning'] = local_date
            await _send_proactive_message(context.bot, user_id, "SYSTEM TRIGGER: It is 8:00 AM local time. Provide a concise, motivating daily plan based on the user's goals. Max 3 sentences.")
            
        # 2. Lunch Prompt
        try:
            l_hour, l_minute = map(int, lunch_time_str.split(':'))
        except:
             l_hour, l_minute = 12, 30
             
        # Trigger within a 15-minute window or exactly the hour
        if local_now.hour == l_hour and state['last_lunch'] != local_date:
            if local_now.minute >= l_minute:
                state['last_lunch'] = local_date
                await _send_proactive_message(context.bot, user_id, "SYSTEM TRIGGER: It is lunchtime. Send a quick, friendly message asking what they are having for lunch to keep them accountable.")

        # 3. Dinner Prompt
        try:
            d_hour, d_minute = map(int, dinner_time_str.split(':'))
        except:
             d_hour, d_minute = 18, 30
             
        if local_now.hour == d_hour and state['last_dinner'] != local_date:
            if local_now.minute >= d_minute:
                state['last_dinner'] = local_date
                await _send_proactive_message(context.bot, user_id, "SYSTEM TRIGGER: It is dinner time. Send a friendly message checking in on what they are having for dinner to finish the day strong.")

async def _send_proactive_message(bot, user_id, prompt_trigger_msg):
    """Helper to generate and send a proactive AI message."""
    try:
        context_str = memory.get_recent_context(user_id, limit=5)
        coach_reply = get_coach_response(user_id, prompt_trigger_msg, context_str)
        # Avoid saving the system trigger to the DB as direct user input to prevent confusion.
        memory.save_message(user_id, "coach", coach_reply)
        await bot.send_message(chat_id=user_id, text=coach_reply)
    except Exception as e:
        print(f"Failed to send proactive message to {user_id}: {e}")

async def ask_for_weight(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job to ping all users for their weekly weigh-in."""
    conn = memory.sqlite3.connect(memory.DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = cursor.fetchall()
    conn.close()
    
    msg = "⚖️ Sunday morning check-in! Step on the scale and tell me your current weight. E.g., '185 lbs'"
    for (user_id,) in users:
        try:
            await context.bot.send_message(chat_id=user_id, text=msg)
            memory.save_message(user_id, "coach", msg)
        except Exception as e:
            print(f"Failed to send weight reminder to {user_id}: {e}")

async def check_in_nudge(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job to nudge users who haven't logged anything in 6 hours."""
    conn = memory.sqlite3.connect(memory.DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = cursor.fetchall()
    
    for (user_id,) in users:
        cursor.execute('''
            SELECT timestamp 
            FROM messages 
            WHERE user_id = ? AND role = 'user' AND content NOT LIKE '[Sent an Audio Voice Note]' AND content NOT LIKE '[Requested Weekly Summary]'
            ORDER BY timestamp DESC LIMIT 1
        ''', (user_id,))
        last_msg = cursor.fetchone()
        
        if last_msg:
            from datetime import timedelta
            last_time = datetime.datetime.fromisoformat(last_msg[0])
            if datetime.datetime.now() - last_time > timedelta(hours=6):
                cursor.execute('''
                    SELECT content FROM messages
                    WHERE user_id = ? AND role = 'coach'
                    ORDER BY timestamp DESC LIMIT 1
                ''', (user_id,))
                last_coach_msg = cursor.fetchone()
                
                if last_coach_msg and "Hey there! I noticed you haven't logged" not in last_coach_msg[0]:
                     try:
                         msg = "Hey there! I noticed you haven't logged anything in a while. Don't forget to track your meals and stay hydrated! 💧"
                         await context.bot.send_message(chat_id=user_id, text=msg)
                         memory.save_message(user_id, "coach", msg)
                     except Exception as e:
                         pass
    conn.close()

if __name__ == '__main__':
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not found in .env")
        exit(1)
        
    application = ApplicationBuilder().token(TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('summary', summary))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    
    job_queue = application.job_queue
    
    # Existing jobs
    job_queue.run_daily(ask_for_weight, time=datetime.time(hour=9, minute=0), days=(0,))
    job_queue.run_repeating(check_in_nudge, interval=3600, first=60)
    
    # NEW JOBS: Proactive Planning & Meal Prompts
    job_queue.run_repeating(proactive_prompts_job, interval=900, first=30) # Runs every 15 minutes
    
    print("Coach Bot is running with v2 Features! Press Ctrl+C to stop.")
    application.run_polling()
