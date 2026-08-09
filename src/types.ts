export type QueryType =
  | "concept"
  | "workflow"
  | "command"
  | "parameter"
  | "file_layout"
  | "code_template";

export type VerificationStatus =
  | "mock_verified"
  | "mock_partial"
  | "manual_verified"
  | "partial_manual_evidence"
  | "code_reference"
  | "web_reference"
  | "insufficient_evidence";

export interface Citation {
  id: string;
  source: string;
  page: string;
  command_name: string;
  section: string;
  verification_status: VerificationStatus;
  retrieval_score: number;
  excerpt: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  queryTypes?: QueryType[];
  citations?: Citation[];
}

export interface ChatSession {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: ChatMessage[];
}

export interface MockAnswer {
  id: string;
  title: string;
  triggers: string[];
  queryTypes: QueryType[];
  answer: string;
  citations: Citation[];
}
