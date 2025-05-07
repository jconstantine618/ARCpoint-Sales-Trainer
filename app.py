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

# Display scenario details for trainee
st.markdown(f"""
**Prospect Company:** {current['prospect']}  
**Category:** {current['category']}  
**Persona:** {current['persona_name']}, {current['persona_role']}  
**Background:** {current['persona_background']}  
**Familiarity with ARCpoint:** {current['arcpoint_familiarity']}  
**Company Info:** {current['company_background']}
""")

# Initialize chat state
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content":
         f"You are role-playing as {current['persona_name']}, the {current['persona_role']} at {current['prospect']}. "
         f"Background: {current['persona_background']}. "
         f"You are {current['arcpoint_familiarity']} with ARCpoint Labs, but you are not currently using ARCpoint as a vendor. "
         f"Internally, you have the following pain point: {current['trigger_pain']} "
         f"and the following likely objection: {current['likely_objection']}. "
         f"Do NOT reveal the pain or objection unless the salesperson asks thoughtful, relevant questions. "
         f"Respond naturally, share details realistically, and behave like a human customer."
        }
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

# Display chat history
for msg in st.session_state.messages[1:]:
    if msg["role"] == "user":
        st.chat_message("user").write(msg["content"])
    else:
        st.chat_message("assistant").write(msg["content"])

# Reset button
if st.sidebar.button("🔄 Reset Chat"):
    st.session_state.messages = [
        {"role": "system", "content":
         f"You are role-playing as {current['persona_name']}, the {current['persona_role']} at {current['prospect']}. "
         f"Background: {current['persona_background']}. "
         f"You are {current['arcpoint_familiarity']} with ARCpoint Labs, but you are not currently using ARCpoint as a vendor. "
         f"Internally, you have the following pain point: {current['trigger_pain']} "
         f"and the following likely objection: {current['likely_objection']}. "
         f"Do NOT reveal the pain or objection unless the salesperson asks thoughtful, relevant questions. "
         f"Respond naturally, share details realistically, and behave like a human customer."
        }
    ]
    st.experimental_rerun()
