import fixtures from "./demo-fixtures.json";
import type { Job, ProcessOptions, ScanResult } from "./types";

export const demoMode = true;

const JOBS_KEY = "sds.demo.jobs.v1";
const DELETED_KEY = "sds.demo.deleted.v1";
const FIXTURES = fixtures as unknown as Job[];
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

let memoryJobs: Job[] = [];
let memoryDeleted: string[] = [];

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

const isStrArr = (v: unknown): v is string[] =>
  Array.isArray(v) && v.every((x) => typeof x === "string");

const isJobArr = (v: unknown): v is Job[] =>
  Array.isArray(v) &&
  v.every((x) => {
    const j = x as Job | null;
    return (
      !!j &&
      typeof j.id === "string" &&
      typeof j.status === "string" &&
      typeof j.created_at === "string"
    );
  });

function readList<T>(key: string, guard: (v: unknown) => v is T): T | null {
  const s = storage();
  if (!s) return null;
  try {
    const raw = s.getItem(key);
    if (raw === null) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!guard(parsed)) throw new Error("invalid shape");
    return parsed;
  } catch {
    try {
      s.removeItem(key);
    } catch {
      /* ignore */
    }
    return null;
  }
}

function writeList(key: string, value: unknown): void {
  if (key === JOBS_KEY) memoryJobs = value as Job[];
  else if (key === DELETED_KEY) memoryDeleted = value as string[];
  const s = storage();
  if (!s) return;
  try {
    s.setItem(key, JSON.stringify(value));
  } catch {
    /* quota or privacy mode */
  }
}

const deletedIds = (): string[] => readList<string[]>(DELETED_KEY, isStrArr) ?? memoryDeleted;
const userJobs = (): Job[] => readList<Job[]>(JOBS_KEY, isJobArr) ?? memoryJobs;

export function seedJobs(): Job[] {
  const deleted = new Set(deletedIds());
  return clone(FIXTURES.filter((j) => !deleted.has(j.id)));
}

export function history(): Job[] {
  return [...seedJobs(), ...clone(userJobs())].sort(
    (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
  );
}

interface PendingRun {
  id: string;
  fileName: string;
  options: ProcessOptions;
  startedAt: number;
  durationMs: number;
}

let pending: PendingRun | null = null;

const STAGES = [
  { stage: "queued", progress: 4, message: "Queued for processing." },
  { stage: "detect", progress: 16, message: "Detecting document contour." },
  { stage: "correct", progress: 36, message: "Correcting perspective." },
  { stage: "enhance", progress: 56, message: "Enhancing legibility." },
  { stage: "ocr", progress: 76, message: "Reading text." },
  { stage: "parse", progress: 92, message: "Mapping fields." },
] as const;

function targetId(run: PendingRun): string {
  const n = run.fileName.toLowerCase();
  if (n.includes("no_document")) return "seed-05";
  if (n.includes("blank")) return "seed-06";
  const t = run.options.documentType;
  if (t === "receipt") return "seed-02";
  if (t === "id_card") return "seed-03";
  if (t === "paper_document") return "seed-04";
  if (t === "business_card") return "seed-01";
  if (/receipt|invoice/.test(n)) return "seed-02";
  if (/ktp|nik|id/.test(n)) return "seed-03";
  if (/mou|memo|paper|letter/.test(n)) return "seed-04";
  return "seed-01";
}

function finish(run: PendingRun): Job {
  const base = FIXTURES.find((j) => j.id === targetId(run));
  if (!base) throw new Error("Job not found");
  const now = new Date().toISOString();
  const failed = base.status === "failed";
  const job: Job = clone(base);
  job.id = run.id;
  job.original_name = run.fileName;
  job.status = failed ? "failed" : "completed";
  job.stage = failed ? "failed" : "parse";
  job.progress = 100;
  job.message = failed ? base.error?.message ?? base.message : "Processing complete.";
  job.created_at = now;
  job.updated_at = now;
  job.error = failed && base.error ? clone(base.error) : null;
  job.result = base.result ? { ...(clone(base.result) as ScanResult), job_id: run.id } : null;
  writeList(JOBS_KEY, [...userJobs().filter((j) => j.id !== job.id), job]);
  pending = null;
  return job;
}

function advance(run: PendingRun, now: number): Job {
  if (now - run.startedAt >= run.durationMs) return finish(run);
  const ratio = Math.max(0, Math.min(1, (now - run.startedAt) / run.durationMs));
  const step = STAGES[Math.min(STAGES.length - 1, Math.floor(ratio * STAGES.length))];
  return {
    id: run.id,
    original_name: run.fileName,
    status: step.stage === "queued" ? "queued" : "processing",
    stage: step.stage,
    progress: step.progress,
    message: step.message,
    created_at: new Date(run.startedAt).toISOString(),
    updated_at: new Date(now).toISOString(),
    result: null,
    error: null,
  };
}

export function getJob(id: string): Job {
  if (pending && pending.id === id) return advance(pending, Date.now());
  const found = [...seedJobs(), ...userJobs()].find((j) => j.id === id);
  if (!found) throw new Error("Job not found");
  return found;
}

export function deleteJob(id: string): { deleted: boolean } {
  if (pending && pending.id === id) pending = null;
  const users = userJobs();
  if (users.some((j) => j.id === id)) {
    writeList(JOBS_KEY, users.filter((j) => j.id !== id));
    return { deleted: true };
  }
  if (FIXTURES.some((j) => j.id === id)) {
    const deleted = deletedIds();
    if (!deleted.includes(id)) writeList(DELETED_KEY, [...deleted, id]);
  }
  return { deleted: true };
}

export function getHealth() {
  return {
    status: "demo",
    ocr_engine: "PP-OCRv6 (sample)",
    ocr_engine_available: true,
    ocr_engine_error: null,
    cpp_accelerator_available: true,
  };
}

export async function createProcess(file: File, options: ProcessOptions): Promise<Job> {
  const id = (Date.now().toString(16) + Math.random().toString(16).slice(2)).slice(0, 12);
  const startedAt = Date.now();
  pending = { id, fileName: file.name, options: { ...options }, startedAt, durationMs: 3200 };
  const iso = new Date(startedAt).toISOString();
  return {
    id,
    original_name: file.name,
    status: "queued",
    stage: "queued",
    progress: 4,
    message: "Queued for processing.",
    created_at: iso,
    updated_at: iso,
    result: null,
    error: null,
  };
}

export function cancelJob(id: string): void {
  if (pending && pending.id === id) pending = null;
}

export async function pollJob(
  id: string,
  onUpdate: (job: Job) => void,
  signal?: AbortSignal,
): Promise<Job> {
  for (;;) {
    if (signal?.aborted) throw new DOMException("Polling stopped", "AbortError");
    const job = getJob(id);
    onUpdate(job);
    if (job.status === "completed" || job.status === "failed") return job;
    await new Promise<void>((resolve, reject) => {
      const onAbort = () => {
        clearTimeout(timer);
        reject(new DOMException("Polling stopped", "AbortError"));
      };
      const timer = setTimeout(() => {
        signal?.removeEventListener("abort", onAbort);
        resolve();
      }, 300);
      signal?.addEventListener("abort", onAbort);
    });
  }
}