"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ResultsPage } from "../../src/screens/ResultsPage";

function ResultsContent() {
  const searchParams = useSearchParams();
  return <ResultsPage jobId={searchParams.get("jobId") ?? ""} />;
}

export default function Page() {
  return (
    <Suspense fallback={<div className="result-loading">Loading result</div>}>
      <ResultsContent />
    </Suspense>
  );
}
