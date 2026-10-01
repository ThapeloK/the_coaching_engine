import { NextResponse } from "next/server";
import { mockDb } from "@/lib/mock/db";

export async function POST(
  _request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const attempt = await mockDb.startAttempt(id);
  return NextResponse.json(attempt, { status: 201 });
}
