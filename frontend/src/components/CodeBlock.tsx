"use client";

import { useState } from "react";
import { Icon } from "./Icon";

interface CodeBlockProps {
  code: string;
  label?: string;
}

export function CodeBlock({ code, label = "API Response (JSON)" }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  async function copyCode() {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <section className="code-block" aria-label={label}>
      <div className="code-block__bar">
        <span>{label}</span>
        <button className="icon-button icon-button--dark" onClick={copyCode} type="button">
          <Icon name={copied ? "check" : "copy"} size={15} />
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre><code>{code}</code></pre>
    </section>
  );
}
