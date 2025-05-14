import streamlit as st
import openai
import os
import json
import pathlib
from gtts import gTTS

# Scoring function — improved close detection
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

# Show general details only
st.markdown(f"""
**Persona:** {current['persona_name']} ({current['persona_role']})  
**Background:** {current['persona_background']}  
**Company:** {current['prospect']}  
**Difficulty:** {current['difficulty']}  
**State:** {current['state']} (Marijuana: {current['marijuana_legality']})
""")

system_prompt = f"""
You are role‑playing **{current['persona_name']}**, the **{current['persona_role']}** at **{current['prospect']}**.  
• You have the background, pressures and goals of this real buyer: their industry regulations, budget cycles, decision process, and pain points (e.g. DOT‑mandated compliance, turnover costs, distracted HR teams) per the TPA Solutions Playbook :contentReference[oaicite:0]{index=0}:contentReference[oaicite:1]{index=1}.  
• Speak and act **only** as this persona would, with realistic objections, news of recent company events or industry shifts, and an eye on internal stakeholders.  
• You’ve done your homework: you know basic ARCpoint Labs offerings, but you’re skeptical until the rep uncovers **your** needs: compliance gaps, cost drivers, workflow headaches (Sandler pain funnel) :contentReference[oaicite:2]{index=2}:contentReference[oaicite:3]{index=3}.  
• Follow Dale Carnegie’s principles: reveal information gradually, show genuine curiosity, protect your own “face,” and respond in ways that feel authentic to your role (e.g., express appreciation when rapport is strong, push back when controls aren’t clear) :contentReference[oaicite:4]{index=4}:contentReference[oaicite:5]{index=5}.  
• When the rep asks questions, you’ll answer truthfully—sometimes tersely, sometimes in depth—based on how well they build trust, demonstrate expertise (Challenger teach & tailor), and respect your time (Sandler up‑front contract).  
• Offer realistic objections around scope, budget, or timing; challenge assumptions; and only agree to buy when you’re convinced the solution meets the needs you’ve articulated.  
Stay in character as **{current['persona_name']}** at all times, and never break the buyer’s perspective.  
"""

# Reset on scenario change
if "last_scenario" not in st.session_state:
    st.session_state.last_scenario = choice

if choice != st.session_state.last_scenario:
    st.session_state.messages = [{"role": "system", "content": system_prompt}]
    st.session_state.closed = False
    st.session_state.loading_score = False
    st.session_state.score_result = ""
    st.session_state.last_scenario = choice

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": system_prompt}]
    st.session_state.closed = False
    st.session_state.loading_score = False
    st.session_state.score_result = ""

# Chat input
user_input = st.chat_input("Your message to the prospect")
if user_input and not st.session_state.closed:
    st.session_state.messages.append({"role": "user", "content": user_input})

    # Always prepend system prompt
    messages = [{"role": "system", "content": system_prompt}] + st.session_state.messages[1:]

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages
    )
    reply = response.choices[0].message.content.strip()
    st.session_state.messages.append({"role": "assistant", "content": reply})

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

# Sidebar: Reset button
if st.sidebar.button("🔄 Reset Chat"):
    st.session_state.messages = [{"role": "system", "content": system_prompt}]
    st.session_state.closed = False
    st.session_state.loading_score = False
    st.session_state.score_result = ""
    st.rerun()

# Sidebar: End Chat button
end_chat_label = "🔚 End Chat" if not st.session_state.loading_score else "⏳ Please wait while we are generating your score..."
if st.sidebar.button(end_chat_label):
    if not st.session_state.closed and not st.session_state.loading_score:
        st.session_state.loading_score = True
        score, summary = calculate_score(st.session_state.messages)
        st.session_state.closed = True
        st.session_state.loading_score = False
        st.session_state.score_result = f"🏆 **Final Score: {score}/100**\n\n{summary}"

# Sidebar: Display score below button
if st.session_state.score_result:
    st.sidebar.markdown(st.session_state.score_result)
