import os
import json
import random
from datetime import datetime

import streamlit as st
import openai

# -------------------------------------------------------------
# Configuration – make sure you set your OPENAI_API_KEY in the
# environment or add it under st.secrets["OPENAI_API_KEY"].
# -------------------------------------------------------------
openai.api_key = os.getenv("OPENAI_API_KEY", st.secrets.get("OPENAI_API_KEY", ""))

if not openai.api_key:
    st.error("OPENAI_API_KEY not found. Set it as env var or in Streamlit secrets!")
    st.stop()

# -------------------------------------------------------------
# Minimal scenario bank – start with 10 to keep MVP lightweight.
# Each scenario can be expanded / loaded from JSON later.
# -------------------------------------------------------------
SCENARIOS = [
    {
        "id": 1,
        "title": "25‑Truck Carrier – New DOT Random Pool",
        "persona": "Logistics Manager Lisa",
        "description": (
            "You are Lisa, logistics manager of a 25‑truck regional carrier. "
            "You recently discovered that after crossing 20 CDL drivers, FMCSA now requires a DOT random testing program. "
            "You worry a TPA will be expensive and overkill for a small fleet."
        ),
        "pain_points": [
            "Unsure how to comply with DOT random selection rules",
            "Limited admin time to manage paperwork",
            "Perception that TPA cost may not fit small‑fleet budget"
        ],
        "likely_objections": [
            "We're too small to outsource", "Extra fees", "Drivers hate off‑site testing times"],
        "arcpoint_offer": "DOT random pool management + mobile collections via Total Reporting"
    },
    {
        "id": 2,
        "title": "Manufacturing Plant – Union Negotiations",
        "persona": "HR Director Hank",
        "description": (
            "You are Hank, HR Director at a 500‑employee manufacturing plant entering union negotiations. "
            "Recent OSHA injuries tied to drug use pushed management to propose random testing, but the union is skeptical."
        ),
        "pain_points": [
            "Safety incidents affecting insurance premiums",
            "Need a fair, defensible drug‑free policy",
            "Union relations are delicate"
        ],
        "likely_objections": [
            "Randoms violate privacy", "Testing slows production", "Cost of program"],
        "arcpoint_offer": "Policy development + onsite rapid panels + supervisor training"
    },
    {
        "id": 3,
        "title": "Staffing Agency – Slow Background Checks",
        "persona": "Operations VP Olivia",
        "description": (
            "You are Olivia, VP Ops at a staffing agency onboarding 100 workers each week. "
            "Manual county searches delay start dates and anger clients."
        ),
        "pain_points": [
            "Turnaround times exceeding SLAs",
            "Multiple vendor portals confusion",
            "Risk of sending unvetted temps"
        ],
        "likely_objections": [
            "Instant searches miss records", "Switching platforms is hard"],
        "arcpoint_offer": "Total Reporting hybrid nat+county search with manual QC"
    },
    {
        "id": 4,
        "title": "Healthcare System – OIG Compliance",
        "persona": "Compliance Officer Carla",
        "description": (
            "You are Carla, compliance officer overseeing nurse onboarding across a regional hospital system. "
            "You need continuous OIG & FACIS monitoring but get too many false positives."
        ),
        "pain_points": ["Regulatory fines", "Manual review workload", "Credentialing backlog"],
        "likely_objections": ["False matches", "Subscription cost"],
        "arcpoint_offer": "Curated OIG/FACIS with human adjudication + auto alerts"
    },
    {
        "id": 5,
        "title": "Fin‑tech Startup – RevOps SaaS",
        "persona": "CRO Colin",
        "description": (
            "You are Colin, CRO of a fin‑tech scale‑up. You rely on complex spreadsheets; unsure a RevOps SaaS is necessary."
        ),
        "pain_points": ["Manual revenue reporting errors", "Board requests real‑time KPIs"],
        "likely_objections": ["Current system 'works'", "Budget quarter tight"],
        "arcpoint_offer": "N/A (placeholder SaaS example)"
    }
]

# -------------------------------------------------------------
# Helper functions
# -------------------------------------------------------------

def init_session():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "scenario_id" not in st.session_state:
        st.session_state.scenario_id = SCENARIOS[0]["id"]
    if "scores" not in st.session_state:
        st.session_state.scores = []


def get_scenario_by_id(sid):
    for s in SCENARIOS:
        if s["id"] == sid:
            return s
    return SCENARIOS[0]


def start_conversation():
    sc = get_scenario_by_id(st.session_state.scenario_id)
    st.session_state.messages = [
        {
            "role": "system",
            "content": (
                "You are " + sc["persona"] + ". Respond as this prospect. "
                "Present pains and objections realistically. Stay in character. "
                "Let the trainee lead with questions; do not sell yourself."
            )
        }
    ]
    st.session_state.scores = []


def chat_completion(messages, temperature=0.7):
    return openai.ChatCompletion.create(
        model="gpt-3.5-turbo-0125",
        messages=messages,
        temperature=temperature,
    ).choices[0].message.content.strip()


def evaluate_response(user_msg, prospect_reply, scenario):
    """Return a dict score (1-5) and feedback string."""
    eval_prompt = [
        {"role": "system", "content": (
            "You are an objective sales coach. "
            "Score the trainee's last message on 1‑5 based on: rapport, discovery questions, empathy, objection handling, and linking to ARCpoint solution (" + scenario["arcpoint_offer"] + "). "
            "Give brief feedback (2‑3 sentences). Return JSON: {\"score\": int, \"feedback\": str}."
        )},
        {"role": "assistant", "content": prospect_reply},
        {"role": "user", "content": user_msg},
    ]
    try:
        raw = chat_completion(eval_prompt, temperature=0.0)
        data = json.loads(raw)
        return data
    except Exception:
        return {"score": 3, "feedback": "Could not parse evaluation."}

# -------------------------------------------------------------
# Streamlit UI
# -------------------------------------------------------------

init_session()

st.sidebar.title("ARCpoint Sales Coach – MVP")
scenario_options = {s["title"]: s["id"] for s in SCENARIOS}
selected_title = st.sidebar.selectbox("Select Scenario", list(scenario_options.keys()))
selected_id = scenario_options[selected_title]
if selected_id != st.session_state.scenario_id:
    st.session_state.scenario_id = selected_id
    start_conversation()

if st.sidebar.button("Restart Scenario"):
    start_conversation()

sc = get_scenario_by_id(st.session_state.scenario_id)

st.header(sc["title"])
st.markdown(f"**Prospect Persona:** {sc['persona']}")
st.markdown(f"*{sc['description']}*")

# Display conversation
for m in st.session_state.messages:
    if m["role"] == "assistant":
        st.chat_message("assistant").markdown(m["content"])
    elif m["role"] == "user":
        st.chat_message("user").markdown(m["content"])

# User input
if prompt := st.chat_input("Your message..."):
    # Append user msg
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Get prospect reply
    prospect_reply = chat_completion(st.session_state.messages)
    st.session_state.messages.append({"role": "assistant", "content": prospect_reply})

    # Evaluate the user's last turn
    eval_result = evaluate_response(prompt, prospect_reply, sc)
    st.session_state.scores.append(eval_result)

    # Show evaluation to trainee
    st.toast(f"Score: {eval_result['score']}/5 – {eval_result['feedback']}")

# Scoreboard
if st.session_state.scores:
    avg = sum([e['score'] for e in st.session_state.scores]) / len(st.session_state.scores)
    st.sidebar.metric("Avg Score", f"{avg:.1f} / 5")
    with st.sidebar.expander("Feedback log"):
        for i, e in enumerate(st.session_state.scores, 1):
            st.write(f"Turn {i}: {e['score']} – {e['feedback']}")

st.sidebar.caption("Powered by OpenAI • MVP 0.1 – customize scenarios & rubric in code.")
