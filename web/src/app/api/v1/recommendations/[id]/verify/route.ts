import { NextResponse } from "next/server";
import { mockDb } from "@/lib/mock/db";

export async function POST(
  request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const body = await request.json();
  const response = await mockDb.verifyRecommendation(id, body);
  return NextResponse.json(response);
}
