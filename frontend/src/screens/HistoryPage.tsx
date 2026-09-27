"use client";

import { useEffect, useMemo, useState } from "react";
import { EmptyState } from "../components/EmptyState";
import { HistoryCard } from "../components/HistoryCard";
import { Icon } from "../components/Icon";
import { getHistory } from "../lib/api";
import type { Job } from "../lib/types";

export function HistoryPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [documentType, setDocumentType] = useState("all");
  const [status, setStatus] = useState("all");

  async function loadHistory() {
    setLoading(true);
    setError(null);
    try {
      setJobs(await getHistory());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "History could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadHistory();
  }, []);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return jobs.filter((job) => {
      const type = job.result?.fields.document_type ?? "pending";
      const matchesSearch = !needle || job.original_name.toLowerCase().includes(needle);
      return matchesSearch
        && (documentType === "all" || type === documentType)
        && (status === "all" || job.status === status);
    });
  }, [documentType, jobs, search, status]);

  return (
    <section className="page-shell page-shell--wide history-page">
      <div className="page-heading page-heading--action">
        <div>
          <span className="eyebrow">Session records</span>
          <h1>Processing history</h1>
          <p>Inspect documents processed by the local API during this workspace session.</p>
        </div>
        <button className="button button--secondary" onClick={() => void loadHistory()} type="button">
          Refresh history
        </button>
      </div>

      <div className="filter-bar">
        <label className="search-field">
          <Icon name="search" size={17} />
          <span className="visually-hidden">Search file names</span>
          <input onChange={(event) => setSearch(event.target.value)} placeholder="Search file names" type="search" value={search} />
        </label>
        <label>
          <span className="visually-hidden">Filter by document type</span>
          <select onChange={(event) => setDocumentType(event.target.value)} value={documentType}>
            <option value="all">All document types</option>
            <option value="business_card">Business cards</option>
            <option value="id_card">ID cards</option>
            <option value="receipt">Receipts</option>
            <option value="paper_document">Paper documents</option>
          </select>
        </label>
        <label>
          <span className="visually-hidden">Filter by status</span>
          <select onChange={(event) => setStatus(event.target.value)} value={status}>
            <option value="all">All statuses</option>
            <option value="completed">Completed</option>
            <option value="failed">Needs attention</option>
            <option value="processing">Processing</option>
            <option value="queued">Queued</option>
          </select>
        </label>
      </div>

      {loading ? (
        <div className="loading-grid" aria-label="Loading processing history">
          {Array.from({ length: 4 }, (_, index) => <div className="history-card history-card--skeleton" key={index} />)}
        </div>
      ) : error ? (
        <div className="error-banner" role="alert"><Icon name="alert" size={18} />{error}</div>
      ) : filtered.length ? (
        <div className="history-grid">
          {filtered.map((job) => (
            <HistoryCard
              job={job}
              key={job.id}
              onDeleted={(jobId) => setJobs((current) => current.filter((item) => item.id !== jobId))}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          action={<button className="button button--primary" onClick={() => setSearch("")} type="button">Clear filters</button>}
          description={jobs.length ? "No records match the current filters." : "Process a document in the scanner and it will appear here automatically."}
          title={jobs.length ? "No matching records" : "No documents processed yet"}
        />
      )}

      <aside className="notice-panel">
        <span><Icon name="alert" size={20} /></span>
        <div>
          <h2>Handling unprocessable images</h2>
          <p>Low contrast, severe occlusion, or a document outside the frame can prevent contour detection. The job fails with a clear message and remains available in history.</p>
        </div>
      </aside>
    </section>
  );
}
