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
    "Rapport":     ["i understand", "appreciate", "thank you", "great question", "how are you"],
    "Pain":        ["what challenges", "issue", "concern", "pain point", "problem"],
    "UpFront":     ["agenda", "scope", "end of call", "contract"],
    "TeachTailor": ["did you know", "we've seen", "in our experience", "often we find"],
    "Close":       ["does that make sense", "ready to proceed", "shall we", "let's move forward"]
}

def calculate_score(messages):
    counts = {p: 0 for p in PILLARS}
    for m in messages:
        if m["role"] != "user":
            continue
        text = m["content"].lower()
        for pillar, kws in PILLARS.items():
            if any(k in text for k in kws):
                counts[pillar] += 1
    sub_scores = {p: min(counts[p], 3) * (20/3) for p in PILLARS}
    total = int(sum(sub_scores.values()))
    feedback = []
    for pillar, pts in sub_scores.items():
        if pts < 12:
            feedback.append(f"⚠️ You scored {int(pts)}/20 on {pillar}. Try adding more {pillar.lower()} questions.")
        else:
            feedback.append(f"✅ Good job on {pillar} ({int(pts)}/20).")
    return total, "\n".join(feedback)

# --- Timer Functions ---
def init_timer():
    if "chat_start" not in st.session_state:
        st.session_state.chat_start = time.time()
        st.session_state.chat_ended = False

def check_time_cap(level):
    caps = {"Easy": 10, "Medium": 15, "Hard": 20}
    maxm = caps.get(level, 10)
    elapsed = (time.time() - st.session_state.chat_start) / 60
    if elapsed >= maxm:
        st.session_state.chat_ended = True
        return True
    return False

# --- OpenAI Client ---
api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
if not api_key:
    st.error("OPENAI_API_KEY not found.")
    st.stop()
client = openai.OpenAI(api_key=api_key)

# --- Load Scenarios ---
DATA_PATH = pathlib.Path(__file__).parent / "data" / "arcpoint_scenarios.json"
with open(DATA_PATH) as f:
    SCENARIOS = json.load(f)

# --- Helper: Build System Prompt ---
def build_system_prompt(current, persona):
    time_limit = {"Easy": 10, "Medium": 15, "Hard": 20}[current["difficulty"]["level"]]
    others = [p["persona_name"] for p in current["decision_makers"] if p != persona]
    note = f"You know {', '.join(others)} is another stakeholder and may need to join." if others else ""
    pains = ", ".join(persona["pain_points"])
    return f"""
You are **{persona['persona_name']}**, the **{persona['persona_role']}** at **{current['prospect']}**.
• Background: {persona['persona_background']}; Pain points: {pains}.
• Difficulty: {current['difficulty']['level']} → {time_limit} minutes.
• {note}

**IMPORTANT:**  
• You are **not** the product expert.  
• **Do not** explain drug testing details, specs or procedures yourself.  
• Whenever asked for specifics—costs, technology, test panels—**defer** back to the sales rep:
  “I’m not sure—could you clarify that?”  
  “Can you tell me more about how that works?”

• Speak only as this persona would, voicing realistic objections, clarifying questions, time pressures and need to check with other stakeholders.  

Stay in character.
""".strip()

# --- UI Setup ---
st.set_page_config(page_title="ARCpoint Sales Trainer", page_icon="💬")
st.title("💬 ARCpoint Sales Training Chatbot")

# --- Download Playbook Button ---
pdf_path = pathlib.Path(__file__).parent / "TPA Solutions Play Book.pdf"
if pdf_path.exists():
    b64 = base64.b64encode(pdf_path.read_bytes()).decode()
    btn = (
      f'<a href="data:application/pdf;base64,{b64}" download="TPA_Solutions_Play_Book.pdf">'
      '<button style="background-color:red;color:white;width:100%;padding:8px;'
      'border:none;border-radius:4px;text-decoration:none;">'
      'Download Sales Playbook</button></a>'
    )
    st.sidebar.markdown(btn, unsafe_allow_html=True)

# --- Scenario Selector ---
scenario_names = [f"{s['id']}. {s['prospect']} ({s['category']})" for s in SCENARIOS]
choice = st.sidebar.selectbox("Choose a scenario", scenario_names)
current = SCENARIOS[scenario_names.index(choice)]

# --- Reset on Scenario Change ---
if "last_scenario" not in st.session_state or choice != st.session_state.last_scenario:
    st.session_state.last_scenario = choice
    st.session_state.current_persona_idx = 0
    st.session_state.messages = []
    st.session_state.closed = False
    st.session_state.loading_score = False
    st.session_state.score_result = ""
    st.session_state.score_value = None
    st.session_state.leaderboard_inserted = False

# --- Persona Selector (returns int) ---
plist = current["decision_makers"]
pidx = st.sidebar.selectbox(
    "Which decision-maker?",
    options=list(range(len(plist))),
    format_func=lambda i: f"{plist[i]['persona_name']} ({plist[i]['persona_role']})",
    index=st.session_state.current_persona_idx
)
st.session_state.current_persona_idx = pidx
persona = plist[pidx]

# --- Inject System Prompt & Init Timer ---
system_prompt = build_system_prompt(current, persona)
init_timer()
if not st.session_state.messages:
    st.session_state.messages = [{"role":"system","content":system_prompt}]

# --- Show Persona Info ---
time_limit = {"Easy": 10, "Medium": 15, "Hard": 20}[current["difficulty"]["level"]]
st.markdown(f"""
**Persona:** {persona['persona_name']} ({persona['persona_role']})  
**Background:** {persona['persona_background']}  
**Company:** {current['prospect']}  
**Time Available:** {time_limit} min  
""")

# --- Chat Input & Processing ---
user_input = st.chat_input("Your message to the prospect")
if user_input and not st.session_state.closed:
    switched = False
    # Detect mention of other persona → switch
    for idx, p in enumerate(plist):
        if idx != pidx and p["persona_name"].lower() in user_input.lower():
            pidx = idx
            st.session_state.current_persona_idx = idx
            persona = plist[idx]
            # rebuild prompt
            system_prompt = build_system_prompt(current, persona)
            st.session_state.messages[0] = {"role":"system","content":system_prompt}
            # announce join
            join_msg = f"**{persona['persona_name']} ({persona['persona_role']}) has joined the meeting.**"
            st.session_state.messages.append({"role":"assistant","content":join_msg})
            switched = True
            break

    if not switched:
        st.session_state.messages.append({"role":"user","content":user_input})
        if check_time_cap(current["difficulty"]["level"]):
            st.session_state.messages.append({
                "role":"assistant",
                "content":f"**{persona['persona_name']}**: Sorry, I need to join another meeting now. Let's pick this up later."
            })
        else:
            msgs = st.session_state.messages.copy()
            msgs[0] = {"role":"system","content":system_prompt}
            resp = client.chat.completions.create(model="gpt-3.5-turbo", messages=msgs)
            st.session_state.messages.append({
                "role":"assistant",
                "content":resp.choices[0].message.content.strip()
            })

# --- Render Chat ---
for m in st.session_state.messages[1:]:
    st.chat_message(m["role"]).write(m["content"])
    if m["role"]=="assistant" and st.session_state.get("voice_mode"):
        tts = gTTS(m["content"])
        tts.save("reply.mp3")
        st.audio(open("reply.mp3","rb").read(), format="audio/mp3")

# --- Sidebar Controls ---
voice_mode = st.sidebar.checkbox("🎙️ Enable Voice Mode", key="voice_mode")
if st.sidebar.button("🔄 Reset Chat"):
    st.session_state.current_persona_idx = 0
    st.session_state.messages = [{"role":"system","content":system_prompt}]
    st.session_state.closed = False
    init_timer()
    st.rerun()

end_label = "⏳ Generating score..." if st.session_state.loading_score else "🔚 End Chat"
if st.sidebar.button(end_label):
    if not st.session_state.closed and not st.session_state.loading_score:
        st.session_state.loading_score = True
        score, fb = calculate_score(st.session_state.messages)
        st.session_state.closed = True
        st.session_state.loading_score = False
        st.session_state.score_result = f"🏆 **Total Score: {score}/100**\n\n{fb}"
        st.session_state.score_value = score

        # What Happened Next
        outp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role":"system","content":"You are a sales coach."},
                {"role":"user","content":(
                    "Based on this chat and a final score of "
                    f"{score}/100, write 3–4 sentences describing "
                    "how the prospect followed up or moved on."
                )}
            ]
        )
        st.sidebar.markdown("### What Happened Next")
        st.sidebar.write(outp.choices[0].message.content.strip())

# --- Leaderboard ---
if st.session_state.get("score_result"):
    st.sidebar.markdown(st.session_state.score_result)
    if not st.session_state.leaderboard_inserted:
        st.sidebar.text_input("Your name:", key="leaderboard_name")
        if st.sidebar.button("🏅 Save my score"):
            nm = st.session_state.get("leaderboard_name")
            if nm:
                c.execute(
                    "INSERT INTO leaderboard (name, score, timestamp) VALUES (?, ?, ?)",
                    (nm, st.session_state.score_value, datetime.datetime.now())
                )
                conn.commit()
                st.session_state.leaderboard_inserted = True
                st.sidebar.success("Your score has been recorded!")
    st.sidebar.write("### Top 10 All-Time Scores")
    for i,(nm,sc) in enumerate(
        c.execute("SELECT name, score FROM leaderboard ORDER BY score DESC, timestamp ASC LIMIT 10"),
        start=1
    ):
        st.sidebar.write(f"{i}. {nm} — {sc}")
