import { assistantRuntimeConfig } from "../config/assistantConfig";

export interface ProcessingDefaultParameter {
  key: string;
  default_value: unknown;
  description: string;
  options: string[];
}

export interface ProcessingDefaultGroup {
  name: string;
  parameters: ProcessingDefaultParameter[];
}

export interface ProcessingFieldInfo {
  key: string;
  description: string;
  default_value: unknown;
  options: string[];
}

export interface ProcessingStepInfo {
  key: string;
  title: string;
  description: string;
  required_inputs: string[];
}

export interface ProcessingWorkflowPreset {
  key: string;
  title: string;
  start_step: string;
  end_step: string;
  description: string;
}

export interface ProcessingDefaultsResponse {
  execution_enabled: boolean;
  safety_notice: string;
  required_inputs: ProcessingFieldInfo[];
  crop_inputs: ProcessingFieldInfo[];
  visible_optional_inputs: ProcessingFieldInfo[];
  default_groups: ProcessingDefaultGroup[];
  processing_steps: ProcessingStepInfo[];
  workflow_presets: ProcessingWorkflowPreset[];
  minimal_template: Record<string, unknown>;
  minimal_template_yaml: string;
}

export interface ProcessingConfigPreviewResponse {
  status: "ready" | "needs_input";
  missing: ProcessingFieldInfo[];
  config: Record<string, unknown>;
  effective_parameters: Record<string, unknown>;
  config_yaml: string;
  workflow: string;
  workflow_start: string;
  workflow_end: string;
  selected_steps: ProcessingStepInfo[];
  required_field_keys: string[];
  execution_enabled: boolean;
  safety_notice: string;
}

export interface ProcessingTaskResponse {
  task_id: string;
  status: "pending_review" | "ready_for_linux_worker";
  task_dir: string;
  config_path: string;
  metadata_path: string;
  missing: ProcessingFieldInfo[];
  config_yaml: string;
  workflow: string;
  workflow_start: string;
  workflow_end: string;
  selected_steps: ProcessingStepInfo[];
  required_field_keys: string[];
  execution_enabled: boolean;
  safety_notice: string;
}

export type ProcessingJobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancel_requested"
  | "cancelled";

export interface ProcessingJobStep {
  key: string;
  title: string;
  status: "pending" | "running" | "succeeded" | "failed" | "skipped";
  started_at?: string | null;
  finished_at?: string | null;
  message?: string | null;
}

export interface ProcessingJobResponse {
  job_id: string;
  task_id: string;
  status: ProcessingJobStatus;
  workflow: string;
  progress_current: number;
  progress_total: number;
  progress_percent: number;
  current_step?: string | null;
  steps: ProcessingJobStep[];
  config_path: string;
  job_path: string;
  log_path: string;
  pid?: number | null;
  return_code?: number | null;
  error?: string | null;
  log_tail: string;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  execution_enabled: boolean;
  safety_notice: string;
}

function trimTrailingSlash(value: string) {
  return value.replace(/\/+$/, "");
}

function uniqueValues(values: string[]) {
  return values.filter((value, index) => value && values.indexOf(value) === index);
}

function fallbackProcessingApiBaseUrl() {
  if (typeof window === "undefined" || !window.location.hostname) {
    return "";
  }

  return `${window.location.protocol}//${window.location.hostname}:8000/api/processing`;
}

function processingApiBaseUrls() {
  return uniqueValues([
    trimTrailingSlash(assistantRuntimeConfig.processingApiBaseUrl),
    trimTrailingSlash(fallbackProcessingApiBaseUrl()),
  ]);
}

function formatFetchError(error: unknown) {
  if (error instanceof Error) return error.message;
  return String(error);
}

async function parseResponse<T>(response: Response, url: string): Promise<T> {
  const payload = (await response.json().catch(() => ({}))) as { detail?: string };

  if (!response.ok) {
    throw new Error(`${payload.detail ?? `HTTP ${response.status}`} (${url})`);
  }

  return payload as T;
}

async function fetchProcessingApi<T>(path: string, init?: RequestInit): Promise<T> {
  const errors: string[] = [];

  for (const baseUrl of processingApiBaseUrls()) {
    const url = `${baseUrl}${path}`;

    try {
      const response = await fetch(url, init);
      return await parseResponse<T>(response, url);
    } catch (error) {
      errors.push(`${url} -> ${formatFetchError(error)}`);
      if (!(error instanceof TypeError)) {
        throw error;
      }
    }
  }

  throw new Error(`无法连接处理后端，已尝试：\n${errors.join("\n")}`);
}

export async function fetchProcessingDefaults(): Promise<ProcessingDefaultsResponse> {
  return fetchProcessingApi<ProcessingDefaultsResponse>("/defaults");
}

export async function previewProcessingConfig(
  inputs: Record<string, unknown>,
): Promise<ProcessingConfigPreviewResponse> {
  return fetchProcessingApi<ProcessingConfigPreviewResponse>("/config/preview", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ inputs }),
  });
}

export async function createProcessingTask(inputs: Record<string, unknown>): Promise<ProcessingTaskResponse> {
  return fetchProcessingApi<ProcessingTaskResponse>("/tasks", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ inputs, allow_incomplete: true }),
  });
}

export async function createProcessingJob(taskId: string, workflow = "configured"): Promise<ProcessingJobResponse> {
  return fetchProcessingApi<ProcessingJobResponse>("/jobs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ task_id: taskId, workflow }),
  });
}

export async function fetchProcessingJob(taskId: string, jobId: string): Promise<ProcessingJobResponse> {
  return fetchProcessingApi<ProcessingJobResponse>(`/tasks/${taskId}/jobs/${jobId}`);
}

export async function cancelProcessingJob(taskId: string, jobId: string): Promise<ProcessingJobResponse> {
  return fetchProcessingApi<ProcessingJobResponse>(`/tasks/${taskId}/jobs/${jobId}/cancel`, {
    method: "POST",
  });
}
