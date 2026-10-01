import { notFound } from "next/navigation";
import { VerifyPanel } from "@/features/manager-console/components/verify-panel";
import { WhyExplainer } from "@/features/manager-console/components/why-explainer";
import { managerApi } from "@/features/manager-console/api/managerApi";
import { staffMembers } from "@/lib/mock/seed";

export const metadata = { title: "Verify, Manager Console" };

export default async function VerifyDetailPage(
  props: PageProps<"/manager/verify/[id]">
) {
  const { id } = await props.params;
  const recommendation = await managerApi.getRecommendation(id);
  if (!recommendation) notFound();

  // The recommendation's staff_id is a database uuid on real data, which the
  // mock roster does not contain. Name comes from the server when it knows it;
  // the roster fills in role and department; the seed answers in mock mode.
  const roster = await managerApi.listStaff();
  const fromRoster = roster.find((s) => s.id === recommendation.staff_id);
  const fromSeed = staffMembers.find((s) => s.id === recommendation.staff_id);

  const staffName =
    recommendation.staff_name ?? fromRoster?.name ?? fromSeed?.name ?? "Unknown";
  const initials =
    staffName
      .split(" ")
      .map((part) => part[0])
      .join("") || "?";
  // Built from the parts that exist, so a missing one never leaves a stray
  // separator behind.
  const staffDetail = [
    fromRoster?.role ?? fromSeed?.role,
    fromRoster?.department ?? fromSeed?.department,
    fromSeed?.started_at,
  ]
    .filter(Boolean)
    .map((part) => String(part).replace(/_/g, " "))
    .join(" · ");

  return (
    <div className="space-y-6">
      <div className="msg-in flex flex-wrap items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-full bg-accent text-sm font-bold text-accent-foreground">
          {initials}
        </div>
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{staffName}</h1>
          {staffDetail && (
            <p className="text-xs text-muted-foreground">{staffDetail}</p>
          )}
        </div>
      </div>

      <div className="fade-up [animation-delay:120ms]">
        <p className="text-lg font-medium leading-snug md:text-xl">
          {recommendation.headline}
        </p>
      </div>

      {recommendation.status === "pending_verify" ? (
        <div className="fade-up [animation-delay:240ms] space-y-4">
          <VerifyPanel recommendation={recommendation} />
          <WhyExplainer recommendation={recommendation} />
        </div>
      ) : (
        <p className="rounded-xl border bg-muted/30 p-4 text-center text-sm text-muted-foreground">
          This recommendation was {recommendation.status}. Refresh the queue
          to see the latest state.
        </p>
      )}
    </div>
  );
}
