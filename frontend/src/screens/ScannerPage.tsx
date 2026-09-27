"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Icon } from "../components/Icon";
import { JobProgress } from "../components/JobProgress";
import { createProcess, pollJob } from "../lib/api";
import type { Job, ProcessOptions } from "../lib/types";

const MAX_FILE_SIZE = 10 * 1024 * 1024;

export function ScannerPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const dragDepthRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [options, setOptions] = useState<ProcessOptions>({
    documentType: "auto",
    fastDenoise: false,
    cppAcceleration: true,
  });

  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview);
      abortRef.current?.abort();
    };
  }, [preview]);

  function chooseFile(nextFile: File | undefined) {
    setError(null);
    setJob(null);
    if (!nextFile) return;
    if (!nextFile.type.startsWith("image/")) {
      setError("Choose a supported image file.");
      return;
    }
    if (nextFile.size > MAX_FILE_SIZE) {
      setError("The selected file is larger than 10 MB.");
      return;
    }
    if (preview) URL.revokeObjectURL(preview);
    setFile(nextFile);
    setPreview(URL.createObjectURL(nextFile));
  }

  // Drag events fire for every child element the pointer crosses, so a naive onDragLeave
  // makes the highlight flicker off mid-drag. Counting enter/leave pairs keeps the active
  // state stable until the drag actually leaves the dropzone.
  function handleDragEnter(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    dragDepthRef.current += 1;
    setDragActive(true);
  }

  function handleDragLeave(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) setDragActive(false);
  }

  function handleDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    dragDepthRef.current = 0;
    setDragActive(false);
    // A folder or a multi-file drop puts entries that are not images first, so take the
    // first usable image rather than blindly trusting index 0.
    const dropped = Array.from(event.dataTransfer.files ?? []);
    const image = dropped.find((item) => item.type.startsWith("image/"));
    if (!image) {
      setError(
        dropped.length
          ? "None of the dropped files is a supported image."
          : "Nothing was dropped. Drag an image file onto the dropzone."
      );
      return;
    }
    if (dropped.length > 1) {
      setError(`${dropped.length} files were dropped. Using the first image, ${image.name}.`);
    }
    chooseFile(image);
  }

  async function processDocument() {
    if (!file) {
      setError("Select an image before starting the pipeline.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const created = await createProcess(file, options);
      setJob(created);
      const controller = new AbortController();
      abortRef.current = controller;
      const finished = await pollJob(created.id, setJob, controller.signal);
      // A failed run is still a result. BRIEF scenario 4 asks for a graceful, observable
      // failure, so every terminal state routes to the results page where the failure is
      // shown as failed, with the reason and the fact that nothing was extracted. Keeping
      // it as an inline scanner error would hide the failure case entirely.
      router.push(`/results?jobId=${finished.id}`);
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") {
        // The user stopped the run. Clear the monitor so the panel returns to its empty
        // state instead of leaving a frozen progress readout on screen.
        setJob(null);
        setFile(null);
        if (preview) URL.revokeObjectURL(preview);
        setPreview(null);
        if (inputRef.current) inputRef.current.value = "";
        return;
      }
      setError(caught instanceof Error ? caught.message : "The processing request failed.");
    } finally {
      setSubmitting(false);
    }
  }

  function reset() {
    abortRef.current?.abort();
    if (preview) URL.revokeObjectURL(preview);
    setFile(null);
    setPreview(null);
    setJob(null);
    setError(null);
    setSubmitting(false);
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <section className="page-shell page-shell--wide scanner-page">
      <div className="page-heading">
        <span className="eyebrow">Scanner workbench</span>
        <h1>Document upload and processing</h1>
        <p>Select a document image, confirm extraction settings, and run the full pipeline.</p>
      </div>

      <div className="scanner-grid">
        <div className="panel upload-panel">
          <div className="panel__heading">
            <div>
              <span className="step-number">01</span>
              <h2>Source ingestion</h2>
            </div>
            {file && !submitting ? <button className="text-button" onClick={reset} type="button">Remove file</button> : null}
          </div>
          <input
            accept="image/jpeg,image/png,image/webp,image/bmp,image/tiff"
            className="visually-hidden"
            onChange={(event) => chooseFile(event.target.files?.[0])}
            ref={inputRef}
            type="file"
          />
          <div
            aria-label="Document dropzone. Drop an image here, or press Enter to browse."
            className={dragActive ? "dropzone is-active" : "dropzone"}
            onClick={() => inputRef.current?.click()}
            onDragEnter={handleDragEnter}
            onDragLeave={handleDragLeave}
            onDragOver={(event) => {
              event.preventDefault();
              if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
            }}
            onDrop={handleDrop}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                inputRef.current?.click();
              }
            }}
            role="button"
            tabIndex={0}
          >
            {preview ? (
              <>
                <img alt="Selected document preview" src={preview} />
                <span className="dropzone__replace">Choose another image</span>
              </>
            ) : (
              <>
                <span className="dropzone__icon"><Icon name="upload" size={28} /></span>
                <strong>Drop a document image here</strong>
                <span>or select a file from your device</span>
                <small>JPG, PNG, WEBP, BMP, TIFF, up to 10 MB</small>
              </>
            )}
          </div>
          {file ? <p className="file-meta"><Icon name="document" size={15} />{file.name}<span>{(file.size / 1024 / 1024).toFixed(2)} MB</span></p> : null}

          <div className="form-section">
            <span className="step-number">02</span>
            <div className="form-section__content">
              <h2>Extraction heuristics</h2>
              <fieldset className="document-type-field">
                <legend>Document type</legend>
                <div className="document-type-options">
                  {([
                    ["auto", "Automatic"],
                    ["business_card", "Business card"],
                    ["id_card", "ID card"],
                    ["receipt", "Receipt"],
                    ["paper_document", "Paper document"],
                  ] as const).map(([value, label]) => (
                    <button
                      aria-pressed={options.documentType === value}
                      className={options.documentType === value ? "is-active" : ""}
                      disabled={submitting}
                      key={value}
                      onClick={() => setOptions((current) => ({ ...current, documentType: value }))}
                      type="button"
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </fieldset>
              <label className="check-field">
                <input
                  checked={options.fastDenoise}
                  disabled={submitting}
                  onChange={(event) => setOptions((value) => ({ ...value, fastDenoise: event.target.checked }))}
                  type="checkbox"
                />
                <span><strong>High-quality denoise</strong><small>Slower processing for noisy captures</small></span>
              </label>
              <label className="check-field">
                <input
                  checked={options.cppAcceleration}
                  disabled={submitting}
                  onChange={(event) => setOptions((value) => ({ ...value, cppAcceleration: event.target.checked }))}
                  type="checkbox"
                />
                <span><strong>Use C++ accelerator</strong><small>Falls back to Python when the binary is unavailable</small></span>
              </label>
            </div>
          </div>

          {error ? <div className="error-banner" role="alert"><Icon name="alert" size={18} /><span>{error}</span></div> : null}
          <button className="button button--primary button--full" disabled={!file || submitting} onClick={processDocument} type="button">
            {submitting ? "Processing document" : "Process document"}
            {!submitting ? <Icon name="chevron" size={17} /> : null}
          </button>
        </div>

        <div className="panel execution-panel">
          {job ? (
            <JobProgress
              message={job.message}
              onCancel={() => abortRef.current?.abort()}
              progress={job.progress}
              stage={job.stage}
            />
          ) : (
            <div className="execution-empty">
              <div className="execution-empty__visual">
                <span className="scan-corner scan-corner--one" />
                <span className="scan-corner scan-corner--two" />
                <span className="scan-corner scan-corner--three" />
                <span className="scan-corner scan-corner--four" />
                <Icon name="scan" size={34} />
              </div>
              <span className="eyebrow">Execution monitor</span>
              <h2>No active process</h2>
              <p>Select an image and run the pipeline to inspect live stage progress here.</p>
            </div>
          )}
          {job ? (
            <div className="pipeline-console">
              <div><span>Job ID</span><code>{job.id}</code></div>
              <div><span>Source</span><code>{job.original_name}</code></div>
              <div><span>State</span><code>{job.stage}</code></div>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
