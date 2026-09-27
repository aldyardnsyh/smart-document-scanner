import type { Job, ProcessOptions } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL
  ?? (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8000" : "");

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

export function createProcess(file: File, options: ProcessOptions): Promise<Job> {
  const form = new FormData();
  form.append("file", file);
  form.append("doc_type", options.documentType);
  form.append("fast_denoise", String(options.fastDenoise));
  form.append("cpp_acceleration", String(options.cppAcceleration));
  return request<Job>("/api/process", { method: "POST", body: form });
}

export function getJob(jobId: string): Promise<Job> {
  return request<Job>(`/api/jobs/${encodeURIComponent(jobId)}`);
}

export function deleteJob(jobId: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/api/jobs/${encodeURIComponent(jobId)}`, {
    method: "DELETE",
  });
}

export function getHistory(): Promise<Job[]> {
  return request<Job[]>("/api/history");
}

export function getHealth(): Promise<{
  status: string;
  ocr_engine: string;
  ocr_engine_available: boolean;
  ocr_engine_error: string | null;
  cpp_accelerator_available: boolean;
}> {
  return request("/api/health");
}

export async function pollJob(
  jobId: string,
  onUpdate: (job: Job) => void,
  signal?: AbortSignal,
): Promise<Job> {
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
