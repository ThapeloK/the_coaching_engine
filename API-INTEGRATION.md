# Connecting the frontend to the backend

For Ziyi, and anyone else working on `web/`.

The short version: the frontend is already connected and working. Nothing here
asks you to change how you build screens. This is a reference for when you add
one.

---

## The two settings that switch it on

In Vercel, or in `web/.env.local` when you are working locally:

```
NEXT_PUBLIC_USE_REAL_API=true
NEXT_PUBLIC_API_BASE_URL=https://coaching-engine-api-w5wg47f7gq-ew.a.run.app/api/v1
```

Locally, point it at `http://127.0.0.1:8000/api/v1` instead.

Set `NEXT_PUBLIC_USE_REAL_API=false` and everything falls back to the mock
store in `src/lib/mock/db.ts`. That still works, so you can build screens
offline without the backend running.

Two things worth knowing:

- These are baked in when the site builds, not read when it runs. If you
  change them in the Vercel dashboard, nothing happens until you redeploy.
- Every page that shows data has `export const dynamic = "force-dynamic"`.
  Without it Next renders the page once at build time and then serves that
  same HTML forever, which means the manager sees whatever the database held
  on the day we deployed. Add that line to any new page that reads data.

---

## How to call it

Use `http` from `src/lib/api/client.ts`. It handles the base URL, who the
caller is, and the errors.

```ts
import { http } from "@/lib/api/client";

const queue = await http.get<Recommendation[]>("/recommendations");
const result = await http.post<VerifyResponse>(
  `/recommendations/${id}/verify`,
  { verdict: "confirmed", dimension_verdicts: [], reason: "", seconds_to_decide: 30 }
);
```

The client already adds:

- `X-CE-Actor`, which is who the request is from
- `Idempotency-Key` on writes, so a double tap on hotel wifi cannot create two
  of something
- `cache: "no-store"`, because this is live data about a decision someone is
  about to make

---

## Who the caller is

Every request carries an `X-CE-Actor` header. The backend uses it to decide
what that person is allowed to see, and the database enforces it.

Right now the client works it out from the route: anything under `/staff` is
Diego, everything else is Marta. You can override it in the browser console
for testing:

```js
localStorage.setItem("ce_actor", "Fiona");
```

In a real deployment this would come from a login. The backend does not care
which, because it reads the same three facts either way.

The people you can act as:

| Name  | Role      | What they see                                     |
|-------|-----------|---------------------------------------------------|
| Diego | staff     | only their own record                             |
| Marta | manager   | her team, once she has observed them              |
| Fiona | ld_admin  | cohort patterns, no individual practice scores    |

---

## The part that will surprise you

**A manager cannot read someone's practice scores until she has logged her own
observation of them.**

This is not a bug and please do not work around it. It is the rule the whole
product rests on. If the manager sees the AI score first, her own observation
is anchored to it, the two measurements stop being independent, and the gap
between them stops meaning anything.

So `GET /staff/{id}/scores?source=practice` can return **409** with a message
explaining why. Show the message. The screen being empty is the honest answer,
not a failure to handle.

The same rule is enforced in the database, so it holds even if the frontend
forgets.

---

## Endpoints

Everything is under `/api/v1`.

### Manager

| Method | Path | What it does |
|---|---|---|
| GET | `/staff` | the team |
| GET | `/staff/{id}/gap` | the transfer gap for one person |
| GET | `/staff/{id}/scores?source=practice\|floor` | one evidence stream. 409 on practice before observing |
| GET | `/observations` | observations this person may see |
| POST | `/observations` | log one. This is what unlocks the practice scores |
| GET | `/recommendations` | the verify queue |
| GET | `/recommendations/{id}` | one, with its citations |
| POST | `/recommendations/{id}/verify` | confirm, correct or reject. Second call returns 409 |
| GET | `/calibration` | how often the AI agrees with managers |
| GET | `/insights/team` | cohort patterns, plus a count of what was hidden |
| POST | `/staff/{id}/coach` | run the agent now. Used by the demo |
| POST | `/reports/weekly` | hand the week to Manus for a written brief |

### Staff

| Method | Path | What it does |
|---|---|---|
| GET | `/scenarios` | practice scenarios for this person |
| POST | `/scenarios/{id}/attempts` | start one. Returns the opening guest line |
| POST | `/attempts/{id}/turns` | send what the staff member said, get the guest reply |
| POST | `/attempts/{id}/complete` | score the whole conversation |
| GET | `/attempts/{id}` | read one back |
| POST | `/debriefs` | a typed debrief |
| POST | `/debriefs/audio` | a spoken one, as a file upload |
| GET | `/debriefs/{id}` | the transcript, what was extracted, and the standard it matched |
| GET | `/voice/{id}.mp3` | the guest's voice for one line |

### Demo and health

| Method | Path | What it does |
|---|---|---|
| GET | `/health` | database, providers, search index, spend |
| POST | `/demo/trace/{id}` | run the agent and return every step |
| GET | `/demo/gate` | try to get fabricated claims past the cite gate |
| GET | `/demo/rls` | one query, three people, three different answers |

---

## Things that are easy to get wrong

**Staff ids.** You can pass a real database id, or `staff-001`, or a name like
`Diego`. All three work. The backend sorts it out, so your existing mock ids
did not need changing.

**The queue gives you everything.** `GET /recommendations` returns whole
objects with citations and calibration attached, not summaries. You do not
need a second call per card.

**Guest audio is optional.** A guest turn may come back with an `audio_id`.
If it does, play `/voice/{audio_id}.mp3`. If it does not, show the text. The
conversation is designed to work without sound, so never block on it.

**Feedback to staff never shows a number.** The API returns words, not scores.
A frontline staff member reads "2 out of 5" as a verdict on them. Please keep
it that way in any new screen.

**Errors come back as JSON** with `title` and `detail`. `ContractError` in the
client already carries them, so show `detail` rather than a generic message.

---

## If something looks wrong

```
https://coaching-engine-api-w5wg47f7gq-ew.a.run.app/health
```

That tells you whether the database is up, which AI providers are working, and
whether the search index is ready. If `search_index.ready` is false, the agent
will refuse to give advice on anybody and the reason will sound sensible. It
is not sensible, it is an empty index.

One quirk of the free hosting: the API sleeps after fifteen minutes of nothing
and takes about a minute to wake up. The first request after a quiet period is
slow. Open the health URL before a demo.

Ask me if anything here does not match what you see. The doc is written from
the code, but the code moves.
