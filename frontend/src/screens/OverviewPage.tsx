import Link from "next/link";
import { CodeBlock } from "../components/CodeBlock";
import { Icon } from "../components/Icon";

const pipeline = [
  { step: "01", title: "Detect", copy: "Find the dominant four-corner document contour." },
  { step: "02", title: "Correct", copy: "Apply a homography transform for a stable top-down view." },
  { step: "03", title: "Enhance", copy: "Balance contrast, suppress noise, and sharpen text." },
  { step: "04", title: "OCR", copy: "Read text lines with per-line confidence from the OCR engine." },
  { step: "05", title: "Parse", copy: "Map recognized text into document-specific fields." },
];

const documentTypes = [
  {
    name: "Business card",
    code: "business_card",
    fields: ["name", "company", "email", "phone"],
  },
  {
    name: "ID card",
    code: "id_card",
    fields: ["nik", "name", "birth_date", "blood_type"],
  },
  {
    name: "Receipt",
    code: "receipt",
    fields: ["merchant", "reference_number", "date", "total"],
  },
  {
    name: "Paper document",
    code: "paper_document",
    fields: ["title", "document_number", "date"],
  },
];

const curl = `curl -X POST http://localhost:8000/api/process \\
  -F "file=@document.jpg" \\
  -F "doc_type=auto"`;

export function OverviewPage() {
  return (
    <>
      <section className="hero page-shell">
        <div className="hero__copy">
          <span className="eyebrow">Computer Vision + OCR Document Pipeline</span>
          <h1>Turn an angled document photo into inspectable data.</h1>
          <p>
            Detect the document, correct perspective, improve readability, extract text, and inspect every
            processing artifact in one workbench.
          </p>
          <div className="button-row">
            <Link className="button button--primary" href="/scanner">
              Open scanner workbench
              <Icon name="chevron" size={17} />
            </Link>
            <a className="button button--secondary" href="/docs" target="_blank" rel="noreferrer">
              Read API docs
            </a>
          </div>
        </div>
        <div className="hero__diagram" aria-label="Five-stage processing pipeline">
          <div className="hero__document">
            <span className="hero__corner hero__corner--one" />
            <span className="hero__corner hero__corner--two" />
            <span className="hero__corner hero__corner--three" />
            <span className="hero__corner hero__corner--four" />
            <div className="hero__scan-line" />
            <p>INPUT_FRAME</p>
          </div>
          <div className="hero__pipeline">
            {pipeline.slice(0, 4).map((item) => <span key={item.step}>{item.title}</span>)}
          </div>
        </div>
      </section>

      <section className="page-shell section-block">
        <div className="section-heading">
          <span className="eyebrow">Pipeline</span>
          <h2>How the five-stage pipeline works</h2>
          <p>Each stage writes an inspectable artifact and reports progress to the active job.</p>
        </div>
        <ol className="pipeline-grid">
          {pipeline.map((item) => (
            <li key={item.step}>
              <span>{item.step}</span>
              <h3>{item.title}</h3>
              <p>{item.copy}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="page-shell section-block">
        <div className="section-heading section-heading--split">
          <div>
            <span className="eyebrow">Structured output</span>
            <h2>Targeted document types and schemas</h2>
          </div>
          <p>Automatic classification is available, or choose a target type before processing.</p>
        </div>
        <div className="document-types">
          {documentTypes.map((item) => (
            <article key={item.code}>
              <div className="document-types__icon"><Icon name="document" size={22} /></div>
              <h3>{item.name}</h3>
              <code>{item.code}</code>
              <ul>
                {item.fields.map((field) => <li key={field}>{field}</li>)}
              </ul>
            </article>
          ))}
        </div>
      </section>

      <section className="page-shell section-block api-callout">
        <div>
          <span className="eyebrow">REST API</span>
          <h2>Use the same pipeline from your application.</h2>
          <p>The browser workbench and API call the identical processing service.</p>
        </div>
        <CodeBlock code={curl} label="POST /api/process" />
      </section>
    </>
  );
}
