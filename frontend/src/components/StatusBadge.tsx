import type { JobStatus } from "../lib/types";

const labels: Record<JobStatus, string> = {
  queued: "Queued",
  processing: "Processing",
  completed: "Completed",
  // Say it plainly. Softening a failure into "needs attention" hides the failure case
  // that the scenario suite is supposed to demonstrate.
  failed: "Failed",
};

export function StatusBadge({ status }: { status: JobStatus }) {
  return <span className={`status-badge status-badge--${status}`}>{labels[status]}</span>;
}
