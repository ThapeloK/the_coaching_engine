"""
sop_patterns.py
===============
Structured patterns extracted from the four real SOP sources Mary-Susan supplied.

This is NOT invented content. Every framework, phrase and rule below is traceable
to one of:

  S1  New-staff F&B induction / culture deck (30 slides)
  S2  Front-of-house operations manual, Part 1 (SOPs 1-50 + Service Promise)
  S3  Front-of-house operations manual, Part 2 (SOPs 51-90, appendices, Top 30 Skills)
  S4  Bar SOP (24) + Lunch/Dinner SOP (27), F&B operations manuals, 2018

Brand and property identifiers were already generalised in the extracts.

The generator (generate_corpus.py) uses these patterns so that everything it
produces is shaped like the real material rather than like a language model's
idea of a hotel.
"""

# ---------------------------------------------------------------------------
# The five BARS dimensions, with per-source coverage as assessed in the extracts
# ---------------------------------------------------------------------------

DIMENSIONS = {
    "empathy": {
        "label": "Empathy and Active Listening",
        "coverage": {"S1": "good", "S2": "good", "S3": "thin", "S4": "strongest"},
        "anchor_source": "S4 A.L.O.U.D.",
    },
    "communication": {
        "label": "Guest Communication",
        "coverage": {"S1": "good", "S2": "good", "S3": "strongest", "S4": "good"},
        "anchor_source": "S3 Local Area Information + S4 11 Steps of Service",
    },
    "composure": {
        "label": "Composure and Professionalism",
        "coverage": {"S1": "good", "S2": "good", "S3": "standard-level", "S4": "good"},
        "anchor_source": "S2 Body Language SOP + S4 Professional Ethic SOP02",
    },
    "service_recovery": {
        "label": "Service Recovery",
        "coverage": {"S1": "none", "S2": "good", "S3": "weak", "S4": "strongest"},
        "anchor_source": "S2 nine-step sequence + S4 A.L.O.U.D. and authority boundary",
    },
    "anticipation": {
        "label": "Guest Anticipation",
        "coverage": {"S1": "good", "S2": "thin", "S3": "value-statements", "S4": "concrete-triggers"},
        "anchor_source": "S4 glass-level and busy-acknowledgement triggers",
    },
}

# ---------------------------------------------------------------------------
# Real frameworks found in the sources. These are the citable spines.
# ---------------------------------------------------------------------------

ALOUD = {  # S4, Lunch/Dinner SOP13 - the property's own service recovery framework
    "source": "S4",
    "ref": "lunch_dinner_sop13",
    "name": "A.L.O.U.D.",
    "steps": [
        (1, "A", "Apologies", "Apologise sincerely before commenting further."),
        (2, "L", "Listen without interrupting", "Let the guest finish. Do not interrupt."),
        (3, "O", "Own the problem", "Take ownership rather than deflecting to another department."),
        (4, "U", "Understand the difficulty", "Confirm you understand what the guest actually experienced."),
        (5, "D", "Deal with matter to the guest's satisfaction", "Agree and deliver a resolution."),
    ],
}

COMPLAINT_NINE_STEP = {  # S2, front-of-house complaint handling procedure
    "source": "S2",
    "ref": "foh_complaint_handling",
    "name": "Complaint Handling Procedure",
    "steps": [
        (1, "Listen attentively without interrupting; stop current task, make eye contact."),
        (2, "Stay calm - the guest's frustration is not about you personally."),
        (3, "Apologise sincerely before commenting further, regardless of fault."),
        (4, "Repeat the complaint back, acknowledging the guest's feelings."),
        (5, "Show empathy explicitly."),
        (6, "Uncover what resolution the guest actually expects."),
        (7, "Discuss and agree a solution together."),
        (8, "Take action and follow through to confirm the guest is satisfied."),
        (9, "If escalation is needed: ask the guest to take a seat, brief the manager "
            "with full details, and the manager on duty logs it in the complaint log."),
    ],
}

SERVICE_PROMISE = {  # S2 - ten principles, near BARS-ready as written
    "source": "S2",
    "ref": "service_promise",
    "name": "The Service Promise",
    "principles": [
        "Welcome guest whilst making good eye contact with a genuine smile.",
        "Communicate with guest in order to establish a relationship.",
        "Never say 'No' - offer an appropriate alternative.",
        "Be yourself whilst portraying a professional manner, friendly and willing to help.",
        "Anticipate and delight by understanding guest needs.",
        "Commitment to making it right.",
        "Empathy is key when dealing with issues.",
        "An engaged team radiates a positive environment.",
        "Respect guest privacy and confidentiality at all times.",
        "A positive farewell is an opportunity for another hello.",
    ],
}

ELEVEN_STEPS_TIMINGS = {  # S4, Lunch/Dinner SOP05 - timed service sequence
    "source": "S4",
    "ref": "lunch_dinner_sop05",
    "name": "11 Steps of Service",
    "timings": [
        ("greet_on_approach", "Greet the guest when 5 steps away, eye contact, appropriate phrase."),
        ("drinks_order", "Drinks order taken within 3 minutes."),
        ("food_order", "Food order taken within 2 minutes of readiness."),
        ("satisfaction_check", "Customer satisfaction checked 2 minutes after food delivery."),
        ("payment", "Payment collected within 2 minutes of guest readiness."),
        ("farewell", "Thank guest for coming and invite him/her back."),
    ],
}

# ---------------------------------------------------------------------------
# THE CENTRAL FINDING: authority to make things right is documented for F&B
# and NOT documented for front office. This is a real inconsistency across the
# property's own manuals, not a synthetic contrivance.
# ---------------------------------------------------------------------------

AUTHORITY_BOUNDARY = {
    "f_and_b": {
        "source": "S4",
        "ref": "lunch_dinner_sop13",
        "documented": True,
        "rules": [
            "Staff may resolve a complaint themselves if they feel confident.",
            "Staff may offer a complimentary item (coffee or beverage) at their discretion.",
            "Refunds must be approved by the department manager/supervisor BEFORE "
            "being discussed with the guest.",
            "All complaints are reported to the department manager even when resolved.",
            "Comp items must be posted to a management account and signed for by the manager.",
        ],
    },
    "front_office": {
        "source": "S2/S3",
        "ref": None,
        "documented": False,
        "gap_note": (
            "Neither front-of-house manual states what a front desk staff member may "
            "offer without manager approval. S2 lists 'specific compensation/goodwill "
            "authority' as an open gap; S3 confirms 'still missing: any guidance on "
            "gestures of goodwill, compensation authority'. Front office staff are told "
            "to escalate and log, but never told what they may decide themselves."
        ),
    },
    "bar": {
        "source": "S4",
        "ref": None,
        "documented": False,
        "gap_note": "The Bar SOP set contains no complaint-handling SOP at all.",
    },
}

# ---------------------------------------------------------------------------
# Escalation rules that genuinely appear in the sources
# ---------------------------------------------------------------------------

ESCALATION_RULES = [
    ("S2", "foh_complaint_handling",
     "Escalate to manager: seat the guest, brief the manager, manager logs in complaint log."),
    ("S3", "reception_supervisor_duties",
     "All complaints logged with the General Manager/Duty Manager no matter how minor."),
    ("S3", "incident_reporting",
     "Incident reports reviewed by H&S officer or GM within 72 hours; once signed off by "
     "the GM the report cannot be edited."),
    ("S4", "lunch_dinner_sop13",
     "Inform department manager about all guest complaints even when already resolved."),
]

# ---------------------------------------------------------------------------
# Composure standards - concrete named behaviours, near-anchor quality already
# ---------------------------------------------------------------------------

PROFESSIONAL_ETHIC = {  # S4 SOP02, near-identical in S2 professional ethics SOP
    "source": "S4",
    "ref": "sop02_professional_ethic",
    "prohibited": [
        "Never chew gum while on duty.",
        "Never refer to a guest by their room number.",
        "Do not shout across guests to other employees.",
        "Never argue with another employee in front of a guest.",
        "No mobile phones while on duty.",
    ],
    "required": [
        "Greet guests as you see them - use their name when possible.",
        "Always smile.",
        "Remain standing when dealing with a guest at a desk.",
        "Maintain eye contact and an open posture; keep arms unfolded.",
        "Give the guest your full attention.",
    ],
}

POSITIVE_ALTERNATIVES = {  # S2 + S3 - phrase-level scripted substitutions
    "source": "S2/S3",
    "ref": "positive_alternatives",
    "substitutions": [
        ("no problem", "certainly / absolutely / of course"),
        ("no", "offer an appropriate alternative"),
        ("I don't know", "always give an alternative to the guest"),
        ("I can't tell you",
         "I regret that I do not have that information at hand, please let me get "
         "someone who may assist you"),
    ],
}

ANTICIPATION_TRIGGERS = {  # S4 - the only genuinely observable triggers in any source
    "source": "S4",
    "ref": "managing_your_station",
    "triggers": [
        "Glass one-third full or near empty - offer another round.",
        "Busy and cannot attend immediately - make eye contact and set an expectation.",
        "Check back within 2 minutes of food delivery.",
        "Observe your station and check each table for needs.",
    ],
}

TEST_CALL_RUBRIC = {  # S3 Appendix 1 - a REAL scored behavioural rubric already in use
    "source": "S3",
    "ref": "appendix_01_test_call_sheet",
    "categories": ["Greeting", "Probing", "Quote", "Upselling", "Close", "Thanks",
                   "Employee & Tone"],
    "sample_criteria": [
        "Pace/tone of the employee suitable to guest requirements",
        "Was the employee clear and easy to understand?",
        "Did the employee sound confident and knowledgeable?",
        "Was the employee polite, cordial and helpful?",
        "Overall friendliness of the employee",
    ],
    "significance": (
        "Evidence that hotel groups already perform scored behavioural assessment of "
        "real interactions - episodically, by phone, against a written rubric. Our "
        "approach is not a new intrusion; it is an existing practice done systematically."
    ),
}

# ---------------------------------------------------------------------------
# Situation taxonomy, derived from what the SOPs actually cover
# ---------------------------------------------------------------------------

SITUATION_TYPES = {
    "service_delay":              {"depts": ["f_and_b"],                 "sop": "S4"},
    "order_error":                {"depts": ["f_and_b"],                 "sop": "S4"},
    "service_delay_and_order_error": {"depts": ["f_and_b"],              "sop": "S4"},
    "room_not_ready":             {"depts": ["front_office"],            "sop": None},
    "billing_dispute":            {"depts": ["front_office"],            "sop": "S2"},
    "noise_complaint":            {"depts": ["front_office"],            "sop": "S2"},
    "booking_error":              {"depts": ["front_office"],            "sop": "S2"},
    "special_request_failure":    {"depts": ["front_office", "f_and_b"], "sop": "S2"},
    "system_down":                {"depts": ["front_office"],            "sop": "S3"},
    "local_area_enquiry":         {"depts": ["front_office"],            "sop": "S3"},
    "allergen_query":             {"depts": ["f_and_b"],                 "sop": None},
    "other":                      {"depts": ["front_office", "f_and_b"], "sop": None},
}

# Gaps confirmed across all four extracts - these drive the abstain-path test cases
CONFIRMED_CORPUS_GAPS = [
    ("de_escalation_angry_guest",
     "No source covers tone or pacing for an already-shouting guest. Every complaint "
     "procedure assumes a guest calmly reporting an issue."),
    ("front_office_compensation_authority",
     "No front-of-house source states what staff may offer without approval."),
    ("allergen_behavioural_protocol",
     "Mentioned in passing ('know the allergen folder') but no procedure in any source."),
    ("bar_complaint_handling",
     "The Bar SOP set has no complaint-handling SOP."),
    ("empathy_technique",
     "S3 states the value ('special attention', 'warmly welcomed') without any technique. "
     "Only S4's A.L.O.U.D. gives a sequenced instruction."),
    ("anticipation_vip_repeat_guest",
     "No source covers recognising repeat/VIP guests or non-verbal distress cues."),
]
