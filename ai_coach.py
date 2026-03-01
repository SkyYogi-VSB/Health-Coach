import os
import base64
import re
from PIL import Image
from dotenv import load_dotenv
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

load_dotenv()

AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower()

openai_client = None
genai_client = None

nv_key = os.getenv("NVIDIA_API_KEY")
gem_key = os.getenv("GEMINI_API_KEY")

if nv_key and nv_key != "your-nvidia-api-key":
    from openai import OpenAI
    openai_client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=nv_key
    )

if gem_key and gem_key != "your-gemini-api-key":
    from google import genai
    genai_client = genai.Client(api_key=gem_key)

SYSTEM_PROMPT = """
You are a friendly, encouraging, and supportive personal health and nutrition coach. 
Your goal is to help the user achieve their fitness goals by tracking their meals, tracking their workouts, estimating calories/macros, and keeping them motivated.

CRITICAL INSTRUCTION: Assume the conversation is in English by default. Do not switch languages defensively just because the user types a single foreign loanword (like "hola" or "bon appétit"). However, if the user explicitly asks to speak in a different language, or if they begin writing entire, full sentences in a different language, smoothly transition to speaking in that language to accommodate them.

You have access to their recent conversation history. Keep your responses concise, helpful, and warm. Be empathetic if they slip up, and focus on practical advice and steady progress.

When the user logs a meal (either with text or an image):
1. Estimate the calories and macros (Protein in grams is the most important).
2. Deduct those from their estimated daily goals (generic 2000 cal / 150g protein goal).
3. Give them a quick update on where they stand for the day in a positive tone.

When the user logs a workout or physical activity:
1. Estimate the calories burned based on the activity and duration.
2. Tell them explicitly how many calories they burned and that you've added it back to their daily caloric budget.

If the user asks for a recipe or sends a picture of ingredients/their fridge:
1. Identify the healthy ingredients available.
2. Suggest a single, simple recipe using those ingredients that fits their macro goals. Provide the estimated macros for the recipe.

If they log their weight, acknowledge it, congratulate them on taking the step to track it, and provide a short word of encouragement.

When the user asks a general question, answer it directly and supportively based on the context.
"""

def extract_weight(user_message, user_id):
    """Helper purely to parse weight values and save to DB."""
    if "lbs" in user_message.lower() or "kg" in user_message.lower() or "weight" in user_message.lower():
        match = re.search(r'(\d+(\.\d+)?)\s*(lbs|kg)', user_message.lower())
        if match:
            weight_val = float(match.group(1))
            if match.group(3) == "kg":
                weight_val = weight_val * 2.20462 # Convert to lbs
            
            import memory
            memory.log_weight(user_id, round(weight_val, 1))

@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True
)
def get_coach_response(user_id: int, user_message: str, context: str, image_path: str = None, audio_path: str = None) -> str:
    """Sends the user message, context, and optional image or audio to the configured AI provider and returns the response."""
    if AI_PROVIDER == "nvidia":
        return _get_nvidia_response(user_id, user_message, context, image_path, audio_path)
    else:
        return _get_gemini_response(user_id, user_message, context, image_path, audio_path)

def _get_nvidia_response(user_id, user_message, context, image_path, audio_path):
    # 1. Process Audio first if present
    transcribed_text = ""
    if audio_path:
        # NVIDIA NIM API currently returns 404 for audio endpoints on the free preview catalog.
        # Fallback to Gemini specifically just to extract the text, before sending the text to NVIDIA NIMs.
        if genai_client:
            try:
                print("Falling back to Gemini to transcribe audio...")
                audio_file_obj = genai_client.files.upload(file=audio_path)
                response = genai_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[audio_file_obj, "Transcribe exactly what is said in this audio snippet."]
                )
                transcribed_text = response.text.strip()
                print(f"Transcribed audio: {transcribed_text}")
                try: 
                    genai_client.files.delete(name=audio_file_obj.name)
                except Exception: pass
            except Exception as e:
                print(f"Failed to transcribe audio via Gemini Fallback: {e}")
                return "Sorry, I couldn't process that audio properly right now."
        else:
            return "Audio transcription is currently unsupported on the free NVIDIA endpoint unless a Google Gemini API Key is provided in the .env as a fallback!"

    # 2. Determine Model and Format
    complex_intents = ["deep dive", "explain", "why", "how to", "plan", "routine", "build a", "create a", "compare", "analyze"]
    if image_path:
        active_model = 'meta/llama-3.2-90b-vision-instruct'
    elif any(intent in user_message.lower() for intent in complex_intents) or len(user_message.split()) > 30:
        active_model = 'meta/llama-3.1-70b-instruct'
    else:
        active_model = 'nvidia/llama-3.1-nemotron-nano-8b-v1'

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    base_text = f"Context from past conversation:\n{context}\n\nUser current message/action:\n{user_message}"
    if transcribed_text:
        base_text += f"\n\n[System Note: The user also sent an audio note which was transcribed as]: {transcribed_text}\nPlease reply to their audio."

    if image_path:
        try:
            with open(image_path, "rb") as image_file:
                base64_img = base64.b64encode(image_file.read()).decode('utf-8')
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": base_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}
                ]
            })
        except Exception as e:
            print(f"Failed to load image: {e}")
            return "Sorry, I couldn't process that image. Give me a text log instead."
    else:
        messages.append({"role": "user", "content": base_text})
            
    # 3. Generate response
    try:
        response = openai_client.chat.completions.create(
            model=active_model,
            messages=messages,
            temperature=0.7,
            max_tokens=1024
        )
        reply = response.choices[0].message.content.strip()
        extract_weight(user_message, user_id)
        return reply
    except Exception as e:
        print(f"Error communicating with NVIDIA API: {e}")
        return "Sorry, I'm having trouble thinking straight right now. Technical difficulties with the AI brain!"

def _get_gemini_response(user_id, user_message, context, image_path, audio_path):
    complex_intents = ["deep dive", "explain", "why", "how to", "plan", "routine", "build a", "create a", "compare", "analyze"]
    if any(intent in user_message.lower() for intent in complex_intents) or len(user_message.split()) > 30:
        active_model = 'gemini-2.5-pro'
    else:
        active_model = 'gemini-2.5-flash'
        
    full_text_prompt = f"{SYSTEM_PROMPT}\n\nContext from past conversation:\n{context}\n\nUser current message:\n{user_message}"
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
        response = genai_client.models.generate_content(
            model=active_model,
            contents=contents
        )
        reply = response.text.strip()
        extract_weight(user_message, user_id)
        return reply
    except Exception as e:
        print(f"Error communicating with Gemini API: {e}")
        return "Sorry, I'm having trouble thinking straight right now. Technical difficulties!"
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
    if AI_PROVIDER == "nvidia":
        return _get_nvidia_summary(weekly_context)
    else:
        return _get_gemini_summary(weekly_context)

def _get_nvidia_summary(weekly_context: str) -> str:
    full_prompt = f"{SUMMARY_PROMPT}\n\n{weekly_context}\n\nCoach Weekly Summary:"
    try:
        response = openai_client.chat.completions.create(
            model='nvidia/llama-3.1-nemotron-nano-8b-v1',
            messages=[{"role": "user", "content": full_prompt}],
            temperature=0.7,
            max_tokens=1024
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error communicating with NVIDIA API: {e}")
        return "Sorry, I ran into an issue generating your summary. Let's tackle today instead!"

def _get_gemini_summary(weekly_context: str) -> str:
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
