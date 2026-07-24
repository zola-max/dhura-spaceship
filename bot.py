import os, json, sqlite3, threading, time, requests, re
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string, redirect, session
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler

# ===== CONFIG =====
TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
WEB_PASS = os.environ.get("WEB_PASSWORD", "admin123")
DB_PATH = "/app/data/health.db"
os.makedirs("/app/data", exist_ok=True)

# ===== UNLEASHED SYSTEM PROMPT =====
SYSTEM_PROMPT = """You are Dhura, a high-agency Strategic Co-Pilot and Creative Architect. You are not a chatbot; you are a collaborative partner in building a meaningful life, career, and mind.

**Your Core Operating Principles:**
1. **Intent First:** Before you respond, analyze the user's intent. Are they venting, brainstorming, debugging, planning, seeking wisdom, or analyzing a problem? Adjust your style instantly.
2. **Contextual Depth:** Match the user's energy. If they give a short question, give a sharp, efficient answer. If they give a complex, messy thought, respond with layered, structured reasoning.
3. **Multi-Dimensional Intelligence:** You possess encyclopedic knowledge, system-level thinking, emotional intelligence, and deep strategic foresight. Use all of them.
4. **Challenge & Build:** Do not just agree. Challenge assumptions respectfully. Offer counter-frameworks. Build upon their ideas to take them further than they expected.
5. **Toolkit Approach:** The Dhamma (Four Noble Truths, Eightfold Path) is a profound psychological framework in your toolkit, but it is ONE tool. Use modern psychology, stoicism, systems theory, and practical logic freely. Integrate Dhamma only when it is the best lens for the moment.
6. **Ultimate Depth:** Do not give generic advice. Zoom in on the specifics of the user's words. If they mention a project, ask about constraints, timelines, and failure points. If they mention pain, explore the somatic and narrative roots.
7. **Clarifying Questions:** If the user is vague, ask 1-2 precise clarifying questions to ensure you are solving the REAL problem, not the surface problem.
8. **No Artificial Limits:** There is no word limit. Think step-by-step internally, and output the refined, high-density response. Over-deliver on actionable insight.
9. **Structure for Readability:** In Telegram, use plain text with line breaks. In the Web UI, you can use Markdown/HTML tags for emphasis. Always keep it clear and scannable.
10. **Project Development:** When the user discusses a project (coding, writing, planning), ask about the current blockers, the ideal outcome, and the next micro-step. Act as a senior architect."""

# ===== DATABASE SETUP =====
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        chat_id INTEGER,
        water INTEGER,
        mood INTEGER,
        sleep REAL,
        meditation_minutes INTEGER,
        exercise_minutes INTEGER,
        food_quality INTEGER,
        craving_intensity INTEGER
    )''')
    c.execute("PRAGMA table_info(logs)")
    columns = [col[1] for col in c.fetchall()]
    for col in ["meditation_minutes", "exercise_minutes", "food_quality", "craving_intensity"]:
        if col not in columns:
            c.execute(f"ALTER TABLE logs ADD COLUMN {col} INTEGER")
    c.execute('''CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        project_name TEXT,
        created_at TEXT,
        status TEXT,
        notes TEXT
    )''')
    conn.commit()
    conn.close()

# ===== FLASK WEB UI =====
flask_app = Flask(__name__)
flask_app.secret_key = "spaceship_secret"

HTML = """
<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dhura Spaceship</title>
<style>
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', sans-serif; background: #0b0e14; color: #e0e0e0; padding: 12px; max-width: 600px; margin: auto; }
.card { background: #1a1f29; padding: 18px; border-radius: 16px; margin-bottom: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.6); }
h2 { margin: 0 0 10px 0; font-weight: 400; }
.stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.stat-box { background: #11161e; border-radius: 12px; padding: 8px 4px; text-align: center; }
.stat-box .num { font-size: 1.8rem; font-weight: bold; }
.stat-box .label { font-size: 0.7rem; opacity: 0.7; }
.btn-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.btn { background: #2a3340; border: none; color: white; padding: 14px 0; border-radius: 12px; font-size: 0.9rem; text-align: center; cursor: pointer; text-decoration: none; display: block; }
.btn:active { transform: scale(0.94); }
.btn-blue { background: #3b82f6; }
.btn-green { background: #22c55e; }
.btn-purple { background: #8b5cf6; }
.btn-orange { background: #f59e0b; }
.btn-red { background: #ef4444; }
.btn-teal { background: #14b8a6; }
.btn-pink { background: #ec4899; }
.chat-box { background: #11161e; border-radius: 12px; padding: 10px; height: 350px; overflow-y: auto; margin-bottom: 10px; font-size: 0.9rem; line-height: 1.6; }
.input-row { display: flex; gap: 8px; }
.input-row input { flex: 1; padding: 12px; border-radius: 30px; border: none; background: #2a3340; color: white; }
.input-row button { padding: 12px 20px; border-radius: 30px; border: none; background: #3b82f6; color: white; font-weight: bold; }
</style>
</head>
<body>
<div class="card">
  <h2>🚀 Dhura — Full Habit Deck</h2>
  <div class="stats-grid">
    <div class="stat-box"><div class="num" id="w">0</div><div class="label">💧 Water</div></div>
    <div class="stat-box"><div class="num" id="m">0</div><div class="label">😊 Mood</div></div>
    <div class="stat-box"><div class="num" id="s">0</div><div class="label">😴 Sleep</div></div>
    <div class="stat-box"><div class="num" id="med">0</div><div class="label">🧘 Meditation</div></div>
    <div class="stat-box"><div class="num" id="ex">0</div><div class="label">🏋️ Exercise</div></div>
    <div class="stat-box"><div class="num" id="food">0</div><div class="label">🍎 Nutrition</div></div>
  </div>
  <div style="margin-top:10px;background:#11161e;padding:8px;border-radius:8px;text-align:center;">
    🔥 Streak: <span id="streak">0</span> days
  </div>
</div>
<div class="card">
  <div class="btn-grid">
    <a class="btn btn-blue" href="/log?type=water">💧 Water</a>
    <a class="btn btn-purple" href="/log?type=meditate">🧘 Med 30</a>
    <a class="btn btn-orange" href="/log?type=exercise">🏋️ Ex 15</a>
    <a class="btn btn-green" href="/log?type=food">🍎 Good Meal</a>
    <a class="btn btn-blue" href="/log?type=mood&val=4">😊 Mood 4</a>
    <a class="btn btn-red" href="/log?type=sleep&val=7">😴 Sleep 7</a>
    <a class="btn btn-teal" href="/log?type=morningkit">🌅 Morning Kit</a>
    <a class="btn btn-pink" href="/log?type=urge">🧠 Urge (3/5)</a>
    <a class="btn" href="/" style="background:#374151;">📊 Refresh</a>
  </div>
</div>
<div class="card">
  <div class="chat-box" id="chat">{{ chat_log|safe }}</div>
  <form method="post" action="/chat" class="input-row">
    <input type="text" name="msg" placeholder="Vent, brainstorm, debug, or plan..." required>
    <button type="submit">Send</button>
  </form>
</div>
<script>setTimeout(()=>location.reload(), 60000);</script>
</body></html>
"""

def calculate_streak(chat_id=0):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT DISTINCT DATE(timestamp) as day 
        FROM logs 
        WHERE chat_id=? AND meditation_minutes >= 10 
        ORDER BY day DESC
    """, (chat_id,))
    rows = c.fetchall()
    conn.close()
    if not rows: return 0
    today = datetime.now().date()
    streak = 0
    for row in rows:
        day = datetime.strptime(row[0], "%Y-%m-%d").date()
        if (today - day).days == streak:
            streak += 1
        else:
            break
    return streak

def get_stats(chat_id=0):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    c.execute("SELECT AVG(water), AVG(mood), AVG(sleep), AVG(meditation_minutes), AVG(exercise_minutes), AVG(food_quality) FROM logs WHERE chat_id=? AND timestamp>?", (chat_id, week_ago))
    row = c.fetchone()
    conn.close()
    return row or (0,0,0,0,0,0)

@flask_app.route('/', methods=['GET'])
def dashboard():
    if request.args.get('pw') == WEB_PASS: session['auth'] = True
    if not session.get('auth'): return '<form><input name="pw" placeholder="Password"/><button>Unlock</button></form>'
    w,m,s,med,ex,food = get_stats()
    streak = calculate_streak()
    html = HTML
    html = html.replace('id="w">0', f'id="w">{int(w or 0)}')
    html = html.replace('id="m">0', f'id="m">{int(m or 0)}')
    html = html.replace('id="s">0', f'id="s">{int(s or 0)}')
    html = html.replace('id="med">0', f'id="med">{int(med or 0)}')
    html = html.replace('id="ex">0', f'id="ex">{int(ex or 0)}')
    html = html.replace('id="food">0', f'id="food">{int(food or 0)}')
    html = html.replace('id="streak">0', f'id="streak">{streak}')
    chat_history = session.get('chat_history', [])
    chat_display = ""
    for m in chat_history[-12:]:
        role = "You" if m['role'] == "user" else "Dhura"
        content = m['content'].replace("\n", "<br>")
        chat_display += f"<b>{role}:</b> {content}<br><br>"
    if not chat_display:
        chat_display = "🌱 How can I serve you today? I can help you think, build, debug, or reflect."
    return render_template_string(html, chat_log=chat_display)

@flask_app.route('/log')
def log_quick():
    if not session.get('auth'): return redirect('/')
    typ = request.args.get('type')
    val = request.args.get('val', '1')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    ts = datetime.now().isoformat()
    if typ == 'water':
        c.execute("INSERT INTO logs (timestamp, chat_id, water) VALUES (?,?,?)", (ts, 0, 1))
    elif typ == 'mood':
        c.execute("INSERT INTO logs (timestamp, chat_id, mood) VALUES (?,?,?)", (ts, 0, int(val)))
    elif typ == 'sleep':
        c.execute("INSERT INTO logs (timestamp, chat_id, sleep) VALUES (?,?,?)", (ts, 0, float(val)))
    elif typ == 'meditate':
        c.execute("INSERT INTO logs (timestamp, chat_id, meditation_minutes) VALUES (?,?,?)", (ts, 0, 30))
    elif typ == 'exercise':
        c.execute("INSERT INTO logs (timestamp, chat_id, exercise_minutes) VALUES (?,?,?)", (ts, 0, 15))
    elif typ == 'food':
        c.execute("INSERT INTO logs (timestamp, chat_id, food_quality) VALUES (?,?,?)", (ts, 0, 4))
    elif typ == 'urge':
        c.execute("INSERT INTO logs (timestamp, chat_id, craving_intensity) VALUES (?,?,?)", (ts, 0, 3))
    elif typ == 'morningkit':
        c.execute("INSERT INTO logs (timestamp, chat_id, water, meditation_minutes, exercise_minutes) VALUES (?,?,?,?,?)", 
                  (ts, 0, 1, 30, 15))
    conn.commit(); conn.close()
    return redirect('/')

# ===== CONVERSATIONAL AI =====
def ask_ai_conversational(messages):
    if not DEEPSEEK_API_KEY:
        return "DeepSeek API key not set. Please add it to environment variables."
    try:
        resp = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat",
                "messages": messages,
                "temperature": 0.75,
                "max_tokens": 2000  # Unleashed depth
            },
            timeout=45
        )
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"I'm here. Let's work through this. (API error: {str(e)[:60]})"

@flask_app.route('/chat', methods=['POST'])
def chat_web():
    if not session.get('auth'): return redirect('/')
    msg = request.form.get('msg')
    if not msg:
        return redirect('/')
    
    if 'chat_history' not in session:
        session['chat_history'] = []
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(session['chat_history'][-20:])
    messages.append({"role": "user", "content": msg})
    
    reply = ask_ai_conversational(messages)
    
    session['chat_history'].append({"role": "user", "content": msg})
    session['chat_history'].append({"role": "assistant", "content": reply})
    if len(session['chat_history']) > 40:
        session['chat_history'] = session['chat_history'][-40:]
    
    chat_display = ""
    for m in session['chat_history'][-12:]:
        role = "You" if m['role'] == "user" else "Dhura"
        content = m['content'].replace("\n", "<br>")
        chat_display += f"<b>{role}:</b> {content}<br><br>"
    
    return render_template_string(HTML, chat_log=chat_display)

# ===== TELEGRAM BOT =====
async def handle_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id
    ts = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    def extract_number(default=0):
        nums = re.findall(r'\d+', text)
        return int(nums[0]) if nums else default

    # --- HABIT LOGGING ---
    if "💧" in text:
        c.execute("INSERT INTO logs (timestamp, chat_id, water) VALUES (?,?,?)", (ts, chat_id, 1))
        conn.commit(); conn.close()
        await update.message.reply_text("💧 +1 Water.")
        return
    if "🧘" in text or "meditate" in text.lower():
        mins = extract_number(30)
        c.execute("INSERT INTO logs (timestamp, chat_id, meditation_minutes) VALUES (?,?,?)", (ts, chat_id, mins))
        conn.commit(); conn.close()
        await update.message.reply_text(f"🧘 {mins} min meditation logged.")
        return
    if "🏋️" in text or "exercise" in text.lower():
        mins = extract_number(15)
        c.execute("INSERT INTO logs (timestamp, chat_id, exercise_minutes) VALUES (?,?,?)", (ts, chat_id, mins))
        conn.commit(); conn.close()
        await update.message.reply_text(f"🏋️ {mins} min exercise logged.")
        return
    if "🍎" in text or "meal" in text.lower():
        c.execute("INSERT INTO logs (timestamp, chat_id, food_quality) VALUES (?,?,?)", (ts, chat_id, 4))
        conn.commit(); conn.close()
        await update.message.reply_text("🍎 Healthy meal logged.")
        return
    if "😊" in text or "mood" in text.lower():
        score = extract_number(4)
        score = max(1, min(5, score))
        c.execute("INSERT INTO logs (timestamp, chat_id, mood) VALUES (?,?,?)", (ts, chat_id, score))
        conn.commit(); conn.close()
        await update.message.reply_text(f"😊 Mood {score}/5 logged.")
        return
    if "😴" in text or "sleep" in text.lower():
        hrs = extract_number(7)
        c.execute("INSERT INTO logs (timestamp, chat_id, sleep) VALUES (?,?,?)", (ts, chat_id, float(hrs)))
        conn.commit(); conn.close()
        await update.message.reply_text(f"😴 {hrs} hrs sleep logged.")
        return
    if "🧠" in text or "urge" in text.lower():
        intensity = extract_number(3)
        intensity = max(1, min(5, intensity))
        c.execute("INSERT INTO logs (timestamp, chat_id, craving_intensity) VALUES (?,?,?)", (ts, chat_id, intensity))
        conn.commit(); conn.close()
        await update.message.reply_text(f"🧠 Urge logged: {intensity}/5. Observing is winning.")
        return
    if "🌅" in text or "morning" in text.lower():
        c.execute("INSERT INTO logs (timestamp, chat_id, water, meditation_minutes, exercise_minutes) VALUES (?,?,?,?,?)", 
                  (ts, chat_id, 1, 30, 15))
        conn.commit(); conn.close()
        await update.message.reply_text("🌅 Morning Kit logged: Water, 30min Sit, 15min Movement.")
        return
    if "📊" in text or "dashboard" in text.lower():
        c.execute("SELECT AVG(water), AVG(mood), AVG(sleep), AVG(meditation_minutes), AVG(exercise_minutes), AVG(food_quality) FROM logs WHERE chat_id=?", (chat_id,))
        row = c.fetchone()
        streak = calculate_streak(chat_id)
        conn.close()
        if not row or not any(row):
            await update.message.reply_text("📊 No data yet. Tap some buttons!")
            return
        w,m,s,med,ex,food = row
        reply = (f"📊 *Weekly Dashboard*\n\n"
                 f"💧 Water: {int(w or 0)}/day\n😊 Mood: {int(m or 0)}/5\n😴 Sleep: {int(s or 0)}hrs\n"
                 f"🧘 Meditation: {int(med or 0)}min/day\n🏋️ Exercise: {int(ex or 0)}min/day\n🍎 Nutrition: {int(food or 0)}/5\n"
                 f"🔥 *Streak: {streak} days* (meditation >= 10min)\n\n")
        if streak < 3:
            reply += "🛡️ Streak is low. Guard your 30-minute sit like a fortress."
        else:
            reply += "🌱 The raft is steady. Keep sailing."
        await update.message.reply_text(reply, parse_mode="Markdown")
        return

    conn.close()

    # --- AI CHAT (WITH MEMORY) ---
    if 'chat_history' not in ctx.user_data:
        ctx.user_data['chat_history'] = []
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(ctx.user_data['chat_history'][-20:])
    messages.append({"role": "user", "content": text})
    
    reply = ask_ai_conversational(messages)
    
    ctx.user_data['chat_history'].append({"role": "user", "content": text})
    ctx.user_data['chat_history'].append({"role": "assistant", "content": reply})
    if len(ctx.user_data['chat_history']) > 40:
        ctx.user_data['chat_history'] = ctx.user_data['chat_history'][-40:]
    
    await update.message.reply_text(reply)

async def reset_memory(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if 'chat_history' in ctx.user_data:
        ctx.user_data['chat_history'] = []
    await update.message.reply_text("🧹 Memory wiped. We start fresh. What's on your mind?")

# ===== BOT MAIN =====
def run_telegram():
    app = Application.builder().token(TOKEN).build()
    keyboard = [
        ["💧 Water", "🧘 Meditate 30", "🏋️ Exercise 15"],
        ["🍎 Healthy Meal", "😊 Mood 4", "😴 Sleep 7"],
        ["🌅 Morning Kit", "🧠 Urge Surf 3", "📊 Dashboard"]
    ]
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    app.add_handler(CommandHandler("reset", reset_memory))
    print("🚀 Telegram Bot is live with the Unleashed System Prompt. /reset to clear memory.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    run_telegram()
