import os, json, sqlite3, threading, time, requests, re
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string, redirect, session
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ===== CONFIG =====
TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
WEB_PASS = os.environ.get("WEB_PASSWORD", "admin123")
DB_PATH = "/app/data/health.db"
os.makedirs("/app/data", exist_ok=True)

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
.chat-box { background: #11161e; border-radius: 12px; padding: 10px; height: 200px; overflow-y: auto; margin-bottom: 10px; font-size: 0.9rem; }
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
    <input type="text" name="msg" placeholder="Type 'meditate 45' or vent..." required>
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
    return render_template_string(html, chat_log="🌱 Tap a button or type 'meditate 45'.")

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

@flask_app.route('/chat', methods=['POST'])
def chat_web():
    if not session.get('auth'): return redirect('/')
    msg = request.form.get('msg')
    reply = ask_ai("You are Kalyāṇamitta, a beautiful Dhamma friend. Listen deeply. Keep it under 120 words.", msg)
    return render_template_string(HTML, chat_log=f"<b>You:</b> {msg}<br><br><b>AI:</b> {reply}")

def ask_ai(system, user):
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
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ],
                "temperature": 0.7,
                "max_tokens": 800
            },
            timeout=30
        )
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"I'm here. Tell me more. (AI offline: {str(e)[:50]})"

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
        await update.message.reply_text(f"🧠 Urge logged: {intensity}/5. You are observing, not acting.")
        return
    if "🌅" in text or "morning" in text.lower():
        c.execute("INSERT INTO logs (timestamp, chat_id, water, meditation_minutes, exercise_minutes) VALUES (?,?,?,?,?)", 
                  (ts, chat_id, 1, 30, 15))
        conn.commit(); conn.close()
        await update.message.reply_text("🌅 Morning Kit logged: 💧 Water, 🧘 30min Sit, 🏋️ 15min Movement.")
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
    reply = ask_ai("You are Kalyāṇamitta. Listen deeply. No advice unless asked. Under 120 words.", text)
    await update.message.reply_text(reply)

def run_telegram():
    app = Application.builder().token(TOKEN).build()
    keyboard = [
        ["💧 Water", "🧘 Meditate 30", "🏋️ Exercise 15"],
        ["🍎 Healthy Meal", "😊 Mood 4", "😴 Sleep 7"],
        ["🌅 Morning Kit", "🧠 Urge Surf 3", "📊 Dashboard"]
    ]
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    print("🚀 Telegram Bot is live.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

# ===== MAIN =====
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    run_telegram()
