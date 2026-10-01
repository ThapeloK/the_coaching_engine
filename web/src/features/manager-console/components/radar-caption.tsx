"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";

/** The sentence under the team radar. Numbers arrive as data and the wording
 * is built here, so nothing technical renders — or ships — until a manager
 * taps Details. The radar picture itself stays in plain view. */
export function RadarCaption({
  observedStaffCount,
  emptyDimensions,
}: {
  observedStaffCount: number;
  emptyDimensions: string[];
}) {
  const [open, setOpen] = useState(false);

  const detail = `Scale 0–5 · means across ${observedStaffCount} staff with observations${
    emptyDimensions.length > 0
      ? ` · no transfer-gap evidence yet for ${emptyDimensions.join(" and ")}`
      : ""
  }`;

  return (
    <div className="mt-2 flex flex-col items-center gap-2">
      <button
        type="button"
        aria-expanded={open}
        aria-controls="radar-caption-details"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1 rounded-full border border-dashed px-3 py-1 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
      >
        Details
        <ChevronDown
          className={`size-3.5 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <p
          id="radar-caption-details"
          className="msg-in text-center text-xs text-muted-foreground"
        >
          {detail}
        </p>
      )}
    </div>
  );
}
