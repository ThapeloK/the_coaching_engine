import { NextResponse } from "next/server";
import { mockDb } from "@/lib/mock/db";
import type { DebriefRegistration } from "@/lib/types";

/**
 * POST /debriefs → 202 { id, status, poll_after_ms } (openapi.yaml).
 *
 * The frozen contract body is a voice upload: upload_key, duration_ms
 * (1000..180000), recorded_at. The staff PWA still posts a typed debrief as
 * plain `text`; both are accepted here until integration migrates the UI.
 */

const MIN_DURATION_MS = 1000;
const MAX_DURATION_MS = 180000;
const POLL_AFTER_MS = 2000; // mock resolves synchronously; poll after the real pipeline's cadence

function problem(status: number, title: string, detail: string) {
  return NextResponse.json(
    { type: "about:blank", title, status, detail },
    { status, headers: { "Content-Type": "application/problem+json" } }
  );
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return problem(400, "Invalid JSON", "Request body must be valid JSON");
  }
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    return problem(400, "Invalid body", "Request body must be a JSON object");
  }

  const {
    text,
    upload_key,
    duration_ms,
    recorded_at,
  } = body as {
    text?: unknown;
    upload_key?: unknown;
    duration_ms?: unknown;
    recorded_at?: unknown;
  };

  if (text !== undefined && typeof text !== "string") {
    return problem(400, "Invalid body", "`text` must be a string");
  }
  if (
    upload_key !== undefined &&
    (typeof upload_key !== "string" || upload_key.trim() === "")
  ) {
    return problem(400, "Invalid body", "`upload_key` must be a non-empty string");
  }
  if (
    duration_ms !== undefined &&
    (typeof duration_ms !== "number" ||
      !Number.isInteger(duration_ms) ||
      duration_ms < MIN_DURATION_MS ||
      duration_ms > MAX_DURATION_MS)
  ) {
    return problem(
      400,
      "Invalid body",
      `\`duration_ms\` must be an integer between ${MIN_DURATION_MS} and ${MAX_DURATION_MS}`
    );
  }
  if (
    recorded_at !== undefined &&
    (typeof recorded_at !== "string" || Number.isNaN(Date.parse(recorded_at)))
  ) {
    return problem(
      400,
      "Invalid body",
      "`recorded_at` must be an ISO 8601 date-time string"
    );
  }
  if (text === undefined && upload_key === undefined) {
    return problem(
      400,
      "Invalid body",
      "Send `text` for a typed debrief, or `upload_key` (+ `duration_ms`, `recorded_at`) for a voice upload"
    );
  }

  try {
    const { id, debrief } = await mockDb.createDebrief(text ?? "");
    const payload: DebriefRegistration = {
      id,
      status: debrief.status,
      poll_after_ms: POLL_AFTER_MS,
    };
    return NextResponse.json(payload, { status: 202 });
  } catch (error) {
    console.error("Failed to register debrief:", error);
    return problem(500, "Internal error", "Could not register the debrief");
  }
}
