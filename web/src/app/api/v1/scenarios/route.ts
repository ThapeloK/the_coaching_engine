import { NextResponse } from "next/server";
import { mockDb } from "@/lib/mock/db";

export async function GET() {
  const scenarios = await mockDb.listScenarios();
  return NextResponse.json(scenarios);
}
