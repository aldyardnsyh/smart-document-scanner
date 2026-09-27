"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { deleteJob } from "../lib/api";
import type { Job } from "../lib/types";
import { Icon } from "./Icon";
import { StatusBadge } from "./StatusBadge";

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

interface HistoryCardProps {
  job: Job;
  onDeleted: (jobId: string) => void;
}

export function HistoryCard({ job, onDeleted }: HistoryCardProps) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const result = job.result;
  const documentType = result?.fields.document_type.replaceAll("_", " ") ?? "Pending classification";
  const thumbnail = result?.assets.original;

  useEffect(() => {
    if (!confirming) return;
    function cancel(event: KeyboardEvent) {
      if (event.key === "Escape") setConfirming(false);
    }
    window.addEventListener("keydown", cancel);
    return () => window.removeEventListener("keydown", cancel);
  }, [confirming]);

  async function remove() {
    setDeleting(true);
    setError(null);
    try {
      await deleteJob(job.id);
      onDeleted(job.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The record could not be deleted.");
      setDeleting(false);
      setConfirming(false);
    }
  }

  // A failed run still carries a result object, populated with `document_detected: false` and
  // zeroed metrics. Testing the presence of `result` therefore treated a failure exactly like
  // a success: the card showed an OCR reading and a confidence bar for an image nothing was
  // read from. The outcome has to be tested directly.
  const failed = job.status === "failed" || result?.document_detected === false;

  return (
    <article
      className={failed ? "history-card history-card--failed" : "history-card"}
      data-job-id={job.id}
      data-outcome={failed ? "failed" : "ok"}
    >
      <div className="history-card__preview">
        {thumbnail ? <img alt={`Preview of ${job.original_name}`} src={thumbnail} /> : <Icon name="document" size={28} />}
        <button
          aria-label={`Delete ${job.original_name}`}
          className="history-card__delete"
          disabled={deleting}
          onClick={() => setConfirming(true)}
          type="button"
        >
          <Icon name="trash" size={15} />
        </button>
        <StatusBadge status={job.status} />
        {confirming ? (
          <div aria-label={`Confirm deletion of ${job.original_name}`} className="delete-confirm" role="alertdialog">
            <strong>Delete this record?</strong>
            <div>
              <button disabled={deleting} onClick={() => setConfirming(false)} type="button">Cancel</button>
              <button disabled={deleting} onClick={() => void remove()} type="button">
                {deleting ? "Deleting" : "Delete"}
              </button>
            </div>
          </div>
        ) : null}
      </div>
      <div className="history-card__body">
        <span className="mono-label">{documentType}</span>
        <h2 title={job.original_name}>{job.original_name}</h2>
        <p>{formatDate(job.created_at)}</p>
        {failed ? (
          <div className="history-card__failure">
            <p className="history-card__failed-label">
              <Icon name="alert" size={15} />
              Failed &middot; nothing extracted
            </p>
            <p className="history-card__error">
              {job.error?.message ?? "No document was detected, so no fields were read."}
            </p>
          </div>
        ) : result ? (
          <>
            <dl className="history-card__metrics">
              <div>
                <dt>OCR</dt>
                <dd>{Math.round(result.ocr_confidence * 100)}%</dd>
              </div>
              <div>
                <dt>Latency</dt>
                <dd>{Math.round(result.processing_time_ms)} ms</dd>
              </div>
            </dl>
            <div
              aria-label={`OCR confidence ${Math.round(result.ocr_confidence * 100)} percent`}
              className="history-card__confidence"
            >
              <span style={{ width: `${Math.max(2, result.ocr_confidence * 100)}%` }} />
            </div>
          </>
        ) : (
          <p className="history-card__error">{job.error?.message ?? job.message}</p>
        )}
        {error ? <p className="history-card__error" role="alert">{error}</p> : null}
        <Link className="button button--secondary button--full" href={`/results?jobId=${job.id}`}>
          Inspect result
          <Icon name="chevron" size={16} />
        </Link>
      </div>
    </article>
  );
}
