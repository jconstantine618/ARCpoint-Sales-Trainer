import streamlit as st
import openai
import os
import json
import pathlib
import time
import sqlite3
import datetime
import base64
from gtts import gTTS

# --- Database Setup for Leaderboard ---
DB_PATH = pathlib.Path(__file__).parent / "leaderboard.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()
c.execute(
    """
    CREATE TABLE IF NOT EXISTS leaderboard (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        score INTEGER,
        timestamp DATETIME
    )
    """
)
conn.commit()

# --- Scoring function — improved close detection ---
def calculate_score(messages):
    total_points = 0
    principle_points = min(len([m for m in messages if m["role"] == "user"]), 30) * 3
    total_points += min(principle_points, 90)

    success_phrases = [
        "yes", "let's move forward", "ready to proceed",
        "let's get started", "i'm excited to begin", "move forward with this partnership"
    ]
    last_responses = " ".join(m["content"].lower() for m in messages[-3:])
    sale_closed = any(phrase in last_responses for phrase in success_phrases)

    if sale_closed:
        total_points += 30

    summary = "✅ You hit several key principles.\n" if total_points >= 70 else "⚠️ You missed important objections or pain points.\n"
    summary += f"Principle points: {principle_points}/90\n"
    summary += f"Sale close bonus: {'30' if sale_closed else '0'}/30\n"
    return total_points, summary

# --- Timer functions ---
def init_timer():
    if 'chat_start' not in st.session_state:
        st.session_state.chat_start = time.time()
        st.session_state.chat_ended = False

def check_time_cap(persona):
    window = persona['time_availability']['window']
    max_minutes = {'<5':5, '5-10':10, '10-15':15}.get(window, 10)
    elapsed = (time.time() - st.session_state.chat_start) / 60
    if elapsed >= max_minutes:
        st.session_state.chat_ended = True
        return True
    return False

# --- Setup OpenAI client ---
api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
if not api_key:
    st.error("OPENAI_API_KEY not found.")
    st.stop()
client = openai.OpenAI(api_key=api_key)

# --- Load scenarios ---
DATA_PATH = pathlib.Path(__file__).parent / "data" / "arcpoint_scenarios.json"
with open(DATA_PATH) as f:
    SCENARIOS = json.load(f)

# --- UI setup ---
st.set_page_config(page_title="ARCpoint Sales Trainer", page_icon="💬")
st.title("💬 ARCpoint Sales Training Chatbot")

# --- Download Sales Playbook Button ---
# Ensure the PDF is located next to this script before running
pdf_path = pathlib.Path(__file__).parent / "TPA Solutions Play Book.pdf"
if pdf_path.exists():
    pdf_bytes = pdf_path.read_bytes()
    b64_pdf = base64.b64encode(pdf_bytes).decode()
    button_html = (
        f'<a href="data:application/pdf;base64,{b64_pdf}" download="TPA_Solutions_Play_Book.pdf">'
        '<div style="background-color:red;color:white;text-align:center;padding:8px;margin-bottom:10px;border-radius:4px;">'
        'Download Sales Playbook</div></a>'
    )
    st.sidebar.markdown(button_html, unsafe_allow_html=True)
else:
    st.sidebar.error("Sales playbook PDF not found. Place 'TPA Solutions Play Book.pdf' next to app.py.")

# --- Sidebar controls ---
scenario_names = [f"{s['id']}. {s['prospect']} ({s['category']})" for s in SCENARIOS]
choice = st.sidebar.selectbox("Choose a scenario", scenario_names)
voice_mode = st.sidebar.checkbox("🎙️ Enable Voice Mode")

# Select scenario and primary persona
current = SCENARIOS[scenario_names.index(choice)]
current_persona = current['decision_makers'][0]

# --- Show persona details ---
st.markdown(f"""
**Persona:** {current_persona['persona_name']} ({current_persona['persona_role']})  
**Background:** {current_persona['persona_background']}  
**Company:** {current['prospect']}  
**Difficulty:** {current['difficulty']['level']}  
**Time Available:** {current_persona['time_availability']['window']} minutes
"""
)

# --- System prompt ---
system_prompt = f"""
You are role‑playing **{current_persona['persona_name']}**, the **{current_persona['persona_role']}** at **{current['prospect']}**.  
• You have the background, pressures and goals of this real buyer: their industry regulations, decision process, and pain points per the playbook.  
• Speak and act **only** as this persona would, with realistic objections and internal decision considerations.  
• You know ARCpoint Labs offerings, but you’re skeptical until the rep uncovers **your** needs.  
• Follow strong sales principles: gradual disclosure, empathy, teaching & tailoring.  
• Respect your time: you have {current_persona['time_availability']['window']} minutes in this meeting.  
Stay in character at all times.
"""

# --- Reset on scenario change and initialize session ---
if "last_scenario" not in st.session_state or choice != st.session_state.last_scenario:
    st.session_state.last_scenario = choice
    st.session_state.messages = [{"role": "system", "content": system_prompt}]
    st.session_state.closed = False
    st.session_state.loading_score = False
    st.session_state.score_result = ""
    st.session_state.leaderboard_inserted = False
    st.session_state.score_value = None

# --- Ensure timer starts ---
init_timer()

# --- Chat input and processing ---
user_input = st.chat_input("Your message to the prospect")
if user_input and not st.session_state.closed:
    st.session_state.messages.append({"role": "user", "content": user_input})
    if check_time_cap(current_persona):
        timeout_msg = (
            f"**{current_persona['persona_name']}**: I'm sorry, but I need to jump to another meeting right now. ""
            " Please send me a summary and we can continue later."
        )
        st.session_state.messages.append({"role": "assistant", "content": timeout_msg})
    else:
        messages = [{"role": "system", "content": system_prompt}] + st.session_state.messages[1:]
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages
        )
        reply = response.choices[0].message.content.strip()
        st.session_state.messages.append({"role": "assistant", "content": reply})

# --- Display chat ---
for msg in st.session_state.messages[1:]:
    if msg["role"] == "user":
        st.chat_message("user").write(msg["content"])
    else:
        st.chat_message("assistant").write(msg["content"])
        if voice_mode:
            tts = gTTS(msg["content"] )
            tts.save("reply.mp3")
            audio_file = open("reply.mp3", "rb")
            st.audio(audio_file.read(), format="audio/mp3")

# --- Sidebar: Reset & End Chat ---
if st.sidebar.button("🔄 Reset Chat"):
    st.session_state.messages = [{"role": "system", "content": system_prompt}]
    st.session_state.closed = False
    st.session_state.loading_score = False
    st.session_state.score_result = ""
    st.session_state.leaderboard_inserted = False
    st.session_state.score_value = None
    init_timer()
    st.rerun()

end_label = ("⏳ Generating score..." if st.session_state.loading_score else "🔚 End Chat")
if st.sidebar.button(end_label):
    if not st.session_state.closed and not st.session_state.loading_score:
        st.session_state.loading_score = True
        score, summary = calculate_score(st.session_state.messages)
        st.session_state.closed = True
        st.session_state.loading_score = False
        st.session_state.score_result = f"🏆 **Final Score: {score}/100**\n\n{summary}"
        st.session_state.score_value = score

# --- Show score and leaderboard ---
if st.session_state.score_result:
    st.sidebar.markdown(st.session_state.score_result)
    if st.session_state.closed and not st.session_state.leaderboard_inserted:
        st.sidebar.write("### Save your result to the leaderboard")
        st.sidebar.text_input("Your name:", key="leaderboard_name")
        if st.sidebar.button("🏅 Save my score"):
            name = st.session_state.get("leaderboard_name")
            if name:
                c.execute(
                    "INSERT INTO leaderboard (name, score, timestamp) VALUES (?, ?, ?)"
                    ,(name, st.session_state.score_value, datetime.datetime.now())
                )
                conn.commit()
                st.session_state.leaderboard_inserted = True
                st.sidebar.success("Your score has been recorded!")
    st.sidebar.write("### Top 10 All-Time Scores")
    rows = c.execute(
        "SELECT name, score FROM leaderboard ORDER BY score DESC, timestamp ASC LIMIT 10"
    ).fetchall()
    for i, (n, s) in enumerate(rows, start=1):
        st.sidebar.write(f"{i}. {n} — {s}")
