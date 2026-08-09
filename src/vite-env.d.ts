/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ASSISTANT_PROVIDER?: "rag_api" | "llm_api" | "mock";
  readonly VITE_RAG_API_URL?: string;
  readonly VITE_LLM_API_BASE_URL?: string;
  readonly VITE_LLM_API_PATH?: string;
  readonly VITE_LLM_MODEL?: string;
  readonly VITE_LLM_API_KEY?: string;
  readonly VITE_LLM_TEMPERATURE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
