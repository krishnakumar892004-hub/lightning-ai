from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from groq import Groq
import os
import httpx
import urllib.parse
import sqlite3

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# GROQ_API_KEY environment variable la irundhu edukum (Railway Variables la add pannunga)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# In-memory chat history (simple version - server restart aana poidum)
chat_history = {}
def init_db():
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        question TEXT,
        answer TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()

init_db()

# Text chat model - groq/compound has built-in web search + code execution,
# so it can answer current-events questions and verify math/code automatically.
CHAT_MODEL = "groq/compound"
# Vision (image understanding) model - image upload analysis ku
VISION_MODEL = "qwen/qwen3.6-27b"

# --- Basic safety filter for image generation ---
# Idhu oru extra layer mattum - 100% foolproof illa, aana explicit/18+ related
# words irundha request ah ingeye block pannidum, API ku pogave pogathu.
BLOCKED_TERMS = [
    "nude", "naked", "nsfw", "porn", "sex", "sexual", "explicit",
    "topless", "hentai", "erotic", "fetish", "genitals", "underage",
    "child", "kid", "minor", "loli", "boobs", "breast", "penis", "vagina",
    "xxx", "onlyfans", "strip", "seductive", "lingerie",
]


def is_prompt_safe(prompt: str) -> bool:
    lowered = prompt.lower()
    return not any(term in lowered for term in BLOCKED_TERMS)
def save_chat(session_id, question, answer):
    conn = sqlite3.connect("chat.db")
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO chat_history(session_id, question, answer)
        VALUES (?, ?, ?)
    """, (session_id, question, answer))

    conn.commit()
    conn.close()


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


@app.post("/chat")
def chat(req: ChatRequest):
    history = chat_history.get(req.session_id, [])
    history.append({"role": "user", "content": req.message})

    try:
        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": "You are Lightning AI"},
                {"role":"user","content":req.message}
            ] + history,
        )
        reply = response.choices[0].message.content
        save_chat(req.session_id, req.message, reply)
        history.append({"role": "assistant", "content": reply})
        chat_history[req.session_id] = history[-20:]  # last 20 messages mattum vekkanga
        return {"reply": reply}
    except Exception as e:
        return {"reply": f"Error: {str(e)}"}


@app.get("/api/status")
def status():
    return {"status": "Lightning AI is running"}


class ImageRequest(BaseModel):
    prompt: str


@app.post("/generate-image")
async def generate_image(req: ImageRequest):
    prompt = req.prompt.strip()

    if not prompt:
        return Response(content="Prompt is empty", status_code=400)

    if not is_prompt_safe(prompt):
        return Response(
            content="This request was blocked. Please describe a safe, non-explicit image.",
            status_code=400,
        )

    # Extra nudge towards safe content, on top of the keyword filter
    safe_prompt = f"{prompt}, safe for work, no nudity"
    encoded = urllib.parse.quote(safe_prompt)
    pollinations_url = f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=768&nologo=true"

    try:
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            img_response = await http_client.get(pollinations_url)
            img_response.raise_for_status()
            return Response(content=img_response.content, media_type="image/jpeg")
    except Exception as e:
        return Response(content=f"Image generation failed: {str(e)}", status_code=500)


class ImageAnalysisRequest(BaseModel):
    image_base64: str  # data URL or raw base64
    question: str = "What is in this image? Describe it in detail."


@app.post("/analyze-image")
def analyze_image(req: ImageAnalysisRequest):
    image_data = req.image_base64
    if not image_data.startswith("data:"):
        image_data = f"data:image/jpeg;base64,{image_data}"

    try:
        response = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": req.question},
                        {"type": "image_url", "image_url": {"url": image_data}},
                    ],
                }
            ],
        )
        return {"reply": response.choices[0].message.content}
    except Exception as e:
        return {"reply": f"Error analyzing image: {str(e)}"}


# Frontend files serve pannurathukku
app.mount("/", StaticFiles(directory="static", html=True), name="static")
