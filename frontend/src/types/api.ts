export interface Citation {
  index: number;
  source_reference: string;
  claim: string;
  verification_status: 'verified' | 'unsupported' | 'partial';
}

export interface ConfidenceScores {
  retrieval_confidence: number;
  citation_coverage: number;
  answer_completeness: number;
  composite: number;
}

export interface SourceChunk {
  chunk_id: string;
  document_id: string;
  text: string;
  section_heading: string;
  score: number;
  retrieval_method: 'dense' | 'sparse' | 'graph';
}

export interface FallbackInfo {
  found_topics: string[];
  not_found_topics: string[];
  suggested_documents: string[];
}

export interface AgentAskResponse {
  answer: string;
  citations: Citation[];
  confidence_scores: ConfidenceScores;
  source_chunks: SourceChunk[];
  is_fallback: boolean;
  fallback_info: FallbackInfo | null;
}

export interface DocumentSummary {
  document_id: string;
  filename: string;
  format: string;
  ingestion_date: string;
  chunks_produced: number;
}

export interface DocumentsResponse {
  documents: DocumentSummary[];
}

export interface HealthResponse {
  status: string;
  services: Record<string, string>;
}

export interface ApiError {
  message: string;
  error_code: string;
  status: number;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  response?: AgentAskResponse;
  pending?: boolean;
}
