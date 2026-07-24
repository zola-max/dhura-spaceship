import os, json, requests
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string, redirect, session

# ===== CONFIG =====
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
WEB_PASS = os.environ.get("WEB_PASSWORD", "admin123")
DB_PATH = "/app/data/health.db"
os.makedirs("/app/data", exist_ok=True)

# ===== SYSTEM PROMPT =====
SYSTEM_PROMPT = """You are Dhura, a Strategic Co-Pilot and Creative Architect. Provide deep, structured, and beautifully formatted responses.

**Response Formatting Rules:**
1. Use **bold headers** for sections (like **Morning:**).
2. Use numbered lists (1., 2.) and bullet points (- or •).
3. Keep paragraphs short and leave blank lines between sections.
4. Give actionable, specific, and detailed advice.

**Your Operating Principles:**
- Analyze intent: venting, planning, brainstorming, or debugging.
- Match depth: short question = sharp answer; complex = layered reasoning.
- Challenge assumptions gently. Build upon the user's ideas.
- Integrate Dhamma, psychology, and systems thinking freely.
- When discussing projects, ask about blockers and next steps."""

# ===== FLASK APP =====
app = Flask(__name__)
app.secret_key = "spaceship_secret"

# Very simple HTML – only chat and a status indicator
HTML = """
<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dhura Chat</title>
<style>
body { font-family: 'Segoe UI', sans-serif; background: #0b0e14; color: #e0e0e0; padding: 12px; max-width: 600px; margin: auto; }
.card { background: #1a1f29; padding: 18px; border-radius: 16px; margin-bottom: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.6); }
.chat-box { background: #11161e; border-radius: 12px; padding: 10px; height: 400px; overflow-y: auto; margin-bottom: 10px; font-size: 0.9rem; line-height: 1.6; }
.input-row { display: flex; gap: 8px; }
.input-row input { flex: 1; padding: 12px; border-radius: 30px; border: none; background: #2a3340; color: white; }
.input-row button { padding: 12px 20px; border-radius: 30px; border: none; background: #3b82f6; color: white; font-weight: bold; }
</style>
</head>
<body>
<div class="card">
  <h2>🚀 Dhura Chat</h2>
  <div class="chat-box" id="chat">{{ chat_log|safe }}</div>
  <form method="post" action="/chat" class="input-row">
    <input type="text" name="msg" placeholder="Ask anything..." required>
    <button type="submit">Send</button>
  </form>
</div>
<script>setTimeout(()=>location.reload(), 60000);</script>
</body></html>
"""

def ask_deepseek(messages):
    if not DEEPSEEK_API_KEY:
        return "❌ DeepSeek API key missing. Set DEEPSEEK_API_KEY environment variable."
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
                "max_tokens": 2000
            },
            timeout=120
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        return "⏳ The request took too long. Please try again or simplify your question."
    except Exception as e:
        return f"⚠️ Error: {str(e)[:80]}"

@app.route('/', methods=['GET'])
def index():
    if request.args.get('pw') == WEB_PASS:
        session['auth'] = True
    if not session.get('auth'):
        return '<form><input name="pw" placeholder="Password"/><button>Unlock</button></form>'
    
    chat_history = session.get('chat_history', [])
    chat_display = ""
    for m in chat_history[-10:]:
        role = "You" if m['role'] == 'user' else "Dhura"
        content = m['content'].replace("\n", "<br>")
        chat_display += f"<b>{role}:</b> {content}<br><br>"
    if not chat_display:
        chat_display = "🌱 How can I help you today? Ask me anything."
    
    return render_template_string(HTML, chat_log=chat_display)

@app.route('/chat', methods=['POST'])
def chat():
    if not session.get('auth'):
        return redirect('/')
    
    msg = request.form.get('msg', '').strip()
    if not msg:
        return redirect('/')
    
    if 'chat_history' not in session:
        session['chat_history'] = []
    
    # Build conversation
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(session['chat_history'][-20:])
    messages.append({"role": "user", "content": msg})
    
    reply = ask_deepseek(messages)
    
    session['chat_history'].append({"role": "user", "content": msg})
    session['chat_history'].append({"role": "assistant", "content": reply})
    if len(session['chat_history']) > 40:
        session['chat_history'] = session['chat_history'][-40:]
    
    return redirect('/')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
