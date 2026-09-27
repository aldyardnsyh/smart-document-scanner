import { useEffect, useState, type CSSProperties } from "react";

import { Icon } from "./Icon";

const stages = [
  { key: "detect", label: "Detect" },
  { key: "correct", label: "Correct" },
  { key: "enhance", label: "Enhance" },
  { key: "ocr", label: "OCR" },
  { key: "parse", label: "Parse" },
];

const CANCEL_AFTER_SECONDS = 25;

function formatElapsed(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

interface JobProgressProps {
  stage: string;
  progress: number;
  message: string;
  onCancel?: () => void;
}

export function JobProgress({ stage, progress, message, onCancel }: JobProgressProps) {
  const [elapsed, setElapsed] = useState(0);
  const activeIndex = Math.max(0, stages.findIndex((item) => item.key === stage));
  const percent = Math.round(progress);
  const finished = progress >= 100;

  useEffect(() => {
    setElapsed(0);
    const timer = window.setInterval(() => {
      setElapsed((value) => value + 1);
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <section className="job-progress" aria-live="polite">
      <div className="job-progress__heading">
        <div>
          <span className="eyebrow">Synchronous pipeline</span>
          <h2>Processing document</h2>
        </div>
        <div
          aria-label={`Processing ${percent} percent`}
          aria-valuemax={100}
          aria-valuemin={0}
          aria-valuenow={percent}
          className={`progress-dial${finished ? " is-finished" : ""}`}
          role="progressbar"
          style={{ "--dial-angle": `${percent * 3.6}deg` } as CSSProperties}
        >
          <span className="progress-dial__sheen" aria-hidden="true" />
          <span className="progress-dial__face">
            <strong>{percent}</strong>
            <small>percent</small>
          </span>
        </div>
      </div>

      <div className="progress-track">
        <span style={{ width: `${Math.max(2, progress)}%` }} />
      </div>

      <div className="job-progress__status">
        <p className="job-progress__message">
          <Icon name="scan" size={16} />
          {message}
        </p>
        <p className="job-progress__elapsed">
          <span className="visually-hidden">Elapsed time </span>
          <span aria-hidden="true">{formatElapsed(elapsed)}</span>
        </p>
      </div>

      <ol className="stage-list">
        {stages.map((item, index) => {
          const complete = index < activeIndex || finished;
          const active = index === activeIndex && !finished;
          return (
            <li
              className={complete ? "is-complete" : active ? "is-active" : ""}
              key={item.key}
            >
              <span>{complete ? <Icon name="check" size={14} /> : index + 1}</span>
              {item.label}
              {active ? <span className="stage-list__sweep" aria-hidden="true" /> : null}
            </li>
          );
        })}
      </ol>

      {onCancel && !finished && elapsed >= CANCEL_AFTER_SECONDS ? (
        <div className="job-progress__cancel">
          <p>Heavy captures take longer because several readings are compared.</p>
          <button className="button button--secondary" onClick={onCancel} type="button">
            Stop processing
          </button>
        </div>
      ) : null}
    </section>
  );
}
