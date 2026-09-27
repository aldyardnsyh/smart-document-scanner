"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CodeBlock } from "../components/CodeBlock";
import { EmptyState } from "../components/EmptyState";
import { ResultViewer } from "../components/ResultViewer";
import { StatusBadge } from "../components/StatusBadge";
import { getJob } from "../lib/api";
import type { Job } from "../lib/types";

function formatDuration(milliseconds: number) {
  return milliseconds < 1000 ? `${Math.round(milliseconds)} ms` : `${(milliseconds / 1000).toFixed(2)} s`;
}

export function ResultsPage({ jobId }: { jobId: string }) {
  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    getJob(jobId)
      .then((record) => active && setJob(record))
      .catch((caught: unknown) => active && setError(caught instanceof Error ? caught.message : "Result not found."))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [jobId]);

  if (loading) {
    return (
      <section className="page-shell page-shell--wide result-loading" aria-label="Loading processing result">
        <div className="skeleton-line skeleton-line--short" />
        <div className="skeleton-line" />
        <div className="result-skeleton" />
      </section>
    );
  }

  if (error || !job) {
    return (
      <section className="page-shell narrow-page">
        <EmptyState
          action={<Link className="button button--primary" href="/history">Return to history</Link>}
          description={error ?? "The requested processing record does not exist."}
          title="Result unavailable"
        />
      </section>
    );
  }

  // A run fails two ways: no document was found, or a document was found and read as empty.
  // The second case still carries `document_detected: true`, so the status has to be tested as
  // well, otherwise a blank capture renders as a successful result with nothing in it.
  if (job.status === "failed" || !job.result?.document_detected) {
    return (
      <section className="page-shell narrow-page">
        <div className="page-heading">
          <div>
            <span className="eyebrow">Processing results: {job.original_name}</span>
            <h1>Failed</h1>
            <p>The pipeline stopped before any field could be extracted. Nothing below was read from this image.</p>
          </div>
          <StatusBadge status={job.status} />
        </div>
        <EmptyState
          action={<Link className="button button--primary" href="/scanner">Try another image</Link>}
          description={job.error?.message ?? "No document contour was detected in this image."}
          icon="alert"
          title="Document not detected"
          tone="danger"
        />
        {job.result ? <CodeBlock code={JSON.stringify(job.result, null, 2)} label="Failure metadata (JSON)" /> : null}
      </section>
    );
  }

  const result = job.result;
  const fields = result.fields.fields;

  return (
    <section className="page-shell page-shell--wide results-page">
      <div className="page-heading page-heading--action">
        <div>
          <span className="eyebrow">Inspection and results</span>
          <h1>Processing results: {job.original_name}</h1>
          <p>Review visual artifacts, extracted fields, confidence, and the raw API response.</p>
        </div>
        <div className="button-row">
          <StatusBadge status={job.status} />
          <Link className="button button--secondary" href="/scanner">Process another</Link>
        </div>
      </div>

      <div className="results-layout">
        <div className="results-main">
          <ResultViewer result={result} />

          <section className="panel fields-panel">
            <div className="panel__heading">
              <h2>Parsed fields</h2>
              <span>
                {result.extracted_field_count} of {result.recognised_field_count} recognised
              </span>
            </div>
            {fields.length ? (
              <dl className="field-list">
                {fields.map((field) => (
                  <div key={field.name}>
                    <dt>{field.name.replaceAll("_", " ")}</dt>
                    <dd>{field.value}</dd>
                    <span><i style={{ width: `${Math.round(field.confidence * 100)}%` }} /></span>
                    <small>
                      {Math.round(field.confidence * 100)}% match score
                      {field.source ? ` · ${field.source.replaceAll("+", " + ")}` : ""}
                    </small>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="muted-copy">No structured fields were recognized. Inspect the OCR text and enhanced image.</p>
            )}

            {result.fields.unclassified?.length ? (
              <div className="residual">
                <h3>Read but not assigned to a field</h3>
                <p className="muted-copy">
                  The engine read this text and the raw JSON carries it, but no field rule
                  matched it. It is grouped by position on the card rather than forced into a
                  schema, so nothing is silently dropped.
                </p>
                <ul>
                  {result.fields.unclassified.map((item, index) => (
                    <li key={`${item.text}-${index}`}>
                      {item.label ? (
                        <span className="residual__label">
                          {item.label.replaceAll("_", " ")}
                          <em>inferred</em>
                        </span>
                      ) : (
                        <span className="residual__label residual__label--none">unlabelled</span>
                      )}
                      <span className="residual__text">{item.text}</span>
                      {typeof item.confidence === "number" ? (
                        <small>{Math.round(item.confidence * 100)}%</small>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>
        </div>

        <aside className="results-sidebar">
          <div className="algorithm-strip">
            <div>
              <span>Detection</span>
              <strong>
                {result.detection_selection === "primary"
                  ? `${Math.round(result.detection_score * 100)}% contour`
                  : "OCR-validated"}
              </strong>
            </div>
            <div><span>Card fills frame</span><strong>{(result.detection_area_ratio * 100).toFixed(1)}%</strong></div>
            <div><span>Rotation</span><strong>{result.rotation_angle.toFixed(1)}°</strong></div>
            <div><span>Enhancer</span><strong>{result.enhancement?.accelerator ?? "python"}</strong></div>
            <div><span>Latency</span><strong>{formatDuration(result.processing_time_ms)}</strong></div>
            <div><span>Input</span><strong>{result.image_width} × {result.image_height}</strong></div>
          </div>

          <section className="panel coverage-panel">
            <div className="coverage-panel__figure">
              <div
                className="confidence-ring confidence-ring--wide"
                style={{ background: `conic-gradient(var(--primary) ${Math.round(result.extraction_coverage * 100) * 3.6}deg, var(--surface-alt) 0)` }}
              >
                <div>
                  <strong>{result.extracted_field_count}/{result.recognised_field_count}</strong>
                  <span>fields extracted</span>
                </div>
              </div>
              <div className="coverage-panel__lede">
                <span className="eyebrow">Extraction coverage</span>
                <p>
                  {result.extracted_field_count} of the {result.recognised_field_count} field
                  types this parser recognises for a{" "}
                  {result.fields.document_type.replaceAll("_", " ")} were recovered.
                </p>
              </div>
            </div>
            <dl className="fact-grid">
              <div><dt>Document type</dt><dd>{result.fields.document_type.replaceAll("_", " ")}</dd></div>
              <div><dt>Classification</dt><dd>{result.fields.classification.score}%</dd></div>
              <div><dt>Mean OCR confidence</dt><dd>{Math.round(result.ocr_confidence * 100)}%</dd></div>
              <div><dt>OCR strategy</dt><dd>{result.ocr?.variant?.replaceAll("_", " ") ?? "unavailable"}</dd></div>
              <div><dt>Crops evaluated</dt><dd>{result.ocr?.evaluated_crops ?? 1}</dd></div>
              <div><dt>Candidate method</dt><dd>{result.detection_method.replaceAll("_", " ")}</dd></div>
            </dl>
            <p className="coverage-panel__note">
              Mean OCR confidence and coverage answer different questions. A high reading only
              says the text was recognised clearly, not that the fields were recovered.
            </p>
          </section>

          <CodeBlock code={JSON.stringify(result, null, 2)} label="Full API response" />
        </aside>
      </div>
    </section>
  );
}
