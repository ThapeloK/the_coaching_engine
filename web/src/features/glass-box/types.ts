/** Shapes returned by the /demo endpoints (services/api/app/demo.py). */

export type StepActor = "code" | "model" | "database";

export interface TraceStep {
  seq: number;
  actor: StepActor;
  label: string;
  ms: number;
  detail: Record<string, unknown>;
}

export interface ModelCall {
  task: string;
  provider: string;
  model: string;
  ms: number;
  prompt_tokens: number;
  completion_tokens: number;
}

export interface TraceRun {
  staff: { id: string; name: string; department: string | null };
  outcome: {
    status: string;
    classification: string | null;
    headline: string | null;
    abstain_reason: string | null;
    citations: number;
    escalation: { rule_id: string; route: string; severity: number } | null;
  };
  trace: {
    steps: TraceStep[];
    calls: ModelCall[];
    total_ms: number;
    total_tokens: number;
    decisions_by_code: number;
    decisions_by_model: number;
  };
}

export interface GateProbe {
  id: string;
  title: string;
  claim: string;
  cited: string[];
  quoted: string | null;
  expected: "pass" | "reject";
  passed: boolean;
  as_expected: boolean;
  failures: string[];
}

export interface GateReport {
  source: string;
  note: string;
  bundle: Array<{
    ref: string;
    kind: string;
    content: string;
    belongs_to: string;
  }>;
  probes: GateProbe[];
  all_as_expected: boolean;
}

export interface RlsReport {
  subject: { id: string; name: string };
  query: string;
  note: string;
  viewers: Array<{
    viewer: string;
    who: string;
    practice_rows: number;
    floor_rows: number;
    expected: string;
  }>;
}
