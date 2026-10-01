import { NextResponse } from "next/server";
import { mockDb } from "@/lib/mock/db";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;
  const gap = await mockDb.getGap(id);
  if (!gap) {
    return NextResponse.json(
      { type: "about:blank", title: "Not found", status: 404, detail: "No gap data for this staff member" },
      { status: 404 }
    );
  }
  return NextResponse.json(gap);
}
