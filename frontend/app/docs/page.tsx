import Link from "next/link";
import { CodeBlock } from "../../src/components/CodeBlock";
import { Icon } from "../../src/components/Icon";

const endpoints = [
  {
    method: "POST",
    path: "/api/process",
    description: "Accept multipart fields file, doc_type, fast_denoise, and cpp_acceleration, then queue a job.",
  },
  {
    method: "GET",
    path: "/api/jobs/{id}",
    description: "Return job status, stage progress, and the full result once processing completes.",
  },
  {
    method: "DELETE",
    path: "/api/jobs/{id}",
    description: "Remove a job and its stored artifacts from the server history.",
  },
  {
    method: "GET",
    path: "/api/history",
    description: "List recent jobs, newest first, for the history screen.",
  },
  {
    method: "GET",
    path: "/api/health",
    description: "Report service health plus the OCR engine and accelerator in use.",
  },
];

const curl = `curl -X POST http://localhost:8000/api/process \\
  -F "file=@document.jpg" \\
  -F "doc_type=auto" \\
  -F "fast_denoise=true" \\
  -F "cpp_acceleration=true"`;

const responseShape = `{
  "job_id": "9f2c1e70",
  "document_detected": true,
  "rotation_angle": 1.4,
  "detection_area_ratio": 0.62,
  "detection_method": "contour",
  "detection_score": 0.91,
  "detection_selection": "largest_quad",
  "corners": [[82, 64], [1518, 71], [1509, 1562], [75, 1551]],
  "image_width": 1600,
  "image_height": 1200,
  "processing_time_ms": 1840,
  "ocr_confidence": 0.88,
  "extracted_field_count": 4,
  "recognised_field_count": 4,
  "extraction_coverage": 1.0,
  "fields": {
    "document_type": "receipt",
    "classification": { "document_type": "receipt", "score": 0.93, "signals": ["total"] },
    "fields": [
      { "name": "merchant", "value": "Kopi Senja", "confidence": 0.9, "source": "line" }
    ]
  },
  "raw_text": "KOPI SENJA\\nTotal 48.000",
  "warnings": [],
  "assets": {
    "original": "/api/jobs/9f2c1e70/assets/original.jpg",
    "detected": "/api/jobs/9f2c1e70/assets/detected.jpg",
    "corrected": "/api/jobs/9f2c1e70/assets/corrected.jpg",
    "enhanced": "/api/jobs/9f2c1e70/assets/enhanced.jpg"
  }
}`;

export default function Page() {
  return (
    <section className="page-shell page-shell--wide docs-page">
      <div className="page-heading">
        <span className="eyebrow">Reference</span>
        <h1>API and demo reference</h1>
        <p>What the hosted demo actually does, and the REST contract the full pipeline exposes.</p>
      </div>

      <section className="section-block" id="demo">
        <div className="section-heading">
          <h2>How demo mode works</h2>
          <p>
            The demo ships as a static export on Vercel. There is no Python, OpenCV, or ONNX runtime on the
            server, so nothing is processed remotely.
          </p>
        </div>
        <ul>
          <li>Your file stays in the browser. It is never uploaded.</li>
          <li>Results come from a stored sample run of the real pipeline.</li>
          <li>Six sample records load on the first visit.</li>
          <li>New records are saved to this browser&apos;s localStorage.</li>
        </ul>
        <p>
          To run the real pipeline, build the container with{" "}
          <code>docker build -t smart-document-scanner . &amp;&amp; docker run -p 8000:8000 smart-document-scanner</code>{" "}
          and open <code>http://localhost:8000</code>. The same image runs on Railway, or locally with the
          Python entrypoint.
        </p>
      </section>

      <section className="section-block" id="rest-api">
        <div className="section-heading">
          <h2>REST API</h2>
          <p>Five endpoints cover processing, job polling, history, and health.</p>
        </div>
        <div className="panel">
          <table>
            <caption className="mono-label">Endpoint reference</caption>
            <thead>
              <tr>
                <th scope="col">Method</th>
                <th scope="col">Path</th>
                <th scope="col">Description</th>
              </tr>
            </thead>
            <tbody>
              {endpoints.map((endpoint) => (
                <tr key={`${endpoint.method} ${endpoint.path}`}>
                  <td>{endpoint.method}</td>
                  <td>
                    <code>{endpoint.path}</code>
                  </td>
                  <td>{endpoint.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="section-block" id="example-request">
        <div className="section-heading">
          <h2>Example request</h2>
          <p>Send the image as multipart form data. Fast denoise and C++ acceleration are optional booleans.</p>
        </div>
        <CodeBlock label="POST /api/process" code={curl} />
      </section>

      <section className="section-block" id="response-shape">
        <div className="section-heading">
          <h2>Response shape</h2>
          <p>Every job result carries detection facts, extraction coverage, parsed fields, and artifact URLs.</p>
        </div>
        <CodeBlock label="Job result (JSON, abbreviated)" code={responseShape} />
      </section>

      <section className="section-block">
        <div className="button-row">
          <Link className="button button--primary" href="/scanner">
            Open scanner
            <Icon name="chevron" size={17} />
          </Link>
          <Link className="button button--secondary" href="/history">
            View history
          </Link>
        </div>
      </section>
    </section>
  );
}