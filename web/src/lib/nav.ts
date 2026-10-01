/**
 * Where "back" goes from any screen, and what to call it.
 *
 * One table instead of a back link hand-written per page. Pages were getting
 * it inconsistently: three of thirteen had one at all, the manager shell sent
 * every screen to the overview even when that skipped a level, and a detail
 * page ended up showing two different back links at once.
 *
 * The rule is the same everywhere: back goes up exactly ONE level, and the
 * label names where it lands rather than saying "Back". A person should be
 * able to read the link and know where they will end up.
 */

export interface BackTarget {
  href: string;
  label: string;
}

/** True for a route segment that is an id rather than a fixed section name. */
function isDynamicSegment(segment: string | undefined): boolean {
  if (!segment) return false;
  // Ids here are uuids or seed ids like "9f2c-diego" or "rec-004": anything
  // with a digit or a dash. Section names are plain words.
  return /[\d-]/.test(segment);
}

export function parentOf(
  pathname: string,
  from?: string | null,
): BackTarget | null {
  const parts = pathname.split("/").filter(Boolean);
  if (parts.length === 0) return null;

  // ---------------------------------------------------------------- manager
  if (parts[0] === "manager") {
    // /manager is the top of the console. Leaving it entirely is the job of
    // the role switch, not of a back link.
    if (parts.length === 1) return null;

    // /manager/verify/<id> goes back to the queue, not past it to the
    // overview. Skipping the queue is what made people press browser back.
    if (parts[1] === "verify" && parts.length > 2) {
      return { href: "/manager/verify", label: "Back to verify queue" };
    }
    return { href: "/manager", label: "Back to overview" };
  }

  // ------------------------------------------------------------------ staff
  if (parts[0] === "staff") {
    if (parts.length === 1) return null;

    // Both a practice run and its results belong to the scenario list.
    if (
      (parts[1] === "practice" || parts[1] === "results") &&
      isDynamicSegment(parts[2])
    ) {
      return { href: "/staff/practice", label: "Back to scenarios" };
    }
    return { href: "/staff", label: "Back to home" };
  }

  // --------------------------------------------------------------- glassbox
  // It sits outside both shells, which is why it had no way out at all.
  //
  // It is reachable from two places and they want different exits. A judge
  // arrives from the landing page and belongs back there. A manager arrives
  // from the console sidebar, and sending them to the landing page threw them
  // out of the console entirely: they lost their place and had to pick their
  // role again to get back. So the link says where it came from and this
  // honours it. Anything else, including a tampered value, falls back to home.
  if (parts[0] === "glassbox") {
    if (from === "manager") {
      return { href: "/manager", label: "Back to the console" };
    }
    return { href: "/", label: "Back to home" };
  }

  return null;
}
