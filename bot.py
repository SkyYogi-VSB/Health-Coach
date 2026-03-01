import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

from ai_coach import get_coach_response, get_coach_summary
import memory

import re
import uuid

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
        "ALRIGHT LISTEN UP! I'm your new AI Health Coach. \n\n"
        "Tell me what you're eating, and I'll track your macros and hold you accountable. "
        "No excuses. Let's get to work! Send me your first meal."
    )
    
    # Save bot's welcome message
    memory.save_message(user_id, "coach", welcome_msg)
    
    await context.bot.send_message(chat_id=update.effective_chat.id, text=welcome_msg)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming text messages (user logging meals or asking questions)."""
    if not await check_allowed(update): return
    
    user_id = update.effective_user.id
    user_msg = update.message.text
    
    # 1. Save the user's message
    memory.save_message(user_id, "user", user_msg)
    
    # 2. Grab the recent context (past messages)
    context_str = memory.get_recent_context(user_id, limit=10)
    
    # 3. Send to AI model
    # Send a "typing..." action so the user knows we are thinking
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    
    coach_reply = get_coach_response(user_id, user_msg, context_str)
    
    # 4. Save the Coach's reply
    memory.save_message(user_id, "coach", coach_reply)
    
    # 5. Send it back to Telegram
    await context.bot.send_message(chat_id=update.effective_chat.id, text=coach_reply)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming photos."""
    if not await check_allowed(update): return
    
    user_id = update.effective_user.id
    caption = update.message.caption or "Here's my meal."
    
    # Send typing action
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    
    # Download the highest resolution photo
    photo_file = await update.message.photo[-1].get_file()
    download_path = os.path.join(os.path.dirname(__file__), f"temp_{user_id}_{uuid.uuid4().hex[:8]}.jpg")
    await photo_file.download_to_drive(download_path)
    
    try:
        # 1. Save user's message (caption + indicator it was a photo)
        memory.save_message(user_id, "user", f"[Sent a photo]: {caption}")
        
        # 2. Grab recent context
        context_str = memory.get_recent_context(user_id, limit=10)
        
        # 3. Send to AI model with the image
        coach_reply = get_coach_response(user_id, caption, context_str, image_path=download_path)
        
        # 4. Save Coach's reply
        memory.save_message(user_id, "coach", coach_reply)
        
        # 5. Send back to Telegram
        await context.bot.send_message(chat_id=update.effective_chat.id, text=coach_reply)
    finally:
        # Cleanup temp image
        if os.path.exists(download_path):
            try:
                os.remove(download_path)
            except Exception:
                pass

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming voice messages (audio)."""
    if not await check_allowed(update): return
    
    user_id = update.effective_user.id
    
    # Send a "typing..." action
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    
    # 1. Download the voice note
    voice_file = await update.message.voice.get_file()
    download_path = os.path.join(os.path.dirname(__file__), f"temp_voice_{user_id}_{uuid.uuid4().hex[:8]}.ogg")
    await voice_file.download_to_drive(download_path)
    
    try:
        # 2. Save the explicit text
        memory.save_message(user_id, "user", "[Sent an Audio Voice Note]")
        
        # 3. Get context
        context_str = memory.get_recent_context(user_id, limit=10)
        
        # 4. Process with AI model
        coach_reply = get_coach_response(user_id, "Transcribe this audio, parse the meal or workout inside it, and reply.", context_str, audio_path=download_path)
        
        # 5. Save the reply
        memory.save_message(user_id, "coach", coach_reply)
        
        # 6. Send to Telegram
        await context.bot.send_message(chat_id=update.effective_chat.id, text=coach_reply)
    finally:
        # Clean up file
        if os.path.exists(download_path):
            try:
                os.remove(download_path)
            except Exception:
                pass

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /summary command to give a weekly breakdown."""
    if not await check_allowed(update): return
    
    user_id = update.effective_user.id
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    
    # Grab the last 7 days of logs and 30 days of weight
    weekly_logs_str = memory.get_weekly_logs(user_id)
    
    # Ask the coach to summarize
    coach_reply = get_coach_summary(weekly_logs_str)
    
    # Save the summary in chat history too
    memory.save_message(user_id, "user", "[Requested Weekly Summary]")
    memory.save_message(user_id, "coach", coach_reply)
    
    await context.bot.send_message(chat_id=update.effective_chat.id, text=coach_reply)

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
    # Find all users
    cursor.execute('SELECT user_id FROM users')
    users = cursor.fetchall()
    
    for (user_id,) in users:
        # Check their last message
        cursor.execute('''
            SELECT timestamp 
            FROM messages 
            WHERE user_id = ? AND role = 'user' AND content NOT LIKE '[Sent an Audio Voice Note]' AND content NOT LIKE '[Requested Weekly Summary]'
            ORDER BY timestamp DESC LIMIT 1
        ''', (user_id,))
        last_msg = cursor.fetchone()
        
        if last_msg:
            from datetime import datetime, timedelta
            last_time = datetime.fromisoformat(last_msg[0])
            # If the last message was over 6 hours ago
            if datetime.now() - last_time > timedelta(hours=6):
                # Don't double ping if we already pinged
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
    start_handler = CommandHandler('start', start)
    summary_handler = CommandHandler('summary', summary)
    text_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text)
    photo_handler = MessageHandler(filters.PHOTO, handle_photo)
    voice_handler = MessageHandler(filters.VOICE, handle_voice)

    application.add_handler(start_handler)
    application.add_handler(summary_handler)
    application.add_handler(text_handler)
    application.add_handler(photo_handler)
    application.add_handler(voice_handler)
    
    # Schedule the weekly weight prompt (0 enables Sunday, run at 9:00 AM server time)
    import datetime
    job_queue = application.job_queue
    job_queue.run_daily(ask_for_weight, time=datetime.time(hour=9, minute=0), days=(0,))
    
    # Run the nudge check every 1 hour
    job_queue.run_repeating(check_in_nudge, interval=3600, first=60)
    
    print("Coach Bot is running with v2 Features! Press Ctrl+C to stop.")
    application.run_polling()
