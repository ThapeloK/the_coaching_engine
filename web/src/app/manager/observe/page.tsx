import { ObserveSurface } from "@/features/manager-console/components/observe-surface";
import { managerApi } from "@/features/manager-console/api/managerApi";
import { staffMembers } from "@/lib/mock/seed";
import type { StaffMember } from "@/lib/types";

export const metadata = { title: "Log observation, Manager Console" };

/** Rendered per request: the roster is live data, and a manager should not be
 * offered a colleague who left last week because the page was built on Tuesday. */
export const dynamic = "force-dynamic";

export default async function ObservePage() {
  // The picker was showing the thirteen seeded names while the property has
  // forty-eight people, so a manager could not log an observation about most
  // of their own team. The seed answers only in mock mode, or if the roster
  // call fails, because a picker with somebody in it beats an empty screen.
  const roster = await managerApi.listStaff().catch(() => []);
  const staff: StaffMember[] = roster.length
    ? roster.map((s) => ({
        id: s.id,
        name: s.name,
        role: s.role ?? "staff",
        department: s.department ?? "other",
        started_at: "",
      }))
    : staffMembers;

  return (
    <div className="mx-auto w-full max-w-4xl">
      <div className="fade-up">
        <ObserveSurface staff={staff} />
      </div>
    </div>
  );
}
