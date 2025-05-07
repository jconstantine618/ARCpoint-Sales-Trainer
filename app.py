import streamlit as st
import openai
import os
import json
import pathlib
from gtts import gTTS

# Setup OpenAI client
api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
if not api_key:
    st.error("OPENAI_API_KEY not found.")
    st.stop()
client = openai.OpenAI(api_key=api_key)

# Load scenarios
DATA_PATH = pathlib.Path(__file__).parent / "data" / "arcpoint_scenarios.json"
with open(DATA_PATH) as f:
    SCENARIOS = json.load(f)

# UI setup
st.set_page_config(page_title="ARCpoint Sales Trainer", page_icon="💬")
st.title("💬 ARCpoint Sales Training Chatbot")

# Sidebar controls
scenario_names = [f"{s['id']}. {s['prospect']} ({s['category']})" for s in SCENARIOS]
choice = st.sidebar.selectbox("Choose a scenario", scenario_names)
voice_mode = st.sidebar.checkbox("🎙️ Enable Voice Mode")

current = SCENARIOS[scenario_names.index(choice)]

# Show details
st.markdown(f"""
**Persona:** {current['persona_name']} ({current['persona_role']})  
**Background:** {current['persona_background']}  
**Company:** {current['prospect']}  
**Employees:** {current['total_employees']} total, {current['dot_employees']} under DOT  
**Difficulty:** {current['difficulty']}  
**State:** {current['state']} (Marijuana: {current['marijuana_legality']})  
**Random Program:** {current['random_program']}  
**Supervisor Training:** {current['supervisor_training']}  
**Policy Updated:** {current['drug_policy_update']}  
**Clearinghouse Knowledge:** {current['clearinghouse_knowledge']}
""")

# Reset chat when scenario changes
if "last_scenario" not in st.session_state:
    st.session_state.last_scenario = choice

if choice != st.session_state.last_scenario:
    st.session_state.messages = [{
        "role": "system",
        "content": f"You are role-playing as {current['persona_name']}, {current['persona_role']} at {current['prospect']}. "
                   f"You are {current['arcpoint_familiarity']}, but NOT a current ARCpoint customer. "
                   f"You have hidden pain points and objections. Only say YES to closing if the salesperson effectively addresses them."
    }]
    st.session_state.closed = False
    st.session_state.last_scenario = choice

# Initialize messages
if "messages" not in st.session_state:
    st.session_state.messages = [{
        "role": "system",
        "content": f"You are role-playing as {current['persona_name']}, {current['persona_role']} at {current['prospect']}. "
                   f"You are {current['arcpoint_familiarity']}, but NOT a current ARCpoint customer. "
                   f"You have hidden pain points and objections. Only say YES to closing if the salesperson effectively addresses them."
    }]
    st.session_state.closed = False

# Chat input
user_input = st.chat_input("Your message to the prospect")
if user_input and not st.session_state.closed:
    st.session_state.messages.append({"role": "user", "content": user_input})
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=st.session_state.messages
    )
    reply = response.choices[0].message.content.strip()
    st.session_state.messages.append({"role": "assistant", "content": reply})

    if any(phrase in user_input.lower() for phrase in ["move forward", "sign up", "get started", "ready to proceed"]):
        score, summary = calculate_score(st.session_state.messages)
        st.session_state.closed = True
        st.success(f"🏆 Final Score: {score}/100")
        st.write(summary)
        if score >= 70:
            st.balloons()
            st.write("🎉 You closed the sale! Excellent job!")
        else:
            st.write("❗ Sale not closed or too many gaps. Review the chat and try again!")

# Show chat history + voice
for msg in st.session_state.messages[1:]:
    if msg["role"] == "user":
        st.chat_message("user").write(msg["content"])
    else:
        st.chat_message("assistant").write(msg["content"])
        if voice_mode:
            tts = gTTS(msg["content"])
            tts.save("reply.mp3")
            audio_file = open("reply.mp3", "rb")
            audio_bytes = audio_file.read()
            st.audio(audio_bytes, format="audio/mp3")

# Reset button
if st.sidebar.button("🔄 Reset Chat"):
    st.session_state.messages = [{
        "role": "system",
        "content": f"You are role-playing as {current['persona_name']}, {current['persona_role']} at {current['prospect']}."
    }]
    st.session_state.closed = False
    st.experimental_rerun()

# Scoring function
def calculate_score(messages):
    total_points = 0
    principle_points = min(len([m for m in messages if m["role"] == "user"]), 30) * 3
    total_points += min(principle_points, 90)
    sale_closed = any("yes" in m["content"].lower() for m in messages[-3:])
    if sale_closed:
        total_points += 30
    summary = "✅ You hit several key principles.\n" if total_points >= 70 else "⚠️ You missed important objections or pain points.\n"
    summary += f"Principle points: {principle_points}/90\n"
    summary += f"Sale close bonus: {'30' if sale_closed else '0'}/30\n"
    return total_points, summary
