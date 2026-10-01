import { managerApi } from "@/features/manager-console/api/managerApi";
import {
  VerifyQueue,
  type VerifyQueueEntry,
} from "@/features/manager-console/components/verify-queue";
import { staffMembers } from "@/lib/mock/seed";
import type { Recommendation } from "@/lib/types";


/** Rendered per request, never prerendered.
 *
 * Without this Next may statically render at build time and the page freezes
 * with whatever the database held during deployment. Everything here is live
 * operational data, and a manager acting on a stale queue is worse than a
 * manager waiting a moment for a fresh one.
 */
export const dynamic = "force-dynamic";

export const metadata = { title: "Verify queue, Manager Console" };

export default async function VerifyQueuePage() {
  const recommendations = await managerApi.listRecommendations();
  const pending = recommendations.filter((r) => r.status === "pending_verify");
  const abstained = recommendations.filter((r) => r.status === "abstained");

  const toEntry = (rec: Recommendation): VerifyQueueEntry => ({
    recommendation: rec,
    // Server first, roster second. Real rows carry database ids the mock
    // roster cannot resolve; mock rows carry no staff_name.
    staffName:
      rec.staff_name ??
      staffMembers.find((s) => s.id === rec.staff_id)?.name ??
      "Staff member",
  });

  return (
    <div className="space-y-6">
      <div className="msg-in">
        <h1 className="text-2xl font-semibold tracking-tight">Verify queue</h1>
        <p className="text-sm text-muted-foreground">
          The agent drafts with citations, then stops. Nothing routes until
          you confirm, correct or reject, and every verdict trains the
          calibration number.
        </p>
      </div>

      <VerifyQueue
        entries={[...pending.map(toEntry), ...abstained.map(toEntry)]}
      />
    </div>
  );
}
