import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

/** The staff side of the same problem. See manager/loading.tsx for why.
 *
 * This one matters more than it looks: the staff app is meant to be used on a
 * phone mid-shift, and a tap that produces nothing for several seconds is the
 * fastest way to teach somebody the tool is broken.
 */
export default function StaffLoading() {
  return (
    <div className="space-y-5">
      <style>{`@keyframes ce-late-hint { to { opacity: 1 } }`}</style>

      <div className="space-y-2">
        <Skeleton className="h-7 w-44" />
        <Skeleton className="h-4 w-64" />
      </div>

      {[0, 1, 2].map((i) => (
        <Card key={i}>
          <CardHeader className="pb-2 space-y-2">
            <Skeleton className="h-4 w-36" />
            <Skeleton className="h-3 w-52" />
          </CardHeader>
          <CardContent className="space-y-3">
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-4/5" />
            <Skeleton className="h-9 w-32 rounded-lg" />
          </CardContent>
        </Card>
      ))}

      <p
        className="text-center text-sm text-muted-foreground"
        style={{ opacity: 0, animation: "ce-late-hint 0.4s ease-out 4s forwards" }}
      >
        Waking the server. The first request after a quiet spell can take up to a minute.
      </p>
    </div>
  );
}
