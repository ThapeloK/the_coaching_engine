import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PracticeChat } from "@/features/staff-pwa/components/practice-chat";
import { staffApi } from "@/features/staff-pwa/api/staffApi";

export default async function PracticeChatPage(
  props: PageProps<"/staff/practice/[id]">
) {
  const { id } = await props.params;
  const scenario = (await staffApi.listScenarios()).find((s) => s.id === id);
  const attempt = await staffApi.startAttempt(id);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-2 pb-3">
        <Button
          variant="ghost"
          size="icon"
          className="size-8 shrink-0"
          nativeButton={false}
          render={<Link href="/staff/practice" />}
        >
          <ArrowLeft className="size-4" />
        </Button>
        <p className="text-sm font-semibold">Practice session</p>
      </div>
      <PracticeChat
        attempt={attempt}
        scenarioTitle={scenario?.title ?? "Practice scenario"}
      />
    </div>
  );
}
