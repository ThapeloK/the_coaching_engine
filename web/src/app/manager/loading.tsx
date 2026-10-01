import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

/** Shown the instant a manager route is requested, while the server renders it.
 *
 * Without a loading.tsx the App Router holds the OLD page on screen until the
 * server responds, with no visual change at all. The overview takes a few
 * seconds even against a warm API, because a transfer gap is computed per
 * person under that person's own permissions and there is deliberately no bulk
 * endpoint that would bypass row level security. On a cold host the first
 * request can take the best part of a minute.
 *
 * The result was a button that looked broken: people clicked it, nothing moved,
 * so they clicked again. This file is the fix. It sits inside ConsoleShell, so
 * the sidebar stays put and only the content area shows as pending.
 */
export default function ManagerLoading() {
  return (
    <div className="space-y-6">
      <style>{`@keyframes ce-late-hint { to { opacity: 1 } }`}</style>

      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="space-y-2">
          <Skeleton className="h-8 w-56" />
          <Skeleton className="h-4 w-80" />
        </div>
        <Skeleton className="h-10 w-44 rounded-lg" />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="space-y-2">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-3 w-full max-w-md" />
          </CardHeader>
          <CardContent className="flex items-center justify-center">
            <Skeleton className="aspect-square w-full max-w-[320px] rounded-full" />
          </CardContent>
        </Card>

        <div className="flex flex-col gap-4">
          {[0, 1, 2].map((i) => (
            <Card key={i}>
              <CardHeader className="pb-2">
                <Skeleton className="h-4 w-32" />
              </CardHeader>
              <CardContent className="space-y-2">
                <Skeleton className="h-8 w-14" />
                <Skeleton className="h-3 w-40" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* Only appears if the wait runs long, which on the free tier means the
          host was asleep. Saying so beats leaving someone to guess. */}
      <p
        className="text-center text-sm text-muted-foreground"
        style={{ opacity: 0, animation: "ce-late-hint 0.4s ease-out 4s forwards" }}
      >
        Waking the server. The first request after a quiet spell can take up to a minute.
      </p>
    </div>
  );
}
