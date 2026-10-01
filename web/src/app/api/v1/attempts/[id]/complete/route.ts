import { NextResponse } from "next/server";
import { mockDb } from "@/lib/mock/db";

export async function POST(
  _request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const result = await mockDb.completeAttempt(id);
  return NextResponse.json(result);
}
