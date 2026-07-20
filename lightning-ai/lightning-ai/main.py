from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from groq import Groq
import os
import httpx
import urllib.parse

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


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


# Groq free tier ku oru request la anuppura text (characters) romba periya
# irundha, Groq API "413 request_too_large" nu kudukum. Adhukku munnadiye
# ingeye check panni, friendly message kudukurom (rough estimate: ~4 chars
# per token, 12000 chars ~ 3000 tokens, safe margin for free tier limits).
MAX_MESSAGE_CHARS = 12000


@app.post("/chat")
def chat(req: ChatRequest):
    if len(req.message) > MAX_MESSAGE_CHARS:
        return {
            "reply": (
                f"Ungaloda question romba periya irukku ({len(req.message)} characters). "
                f"Groq free tier oru request ku max ~{MAX_MESSAGE_CHARS} characters "
                "mattum than allow pannum. Please andha text ah 2-3 parts ah pirichi, "
                "oru part mattum oru message ah anuppunga."
            )
        }

    history = chat_history.get(req.session_id, [])
    history.append({"role": "user", "content": req.message})

    system_prompt = (
        "You are Lightning AI, a highly capable assistant similar in quality to "
        "Claude, ChatGPT, Gemini, and Grok. Give accurate, well-reasoned answers. "
        "For coding questions, explain clearly and provide clean, working code in "
        "proper code blocks. For math and science, show step-by-step working before "
        "the final answer. For essays, history, or long-form topics, structure your "
        "answer with clear headings and bullet points where useful. Use markdown "
        "formatting (headings, bold, lists, code blocks) so the answer is easy to "
        "read. Always double-check facts and calculations before answering, and be "
        "explicit if something is uncertain rather than guessing confidently. "
        "IMPORTANT: Never refuse or say a question is 'too long' or 'too big' to "
        "answer. No matter how long or detailed the user's question or pasted "
        "content is, always read all of it and give a complete, thorough answer. "
        "If the input is extremely long, prioritize covering it fully and "
        "accurately, breaking the answer into clear sections rather than "
        "shortening or skipping parts."
    )

    # If this message is very long, drop older history so there is maximum
    # room for the model to actually read and answer the full question.
    is_long_message = len(req.message) > 4000
    messages_to_send = [{"role": "system", "content": system_prompt}]
    messages_to_send += [history[-1]] if is_long_message else history

    try:
        response = client.chat.completions.create(
            model=CHAT_MODEL,
            max_tokens=4096,
            messages=messages_to_send,
        )
        reply = response.choices[0].message.content
        history.append({"role": "assistant", "content": reply})
        chat_history[req.session_id] = history[-20:]  # last 20 messages mattum vekkanga
        return {"reply": reply}
    except Exception as e:
        # If it failed due to context/length limits, retry with just the
        # latest question and no prior history, to maximize available room.
        try:
            fallback_response = client.chat.completions.create(
                model=CHAT_MODEL,
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": req.message},
                ],
            )
            reply = fallback_response.choices[0].message.content
            chat_history[req.session_id] = [
                {"role": "user", "content": req.message},
                {"role": "assistant", "content": reply},
            ]
            return {"reply": reply}
        except Exception as e2:
            # Last resort: drop max_tokens entirely and just send the question,
            # in case the token limit itself was the problem.
            try:
                last_response = client.chat.completions.create(
                    model=CHAT_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": req.message},
                    ],
                )
                reply = last_response.choices[0].message.content
                chat_history[req.session_id] = [
                    {"role": "user", "content": req.message},
                    {"role": "assistant", "content": reply},
                ]
                return {"reply": reply}
            except Exception as e3:
                err_text = str(e3)
                if "413" in err_text or "request_too_large" in err_text:
                    return {
                        "reply": (
                            "Indha question AI ku romba periyadhu (too large) nu "
                            "Groq server solludhu. Please andha text ah konjam short "
                            "pannunga alladhu 2-3 messages ah pirichi anuppunga."
                        )
                    }
                return {"reply": f"Error: {err_text}"}


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
    pollinations_url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true"

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

    instruction = (
        "You are Lightning AI. Look carefully at the image, which may contain a question "
        "paper, math problem, diagram, or document. Read all text in the image accurately "
        "before answering. If it contains questions, solve each one with clear step-by-step "
        "working and give the final answer clearly. Use markdown formatting (headings, bold, "
        "lists, code blocks) to keep the answer neat and easy to read. If any part of the "
        "image is unclear, say so rather than guessing.\n\nUser's request: "
        + req.question
    )

    # Rough guard: base64 payload over ~15MB is very likely to be rejected
    # by the API as too large, regardless of client-side compression.
    if len(image_data) > 15 * 1024 * 1024:
        return {"reply": "This image is too large for the AI to process. Please try a smaller photo or a screenshot instead of a full-resolution camera image."}

    try:
        response = client.chat.completions.create(
            model=VISION_MODEL,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": instruction},
                        {"type": "image_url", "image_url": {"url": image_data}},
                    ],
                }
            ],
        )
        return {"reply": response.choices[0].message.content}
    except Exception as e:
        err_text = str(e)
        if "request_too_large" in err_text or "413" in err_text:
            return {"reply": "This image is too large for the AI to process. Please try a smaller photo (e.g. take a screenshot or use a lower-resolution image) and upload it again."}
        return {"reply": f"Error analyzing image: {err_text}"}


# Frontend files serve pannurathukku
app.mount("/", StaticFiles(directory="static", html=True), name="static")
