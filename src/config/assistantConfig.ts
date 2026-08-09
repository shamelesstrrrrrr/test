import type { AssistantEngineMode } from "../services/assistantEngine";

export interface RagApiConfig {
  apiUrl: string;
}

export interface LlmApiConfig {
  apiKey: string;
  baseUrl: string;
  endpointPath: string;
  model: string;
  temperature: number;
}

export interface AssistantRuntimeConfig {
  provider: AssistantEngineMode;
  rag: RagApiConfig;
  llm: LlmApiConfig;
  processingApiBaseUrl: string;
  missingFields: string[];
}

function trimEnv(value: string | undefined) {
  return value?.trim() ?? "";
}

function normalizeEndpointPath(value: string) {
  if (!value) return "/v1/chat/completions";
  return value.startsWith("/") ? value : `/${value}`;
}

function readTemperature(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0.2;
}

function readProviderMode(): AssistantEngineMode {
  const value = import.meta.env.VITE_ASSISTANT_PROVIDER;
  if (value === "mock") return "mock";
  if (value === "rag_api") return "rag_api";
  return "llm_api";
}

export function getAssistantRuntimeConfig(): AssistantRuntimeConfig {
  const provider = readProviderMode();
  const rag: RagApiConfig = {
    apiUrl: trimEnv(import.meta.env.VITE_RAG_API_URL) || "http://127.0.0.1:8000/api/chat",
  };
  const llm: LlmApiConfig = {
    apiKey: trimEnv(import.meta.env.VITE_LLM_API_KEY),
    baseUrl: trimEnv(import.meta.env.VITE_LLM_API_BASE_URL).replace(/\/$/, ""),
    endpointPath: normalizeEndpointPath(trimEnv(import.meta.env.VITE_LLM_API_PATH)),
    model: trimEnv(import.meta.env.VITE_LLM_MODEL),
    temperature: readTemperature(trimEnv(import.meta.env.VITE_LLM_TEMPERATURE)),
  };

  const missingFields = [
    ...(provider === "llm_api"
      ? [
          ["VITE_LLM_API_BASE_URL", llm.baseUrl],
          ["VITE_LLM_MODEL", llm.model],
        ]
      : []),
    ...(provider === "rag_api" ? [["VITE_RAG_API_URL", rag.apiUrl]] : []),
  ]
    .filter(([, value]) => !value)
    .map(([key]) => key);

  return {
    provider,
    rag,
    llm,
    processingApiBaseUrl:
      trimEnv(import.meta.env.VITE_PROCESSING_API_BASE_URL) || "http://127.0.0.1:8000/api/processing",
    missingFields,
  };
}

export const assistantRuntimeConfig = getAssistantRuntimeConfig();
