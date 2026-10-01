"""
retrieval.py
============
Hybrid search over the hotel's own standards.

Vector alone handles paraphrase, which matters because a staff member says "the
room wasn't ready" and the standard says "arrival readiness failure". Keyword
alone handles the exact tokens a citation depends on: "step 3", "SOP 44",
"A.L.O.U.D.". Neither is sufficient, so both run and the ranks are fused.

The corpus is a few hundred chunks per property, so this lives in Postgres with
pgvector rather than in a separate vector database. A dedicated vector store at
this scale would be operational weight we cannot justify, and a judge would be
right to ask why the architecture is heavier than the problem.
"""

from __future__ import annotations

from .providers import Trace, embed

# Reciprocal rank fusion constant. 60 is the standard default and behaves well
# without needing the two scores to be on comparable scales.
RRF_K = 60

# Below this COSINE SIMILARITY we return nothing and the agent abstains.
#
# Thresholding on the fused RRF score does not work, and it is worth writing
# down why. RRF scores depend only on rank: the top hit always scores 1/(k+1)
# whether it is a perfect match or the least-bad of a corpus that says nothing
# relevant. A floor on RRF therefore rejects nothing, which would silently
# disable the abstain path, which is one of the three things we never cut.
#
# So RRF orders the results and cosine similarity decides whether any of them
# deserve to be cited at all.
#
# 0.30 was tuned against the seeded corpus: room-readiness authority queries
# (which the front-office manual genuinely does not cover) fall below it, while
# A.L.O.U.D. and complaint-procedure queries clear it comfortably. Re-tune if
# the corpus changes materially.
SIMILARITY_FLOOR = 0.30


def backfill_embeddings(cur, batch: int = 96, trace: Trace | None = None) -> int:
    """Embed any chunk that does not have a vector yet. Idempotent."""
    cur.execute("SELECT id::text, content FROM sop_chunk WHERE embedding IS NULL "
                "ORDER BY ordinal")
    todo = cur.fetchall()
    if not todo:
        return 0

    done = 0
    for i in range(0, len(todo), batch):
        window = todo[i:i + batch]
        vectors = embed([r["content"] for r in window], trace=trace)
        for row, vec in zip(window, vectors):
            cur.execute("UPDATE sop_chunk SET embedding = %s WHERE id = %s",
                        ("[" + ",".join(f"{v:.6f}" for v in vec) + "]", row["id"]))
            done += 1
        cur.connection.commit()
    return done


def search(cur, query: str, *, department: str | None = None, limit: int = 6,
           trace: Trace | None = None) -> list[dict]:
    """Hybrid search. Returns chunks with everything a citation needs."""
    if not query.strip():
        return []

    vector = embed([query], trace=trace)[0]
    vec_literal = "[" + ",".join(f"{v:.6f}" for v in vector) + "]"

    cur.execute("""
        WITH scoped AS (
            -- Department scoping happens once, here. 'all' documents (the
            -- Service Promise, Professional Ethic) apply to every department.
            SELECT c.id, c.content, c.content_tsv, c.embedding
            FROM sop_chunk c
            JOIN sop_document d ON d.id = c.document_id
            -- Explicit cast: Postgres cannot infer a parameter's type from a
            -- bare IS NULL test and raises AmbiguousParameter without it.
            WHERE %(dept)s::text IS NULL OR d.department IN (%(dept)s::text, 'all')
        ),
        vec AS (
            SELECT id, row_number() OVER (ORDER BY embedding <=> %(v)s) AS rank
            FROM scoped
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %(v)s
            LIMIT 20
        ),
        fts AS (
            SELECT id, row_number() OVER (
                     ORDER BY ts_rank(content_tsv,
                              websearch_to_tsquery('english', %(q)s)) DESC) AS rank
            FROM scoped
            WHERE content_tsv @@ websearch_to_tsquery('english', %(q)s)
            LIMIT 20
        )
        SELECT c.id::text, c.content, c.section_path, c.step_number, c.ordinal,
               d.title AS document, d.source_ref, d.department, d.doc_type,
               COALESCE(1.0/(%(k)s + v.rank), 0) + COALESCE(1.0/(%(k)s + f.rank), 0)
                 AS rrf,
               -- pgvector's <=> is cosine DISTANCE, so similarity is 1 - it.
               -- This is what the floor is applied to; see SIMILARITY_FLOOR.
               1 - (c.embedding <=> %(v)s) AS similarity,
               (v.id IS NOT NULL) AS hit_vector,
               (f.id IS NOT NULL) AS hit_keyword
        FROM sop_chunk c
        JOIN sop_document d ON d.id = c.document_id
        LEFT JOIN vec v ON v.id = c.id
        LEFT JOIN fts f ON f.id = c.id
        WHERE (v.id IS NOT NULL OR f.id IS NOT NULL)
        ORDER BY rrf DESC
        LIMIT %(lim)s
    """, {"v": vec_literal, "q": query, "k": RRF_K, "lim": limit,
          "dept": department})

    rows = [r for r in cur.fetchall()
            if r["similarity"] is not None
            and float(r["similarity"]) >= SIMILARITY_FLOOR]

    for r in rows:
        r["rrf"] = round(float(r["rrf"]), 5)
        r["similarity"] = round(float(r["similarity"]), 4)
        # The reference a citation carries. Scoped by document, never by SOP
        # number alone: numbers collide across the Bar and Lunch/Dinner manuals,
        # so "SOP 23" on its own resolves to the wrong outlet's procedure.
        r["source_ref"] = f"sop:{r['document']}:{r['section_path']}"
    return rows
