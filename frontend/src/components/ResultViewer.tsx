"use client";

import { useState } from "react";
import { Icon } from "./Icon";
import type { ScanResult } from "../lib/types";

type AssetKey = "original" | "detected" | "corrected" | "enhanced";

const assetLabels: Record<AssetKey, string> = {
  original: "Original",
  detected: "Detection",
  corrected: "Corrected",
  enhanced: "Enhanced",
};

export function ResultViewer({ result }: { result: ScanResult }) {
  const available = (Object.keys(assetLabels) as AssetKey[]).filter((key) => Boolean(result.assets[key]));
  const [active, setActive] = useState<AssetKey>(available.includes("detected") ? "detected" : available[0]);
  const [zoom, setZoom] = useState(1);

  return (
    <section className="result-viewer">
      <div className="result-viewer__toolbar">
        <div className="tab-list" role="tablist" aria-label="Processed image views">
          {available.map((key) => (
            <button
              aria-selected={active === key}
              className={active === key ? "is-active" : ""}
              key={key}
              onClick={() => { setActive(key); setZoom(1); }}
              role="tab"
              type="button"
            >
              {assetLabels[key]}
            </button>
          ))}
        </div>
        <div className="zoom-controls" aria-label="Image zoom controls">
          <button aria-label="Zoom out" disabled={zoom <= 1} onClick={() => setZoom((value) => Math.max(1, value - 0.25))} type="button">
            <Icon name="zoom-out" size={17} />
          </button>
          <span>{Math.round(zoom * 100)}%</span>
          <button aria-label="Zoom in" disabled={zoom >= 2} onClick={() => setZoom((value) => Math.min(2, value + 0.25))} type="button">
            <Icon name="zoom-in" size={17} />
          </button>
          <button onClick={() => setZoom(1)} type="button">Fit</button>
        </div>
      </div>
      <div className="result-viewer__canvas">
        <div className="result-viewer__image" style={{ transform: `scale(${zoom})` }}>
          <img alt={`${assetLabels[active]} document view`} src={result.assets[active]} />
        </div>
      </div>
      <div className="result-viewer__caption">
        <span>{assetLabels[active]} artifact</span>
        {result.assets[active] ? (
          <a download href={result.assets[active]}>Download image</a>
        ) : null}
      </div>
    </section>
  );
}
