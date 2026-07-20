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

# GROQ_API_KEY environment variable la irundhu edukum (Railway/Render Variables la add pannunga)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

_key = os.environ.get("GROQ_API_KEY")
if not _key:
    print("[Lightning AI] WARNING: GROQ_API_KEY is NOT set!", flush=True)
else:
    print(f"[Lightning AI] GROQ_API_KEY loaded, starts with: {_key[:6]}...", flush=True)

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


SYSTEM_PROMPT = (
    "You are Lightning AI, a highly capable assistant similar in quality to "
    "Claude, ChatGPT, Gemini, and Grok. Give accurate, well-reasoned answers. "
    "For coding questions, explain clearly and provide clean, working code in "
    "proper code blocks. For math and science, show step-by-step working before "
    "the final answer. For essays, history, or long-form topics, structure your "
    "answer with clear headings and bullet points where useful. Use markdown "
    "formatting (headings, bold, lists, code blocks) so the answer is easy to "
    "read. Always double-check facts and calculations before answering, and be "
    "explicit if something is uncertain rather than guessing confidently."
)

# Groq oru request ku evlo characters varaikkum ஏற்கும்னு exact-a theriyathu
# (free tier, model change aana idhu change aagum), so safe-a oru chunk size
# vechirukom. Idhukku mela irundha, kelaya question ah chunks ah pirichi,
# ஒவ்வொரு chunk-ஆ Groq-கிட்ட separate-a anுப்பி, answers-ah join panni oru
# complete reply ah kudukurom — so எவ்வளவு periya question-ஆ கேட்டாலும் work aagum.
CHUNK_CHARS = 10000


def split_into_chunks(text: str, max_len: int = CHUNK_CHARS):
    """Splits text into <= max_len pieces, preferring paragraph/line breaks
    so words/sentences don't get cut in half."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    remaining = text
    while len(remaining) > max_len:
        window = remaining[:max_len]
        # Prefer to cut at the last paragraph break, else last line break,
        # else last space, so we don't slice a word/sentence in half.
        cut = window.rfind("\n\n")
        if cut < max_len * 0.5:
            cut = window.rfind("\n")
        if cut < max_len * 0.5:
            cut = window.rfind(" ")
        if cut < max_len * 0.5:
            cut = max_len  # nothing decent to split on, hard cut
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def ask_groq(messages_to_send):
    """Calls Groq with a 3-step fallback (full messages -> latest-only ->
    latest-only without max_tokens) so a context/size issue on one attempt
    doesn't fail the whole request. Returns (reply_text, error_text_or_None)."""
    last_user_msg = messages_to_send[-1]
    attempts = [
        {"messages": messages_to_send, "max_tokens": 4096},
        {"messages": [messages_to_send[0], last_user_msg], "max_tokens": 4096},
        {"messages": [messages_to_send[0], last_user_msg], "max_tokens": None},
    ]
    last_error = None
    for attempt in attempts:
        try:
            kwargs = {"model": CHAT_MODEL, "messages": attempt["messages"]}
            if attempt["max_tokens"] is not None:
                kwargs["max_tokens"] = attempt["max_tokens"]
            response = client.chat.completions.create(**kwargs)
            return response.choices[0].message.content, None
        except Exception as e:
            last_error = str(e)
            print(f"[Lightning AI] Groq call failed (model={CHAT_MODEL}): {last_error}", flush=True)
    return None, last_error


@app.post("/chat")
def chat(req: ChatRequest):
    history = chat_history.get(req.session_id, [])
    history.append({"role": "user", "content": req.message})

    chunks = split_into_chunks(req.message)

    if len(chunks) == 1:
        # Normal-size question - single call, with chat history for context.
        is_long_message = len(req.message) > 4000
        messages_to_send = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages_to_send += [history[-1]] if is_long_message else history

        reply, error = ask_groq(messages_to_send)
        if error and ("413" in error or "request_too_large" in error):
            # Even the single message alone was too big for Groq - fall back
            # to the chunked path below instead of giving up.
            chunks = split_into_chunks(req.message, max_len=CHUNK_CHARS // 2)
        elif error:
            return {"reply": f"Error: {error}"}
        else:
            history.append({"role": "assistant", "content": reply})
            chat_history[req.session_id] = history[-20:]
            return {"reply": reply}

    # Long question - answer it part by part so nothing gets rejected, then
    # stitch everything into one complete reply.
    part_replies = []
    total = len(chunks)
    for i, chunk in enumerate(chunks, start=1):
        part_instruction = (
            f"This is part {i} of {total} of one long question/document the user "
            "pasted (it was split only because of length, not by the user). "
            "Read this part and give a complete, thorough answer to whatever it "
            "contains. Don't say the question is too long."
        )
        messages_to_send = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": part_instruction + "\n\n---\n\n" + chunk},
        ]
        reply, error = ask_groq(messages_to_send)
        if error:
            part_replies.append(
                f"**[Part {i}/{total} failed: {error}]**"
            )
        else:
            part_replies.append(
                (f"**Part {i}/{total}:**\n\n" if total > 1 else "") + reply
            )

    final_reply = "\n\n---\n\n".join(part_replies)
    history.append({"role": "assistant", "content": final_reply})
    chat_history[req.session_id] = history[-20:]
    return {"reply": final_reply}


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
