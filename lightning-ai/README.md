# ⚡ Lightning AI

ChatGPT / Claude மாதிரி ஒரு full-stack AI web application.

**Features**
- 💬 Ask any question → AI answers (OpenAI GPT)
- 🎨 Generate images from a text prompt
- 🖼️ Upload an image + ask a question about it (vision)
- 🔐 Gmail login (Google OAuth)
- 🗄️ Every question/answer stored in MySQL, per logged-in user
- ⚡ Attractive dark "lightning" themed UI (not a plain white page)

Stack: **HTML/CSS/JS (frontend) + Python Flask (backend) + MySQL (database)**, deploy-ready for **Render**.

---

## 1. Project structure

```
lightning-ai/
├── app.py                  # Flask backend (all routes + logic)
├── requirements.txt        # Python dependencies
├── schema.sql              # MySQL table definitions (optional manual run)
├── Procfile                 # Render/gunicorn start command
├── render.yaml              # Render deployment config
├── .env.example             # Copy this to ".env" and fill your keys
├── templates/
│   ├── login.html
│   └── index.html
└── static/
    ├── css/style.css
    ├── js/script.js
    └── uploads/            # uploaded/generated images stored here
```

---

## 2. Local setup (test on your computer first)

### Step 1 — Install requirements
```bash
cd lightning-ai
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
```

### Step 2 — Create MySQL database
MySQL-ஐ உங்க கம்ப்யூட்டர்ல install பண்ணி (or use XAMPP/WAMP), இதை run பண்ணுங்க:
```sql
CREATE DATABASE lightning_ai;
```
(Tables automatically create ஆகிடும் app run ஆனதும். `schema.sql` file-ஐயும் manual-ஆ run பண்ணலாம்.)

### Step 3 — Get your API keys

**a) OpenAI API key** (chat + image generation + image understanding):
1. https://platform.openai.com/api-keys க்கு போங்க
2. "Create new secret key" → copy பண்ணுங்க
3. Billing-ல சிறிதளவு credit add பண்ணுங்க (image generation-க்கு paid tier தேவை)

**b) Google OAuth credentials** (Gmail login):
1. https://console.cloud.google.com/apis/credentials க்கு போங்க
2. "Create Credentials" → "OAuth client ID" → Application type: **Web application**
3. Authorized redirect URIs-ல இதை add பண்ணுங்க:
   - Local testing: `http://localhost:5000/auth/callback`
   - Render deploy பண்ணதும்: `https://your-app-name.onrender.com/auth/callback`
4. Client ID மற்றும் Client Secret-ஐ copy பண்ணுங்க

### Step 4 — Configure environment variables
`.env.example` file-ஐ `.env` என rename பண்ணி, உங்க real values fill பண்ணுங்க:
```bash
cp .env.example .env
```

### Step 5 — Run the app
```bash
python app.py
```
Browser-ல திறங்க: **http://localhost:5000**

---

## 3. Deploy to Render (via GitHub)

### Step 1 — Push code to GitHub
```bash
git init
git add .
git commit -m "Lightning AI - initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/lightning-ai.git
git push -u origin main
```
⚠️ **`.env` file-ஐ GitHub-ல push பண்ணாதீங்க** (already `.gitignore`-ல block பண்ணி இருக்கு).

### Step 2 — Create a MySQL database (Render doesn't provide free MySQL)
Render-ல free MySQL இல்ல, so free hosted MySQL options:
- [Railway.app](https://railway.app) → MySQL plugin (free tier)
- [Aiven.io](https://aiven.io) → free MySQL tier
- [db4free.net](https://www.db4free.net) → free MySQL for testing

இதுல இருந்து கிடைக்கற **host, port, username, password, db name**-ஐ note பண்ணுங்க.

### Step 3 — Create Web Service on Render
1. https://dashboard.render.com → "New" → "Web Service"
2. உங்க GitHub repo-வை connect பண்ணுங்க
3. Render `render.yaml`-ஐ auto-detect பண்ணும். இல்லாட்டி manual-ஆ:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
4. **Environment** tab-ல இந்த variables add பண்ணுங்க:
   - `SECRET_KEY`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`
   - `OPENAI_API_KEY`
   - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
5. "Create Web Service" click பண்ணுங்க → deploy ஆரம்பிக்கும்

### Step 4 — Update Google OAuth redirect URI
Deploy ஆனதும் கிடைக்கற URL-ஐ (e.g. `https://lightning-ai.onrender.com`) Google Cloud Console-ல authorized redirect URI-ல சேருங்க:
```
https://lightning-ai.onrender.com/auth/callback
```

Done! இப்போ உங்க site live-ஆ இருக்கும். 🎉

---

## 4. How it works (summary)

| Feature | How |
|---|---|
| Ask questions | `/api/chat` → OpenAI `gpt-4o-mini` chat completion |
| Generate image | `/api/generate-image` → OpenAI `gpt-image-1` image generation |
| Upload image + ask | `/api/upload-image` → OpenAI vision model reads image + answers |
| Gmail login | Google OAuth (Authlib) → creates/loads user in `users` table |
| History | Every Q&A saved in `chat_history` table, linked to `user_id`, shown in sidebar |

## 5. Notes
- Costs: OpenAI API is pay-as-you-go (small cost per request). Google login and Render hosting (free tier) are free.
- Free MySQL hosts sometimes sleep/limit connections — for serious production use, consider a paid MySQL plan.
- To change the AI model, edit the `model="..."` values inside `app.py`.
