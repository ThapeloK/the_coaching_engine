import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ScreenNav } from "@/components/screen-nav";

/** The glass box runs the real agent, so it is the slowest page on the site by
 * design: a trace is an actual model call, not a replay. That is the whole
 * point of the page, but it does mean a judge clicking it needs to see
 * immediately that something started. See manager/loading.tsx.
 */
export default function GlassboxLoading() {
  return (
    <div className="mx-auto w-full max-w-5xl space-y-6 p-6">
      {/* Unlike the manager and staff loading screens, this one needs
          its own nav: /glassbox has no shell, so while the page loads
          there is nothing else on screen to navigate with. */}
      <ScreenNav />
      <style>{`@keyframes ce-late-hint { to { opacity: 1 } }`}</style>

      <div className="space-y-2">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-full max-w-xl" />
      </div>

      {[0, 1, 2].map((i) => (
        <Card key={i}>
          <CardHeader className="space-y-2">
            <Skeleton className="h-5 w-56" />
            <Skeleton className="h-3 w-full max-w-lg" />
          </CardHeader>
          <CardContent className="space-y-2">
            {[0, 1, 2, 3].map((r) => (
              <Skeleton key={r} className="h-10 w-full rounded-lg" />
            ))}
          </CardContent>
        </Card>
      ))}

      <p
        className="text-center text-sm text-muted-foreground"
        style={{ opacity: 0, animation: "ce-late-hint 0.4s ease-out 4s forwards" }}
      >
        Running the agent for real. This is a live model call, not a recording.
      </p>
    </div>
  );
}
