import { NextResponse } from "next/server";
import { mockDb } from "@/lib/mock/db";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const recommendation = await mockDb.getRecommendation(id);
  if (!recommendation) {
    return NextResponse.json(
      { type: "about:blank", title: "Not found", status: 404, detail: "Recommendation not found" },
      { status: 404 }
    );
  }
  return NextResponse.json(recommendation);
}
