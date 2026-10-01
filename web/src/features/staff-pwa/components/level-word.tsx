import { levelWord } from "@/lib/format";

/** Staff-facing level chip: renders the qualitative word, never the numeric
 * level — numbers are manager-side vocabulary. Tier tones reuse the palette
 * the numeric chips used, so an unscored dimension stays muted and scored
 * levels keep their green/amber/rose weight without a digit in sight. */
export function LevelWord({
  level,
  prefix,
}: {
  level: number | null;
  prefix?: string;
}) {
  const word = levelWord(level) ?? "–";
  const tone =
    level === null
      ? "bg-muted text-muted-foreground"
      : level >= 4
        ? "bg-[oklch(0.66_0.055_152)]/15 text-[oklch(0.38_0.055_152)]"
        : level === 3
          ? "bg-[oklch(0.8_0.06_80)]/15 text-[oklch(0.47_0.065_72)]"
          : "bg-[oklch(0.7_0.085_28)]/15 text-[oklch(0.44_0.09_28)]";
  return (
    <span
      className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${tone}`}
    >
      {prefix ? `${prefix} · ${word}` : word}
    </span>
  );
}
