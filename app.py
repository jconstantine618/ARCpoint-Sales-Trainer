import streamlit as st
import openai
import os
import json
import pathlib

# --- Setup OpenAI client ---
api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
if not api_key:
    st.error("OPENAI_API_KEY not found. Add it to Streamlit secrets or .env.")
    st.stop()

client = openai.OpenAI(api_key=api_key)

# --- Load scenarios ---
DATA_PATH = pathlib.Path(__file__).parent / "data" / "arcpoint_scenarios.json"
with open(DATA_PATH) as f:
    SCENARIOS = json.load(f)

# --- Streamlit UI ---
st.set_page_config(page_title="ARCpoint Sales Trainer", page_icon="💬")
st.title("💬 ARCpoint Sales Training Chatbot")

# Select scenario
scenario_names = [f"{s['id']}. {s['prospect']} ({s['category']})" for s in SCENARIOS]
choice = st.sidebar.selectbox("Choose a scenario", scenario_names)
current = SCENARIOS[scenario_names.index(choice)]

# Display scenario details
st.markdown(f"""
**Prospect Persona:** {current['prospect']}

**Trigger/Pain:** {current['trigger_pain']}

**Likely Objection:** {current['likely_objection']}

""")

# Initialize chat state
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content":
         f"You are role-playing {current['prospect']}, a customer considering ARCpoint Labs services. "
         f"Your pain point is: {current['trigger_pain']}. "
         f"You worry: {current['likely_objection']}. "
         f"Engage as a realistic customer: share pain, raise objections, ask questions, "
         f"and respond naturally to the salesperson."}
    ]

# Chat input
user_input = st.chat_input("Your message to the prospect")
if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})

    # Call OpenAI API
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=st.session_state.messages,
    )
    prospect_reply = response.choices[0].message.content.strip()

    st.session_state.messages.append({"role": "assistant", "content": prospect_reply})

# Display chat
for msg in st.session_state.messages[1:]:
    if msg["role"] == "user":
        st.chat_message("user").write(msg["content"])
    else:
        st.chat_message("assistant").write(msg["content"])

# Reset button
if st.sidebar.button("🔄 Reset Chat"):
    st.session_state.messages = [
        {"role": "system", "content":
         f"You are role-playing {current['prospect']}, a customer considering ARCpoint Labs services. "
         f"Your pain point is: {current['trigger_pain']}. "
         f"You worry: {current['likely_objection']}. "
         f"Engage as a realistic customer: share pain, raise objections, ask questions, "
         f"and respond naturally to the salesperson."}
    ]
    st.experimental_rerun()
