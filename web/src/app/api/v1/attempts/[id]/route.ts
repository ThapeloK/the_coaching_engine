import { NextResponse } from "next/server";
import { mockDb } from "@/lib/mock/db";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const attempt = await mockDb.getAttempt(id);
  if (!attempt) {
    return NextResponse.json(
      { type: "about:blank", title: "Not found", status: 404, detail: "Attempt not found" },
      { status: 404 }
    );
  }
  return NextResponse.json(attempt);
}
