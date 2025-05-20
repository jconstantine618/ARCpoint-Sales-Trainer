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
c.execute("""
CREATE TABLE IF NOT EXISTS leaderboard (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    score INTEGER,
    timestamp DATETIME
)
""")
conn.commit()

# --- Pillar-Based Scoring Function ---
PILLARS = {
    "Rapport": ["i understand", "appreciate", "thank you", "great question", "how are you"],
    "Pain": ["what challenges", "issue", "concern", "pain point", "problem"],
    "UpFront": ["agenda", "scope", "end of call", "contract"],
    "TeachTailor": ["did you know", "we've seen", "in our experience", "often we find"],
    "Close": ["does that make sense", "ready to proceed", "shall we", "let's move forward"]
}

def calculate_score(messages):
    counts = {p: 0 for p in PILLARS}
    for msg in messages:
        if msg["role"] != "user":
            continue
        text = msg["content"].lower()
        for pillar, kws in PILLARS.items():
            if any(k in text for k in kws):
                counts[pillar] += 1
    # Sub-scores capped at 3 occurrences => 20 points each
    sub_scores = {p: min(counts[p], 3) * (20/3) for p in PILLARS}
    total = int(sum(sub_scores.values()))
    # Build feedback
    feedback_lines = []
    for pillar, score in sub_scores.items():
        if score < 12:  # less than 60%
            feedback_lines.append(f"⚠️ You scored {int(score)}/20 on {pillar}. Try adding more {pillar.lower()} questions.")
        else:
            feedback_lines.append(f"✅ Good job on {pillar} ({int(score)}/20).")
    return total, "\n".join(feedback_lines)

# --- Timer Functions ---
def init_timer():
    if 'chat_start' not in st.session_state:
        st.session_state.chat_start = time.time()
        st.session_state.chat_ended = False

def check_time_cap(difficulty_level):
    caps = {"Easy": 10, "Medium": 15, "Hard": 20}
    max_minutes = caps.get(difficulty_level, 10)
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
pdf_path = pathlib.Path(__file__).parent / "TPA Solutions Play Book.pdf"
if pdf_path.exists():
    with open(pdf_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    playbook_link = (
        f'<a href="data:application/pdf;base64,{b64}" download="TPA_Solutions_Play_Book.pdf">'
        '<button style="background-color:red;color:white;width:100%;padding:8px;border:none;border-radius:4px;">'
        'Download Sales Playbook</button></a>'
    )
    st.sidebar.markdown(playbook_link, unsafe_allow_html=True)

# --- Sidebar: Scenario Selection ---
scenario_names = [f"{s['id']}. {s['prospect']} ({s['category']})" for s in SCENARIOS]
choice = st.sidebar.selectbox("Choose a scenario", scenario_names)
current = SCENARIOS[scenario_names.index(choice)]

# --- Reset session when scenario changes ---
if "last_scenario" not in st.session_state or choice != st.session_state.last_scenario:
    st.session_state.last_scenario = choice
    st.session_state.current_persona_idx = 0
    st.session_state.messages = []
    st.session_state.closed = False
    st.session_state.loading_score = False
    st.session_state.score_result = ""
    st.session_state.score_value = None
    st.session_state.leaderboard_inserted = False

# --- Persona Selection ---
persona_list = current['decision_makers']
persona_options = [
    f"{i+1}. {p['persona_name']} ({p['persona_role']})"
    for i, p in enumerate(persona_list)
]
persona_idx = st.sidebar.selectbox("Which decision-maker?", persona_options, index=st.session_state.current_persona_idx)
st.session_state.current_persona_idx = persona_idx
current_persona = persona_list[persona_idx]

# --- Persona Awareness Note ---
other_names = [p['persona_name'] for p in persona_list if p != current_persona]
other_note = ""
if other_names:
    other_note = f"You know {', '.join(other_names)} is another stakeholder and may need to join."

# --- Build System Prompt ---
time_limit = {"Easy":10, "Medium":15, "Hard":20}[current['difficulty']['level']]
system_prompt = f"""
You are **{current_persona['persona_name']}**, the **{current_persona['persona_role']}** at **{current['prospect']}**.
• Background: {current_persona['persona_background']}; pains: {', '.join(current_persona['pain_points'])}.
• Difficulty level: {current['difficulty']['level']} → {time_limit} minutes to complete this call.
• {other_note}
• Speak only as this persona, with realistic objections and timing.
Stay in character.
"""

# --- Initialize timer and messages ---
init_timer()
if not st.session_state.messages:
    st.session_state.messages = [{"role":"system","content":system_prompt}]

# --- Display Persona Info & Chat ---
st.markdown(f"""
**Persona:** {current_persona['persona_name']} ({current_persona['persona_role']})  
**Background:** {current_persona['persona_background']}  
**Company:** {current['prospect']}  
**Time Available:** {time_limit} min  
""")

user_input = st.chat_input("Your message to the prospect")
if user_input and not st.session_state.closed:
    # If rep mentions another persona, switch
    for idx, p in enumerate(persona_list):
        if idx != persona_idx and p['persona_name'].lower() in user_input.lower():
            st.session_state.current_persona_idx = idx
            current_persona = persona_list[idx]
            switch_msg = f"**{current_persona['persona_name']} ({current_persona['persona_role']}) has joined the meeting.**"
            st.session_state.messages.append({"role":"assistant","content":switch_msg})
            # rebuild prompt
            system_prompt = system_prompt  # can regenerate if needed
            break
    else:
        # Regular chat turn
        st.session_state.messages.append({"role":"user","content":user_input})
        if check_time_cap(current['difficulty']['level']):
            timeout = f"**{current_persona['persona_name']}**: Sorry, I need to join another meeting now. Let's pick this up later."
            st.session_state.messages.append({"role":"assistant","content":timeout})
        else:
            msgs = st.session_state.messages.copy()
            msgs[0] = {"role":"system","content":system_prompt}
            response = client.chat.completions.create(model="gpt-3.5-turbo", messages=msgs)
            reply = response.choices[0].message.content.strip()
            st.session_state.messages.append({"role":"assistant","content":reply})

# render chat
for msg in st.session_state.messages[1:]:
    st.chat_message(msg["role"]).write(msg["content"])
    if msg["role"]=="assistant" and st.session_state.get("voice_mode"):
        tts = gTTS(msg["content"])
        tts.save("reply.mp3")
        st.audio(open("reply.mp3","rb").read(), format="audio/mp3")

# --- Sidebar Controls ---
voice_mode = st.sidebar.checkbox("🎙️ Enable Voice Mode", key="voice_mode")
if st.sidebar.button("🔄 Reset Chat"):
    st.session_state.last_scenario = choice
    st.session_state.current_persona_idx = 0
    st.session_state.messages = [{"role":"system","content":system_prompt}]
    st.session_state.closed = False
    init_timer()
    st.rerun()

end_label = "⏳ Generating score..." if st.session_state.loading_score else "🔚 End Chat"
if st.sidebar.button(end_label):
    if not st.session_state.closed and not st.session_state.loading_score:
        st.session_state.loading_score = True
        total_score, feedback = calculate_score(st.session_state.messages)
        st.session_state.closed = True
        st.session_state.loading_score = False
        st.session_state.score_result = f"🏆 **Total Score: {total_score}/100**\n\n{feedback}"
        st.session_state.score_value = total_score

        # Generate "What Happened Next"
        outcome_prompt = [
            {"role":"system","content":"You are a sales coach."},
            {"role":"user","content":(
                "Based on this chat and a final score of "
                f"{total_score}/100, write a 3–4 sentence 'What Happened Next' scenario "
                "describing how the prospect followed up or moved on."
            )}
        ]
        outcome = client.chat.completions.create(model="gpt-3.5-turbo", messages=outcome_prompt)
        st.sidebar.markdown("### What Happened Next")
        st.sidebar.write(outcome.choices[0].message.content.strip())

# show score & leaderboard
if st.session_state.score_result:
    st.sidebar.markdown(st.session_state.score_result)
    if not st.session_state.leaderboard_inserted:
        st.sidebar.text_input("Your name:", key="leaderboard_name")
        if st.sidebar.button("🏅 Save my score"):
            name = st.session_state.get("leaderboard_name")
            if name:
                c.execute(
                    "INSERT INTO leaderboard (name, score, timestamp) VALUES (?, ?, ?)",
                    (name, st.session_state.score_value, datetime.datetime.now())
                )
                conn.commit()
                st.session_state.leaderboard_inserted = True
                st.sidebar.success("Your score has been recorded!")
    st.sidebar.write("### Top 10 All-Time Scores")
    rows = c.execute("SELECT name, score FROM leaderboard ORDER BY score DESC, timestamp ASC LIMIT 10").fetchall()
    for i, (n, s) in enumerate(rows, start=1):
        st.sidebar.write(f"{i}. {n} — {s}")
