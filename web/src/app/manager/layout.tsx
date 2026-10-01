import type { Metadata } from "next";
import { ConsoleShell } from "@/features/manager-console/components/console-shell";

export const metadata: Metadata = {
  title: "Manager Console · The Coaching Engine",
};

export default function ManagerLayout({
  children,
}: LayoutProps<"/manager">) {
  return <ConsoleShell>{children}</ConsoleShell>;
}
