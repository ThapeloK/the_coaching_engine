/**
 * The mark.
 *
 * An open C. The mouth on the right is the transfer gap, which is the thing
 * the whole product is about, so it is the one asymmetry in an otherwise
 * regular shape and the eye goes to it.
 *
 * The two colours are the two evidence streams, and they follow the rule the
 * rest of the interface already uses: teal is what the machine measured,
 * violet is what a human decided. Teal carries the long sweep; violet closes
 * toward the opening and stops short of it.
 *
 * Inline SVG rather than an <img> for three reasons: it inherits currentColor
 * when we ask it to, it cannot flash in late on a slow connection, and it is
 * one request fewer on a page a judge is waiting for.
 */

export function Logo({
  className = "size-8",
  tone = "brand",
  title,
}: {
  className?: string;
  /** "brand" is the two-colour mark. "current" inherits the surrounding text
   * colour, for a footer or a reversed header where two colours would fight. */
  tone?: "brand" | "current";
  /** Give it a title only where it is the sole thing naming the product.
   * Beside the words "The Coaching Engine" it is decoration, and a screen
   * reader announcing it twice is noise. */
  title?: string;
}) {
  const teal = tone === "current" ? "currentColor" : "#0E7C86";
  const violet = tone === "current" ? "currentColor" : "#5B4B8A";
  return (
    <svg
      viewBox="0 0 200 200"
      className={className}
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      fill="none"
    >
      {title ? <title>{title}</title> : null}
      <path
        d="M 142.43 57.57 A 60 60 0 1 0 65.59 149.15"
        stroke={teal}
        strokeWidth="30"
        strokeLinecap="round"
      />
      <path
        d="M 65.59 149.15 A 60 60 0 0 0 142.43 142.43"
        stroke={violet}
        strokeWidth="30"
        strokeLinecap="round"
      />
    </svg>
  );
}

/**
 * Mark plus wordmark. "Coaching" carries the weight and "Engine" is set light,
 * so the name has a shape at a glance instead of reading as three equal words.
 */
export function LogoLockup({
  subtitle,
  className = "",
  markClassName = "size-9",
}: {
  subtitle?: string;
  className?: string;
  markClassName?: string;
}) {
  return (
    <span className={`flex items-center gap-2.5 ${className}`}>
      <Logo className={`${markClassName} shrink-0`} />
      <span className="leading-tight">
        <span className="block text-sm font-semibold tracking-tight">
          The Coaching <span className="font-normal text-muted-foreground">Engine</span>
        </span>
        {subtitle ? (
          <span className="block text-xs text-muted-foreground">{subtitle}</span>
        ) : null}
      </span>
    </span>
  );
}
