import { NextResponse } from "next/server";
import { mockDb } from "@/lib/mock/db";

export async function GET() {
  const recommendations = await mockDb.listRecommendations();
  return NextResponse.json(recommendations);
}
