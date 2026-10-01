import type { Metadata } from "next";
import { StaffShell } from "@/features/staff-pwa/components/staff-shell";

export const metadata: Metadata = {
  title: "Staff · The Coaching Engine",
};

export default function StaffLayout({ children }: LayoutProps<"/staff">) {
  return <StaffShell>{children}</StaffShell>;
}
