import { NextResponse } from "next/server";
import { mockDb } from "@/lib/mock/db";

export async function GET() {
  const insights = await mockDb.getTeamInsights();
  return NextResponse.json(insights);
}
