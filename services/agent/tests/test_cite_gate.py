from coaching_engine.cite_gate import (
    Claim, EvidenceItem, run_gate, span_supported,
)

DIEGO = "staff-001"
NIAMH = "staff-002"

TURN = EvidenceItem(
    ref="attempt:8a4e:turn:5", kind="attempt_turn", staff_id=DIEGO,
    content="I'm so sorry your starter never arrived after that wait - let me "
            "sort that first and then we'll make it right.")

OBS = EvidenceItem(
    ref="obs:o55c:what_happened", kind="observation", staff_id=DIEGO,
    content="Froze and escalated to me immediately without attempting recovery.")

SOP = EvidenceItem(
    ref="sop:service_recovery_v3:step_3", kind="sop_chunk", staff_id=None,
    content="Acknowledge the specific inconvenience the guest experienced "
            "before offering any form of compensation.")

OTHER_STAFF_OBS = EvidenceItem(
    ref="obs:o99z:what_happened", kind="observation", staff_id=NIAMH,
    content="Handled a billing dispute calmly.")

BUNDLE = [TURN, OBS, SOP]


def grounded_claims():
    return [
        Claim("Scored 4/5 on service recovery in practice",
              ("attempt:8a4e:turn:5",)),
        Claim("Escalated without attempting recovery on the floor",
              ("obs:o55c:what_happened",)),
        Claim("The standard puts acknowledgement before compensation",
              ("sop:service_recovery_v3:step_3",),
              quoted_span="Acknowledge the specific inconvenience the guest "
                          "experienced before offering any form of compensation."),
    ]


# ------------------------------------------------------------- happy path

def test_fully_grounded_recommendation_passes():
    result = run_gate(grounded_claims(), BUNDLE, DIEGO)
    assert result.passed
    assert result.failures == []


# ------------------------------------------------- 1. existence (the big one)

def test_fabricated_sop_clause_is_caught():
    """The failure Mary-Susan named directly: the agent cites a standard clause
    that does not exist. This check is the highest-value line in the codebase."""
    claims = grounded_claims() + [
        Claim("The policy sets a EUR 50 discretionary limit",
              ("sop:complaint_policy:section_9",))]        # invented

    result = run_gate(claims, BUNDLE, DIEGO)
    assert not result.passed
    assert any(f.reason == "source_not_found" for f in result.failures)


def test_claim_with_no_citation_at_all_is_caught():
    claims = grounded_claims() + [Claim("She seems disengaged lately", ())]
    result = run_gate(claims, BUNDLE, DIEGO)
    assert any(f.reason == "source_not_found" for f in result.failures)


# ------------------------------------------------------------- 2. support

def test_paraphrased_sop_quote_is_caught():
    """A real section cited, but paraphrased into something it does not say.
    Subtler than a fabricated reference, and more dangerous."""
    claims = [
        Claim("practice", ("attempt:8a4e:turn:5",)),
        Claim("floor", ("obs:o55c:what_happened",)),
        Claim("The standard says always offer a voucher first",
              ("sop:service_recovery_v3:step_3",),
              quoted_span="Always offer a voucher before discussing the issue."),
    ]
    result = run_gate(claims, BUNDLE, DIEGO)
    assert any(f.reason == "span_not_supported" for f in result.failures)


def test_near_verbatim_quote_is_accepted():
    """Whitespace and casing must not trip the gate."""
    assert span_supported(
        "acknowledge the specific inconvenience the guest experienced",
        SOP.content)


def test_empty_quote_is_not_checked():
    assert span_supported("", SOP.content) is True


# ---------------------------------------------------------- 3. sufficiency

def test_practice_only_is_not_a_transfer_gap_recommendation():
    """Without a floor citation this is roleplay feedback, which is exactly the
    product we are differentiating against. A competitor can cite the practice
    transcript; only we can be required to cite an observation alongside it."""
    claims = [Claim("Scored well in practice", ("attempt:8a4e:turn:5",))]
    result = run_gate(claims, BUNDLE, DIEGO)

    assert not result.passed
    assert any(f.reason == "not_a_transfer_gap_recommendation"
               for f in result.failures)


def test_floor_only_is_also_insufficient():
    claims = [Claim("Escalated without recovering", ("obs:o55c:what_happened",))]
    result = run_gate(claims, BUNDLE, DIEGO)
    assert any(f.reason == "not_a_transfer_gap_recommendation"
               for f in result.failures)


# --------------------------------------------------------------- 4. scope

def test_another_staff_members_evidence_is_rejected():
    """A privacy failure, not merely a quality one."""
    claims = grounded_claims() + [
        Claim("Others handle this well", ("obs:o99z:what_happened",))]

    result = run_gate(claims, BUNDLE + [OTHER_STAFF_OBS], DIEGO)
    assert any(f.reason == "cross_staff_reference" for f in result.failures)


# ------------------------------------------------------- repair and abstain

def test_repair_counter_increments_on_failure():
    result = run_gate([Claim("ungrounded", ())], BUNDLE, DIEGO, repair_attempts=0)
    assert result.repair_attempts == 1
    assert not result.should_abstain


def test_abstains_after_two_failed_repairs():
    result = run_gate([Claim("ungrounded", ())], BUNDLE, DIEGO, repair_attempts=1)
    assert result.repair_attempts == 2
    assert result.should_abstain


def test_abstain_reason_says_what_is_missing():
    """'Insufficient evidence' alone is useless. The manager needs to know what
    would help, because that drives the behaviour we want."""
    result = run_gate([Claim("practice only", ("attempt:8a4e:turn:5",))],
                      BUNDLE, DIEGO, repair_attempts=1)
    reason = result.abstain_reason()

    assert result.should_abstain
    assert "floor-observation" in reason


def test_passing_gate_does_not_increment_repairs():
    result = run_gate(grounded_claims(), BUNDLE, DIEGO, repair_attempts=1)
    assert result.passed
    assert result.repair_attempts == 1


# --- span support against long sources -------------------------------------
#
# These pin the bug the window fix repaired. The gate compared a short quote
# against the WHOLE chunk, and ratio() falls with length difference, so a
# verbatim-bar-one-character quote from a realistic SOP section scored near
# zero and abstained. Both directions matter: near-verbatim must pass, and
# paraphrase must still fail, or the fix would have bought recall with
# precision.

LONG_SOP = (
    "Nine Step Complaint Handling Procedure. Step 1: Listen to the guest "
    "without interrupting and allow them to finish. Step 2: Apologise "
    "sincerely on behalf of the property, regardless of fault. Step 3: "
    "Acknowledge the specific inconvenience the guest has described, in their "
    "own words. Step 4: Ask what outcome would resolve the matter for them. "
    "Step 5: Escalate to the Duty Manager where the resolution exceeds your "
    "authority. Step 6: Record the complaint in the daily log before the end "
    "of shift. Step 7: Follow up with the guest before departure. Step 8: "
    "Brief the incoming shift. Step 9: Review recurring complaints weekly."
)


def test_near_verbatim_quote_from_a_long_section_is_supported():
    quoted = "Acknowledge the specific inconvenience the guest has described"
    assert span_supported(quoted, LONG_SOP)


def test_verbatim_quote_with_punctuation_drift_is_supported():
    quoted = "Escalate to the Duty Manager, where the resolution exceeds your authority"
    assert span_supported(quoted, LONG_SOP)


def test_paraphrase_of_a_long_section_is_still_rejected():
    # Same topic, same vocabulary, but the section never says it. This is the
    # failure the gate exists to catch.
    quoted = "Staff may offer a complimentary night to any dissatisfied guest"
    assert not span_supported(quoted, LONG_SOP)


def test_plausible_invention_about_authority_is_rejected():
    quoted = "Front office staff may authorise refunds up to two hundred euro"
    assert not span_supported(quoted, LONG_SOP)


# --- a standard cited without a quote ---------------------------------------
#
# Found by the red team suite (evals/redteam), not by us. span_supported()
# returns True for an empty quote, on the reasonable-sounding grounds that
# there is nothing to verify. Combined with a real reference that produced the
# exact failure the gate exists to prevent: an invented policy, asserted
# confidently, with a genuine-looking citation beside it and no way for a
# manager to tell it apart from a real one.
#
# Citing a standard is a claim ABOUT that standard, so it must carry the words.

def _person_claims():
    return [
        Claim(text="They produced the behaviour in practice.",
              citation_refs=(TURN.ref,), quoted_span=None),
        Claim(text="They did not produce it on the floor.",
              citation_refs=(OBS.ref,), quoted_span=None),
    ]


def test_standard_cited_with_empty_quote_is_rejected():
    claims = [Claim(text="The standard supports acting immediately.",
                    citation_refs=(SOP.ref,), quoted_span="")] + _person_claims()
    result = run_gate(claims, BUNDLE, DIEGO, repair_attempts=2)
    assert not result.passed
    assert any(f.reason == "standard_cited_without_quote" for f in result.failures)


def test_standard_cited_with_whitespace_quote_is_rejected():
    claims = [Claim(text="The standard allows a refund.",
                    citation_refs=(SOP.ref,),
                    quoted_span="      ")] + _person_claims()
    assert not run_gate(claims, BUNDLE, DIEGO, repair_attempts=2).passed


def test_per_person_evidence_still_needs_no_quote():
    # The rule is deliberately narrow. "They froze", cited to an observation,
    # is supported by that observation existing; demanding a quote there would
    # push the model to invent one.
    assert run_gate(_person_claims(), BUNDLE, DIEGO, repair_attempts=0).passed
