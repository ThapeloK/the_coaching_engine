"use client";

import { useState } from "react";
import { ChevronDown, HelpCircle } from "lucide-react";
import { RecommendationCard } from "./recommendation-card";
import type { Recommendation } from "@/lib/types";

export function WhyExplainer({
  recommendation,
}: {
  recommendation: Recommendation;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        aria-controls="why-panel"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed p-3 text-sm font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
      >
        <HelpCircle className="size-4" />
        Why is the AI saying this?
        <ChevronDown
          className={`size-4 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div id="why-panel" className="msg-in mt-4">
          <RecommendationCard recommendation={recommendation} />
        </div>
      )}
    </div>
  );
}
