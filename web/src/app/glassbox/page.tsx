import { Logo } from "@/components/logo";
import { GlassBox } from "@/features/glass-box/components/glass-box";
import { ScreenNav } from "@/components/screen-nav";
import { parentOf } from "@/lib/nav";

export const metadata = {
  title: "Glass box, The Coaching Engine",
  description:
    "Check the three claims instead of believing them: where the reasoning "
    + "lives, what the cite gate rejects, and who the database lets you read.",
};

/** The page exists for one audience: someone who has just been told this is a
 * wrapper around a language model and wants to see for themselves. Every panel
 * below runs production code on demand. Nothing is recorded or replayed. */
export default async function GlassBoxPage({
  searchParams,
}: {
  searchParams: Promise<{ from?: string }>;
}) {
  // Resolved here rather than in the browser: the exit depends on where the
  // visitor came from, and reading the query string client-side would need a
  // Suspense boundary on a page that is otherwise static.
  const { from } = await searchParams;

  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6">
      {/* This page sits outside both shells and is linked from two places that
          want different exits: a judge from the landing page belongs back
          there, a manager from the console sidebar belongs back in the
          console. */}
      <ScreenNav back={parentOf("/glassbox", from)} />
      <header className="mb-8">
        <div className="mb-3 flex items-center gap-2">
          <Logo className="size-7 shrink-0" />
          <p className="text-sm font-semibold">
            The Coaching{" "}
            <span className="font-normal text-muted-foreground">Engine</span>
          </p>
        </div>
        <h1 className="font-[family-name:var(--font-heading)] text-3xl font-semibold tracking-tight">
          The glass box
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Three claims we would rather you checked than believed. Each panel
          calls the same code the product runs, live, when you press the button.
          If a panel says the gate rejected a fabricated citation, it is because
          the gate rejected it a moment ago.
        </p>
      </header>
      <GlassBox />
    </main>
  );
}
