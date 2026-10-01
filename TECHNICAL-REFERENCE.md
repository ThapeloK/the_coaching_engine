# The Coaching Engine: complete technical reference

Everything that was built, why each decision was taken, and where it lives.
Written 13 Sept 2026 against the deployed system.

If you read one section, read **2. The one idea**. Everything else is
consequences of it.

---

## 1. What it is in one paragraph

Hotels spend money on training and have no way of knowing whether it changed
anything on the floor. This measures that. Staff practise scored scenarios and
give short spoken debriefs after real shifts. Managers log twenty second
observations of what they actually saw. The system holds those as two
independent evidence streams, computes the distance between them per skill, and
produces a cited coaching recommendation that no human sees until a manager
verifies it. When the two streams disagree in a particular direction, it says
the opposite of what every training platform says: do not send this person on a
course.

---

## 2. The one idea: the transfer gap

Every other product measures **completion**. This measures **transfer**.

Two numbers per person per skill:

| Stream | Where it comes from | What it proves |
|---|---|---|
| **Practice** | AI-scored roleplay scenarios | what they *can* do |
| **Floor** | a manager's own observation | what they *did* do |

The gap between them is the product. Four quadrants:

| Quadrant | Practice | Floor | What it means | What to do |
|---|---|---|---|---|
| **COMPETENT** | high | high | it transferred | nothing |
| **SKILL GAP** | low | low | they cannot do it yet | train them |
| **BLOCKED** | **high** | **low** | they can do it and did not | **do NOT train.** Something stopped them: authority, staffing, process |
| **RECALIBRATE** | low | high | our scoring is wrong, or they compensate with charm | fix the rubric, not the person |

**BLOCKED is the commercially important one.** It is the case where the
industry's default action, buy more training, is actively wrong and wastes
money. A product willing to say "do not buy training" is making a claim no
competitor selling training can make.

Diego in the demo: practice **4.79**, floor **1.62**, gap **3.17**, BLOCKED. He
knows how to recover a service failure. Nobody has told him what he is allowed
to offer a guest without asking permission. That is an authority gap and it is
not his to fix.

Code: `services/agent/coaching_engine/transfer_gap.py`.

### Recency weighting

An unweighted mean lets a strong attempt from eleven weeks ago mask a decline,
so scores decay with a **28 day half life**. Four weeks is chosen to match the
learning transfer literature: skills decay without ongoing support, so a month
old score carries about half the weight of a fresh one.

A score dated after today raises rather than being silently clamped, because
you cannot weight the age of something that has not happened.

---

## 3. Architecture

```
Next.js 16 (Vercel)                 FastAPI (Cloud Run, europe-west1)
  manager console                     30 endpoints
  staff PWA                           agent graph
  glass box                           cite gate
        |                                   |
        |  HTTPS, X-CE-Actor header         |
        +-----------------------------------+
                                            |
                            Neon Postgres 18.6 (Frankfurt)
                            22 tables, pgvector(768)
                            ROW LEVEL SECURITY on every table
```

**The API holds no authorisation logic.** Identity is resolved from a header,
pushed into the Postgres session, and every policy in `db/policies.sql` applies
from there. If a manager may not see a practice score, the database returns no
row. Authorisation implemented twice is authorisation implemented wrong.

### Size

| | |
|---|---|
| API | 5,112 lines Python |
| Agent (pure, no I/O) | 691 lines Python |
| Web | 15,846 lines TypeScript |
| Database | 394 lines schema, 184 lines policies |
| Endpoints | 30 |
| Tables | 22 |

### Tests

| Suite | Count | Needs |
|---|---|---|
| `services/agent` | **75** | nothing. No keys, no network, no database |
| `db/test_rls.py` | **10** | database. Negative tests: each tries to read something it must not |
| `tests/test_voice_observation.py` | **11** offline, 16 with `--base` | nothing offline |
| `tests/test_e2e.py` | 15 | a running API, spends about 2 cents |

96 tests run with no credentials at all. That is deliberate: the reasoning is
pure functions, so it can be tested exhaustively and cheaply.

---

## 4. The nine step flow

1. **Staff practises** a scenario. A model plays the guest; four turns.
2. **Scoring** against a BARS rubric, 1 to 5, with a quoted evidence span.
3. **Staff debriefs** after a real shift, by voice or text, in any language.
4. **Manager observes** on the floor: twenty seconds, one person, what they saw.
5. **Transfer gap** computed per dimension. Arithmetic, no model.
6. **Retrieval** over the hotel's own SOPs, hybrid vector plus full text.
7. **The agent drafts** a recommendation, constrained by the quadrant.
8. **The cite gate** checks it. Fails, it abstains rather than ships.
9. **A human verifies.** Nothing routes anywhere until a manager confirms,
   corrects or rejects. No timeout, no auto-approve.

---

## 5. The agent, and what it is not allowed to do

The glass box (`/glassbox`) runs this live and labels every step with who made
it. A typical run: **6 or 7 decisions by code, 1 by the model.**

| Step | Who | What |
|---|---|---|
| Read both evidence streams | database | under row level security |
| Compute the transfer gap | **code** | arithmetic, no model called yet |
| Select the focus dimension | **code** | widest absolute gap, deterministic |
| Hybrid search the SOPs | database | vector + full text, fused by RRF, cosine floor 0.30 |
| **Constrain the schema** | **code** | see below |
| Classify the cause | model | from the options code left it |
| Draft the recommendation | model | must cite |
| Cite gate | **code** | four checks, any failure abstains |
| Route the escalation | **code** | rule table, not judgement |

### The constrain step is the one to understand

Before the model is asked anything, code removes options from the JSON schema
it is allowed to return. If the quadrant is BLOCKED, the skill is *proven
present*, so `behavioural` is deleted from the enum of possible causes.

The model cannot return it. Not "is told not to". Cannot. Prompt injection,
jailbreak, a bad day: the token is not in the grammar it is decoding against.

This is the answer to "what if the model ignores your prompt".

### The cite gate, four checks

`services/agent/coaching_engine/cite_gate.py`.

1. **Source exists**, the cited id is in the evidence bundle
2. **Span is genuine**, the quoted text really appears in that chunk
3. **Both streams**, at least one practice citation AND one floor citation
4. **No cross-staff evidence**, nothing about a different person

Any failure and the whole recommendation **abstains**. It does not degrade, it
does not ship a weaker version. Abstention is a first class outcome and appears
in the interface as one.

Exact substring is too brittle for real text, so check 2 falls back to a
similarity ratio against the best matching window, with `autojunk=False`
because SequenceMatcher's default heuristic treats most of the alphabet as junk
on long character sequences and silently scored real quotes as noise.

### Escalation routing

A rule table, not a model. `routing.py`. When a pattern spans at least **five**
staff it stops being a coaching matter and becomes an operations matter, and it
routes to Operations or L&D instead of to the individual. Individual coaching
is suppressed when the root cause is process or policy: telling five people to
try harder at a broken process is how you lose five people.

---

## 6. Row level security

`db/policies.sql`, 184 lines. Every table has RLS enabled, `AS RESTRICTIVE`,
and `FORCE ROW LEVEL SECURITY` so even the table owner obeys it. The API
connects as `ce_app`, which owns nothing.

Identity arrives per request and is pushed into the session:

```sql
SELECT set_config('app.property_id', %s, true);   -- true = transaction-local
SELECT set_config('app.staff_id',    %s, true);
SELECT set_config('app.role',        %s, true);
```

Transaction-local matters more than it looks: a leaked identity on a pooled
connection is exactly how a multi-tenant system shows one customer another's
data.

### The sequencing rule, BR-01

The policy that makes this evidence rather than opinion:

```sql
CREATE POLICY score_manager_practice ON score FOR SELECT
    USING (property_id = app_property()
       AND app_role() = 'manager'
       AND source = 'practice'
       AND EXISTS (SELECT 1 FROM team_assignment t
                    WHERE t.manager_id = app_staff() AND t.staff_id = score.staff_id)
       AND has_observed(app_staff(), score.staff_id));
```

A manager cannot read a staff member's practice scores until they have logged
their own observation of that person. The API returns **409**, and the message
says so plainly, because the manager has done nothing wrong: they simply have
to go first.

Why: if you read the machine's opinion before forming your own, you will agree
with it. Then you have two opinions and no evidence, and the whole comparison
is worthless.

### k-anonymity

Team patterns appear only when **at least five** staff share them. Below the
threshold a "pattern" is a person, and an aggregate that identifies an
individual is not an aggregate.

L&D see cohorts and floor scores; they never see an individual's practice
transcripts.

---

## 7. Data model, the parts that matter

22 tables. The ones carrying the idea:

- **`score`**, every measurement, `source` is `practice` or `floor`. The two
  streams are the same table with a discriminator, so the gap is one query.
- **`observation`** + **`observation_rating`**, a manager's floor capture.
  A dimension they did not witness stays **null** and produces no score row.
  Writing a midpoint would quietly compress the gap.
- **`recommendation`** + **`recommendation_citation`**, the draft and its
  evidence. Citations are rows, not prose, so the gate can check them.
- **`verification`**, who confirmed what, and when.
- **`audit_event`**, append-only. INSERT allowed, UPDATE and DELETE denied by
  policy. Article 12 of the EU AI Act wants to know what was recommended, on
  whom, and who decided.
- **`sop_chunk`**, the hotel's own manuals, `vector(768)` plus a generated
  `tsvector`, so one table serves both halves of hybrid search.

---

## 8. Providers, and why each

| Task | Provider | Why |
|---|---|---|
| Guest turn in practice | Groq `qwen3.8-27b` | ~700ms vs ~1400ms. The only task a human waits on live |
| Scoring | OpenAI `gpt-4o-mini` | structured output, cheap, deterministic at temp 0 |
| Coaching draft | OpenAI `gpt-4o` | the one place quality of writing shows |
| Cause classification | **Vertex AI** `gemini-2.5-flash-lite` | one call, strict enum already constrained by code |
| Transcription | Groq `whisper-large-v3-turbo` | language detected, not assumed |
| Spanish translation | Groq `llama-3.3-70b-versatile` | what the Glorvox thesis deployed after comparing 14 models |
| Guest voice | ElevenLabs | reliable, handles dialogue. **Nearly out of free credits** |
| Weekly brief | Manus | asynchronous agent work, minutes not seconds |
| Tracing | Langfuse | every run, cost and failure visible |

Every task has a **fallback** except where none is needed. A provider outage
during a five minute pitch is not hypothetical: Groq retired a pinned model id
under us once already.

**Spend control:** `CE_DAILY_USD_LIMIT`, default $5, checked *before* each call,
not after. A ceiling that notices it has been exceeded is not a ceiling. One
agent run costs about half a cent.

---

## 9. Regional Spanish, from the thesis

A hotel floor in Ireland is not an English speaking floor, and Spanish is not
one Spanish. `guagua` is a bus in the Caribbean and a baby in the Andes.

This matters because a debrief is **evidence**: it is scored, it becomes half a
transfer gap, and it can send somebody on training. Misreading one means
assessing a person on a sentence they did not say, and it only ever happens to
the people not working in their first language.

Two failures, both closed:

1. Transcription pinned `language="en"`, so Spanish came back as confident
   nonsense and was then scored. Whisper now detects. (It reports `"spanish"`,
   not `"es"`, which is worth knowing.)
2. Regional vocabulary is now retrieved from a curated lexicon and its glosses
   put into the translation prompt.

Measured, from *Context-Aware Real-Time Speech Translation Using LLMs*
(N. Alvares, MSc AI, NCI, 2026):

| | regionally marked term survives translation |
|---|---|
| without retrieval | 31.2% |
| with retrieval | **46.5%** |

n=157, exact McNemar, p=8.05e-07. Replicated 40.5% → **70.3%** (n=121,
p=2.91e-11).

116 lexicon entries across 21 countries. **No new service, no model to host:**
the whole claim of the method is that the knowledge goes in the prompt.

The staff member sees their own sentence, the English their manager reads, and
every term looked up, with ambiguous ones flagged.

Code: `services/api/app/dialect/`.

---

## 10. Governance

**This is high risk AI under EU AI Act Annex III 4(b)**: systems used to
evaluate performance and behaviour of people in a work relationship. We say so
ourselves rather than waiting to be told.

### What we refused to build

- **Annex III 4(c), live guest monitoring and emotion inference.** Not built.
- **Tone analysis of staff voice.** Proposed in a mentor session and declined.
  Inferring emotion from a worker's voice at work is prohibited outright by
  **Article 5(1)(f)**, not merely high risk.
- **Audio retention.** Recordings are transcribed and dropped in the same call.
  No voiceprint, no speaker identification. There is no biometric data in this
  system to leak.

### What we built instead

- Human verification before anything reaches a staff member
- An append-only audit trail that cannot be updated or deleted
- Abstention as a first class outcome
- k-anonymity on every aggregate
- A glass box page that lets a sceptic check the three hard claims live

**The distinction to state carefully:** humans wrote the rubric, the dimensions
and the SOPs. The AI reads them and analyses against them. A human verifies
before anything reaches a person. If that line blurs, the governance story
blurs with it.

---

## 11. Deployment

| Piece | Where |
|---|---|
| Frontend | Vercel, auto-deploys from `main` |
| API | **Google Cloud Run**, europe-west1, `min-instances 1` |
| Database | Neon Postgres 18.6, Frankfurt |
| Tracing | Langfuse Cloud |

**Frontend and backend deploy separately.** Vercel picks up a push to `main` on
its own; Cloud Run does not. Anything touching `services/api/` needs
`python scripts/deploy_cloudrun.py` run by hand.

### Why Cloud Run and not Render

Measured, same endpoint, three consecutive calls:

```
Cloud Run   0.40s   0.44s   0.45s
Render     14.81s   0.53s   0.53s
```

That first Render number is the free tier waking from sleep. It is what a judge
would have watched.

Render is still running as a rollback: put its URL back in the one Vercel
variable and redeploy.

### Deployment gotchas already paid for

- `NEXT_PUBLIC_*` is inlined at **build** time. A Vercel build without it ships
  a site whose server pages work and whose browser calls go to Vercel itself.
- A `NEXT_PUBLIC_*` variable must be type **Config**, not Secret. A saved
  Secret cannot be converted; delete and recreate.
- Redeploy **without build cache** after changing one.
- Roles granted to a **person** do not apply to a **service account**.
- Artifact Registry Writer can push into a repository and cannot create one.
- `.env` on a laptop points at localhost. Shipping that to Cloud Run produces a
  service that starts, serves `/health`, and cannot reach a database.

---

## 12. What is not real, stated plainly

- **All staff are synthetic.** Performance data is personal data; there is no
  hotel partner and no data agreement, so using real people would be
  indefensible for a team pitching governance. This is a choice, not a gap.
- **The SOPs are real**, from a working hotel, used with permission. The
  situations around them are invented.
- **No live guests.** Deliberately out of scope.
- **The evaluation labels are not trustworthy yet.** The golden set has 45
  items, every `ground_truth_scores` value is null, and 40 of 45 point at just
  2 of 62 SOP chunks. **No accuracy number can be quoted.**
- **Authentication is demo grade.** Identity comes from a header. What happens
  next, pushing it into the database session so RLS applies, is production
  grade and identical either way.

---

## 13. Where things live

```
services/api/app/        FastAPI. main.py is 30 endpoints
  agent.py               the graph
  providers.py           every model call, routing, fallbacks, spend
  practice.py            scenarios, attempts, debriefs
  voice_observation.py   spoken manager observations
  dialect/               regional Spanish, ported from the thesis
  queries.py             all SQL
  demo.py                the glass box endpoints
services/agent/coaching_engine/
  transfer_gap.py        quadrants, recency weighting
  cite_gate.py           four checks
  calibration.py         Wilson interval, weighted kappa
  routing.py             escalation rules
db/schema.sql            22 tables
db/policies.sql          row level security
web/src/                 Next.js 16 App Router
scripts/deploy_cloudrun.py
```

Docs: `README.md` (the tour), `PROGRESS.md` (plain language, for the team),
The pitch material lives outside this repository.
