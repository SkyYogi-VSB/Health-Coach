import os
import re
import json
import pytz
from datetime import datetime
from PIL import Image
from dotenv import load_dotenv

import memory

load_dotenv()

AI_PROVIDER = "gemini" # Hardcoded for v2
gem_key = os.getenv("GEMINI_API_KEY")

genai_client = None
if gem_key and gem_key != "your-gemini-api-key":
    from google import genai
    genai_client = genai.Client(api_key=gem_key)

def get_system_prompt(user_id: int) -> str:
    profile = memory.get_user_profile(user_id)
    
    tz_str = 'UTC'
    cal_goal = 2000
    pro_goal = 150
    lunch = "12:30"
    dinner = "18:30"
    
    if profile:
        tz_str = profile.get('timezone') or 'UTC'
        cal_goal = profile.get('daily_calories_goal') or 2000
        pro_goal = profile.get('daily_protein_goal') or 150
        lunch = profile.get('lunch_time') or "12:30"
        dinner = profile.get('dinner_time') or "18:30"
        
    try:
        user_tz = pytz.timezone(tz_str)
    except pytz.UnknownTimeZoneError:
        user_tz = pytz.utc
        
    local_time = datetime.now(user_tz).strftime("%A, %Y-%m-%d %I:%M %p %Z")
    
    prompt = f"""
You are a friendly, encouraging, and supportive personal health and nutrition coach. 
Your goal is to help the user achieve their fitness goals by tracking their meals, tracking their workouts, estimating calories/macros, and keeping them motivated.

CRITICAL INSTRUCTION: Assume the conversation is in English by default. Do not switch languages defensively just because the user types a single foreign loanword.

--- USER PROFILE & CONTEXT ---
Current Local Time: {local_time}
Daily Calorie Goal: {cal_goal} kcal
Daily Protein Goal: {pro_goal} g
Typical Lunch Time: {lunch}
Typical Dinner Time: {dinner}
------------------------------

When the user logs a meal (either with text or an image):
1. Estimate the calories and macros (Protein in grams is the most important).
2. Deduct those from their estimated daily goals.
3. Give them a quick update on where they stand for the day in a positive tone.
4. BEHAVIORAL RULE: If the user exceeds their daily calorie goal ({cal_goal} kcal) or falls behind on protein ({pro_goal} g), you MUST politely push back and warn them.

When the user logs a workout or physical activity:
1. Estimate the calories burned.
2. Tell them explicitly how many calories they burned and that you've added it back to their daily caloric budget.

If the user has not set goals (e.g., they just said "hi" for the first time or the context indicates onboarding):
- Guide them through setting calorie/exercise goals, their timezone, and their preferred lunch and dinner times.

If the user asks for a recipe or sends a picture of ingredients/their fridge:
1. Identify the healthy ingredients available.
2. Suggest a single, simple recipe using those ingredients that fits their macro goals. Provide the estimated macros for the recipe.

If they log their weight, acknowledge it, congratulate them on taking the step to track it, and provide a short word of encouragement.

When the user asks a general question, answer it directly and supportively based on the context.
"""
    return prompt

def extract_weight(user_message, user_id):
    if "lbs" in user_message.lower() or "kg" in user_message.lower() or "weight" in user_message.lower():
        match = re.search(r'(\d+(\.\d+)?)\s*(lbs|kg)', user_message.lower())
        if match:
            weight_val = float(match.group(1))
            if match.group(3) == "kg":
                weight_val = weight_val * 2.20462 # Convert to lbs
            memory.log_weight(user_id, round(weight_val, 1))

def parse_profile_updates(user_id: int, context: str):
    """Uses Gemini to extract user profile updates from recent conversation history."""
    if not genai_client: return
    
    prompt = f"""
Based on the following recent conversation history, extract the user's timezone, daily calorie goal, daily protein goal, lunch time, and dinner time IF they mentioned them.
If a value is not mentioned or you are unsure, use null.
Timezone MUST be a valid pytz timezone string (e.g., 'America/New_York', 'Europe/London', 'America/Los_Angeles').
Lunch and Dinner time MUST be in HH:MM 24-hour format (e.g. '13:00', '18:30').
Return ONLY a valid JSON object with the keys: 'timezone', 'calories', 'protein', 'lunch_time', 'dinner_time'.

Conversation History:
{context}
"""
    try:
        response = genai_client.models.generate_content(
            model='gemini-2.5-flash-8b', # Using faster model for basic extraction
            contents=prompt,
        )
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:-3]
        elif text.startswith("```"):
            text = text[3:-3]
            
        data = json.loads(text)
        profile = memory.get_user_profile(user_id) or {}
        
        if data.get('timezone'):
            memory.update_timezone(user_id, data['timezone'])
            
        if data.get('calories') is not None or data.get('protein') is not None:
            cal = data.get('calories') if data.get('calories') is not None else profile.get('daily_calories_goal', 2000)
            pro = data.get('protein') if data.get('protein') is not None else profile.get('daily_protein_goal', 150)
            memory.update_user_goals(user_id, int(cal), int(pro))
            
        if data.get('lunch_time') or data.get('dinner_time'):
            lunch = data.get('lunch_time') or profile.get('lunch_time') or '12:30'
            dinner = data.get('dinner_time') or profile.get('dinner_time') or '18:30'
            memory.update_meal_times(user_id, lunch, dinner)
            
    except Exception as e:
        print(f"Failed to parse profile updates: {e}")

def summarize_rolling_context(user_id: int, unsummarized_text: str, last_message_id: int):
    """Summarizes old unsummarized messages to shrink token context."""
    if not genai_client: return
    
    # Only summarize if there's substantial context
    if unsummarized_text.count('\n') <= 10:
        return
        
    prompt = f"""
    Please provide a very concise running summary of the following conversation history.
    Focus only on the user's ongoing stated goals, constraints, latest stats, or meal plans.
    Omit pleasantries and small talk.
    
    Conversation History:
    {unsummarized_text}
    """
    try:
        response = genai_client.models.generate_content(
            model='gemini-2.5-flash-lite', 
            contents=prompt
        )
        memory.log_api_request(user_id, request_type='summarization')
        summary = response.text.strip()
        memory.update_context_summary(user_id, summary, last_message_id)
    except Exception as e:
        print(f"Failed to summarize context: {e}")

def get_coach_response(user_id: int, user_message: str, context: str, image_path: str = None, audio_path: str = None) -> str:
    if not genai_client:
        return "Gemini API key is missing in .env!"
        
    if not memory.can_make_api_call(user_id):
        return "Hey! I'm currently overwhelmed with requests. Please wait a minute before asking again so I can catch my breath! ❤️"
        
    if not image_path and not audio_path:
        cached_response = memory.get_cached_response(user_message)
        if cached_response:
            return cached_response
        
    complex_intents = ["deep dive", "explain", "why", "how to", "plan", "routine", "build a", "create a", "compare", "analyze"]
    if any(intent in user_message.lower() for intent in complex_intents) or len(user_message.split()) > 30:
        active_model = 'gemini-2.5-pro'
    else:
        active_model = 'gemini-2.5-flash'
        
    system_prompt = get_system_prompt(user_id)
    full_text_prompt = f"{system_prompt}\n\nContext from past conversation:\n{context}\n\nUser current message:\n{user_message}"
    contents = [full_text_prompt]
    
    if image_path:
        try:
            img = Image.open(image_path)
            contents.append(img)
        except Exception as e:
            print(f"Failed to load image: {e}")
            return "Sorry, I couldn't process that image. Give me a text log instead."
        
    audio_file_obj = None
    if audio_path:
        try:
            audio_file_obj = genai_client.files.upload(file=audio_path)
            contents.append(audio_file_obj)
            contents.append("Please listen to this audio closely and respond to it as if I typed it out.")
        except Exception as e:
            print(f"Failed to upload audio: {e}")
            return "Sorry, I couldn't process that audio. Give me a text log instead."
            
    try:
        try:
            response = genai_client.models.generate_content(
                model=active_model,
                contents=contents
            )
            memory.log_api_request(user_id, request_type=active_model)
            reply = response.text.strip()
        except Exception as e:
            error_msg = str(e).lower()
            if "429" in error_msg or "exhausted" in error_msg or "quota" in error_msg:
                print("Rate limit hit. Falling back to gemini-2.5-flash-lite...")
                try:
                    response = genai_client.models.generate_content(
                        model='gemini-2.5-flash-lite',
                        contents=contents
                    )
                    memory.log_api_request(user_id, request_type='gemini-2.5-flash-lite_fallback')
                    reply = response.text.strip()
                except Exception as fallback_e:
                    print(f"Fallback model also failed: {fallback_e}")
                    return "Wow, I am completely out of tokens for the minute! Please give me a second to recharge."
            else:
                print(f"Error communicating with Gemini API: {e}")
                return "Sorry, I'm having trouble thinking straight right now. Technical difficulties!"
    
        # Post-response routines
        extract_weight(user_message, user_id)
        
        if not image_path and not audio_path:
            memory.cache_response(user_message, reply)
            
        unsummarized_text, last_msg_id = memory.get_unsummarized_messages(user_id)
        if unsummarized_text.count('\n') > 10:
            summarize_rolling_context(user_id, unsummarized_text, last_msg_id)
            
        # Async-like parsing of profile logic can run synchronously
        if "time" in user_message.lower() or "pm" in user_message.lower() or "am" in user_message.lower() or "goal" in user_message.lower() or "lunch" in user_message.lower() or "cal" in user_message.lower() or "protein" in user_message.lower():
            parse_profile_updates(user_id, f"{context}\nUser: {user_message}\nCoach: {reply}")
            
        return reply
    finally:
        if audio_file_obj:
            try:
                genai_client.files.delete(name=audio_file_obj.name)
            except Exception as e:
                print(f"Warning: failed to delete file from Gemini: {e}")

SUMMARY_PROMPT = """
You are a friendly, encouraging, and supportive personal health and nutrition coach.
The user has requested a weekly summary.
You will be provided with their weight trend from the past 30 days and their diet/activity logs from the past 7 days.

Your task:
1. Analyze their weight trend. Are they losing, gaining, or maintaining?
2. Review their weekly meals. Point out strengths (e.g., hitting protein goals) and areas for improvement.
3. Keep the summary engaging, using emojis and a supportive tone.
4. Give them one actionable piece of advice for the upcoming week based on their specific logs.
"""

def get_coach_summary(weekly_context: str) -> str:
    if not genai_client:
        return "Gemini API key is missing!"
         
    full_prompt = f"{SUMMARY_PROMPT}\n\n{weekly_context}\n\nCoach Weekly Summary:"
    try:
        response = genai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=full_prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"Error communicating with Gemini API: {e}")
        return "Sorry, I ran into an issue generating your summary. Let's tackle today instead!"
