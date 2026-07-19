# Lightning AI ⚡

Ready-made AI chat website. Backend Python (FastAPI) + Groq LLM API. Frontend simple HTML/JS, dark neon theme.

## Files
- `main.py` — backend server
- `static/index.html` — chat website (frontend)
- `requirements.txt` — Python dependencies
- `Procfile` — Railway ku evvalavu venum nu sollum command

## Setup Steps (Free)

### 1. Groq API Key vaanga
1. https://console.groq.com ku pogunga
2. Sign up pannunga (free)
3. "API Keys" section la oru key create pannunga
4. Andha key ah copy pannunga (safe ah vekkanga, oru thadava mattum kaamikum)

### 2. Github la upload pannunga
1. github.com la account create pannunga (free)
2. New repository create pannunga (e.g. "lightning-ai")
3. Indha zip file la irukura ellame (main.py, static folder, requirements.txt, Procfile) andha repo ku upload pannunga

### 3. Railway la deploy pannunga
1. https://railway.app ku pogunga, Github account use panni sign up pannunga (free)
2. "New Project" → "Deploy from GitHub repo" → ungaloda "lightning-ai" repo select pannunga
3. Deploy start aagum, adhu "Settings" → "Variables" ku pogunga
4. Oru new variable add pannunga:
   - Key: `GROQ_API_KEY`
   - Value: (step 1 la vaanga key ah paste pannunga)
5. Save pannina udane Railway automatic ah redeploy pannidum
6. "Settings" → "Networking" → "Generate Domain" click pannunga — idhu ungaloda free website URL kudukum (example: `lightning-ai-production.up.railway.app`)

### 4. Website open pannunga
Andha URL ah browser la open pannina, ungaloda "Lightning AI" chat website ready!

## Local ah test panna venuma? (optional)
```
pip install -r requirements.txt
export GROQ_API_KEY=your_key_here
uvicorn main:app --reload
```
Browser la `http://localhost:8000` open pannunga.

## New Features Added
- **💬 Chat mode** — normal AI conversation (model: `groq/compound` — this has built-in web search + code execution, so it can answer current-events questions, do accurate math, and explain/write code)
- **🎨 Generate Image mode** — type a description, AI draws an image (uses free Pollinations.ai API, no key needed)
- **📎 Upload Image** — upload a photo and ask questions about it, e.g. a math problem or diagram in a picture (model: `qwen/qwen3.6-27b`, vision-capable)

## About the Image Generation Safety Filter
Server side oru basic keyword filter add pannirukom (`main.py` la `BLOCKED_TERMS` list) — explicit/18+ related words irundha, image request ah backend le block pannidum, API ku pogave pogathu. Idhu **oru extra safety layer mattum** — 100% foolproof nu solla mudiyathu, edhuvume AI image tool 100% guarantee kudukathu. Venumna `BLOCKED_TERMS` list ku `main.py` la vera words add pannalam.

## Notes
- Free Groq API ku daily limit irukku, adhukulla use panradhu podhum normal chat ku
- Pollinations.ai image API **free but rate-limited** (~1 request every 15 seconds without an account) — "unlimited" illa, but cost illama use pannalam
- Railway free tier la konjo naala inactive ah irundha app sleep aaidum, aana next request ku automatic ah wake up aagum
- Ungaloda peru "Lightning AI" nu already header la, title la set pannirukom
- Groq models frequently change/deprecate aagum — edhavadhu error vandha, console.groq.com/docs/models ku poi current model name check pannunga
