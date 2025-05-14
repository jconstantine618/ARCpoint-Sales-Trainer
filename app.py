import streamlit as st
import openai
import os
import json
import pathlib
import time
from gtts import gTTS

# --- Scoring function — improved close detection ---
def calculate_score(messages):
    total_points = 0
    principle_points = min(len([m for m in messages if m["role"] == "user"]), 30) * 3
    total_points += min(principle_points, 90)

    # Check for multiple success phrases
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


def check_time_cap(current_persona):
    window = current_persona['time_availability']['window']
    if window == '<5':
        max_minutes = 5
    elif window == '5-10':
        max_minutes = 10
    elif window == '10-15':
        max_minutes = 15
    else:
        max_minutes = 10

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

# --- Sidebar controls ---
scenario_names = [f"{s['id']}. {s['prospect']} ({s['category']})" for s in SCENARIOS]
choice = st.sidebar.selectbox("Choose a scenario", scenario_names)
voice_mode = st.sidebar.checkbox("🎙️ Enable Voice Mode")

current = SCENARIOS[scenario_names.index(choice)]

# --- Show persona details ---
st.markdown(f"""
**Persona:** {current['persona_name']} ({current['persona_role']})  
**Background:** {current['persona_background']}  
**Company:** {current['prospect']}  
**Difficulty:** {current['difficulty']['level']}  
**State:** {current['state']} (Marijuana: {current['marijuana_legality']})
"""
)

# --- System prompt ---
system_prompt = f"""
You are role‑playing **{current['persona_name']}**, the **{current['persona_role']}** at **{current['prospect']}**.  
• You have the background, pressures and goals of this real buyer: their industry regulations, decision process, and pain points per the playbook.  
• Speak and act **only** as this persona would, with realistic objections and internal decision considerations.  
• You know ARCpoint Labs offerings, but you’re skeptical until the rep uncovers **your** needs.  
• Follow strong sales principles: gradual disclosure, empathy, teaching & tailoring.  
• Respect your time: you have {current['time_availability']['window']} minutes in this meeting.  
Stay in character at all times.
"""

# --- Reset on scenario change and initialize session ---
if "last_scenario" not in st.session_state or choice != st.session_state.last_scenario:
    st.session_state.last_scenario = choice
    st.session_state.messages = [{"role": "system", "content": system_prompt}]
    st.session_state.closed = False
    st.session_state.loading_score = False
    st.session_state.score_result = ""

# --- Ensure timer starts ---
init_timer()

# --- Chat input and processing ---
user_input = st.chat_input("Your message to the prospect")
if user_input and not st.session_state.closed:
    # Append user message
    st.session_state.messages.append({"role": "user", "content": user_input})

    # Check time cap before AI call
    if check_time_cap(current):
        timeout_msg = (
            f"**{current['persona_name']}**: I'm sorry, but I need to jump to another meeting right now. "
            "Please send me a summary and we can continue later."
        )
        st.session_state.messages.append({"role": "assistant", "content": timeout_msg})
    else:
        # Build message list and send to OpenAI
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

if st.session_state.score_result:
    st.sidebar.markdown(st.session_state.score_result)
