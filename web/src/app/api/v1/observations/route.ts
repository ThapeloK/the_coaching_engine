import { NextResponse } from "next/server";
import { mockDb } from "@/lib/mock/db";

export async function GET() {
  const observations = await mockDb.listObservations();
  return NextResponse.json(observations);
}

export async function POST(request: Request) {
  const body = await request.json();
  const response = await mockDb.logObservation(body);
  return NextResponse.json(response, { status: 201 });
}
