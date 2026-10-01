import { NextResponse } from "next/server";
import { mockDb } from "@/lib/mock/db";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const debrief = await mockDb.getDebrief(id);
  if (!debrief) {
    return NextResponse.json(
      { type: "about:blank", title: "Not found", status: 404, detail: "Debrief not found" },
      { status: 404 }
    );
  }
  return NextResponse.json(debrief);
}
