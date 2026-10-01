"use client";

import { useState } from "react";
import { Mic, PointerIcon } from "lucide-react";
import { ObservationForm } from "./observation-form";
import { VoiceObserve } from "./voice-observe";
import type { StaffMember } from "@/lib/types";

/**
 * Two ways to log the same thing, and the manager picks per moment.
 *
 * Speaking is the default because it is the one that gets used: it works while
 * walking, covers several people in one go, and does not require stopping,
 * which is the real reason floor observations go unlogged. The tap-through
 * wizard stays exactly as it was, one tap away, because it is the one that
 * works in a silent lobby, with a blocked microphone, or when the manager
 * simply prefers a form.
 *
 * Neither is a lesser version of the other. Both end at the same POST with the
 * same rules, and a spoken observation is not marked differently in anyone's
 * record: what is recorded is what the manager confirmed, not how they typed
 * it.
 */
export function ObserveSurface({ staff }: { staff: StaffMember[] }) {
  const [mode, setMode] = useState<"speak" | "tap">("speak");

  return (
    <div className="space-y-4">
      <div
        role="tablist"
        aria-label="How to log this observation"
        className="inline-flex rounded-xl border bg-card p-1"
      >
        <ModeTab
          selected={mode === "speak"}
          onClick={() => setMode("speak")}
          icon={<Mic className="size-3.5" />}
          label="Speak it"
        />
        <ModeTab
          selected={mode === "tap"}
          onClick={() => setMode("tap")}
          icon={<PointerIcon className="size-3.5" />}
          label="Tap it through"
        />
      </div>

      <div key={mode} className="fade-up">
        {mode === "speak" ? (
          <VoiceObserve staff={staff} />
        ) : (
          <ObservationForm staff={staff} />
        )}
      </div>
    </div>
  );
}

function ModeTab({
  selected,
  onClick,
  icon,
  label,
}: {
  selected: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={selected}
      onClick={onClick}
      className={`inline-flex min-h-10 items-center gap-1.5 rounded-lg px-3.5 text-sm font-medium transition-colors ${
        selected
          ? "bg-primary text-primary-foreground"
          : "text-muted-foreground hover:text-foreground"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}
