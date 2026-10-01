"use client";

import { Logo } from "@/components/logo";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { History, Home, MessageCircle, ShieldQuestion } from "lucide-react";
import {
  completedAttempt,
  currentManager,
  historyAug26Attempt,
  historyAug29Attempt,
  staffMembers,
} from "@/lib/mock/seed";
import type { ScoreResult } from "@/lib/types";
import { ScreenNav } from "@/components/screen-nav";

const tabs = [
  { href: "/staff", label: "Home", icon: Home },
  { href: "/staff/practice", label: "Practice", icon: MessageCircle },
  // The only tab somebody opens DURING a shift, with a guest in front of
  // them. The other three are all after the fact.
  { href: "/staff/ask", label: "Can I?", icon: ShieldQuestion },
  { href: "/staff/history", label: "My practice", icon: History },
];

// The staff PWA is the narrative actor's phone in the demo: roster id
// 9f2c-diego (seed.sql staff-001). Header strings come from the roster so a
// rename in seed.ts flows through without touching the shell.
const actor = staffMembers.find((s) => s.id === "9f2c-diego");

/** Initials from the name field itself (first letters of each word). */
function initials(name: string): string {
  return (
    name
      .trim()
      .split(/\s+/)
      .map((word) => word[0]?.toUpperCase() ?? "")
      .join("")
      .slice(0, 2) || "?"
  );
}

/** The actor's completed practice runs in the seed (the staff PWA narrates
 * one staff member, so the header's growth read is their own data — never
 * static). */
const actorPracticeResults = [
  completedAttempt.result,
  historyAug29Attempt.result,
  historyAug26Attempt.result,
].filter((result): result is ScoreResult => result !== null);

/** Completed practice runs in the month of the actor's most recent run — the
 * narrative's "this month". Mirrors the pool-as-of rule in mock/db.ts: the
 * latest score date is the reference point, so the count never ages out as
 * the real calendar moves on. */
function practicesThisMonth(): number {
  if (actorPracticeResults.length === 0) return 0;
  const months = actorPracticeResults.map((result) =>
    result.completed_at.slice(0, 7)
  );
  months.sort();
  const newestMonth = months[months.length - 1];
  return actorPracticeResults.filter(
    (result) => result.completed_at.slice(0, 7) === newestMonth
  ).length;
}

/** Header growth line — replaces the old practice-mean badge (a numeric
 * score no staff member ever sees). */
const practicesThisMonthCount = practicesThisMonth();
const growthLabel = `${practicesThisMonthCount} ${
  practicesThisMonthCount === 1 ? "practice" : "practices"
} this month`;

export function StaffShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-dvh justify-center bg-muted/40">
      <div className="relative flex min-h-dvh w-full max-w-md flex-col bg-background shadow-2xl ring-1 ring-border">
        <header className="flex items-center gap-3 border-b px-4 py-3.5">
          <div className="flex size-9 items-center justify-center rounded-full bg-primary text-sm font-bold text-primary-foreground">
            {actor ? initials(actor.name) : "?"}
          </div>
          <div className="min-w-0 flex-1 leading-tight">
            <p className="truncate text-sm font-semibold">
              {actor?.name ?? "Team member"}
            </p>
            <p className="truncate text-xs text-muted-foreground">
              {[actor?.role, currentManager.property]
                .filter((part): part is string => Boolean(part))
                .join(" · ")}
            </p>
          </div>
          <div className="ml-auto flex max-w-[46%] shrink-0 items-center justify-end rounded-full bg-[oklch(0.66_0.055_152)]/15 px-2.5 py-1 text-right text-xs font-medium leading-tight text-[oklch(0.38_0.055_152)] ring-1 ring-[oklch(0.55_0.05_150)]/25">
            {growthLabel}
          </div>
          <Logo className="size-6 shrink-0" title="The Coaching Engine" />
        </header>

        <main className="flex flex-1 flex-col px-4 pb-24 pt-4">
          {/* The staff app had three tabs and no exit. This is the way
              back out to pick another role. */}
          <ScreenNav />
          {children}
        </main>

        <nav className="fixed bottom-0 left-1/2 z-20 flex w-full max-w-md -translate-x-1/2 border-t bg-background/95 backdrop-blur">
          {tabs.map((tab) => {
            const active =
              tab.href === "/staff"
                ? pathname === "/staff"
                : pathname.startsWith(tab.href);
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={`flex flex-1 flex-col items-center gap-0.5 py-2.5 text-xs font-medium ${
                  active ? "text-primary" : "text-muted-foreground"
                }`}
              >
                <tab.icon className="size-5" />
                {tab.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
