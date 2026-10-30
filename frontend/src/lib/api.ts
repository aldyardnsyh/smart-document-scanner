import * as demo from "./demo";
import type { Job, ProcessOptions } from "./types";

export const DEMO_MODE =
  process.env.NEXT_PUBLIC_DEMO_MODE === "1" || !process.env.NEXT_PUBLIC_API_BASE_URL;

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, init);
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(payload?.detail ?? `Request failed with status ${response.status}`, response.status);
  }
  return (await response.json()) as T;
}

export interface HealthStatus {
  status: string;
  ocr_engine: string;
  ocr_engine_available: boolean;
  ocr_engine_error: string | null;
  cpp_accelerator_available: boolean;
}

export function createProcess(file: File, options: ProcessOptions): Promise<Job> {
  if (DEMO_MODE) return demo.createProcess(file, options);

  const form = new FormData();
  form.append("file", file);
  form.append("doc_type", options.documentType);
  form.append("fast_denoise", String(options.fastDenoise));
  form.append("cpp_acceleration", String(options.cppAcceleration));
  return request<Job>("/api/process", { method: "POST", body: form });
}

export function getJob(jobId: string): Promise<Job> {
  if (DEMO_MODE) return Promise.resolve().then(() => demo.getJob(jobId));
  return request<Job>(`/api/jobs/${encodeURIComponent(jobId)}`);
}

export function deleteJob(jobId: string): Promise<{ deleted: boolean }> {
  if (DEMO_MODE) return Promise.resolve(demo.deleteJob(jobId));
  return request<{ deleted: boolean }>(`/api/jobs/${encodeURIComponent(jobId)}`, {
    method: "DELETE",
  });
}

export function getHistory(): Promise<Job[]> {
  if (DEMO_MODE) return Promise.resolve(demo.history());
  return request<Job[]>("/api/history");
}

export function getHealth(): Promise<HealthStatus> {
  if (DEMO_MODE) return Promise.resolve(demo.getHealth());
  return request<HealthStatus>("/api/health");
}

export async function pollJob(
  jobId: string,
  onUpdate: (job: Job) => void,
  signal?: AbortSignal,
): Promise<Job> {
  if (DEMO_MODE) {
    try {
      return await demo.pollJob(jobId, onUpdate, signal);
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        demo.cancelJob(jobId);
      }
      throw error;
    }
  }

  while (true) {
    if (signal?.aborted) {
      throw new DOMException("Polling stopped", "AbortError");
    }
    const job = await getJob(jobId);
    onUpdate(job);
    if (job.status === "completed" || job.status === "failed") {
      return job;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 450));
  }
}