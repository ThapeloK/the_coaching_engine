import { StandardsAudit } from "@/features/manager-console/components/standards-audit";

/** Rendered per request. The report is live operational data and a manager
 * reading a stale one would be acting on a document revision that has since
 * changed. */
export const dynamic = "force-dynamic";

export default function StandardsPage() {
  return <StandardsAudit />;
}
