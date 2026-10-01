"use client";

// Talks to the API through http from lib/api/client, never a bare fetch to a
// relative path. A relative "/api/v1/..." resolves against whatever host serves
// the page, so once deployed the browser asks the WEBSITE for coaching data
// instead of the API. This repo also serves routes under /api/v1, so it comes
// back 500 rather than 404 and reads as a backend fault. The client also adds
// the actor header and the idempotency key.

import { Logo } from "@/components/logo";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  BarChart3,
  ClipboardCheck,
  Eye,
  ListChecks,
  PenLine,
  ScanSearch,
  Sparkles,
  Users,
} from "lucide-react";
import { ScreenNav } from "@/components/screen-nav";
import { Badge } from "@/components/ui/badge";
import { currentManager } from "@/lib/mock/seed";
import { managerApi } from "@/features/manager-console/api/managerApi";

const nav = [
  { href: "/manager", label: "Overview", icon: Sparkles },
  { href: "/manager/observe", label: "Log observation", icon: ClipboardCheck },
  { href: "/manager/verify", label: "Verify queue", icon: ListChecks, badge: true },
  { href: "/manager/gap", label: "Transfer gap", icon: BarChart3 },
  { href: "/manager/insights", label: "Team insights", icon: Users },
  // Before anybody is coached at all: what the property has actually
  // written down, and what it has not.
  { href: "/manager/standards", label: "Standards audit", icon: ScanSearch },
  // The other end of the same loop: the gap says what is wrong, this
  // writes the practice that answers it.
  { href: "/manager/scenarios", label: "Next scenario", icon: PenLine },
  // Outside /manager on purpose: it is not part of a manager's job, it is
  // for the person who wants to check our claims rather than believe them.
  { href: "/glassbox", label: "Glass box", icon: Eye },
];

export function ConsoleShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [pending, setPending] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    managerApi
      .listRecommendations()
      .then((list) => {
        if (cancelled) return;
        setPending(list.filter((r) => r.status === "pending_verify").length);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  return (
    <div className="flex min-h-dvh">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-60 flex-col border-r bg-sidebar md:flex">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <Logo className="size-8 shrink-0" />
          <div className="leading-tight">
            <p className="text-sm font-semibold">
              The Coaching{" "}
              <span className="font-normal text-muted-foreground">Engine</span>
            </p>
            <p className="text-xs text-muted-foreground">Manager Console</p>
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-1 px-3">
          {nav.map((item) => {
            const active =
              item.href === "/manager"
                ? pathname === "/manager"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href === "/glassbox" ? "/glassbox?from=manager" : item.href}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-sidebar-foreground/70 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
                }`}
              >
                <item.icon className="size-4 shrink-0" />
                <span className="flex-1">{item.label}</span>
                {item.badge && pending !== null && pending > 0 && (
                  <Badge className="h-5 min-w-5 justify-center rounded-full px-1.5 text-xs">
                    {pending}
                  </Badge>
                )}
              </Link>
            );
          })}
        </nav>
        <div className="border-t px-5 py-4">
          {/* Identity follows seed.ts's currentManager (staff-014), no copy
              of the manager's name or property hardcoded in the shell. */}
          <p className="text-sm font-medium">{currentManager.name}</p>
          <p className="text-xs text-muted-foreground">
            {currentManager.role} · {currentManager.property}
          </p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col md:pl-60">
        {/* The sidebar is hidden below md, so without this a phone shows a
            console with nothing naming the product on it. */}
        <div className="flex items-center gap-2 border-b px-4 py-3 md:hidden">
          <Logo className="size-6 shrink-0" />
          <p className="text-sm font-semibold">
            The Coaching{" "}
            <span className="font-normal text-muted-foreground">Engine</span>
          </p>
        </div>
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 md:px-8 md:py-8">
          {/* Back goes up one level, not always to the overview, and the
              role switch is the way out of the console entirely. Both live in
              the content area so they sit in the same place on a phone. */}
          <ScreenNav />
          {children}
        </main>
        <MobileNav pathname={pathname} pending={pending} />
      </div>
    </div>
  );
}

function MobileNav({
  pathname,
  pending,
}: {
  pathname: string;
  pending: number | null;
}) {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-20 flex border-t bg-background/95 backdrop-blur md:hidden">
      {nav.map((item) => {
        const active =
          item.href === "/manager"
            ? pathname === "/manager"
            : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href === "/glassbox" ? "/glassbox?from=manager" : item.href}
            className={`relative flex flex-1 flex-col items-center gap-0.5 py-2.5 text-xs font-medium ${
              active ? "text-primary" : "text-muted-foreground"
            }`}
          >
            <item.icon className="size-5" />
            {item.label.split(" ")[0]}
            {item.badge && pending !== null && pending > 0 && (
              <span className="absolute right-1/4 top-1.5 flex size-4 items-center justify-center rounded-full bg-primary text-[9px] font-bold text-primary-foreground">
                {pending}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
