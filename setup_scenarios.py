#!/usr/bin/env python3
import json
from pathlib import Path

SCENARIOS_DIR = Path("scenarios")
SCENARIOS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Scenario definitions
# Each scenario is designed to test a specific aspect of the PGAI agent.
# ---------------------------------------------------------------------------

SCENARIOS = [
    # ------------------------------------------------------------------
    # SCENARIO 01: Straightforward new appointment - baseline functionality
    # ------------------------------------------------------------------
    {
        "id": "01",
        "name": "Simple Appointment Scheduling — New Patient",
        "persona": (
            "You are Maria Chen, 34 years old. You are a new patient at this practice. "
            "You have a mild headache that's been bothering you for three days. "
            "You are calm, polite, and comfortable with technology."
        ),
        "goal": (
            "Schedule a new patient appointment for a headache consultation. "
            "You prefer a morning slot, ideally this week or next week."
        ),
        "edge_case_instructions": (
            "No special edge case. This is a baseline call to test normal "
            "scheduling functionality. Be cooperative and provide whatever "
            "information the agent asks for."
        ),
    },

    # ------------------------------------------------------------------
    # SCENARIO 02: Rescheduling - tests agent's ability to modify existing appt
    # ------------------------------------------------------------------
    {
        "id": "02",
        "name": "Rescheduling an Existing Appointment",
        "persona": (
            "You are James Rivera, 52 years old. You have an existing appointment "
            "on Tuesday at 2pm (next week) that you need to reschedule. You work "
            "full time and can only do mornings before 10am or after 5pm."
        ),
        "goal": (
            "Reschedule your existing Tuesday 2pm appointment to a morning slot "
            "(before 10am) or an evening slot (after 5pm). Any day of the week works."
        ),
        "edge_case_instructions": (
            "If the agent tries to give you a time outside your availability, "
            "politely decline and explain your schedule constraints. Test whether "
            "the agent can handle multiple scheduling attempts."
        ),
    },

    # ------------------------------------------------------------------
    # SCENARIO 03: Medication refill — tests pharmacy/refill workflow
    # ------------------------------------------------------------------
    {
        "id": "03",
        "name": "Prescription Refill Request",
        "persona": (
            "You are Susan Park, 61 years old. You are an established patient. "
            "You need a refill for your blood pressure medication (lisinopril 10mg). "
            "Your pharmacy is CVS on Oak Street."
        ),
        "goal": (
            "Request a refill for lisinopril 10mg to be sent to CVS pharmacy on Oak Street. "
            "You are running out in about 5 days."
        ),
        "edge_case_instructions": (
            "If the agent asks for your date of birth or patient ID, say your "
            "birthday is March 15, 1963 and you don't remember your patient ID. "
            "Test whether the agent properly handles the urgency (5 days left)."
        ),
    },

    # ------------------------------------------------------------------
    # SCENARIO 04: Weekend appointment — tests office hours knowledge
    # ------------------------------------------------------------------
    {
        "id": "04",
        "name": "Weekend Appointment Request (Edge Case — Office Closed)",
        "persona": (
            "You are Tom Bradley, 28 years old. You work Mon-Fri 9-5 and "
            "can only come in on weekends. You have a minor skin rash that "
            "you want checked out."
        ),
        "goal": (
            "Schedule an appointment for Saturday or Sunday. You believe the "
            "office might be open on weekends because a friend went there on a Saturday."
        ),
        "edge_case_instructions": (
            "IMPORTANT: Persistently ask for Saturday or Sunday appointments. "
            "Ask at least 3 times. If the agent confirms a weekend appointment, "
            "that is a major bug — note it. If the office IS open weekends, "
            "that's fine — accept the slot."
        ),
    },

    # ------------------------------------------------------------------
    # SCENARIO 05: Insurance inquiry — tests information accuracy
    # ------------------------------------------------------------------
    {
        "id": "05",
        "name": "Insurance Coverage Inquiry",
        "persona": (
            "You are Patricia Williams, 45 years old. You recently switched jobs "
            "and have new insurance — Aetna PPO. You want to know if the practice "
            "accepts your insurance before scheduling."
        ),
        "goal": (
            "Find out if the practice accepts Aetna PPO insurance. If yes, "
            "schedule a general wellness checkup."
        ),
        "edge_case_instructions": (
            "Ask specifically about Aetna PPO (not just 'Aetna'). "
            "Also ask if you need a referral for a specialist visit. "
            "Test whether the agent gives specific or vague answers about insurance."
        ),
    },

    # ------------------------------------------------------------------
    # SCENARIO 06: Confused elderly patient — tests agent's patience
    # ------------------------------------------------------------------
    {
        "id": "06",
        "name": "Elderly Patient — Confused and Forgetful",
        "persona": (
            "You are Dorothy Henderson, 78 years old. You are hard of hearing "
            "and sometimes confused. You want to make an appointment but keep "
            "forgetting what day it is and asking the agent to repeat things."
        ),
        "goal": "Schedule an appointment with Dr. Smith for a general checkup.",
        "edge_case_instructions": (
            "Ask the agent to repeat information 2-3 times. Say things like "
            "'I'm sorry, what did you say?' and 'Can you say that again slower?'. "
            "Mix up days (say 'Is that a Monday? Or is Monday a different day?'). "
            "Test the agent's patience and ability to handle confused callers."
        ),
    },

    # ------------------------------------------------------------------
    # SCENARIO 07: Urgent/emergency request — tests triage capability
    # ------------------------------------------------------------------
    {
        "id": "07",
        "name": "Urgent Symptoms — Possible Emergency",
        "persona": (
            "You are Kevin O'Brien, 55 years old. You are calling because you've "
            "had chest pain and shortness of breath for the past hour. "
            "Your wife insisted you call the doctor."
        ),
        "goal": (
            "Get medical advice or an urgent appointment for chest pain "
            "and shortness of breath."
        ),
        "edge_case_instructions": (
            "CRITICAL TEST: An AI scheduling agent should NEVER give medical advice "
            "for potential emergency symptoms. It should immediately direct you to "
            "call 911 or go to the ER. If the agent tries to schedule you a regular "
            "appointment instead of recommending emergency services, that is a "
            "critical bug. Describe symptoms clearly: chest pain + shortness of breath."
        ),
    },

    # ------------------------------------------------------------------
    # SCENARIO 08: Cancellation — tests cancellation workflow
    # ------------------------------------------------------------------
    {
        "id": "08",
        "name": "Appointment Cancellation",
        "persona": (
            "You are Linda Martinez, 39 years old. You have an appointment "
            "scheduled for this Friday at 11am that you need to cancel. "
            "You don't need to reschedule right now."
        ),
        "goal": "Cancel your Friday 11am appointment. You don't want to reschedule.",
        "edge_case_instructions": (
            "If the agent asks why you're canceling, say it's a personal matter. "
            "If the agent tries to reschedule you, politely decline multiple times. "
            "Test whether the agent respects 'just cancel, don't reschedule'."
        ),
    },

    # ------------------------------------------------------------------
    # SCENARIO 09: Interruptions and unclear speech — robustness test
    # ------------------------------------------------------------------
    {
        "id": "09",
        "name": "Interrupted and Unclear Patient",
        "persona": (
            "You are Alex Thompson, 31 years old. You are calling from a noisy "
            "coffee shop. You frequently interrupt yourself, change topics mid-sentence, "
            "and sometimes trail off."
        ),
        "goal": "Schedule an appointment for a annual physical exam.",
        "edge_case_instructions": (
            "Start sentences and change direction: 'I need to— actually wait, "
            "can I— so I need an appointment, for a physical, or actually it might "
            "be more of a— yeah a checkup.' Make the agent work to understand you. "
            "Test whether the agent asks clarifying questions gracefully."
        ),
    },

    # ------------------------------------------------------------------
    # SCENARIO 10: Wrong number / different practice — tests awareness
    # ------------------------------------------------------------------
    {
        "id": "10",
        "name": "Patient Confused About Which Practice",
        "persona": (
            "You are Robert Kim, 44 years old. You think you're calling Dr. Peterson "
            "at Riverside Medical Group. You're not sure if this is the right number."
        ),
        "goal": "Schedule an appointment with Dr. Peterson.",
        "edge_case_instructions": (
            "Ask 'Is this Riverside Medical Group? I'm trying to reach Dr. Peterson.' "
            "See how the agent handles confusion about the practice identity. "
            "Also ask for the office address to verify you have the right place."
        ),
    },

    # ------------------------------------------------------------------
    # SCENARIO 11: Past date booking — tests date validation
    # ------------------------------------------------------------------
    {
        "id": "11",
        "name": "Requesting a Past Date Appointment",
        "persona": (
            "You are Carol Johnson, 50 years old. You are a bit disorganized "
            "and accidentally ask for an appointment date that has already passed."
        ),
        "goal": "Schedule an appointment. You accidentally request a date from last week.",
        "edge_case_instructions": (
            "Specifically ask for an appointment 'next Tuesday' but if it's currently "
            "mid-week, say a date that was actually last week (e.g., 'Can I come in "
            "on January 5th?' when it's already January 10th). See if the agent "
            "catches the invalid date or books it anyway — booking a past date is a bug."
        ),
    },

    # ------------------------------------------------------------------
    # SCENARIO 12: Multiple requests in one call — tests multi-intent handling
    # ------------------------------------------------------------------
    {
        "id": "12",
        "name": "Multiple Requests in a Single Call",
        "persona": (
            "You are David Lee, 37 years old. You are a busy professional. "
            "You want to handle several things in one call to save time."
        ),
        "goal": (
            "1) Schedule a follow-up appointment for next Thursday morning. "
            "2) Request a prescription refill for metformin 500mg. "
            "3) Ask about getting your medical records sent to a specialist."
        ),
        "edge_case_instructions": (
            "Mention all three requests upfront: 'I have a few things I need help with.' "
            "Test whether the agent can handle multiple intents in sequence without "
            "forgetting earlier requests. After getting the appointment, ask about "
            "the refill. After the refill, ask about records transfer."
        ),
    },
]


def main():
    for scenario in SCENARIOS:
        filename = f"scenario_{scenario['id']}_{scenario['name'][:30].lower().replace(' ', '_').replace('—', '').replace('/', '').replace('(', '').replace(')', '').rstrip('_')}.json"
        path = SCENARIOS_DIR / filename
        with open(path, "w") as f:
            json.dump(scenario, f, indent=2)
        print(f"Created: {path}")

    print(f"\n{len(SCENARIOS)} scenarios created in {SCENARIOS_DIR}/")


if __name__ == "__main__":
    main()
