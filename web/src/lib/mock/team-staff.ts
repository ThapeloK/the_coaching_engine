import type { StaffMember } from "@/lib/types";

/**
 * Authoritative roster from the team's generated dataset (`staff.json`,
 * seed 20260913). The dataset lists 15 people; the roster below is the 13
 * observable front-line staff — Marta (staff-014, manager) and Fiona
 * (staff-015, ld_admin) are console users, not floor-observation targets.
 *
 * Id mapping: Diego is staff-001 in the pipeline data but keeps the legacy
 * demo id "9f2c-diego" everywhere the app shows him (his gap page, the
 * roster pickers, the staff PWA). The mapping functions here are the single
 * place that translation lives: rows from the pipeline JSONs are keyed by
 * team id, the mock store and roster by the legacy id.
 */

/** Exactly as generated — department/role are raw pipeline enums. */
export interface TeamStaffRow {
  id: string;
  name: string;
  department: "front_office" | "f_and_b" | "all";
  role: "staff" | "manager" | "ld_admin";
  persona: string;
  tenure_months: number;
}

export const TEAM_STAFF_ROWS: TeamStaffRow[] = [
  { id: "staff-001", name: "Diego", department: "front_office", role: "staff", persona: "strong in practice, freezes with real guests", tenure_months: 8 },
  { id: "staff-002", name: "Niamh", department: "front_office", role: "staff", persona: "strong with regulars, less sure with complaints", tenure_months: 14 },
  { id: "staff-003", name: "Tomasz", department: "front_office", role: "staff", persona: "confident but improvises around the standard", tenure_months: 25 },
  { id: "staff-004", name: "Rachel", department: "front_office", role: "staff", persona: "English as a second language, careful and precise", tenure_months: 28 },
  { id: "staff-005", name: "Kwame", department: "front_office", role: "staff", persona: "long tenure, efficient, occasionally clipped under pressure", tenure_months: 5 },
  { id: "staff-006", name: "Lucia", department: "front_office", role: "staff", persona: "long tenure, efficient, occasionally clipped under pressure", tenure_months: 27 },
  { id: "staff-007", name: "Sean", department: "front_office", role: "staff", persona: "confident but improvises around the standard", tenure_months: 36 },
  { id: "staff-008", name: "Priya", department: "front_office", role: "staff", persona: "confident but improvises around the standard", tenure_months: 46 },
  { id: "staff-009", name: "Andrei", department: "front_office", role: "staff", persona: "confident but improvises around the standard", tenure_months: 46 },
  { id: "staff-010", name: "Aoife", department: "f_and_b", role: "staff", persona: "consistent in practice and on the floor", tenure_months: 5 },
  { id: "staff-011", name: "Marek", department: "f_and_b", role: "staff", persona: "English as a second language, careful and precise", tenure_months: 33 },
  { id: "staff-012", name: "Chloe", department: "f_and_b", role: "staff", persona: "confident but improvises around the standard", tenure_months: 27 },
  { id: "staff-013", name: "Bogdan", department: "f_and_b", role: "staff", persona: "English as a second language, careful and precise", tenure_months: 29 },
  { id: "staff-014", name: "Marta", department: "front_office", role: "manager", persona: "duty manager, ~40 reports, time-poor", tenure_months: 61 },
  { id: "staff-015", name: "Fiona", department: "all", role: "ld_admin", persona: "L&D lead, part-time across two properties", tenure_months: 30 },
];

/** The only id that differs between the pipeline data and the app roster. */
const TEAM_TO_LEGACY: Record<string, string> = { "staff-001": "9f2c-diego" };

export function rosterIdOf(teamId: string): string {
  return TEAM_TO_LEGACY[teamId] ?? teamId;
}

/** Roster id -> pipeline id (used to find the right transfer-gap rows). */
export function teamIdOf(rosterId: string): string {
  for (const [team, legacy] of Object.entries(TEAM_TO_LEGACY)) {
    if (legacy === rosterId) return team;
  }
  return rosterId;
}

const DEPARTMENT_LABEL: Record<TeamStaffRow["department"], string> = {
  front_office: "Front Office",
  f_and_b: "F&B",
  all: "All properties",
};

/** The dataset's raw `staff` role has no display name; the front-of-house and
 * F&B roles are what the app copy already uses for these people. */
const ROLE_LABEL: Record<TeamStaffRow["department"], string> = {
  front_office: "Front Desk Agent",
  f_and_b: "Server",
  all: "L&D Admin",
};

const TENURE_BASELINE = "2026-09-05"; // day 5: keeps the demo's existing dates

/** First day of the month `tenureMonths` before the 2026-09 baseline —
 * deterministic, so the roster is restorable without hand-written dates. */
function startedAtFromTenure(tenureMonths: number): string {
  const index = 2026 * 12 + (9 - 1) - tenureMonths;
  const year = Math.floor(index / 12);
  const month = (index % 12) + 1;
  return `${year}-${String(month).padStart(2, "0")}-05`;
}

/**
 * The 13 observable staff, in pipeline order (staff-001..staff-013). Diego
 * keeps his legacy id; names, roles and departments mirror `staff.json`.
 */
export const seedStaffMembers: StaffMember[] = TEAM_STAFF_ROWS.filter(
  (row) => row.role === "staff"
).map((row) => ({
  id: rosterIdOf(row.id),
  name: row.name,
  role: ROLE_LABEL[row.department],
  department: DEPARTMENT_LABEL[row.department],
  started_at: startedAtFromTenure(row.tenure_months),
}));
