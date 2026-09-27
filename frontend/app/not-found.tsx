import Link from "next/link";

export default function NotFound() {
  return (
    <section className="page-shell narrow-page">
      <span className="eyebrow">404</span>
      <h1>Page not found</h1>
      <p>The requested workbench view does not exist.</p>
      <Link className="button button--primary" href="/">Return to overview</Link>
    </section>
  );
}
