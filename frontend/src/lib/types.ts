export type JobStatus = "queued" | "processing" | "completed" | "failed";
export type DocumentType = "auto" | "business_card" | "id_card" | "receipt" | "paper_document";

export interface Classification {
  document_type: string;
  score: number;
  signals: string[];
}

export interface ExtractedField {
  name: string;
  value: string;
  confidence: number;
  source: string;
}

export interface ScanResult {
  job_id: string;
  document_detected: boolean;
  rotation_angle: number;
  detection_area_ratio: number;
  detection_method: string;
  detection_score: number;
  detection_selection: string;
  corners: number[][];
  image_width: number;
  image_height: number;
  processing_time_ms: number;
  ocr_confidence: number;
  // Extraction coverage is reported as an explicit fraction of the recognisable schema so
  // the UI never has to invent a headline percentage from OCR confidence alone.
  extracted_field_count: number;
  recognised_field_count: number;
  extraction_coverage: number;
  fields: {
    document_type: string;
    classification: Classification;
    fields: ExtractedField[];
    // Text the engine read that no field rule claimed. Grouped by position, and labelled
    // only when the content supports a name, so the UI can show it instead of dropping it.
    unclassified?: Array<{
      text: string;
      confidence?: number;
      reason: string;
      tier?: number;
      label?: string | null;
      inferred?: boolean;
      line_count?: number;
    }>;
  };
  raw_text: string;
  warnings: string[];
  ocr?: {
    variant: string;
    psm?: number;
    selection_score?: number;
    candidates?: number;
    evaluated_crops?: number;
  };
  enhancement?: {
    accelerator: string;
    threshold: string;
  };
  assets: {
    original: string;
    detected: string;
    corrected?: string;
    enhanced?: string;
  };
}

export interface JobError {
  code: string;
  message: string;
}

export interface Job {
  id: string;
  original_name: string;
  status: JobStatus;
  stage: string;
  progress: number;
  message: string;
  created_at: string;
  updated_at: string;
  result: ScanResult | null;
  error: JobError | null;
}

export interface ProcessOptions {
  documentType: DocumentType;
  fastDenoise: boolean;
  cppAcceleration: boolean;
}
