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

export interface ProcessingDefaultsResponse {
  execution_enabled: boolean;
  safety_notice: string;
  required_inputs: ProcessingFieldInfo[];
  crop_inputs: ProcessingFieldInfo[];
  visible_optional_inputs: ProcessingFieldInfo[];
  default_groups: ProcessingDefaultGroup[];
  minimal_template: Record<string, unknown>;
  minimal_template_yaml: string;
}

export interface ProcessingConfigPreviewResponse {
  status: "ready" | "needs_input";
  missing: ProcessingFieldInfo[];
  config: Record<string, unknown>;
  effective_parameters: Record<string, unknown>;
  config_yaml: string;
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

async function parseResponse<T>(response: Response): Promise<T> {
  const payload = (await response.json().catch(() => ({}))) as { detail?: string };

  if (!response.ok) {
    throw new Error(payload.detail ?? `HTTP ${response.status}`);
  }

  return payload as T;
}

export async function fetchProcessingDefaults(): Promise<ProcessingDefaultsResponse> {
  const response = await fetch(`${assistantRuntimeConfig.processingApiBaseUrl}/defaults`);
  return parseResponse<ProcessingDefaultsResponse>(response);
}

export async function previewProcessingConfig(
  inputs: Record<string, unknown>,
): Promise<ProcessingConfigPreviewResponse> {
  const response = await fetch(`${assistantRuntimeConfig.processingApiBaseUrl}/config/preview`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ inputs }),
  });

  return parseResponse<ProcessingConfigPreviewResponse>(response);
}

export async function createProcessingTask(inputs: Record<string, unknown>): Promise<ProcessingTaskResponse> {
  const response = await fetch(`${assistantRuntimeConfig.processingApiBaseUrl}/tasks`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ inputs, allow_incomplete: true }),
  });

  return parseResponse<ProcessingTaskResponse>(response);
}

export async function createProcessingJob(taskId: string, workflow = "full"): Promise<ProcessingJobResponse> {
  const response = await fetch(`${assistantRuntimeConfig.processingApiBaseUrl}/jobs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ task_id: taskId, workflow }),
  });

  return parseResponse<ProcessingJobResponse>(response);
}

export async function fetchProcessingJob(taskId: string, jobId: string): Promise<ProcessingJobResponse> {
  const response = await fetch(`${assistantRuntimeConfig.processingApiBaseUrl}/tasks/${taskId}/jobs/${jobId}`);
  return parseResponse<ProcessingJobResponse>(response);
}

export async function cancelProcessingJob(taskId: string, jobId: string): Promise<ProcessingJobResponse> {
  const response = await fetch(`${assistantRuntimeConfig.processingApiBaseUrl}/tasks/${taskId}/jobs/${jobId}/cancel`, {
    method: "POST",
  });

  return parseResponse<ProcessingJobResponse>(response);
}
