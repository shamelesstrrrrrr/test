import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  Copy,
  FileCheck2,
  Loader2,
  Save,
  ServerCog,
  X,
} from "lucide-react";
import {
  cancelProcessingJob,
  createProcessingTask,
  createProcessingJob,
  fetchProcessingDefaults,
  fetchProcessingJob,
  previewProcessingConfig,
  type ProcessingJobResponse,
  type ProcessingConfigPreviewResponse,
  type ProcessingDefaultsResponse,
  type ProcessingFieldInfo,
  type ProcessingTaskResponse,
} from "./services/processingApi";

interface ProcessingTaskModalProps {
  onClose: () => void;
  onTaskSaved?: (task: ProcessingTaskResponse) => void;
  onJobStarted?: (job: ProcessingJobResponse) => void;
}

const FIELD_LABELS: Record<string, string> = {
  task_id: "任务编号",
  task_root: "Linux 任务根目录",
  raw_zip_dir: "Sentinel-1 ZIP 路径",
  dem_file: "DEM 文件路径",
  master_date: "主影像日期",
  bn_start1: "Burst 起始编号",
  bn_end1: "Burst 结束编号",
  env_scripts: "Linux 环境脚本",
  matlab_func_dir: "MATLAB 函数目录",
  satellite: "卫星",
  polarization: "极化",
  swath: "子波束",
  enable_crop: "是否裁剪",
  diff_method: "差分方法",
  shp_method: "SHP 方法",
  phase_opt_method: "相位优化方法",
  point_selection_method: "点选择方法",
  stamps_mode: "StaMPS 模式",
  crop_roff: "crop_roff",
  crop_nr: "crop_nr",
  crop_loff: "crop_loff",
  crop_nl: "crop_nl",
};

const BASIC_INPUT_KEYS = ["task_id", "task_root", "raw_zip_dir", "dem_file", "master_date", "env_scripts", "matlab_func_dir"];
const SLC_INPUT_KEYS = ["satellite", "polarization", "swath", "bn_start1", "bn_end1"];
const METHOD_INPUT_KEYS = ["enable_crop", "diff_method", "shp_method", "phase_opt_method", "point_selection_method", "stamps_mode"];
const HIDDEN_ADVANCED_PARAMETER_KEYS = new Set([
  "skip_unzip",
  "skip_generate_slc",
  "skip_extract_burst",
  "notify_enabled",
  "notify_channel",
  "qq_mail_user_env",
  "qq_mail_auth_code_env",
  "qq_mail_to_env",
]);

function isPlaceholder(value: unknown) {
  return typeof value === "string" && value.trim().startsWith("<") && value.trim().endsWith(">");
}

function valueToInput(value: unknown) {
  if (Array.isArray(value)) return value.filter((item) => !isPlaceholder(item)).join("\n");
  if (typeof value === "boolean") return value ? "true" : "false";
  if (value == null || isPlaceholder(value)) return "";
  return String(value);
}

function hasInputValue(value: unknown) {
  if (typeof value !== "string") return value != null;
  const stripped = value.trim();
  return Boolean(stripped) && !isPlaceholder(stripped);
}

function buildInitialInputs(defaults: ProcessingDefaultsResponse) {
  return Object.fromEntries(
    Object.entries(defaults.minimal_template).map(([key, value]) => [key, valueToInput(value)]),
  );
}

function formatValue(value: unknown) {
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? "true" : "false";
  if (value == null || value === "") return "<空>";
  return String(value);
}

function fieldsByKeys(fields: ProcessingFieldInfo[], keys: string[]) {
  const byKey = new Map(fields.map((field) => [field.key, field]));
  return keys.map((key) => byKey.get(key)).filter((field): field is ProcessingFieldInfo => Boolean(field));
}

function FieldControl({
  field,
  value,
  onChange,
  allowDefault = false,
}: {
  field: ProcessingFieldInfo;
  value: string;
  onChange: (value: string) => void;
  allowDefault?: boolean;
}) {
  const label = FIELD_LABELS[field.key] ?? field.key;
  const defaultText = formatValue(field.default_value);
  const placeholder = allowDefault && field.default_value !== undefined ? `默认：${defaultText}` : `填写 ${field.key}`;

  if (field.key === "env_scripts") {
    return (
      <label className="processing-field wide">
        <span>{label}</span>
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="/opt/gamma/gamma_env.sh&#10;/opt/stamps/stamps_env.sh"
          rows={3}
        />
        <small>{field.description}</small>
      </label>
    );
  }

  if (field.options.length > 0) {
    return (
      <label className="processing-field">
        <span>{label}</span>
        <select value={value} onChange={(event) => onChange(event.target.value)}>
          {allowDefault && <option value="">使用默认：{defaultText}</option>}
          {field.options.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        <small>{field.description}</small>
      </label>
    );
  }

  return (
    <label className="processing-field">
      <span>{label}</span>
      <input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} />
      <small>{field.description}</small>
    </label>
  );
}

function isActiveJob(job: ProcessingJobResponse | null) {
  return Boolean(job && ["queued", "running", "cancel_requested"].includes(job.status));
}

const JOB_STATUS_LABELS: Record<ProcessingJobResponse["status"], string> = {
  queued: "排队中",
  running: "处理中",
  succeeded: "已完成",
  failed: "失败",
  cancel_requested: "正在停止",
  cancelled: "已停止",
};

export function ProcessingTaskModal({ onClose, onTaskSaved, onJobStarted }: ProcessingTaskModalProps) {
  const [defaults, setDefaults] = useState<ProcessingDefaultsResponse | null>(null);
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<ProcessingConfigPreviewResponse | null>(null);
  const [createdTask, setCreatedTask] = useState<ProcessingTaskResponse | null>(null);
  const [job, setJob] = useState<ProcessingJobResponse | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    let alive = true;

    async function loadDefaults() {
      try {
        setIsLoading(true);
        const response = await fetchProcessingDefaults();
        if (!alive) return;
        const nextInputs = buildInitialInputs(response);
        setDefaults(response);
        setInputs(nextInputs);
        setPreview(await previewProcessingConfig(nextInputs));
      } catch (loadError) {
        if (alive) {
          setError(loadError instanceof Error ? loadError.message : String(loadError));
        }
      } finally {
        if (alive) setIsLoading(false);
      }
    }

    void loadDefaults();

    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!isActiveJob(job)) return undefined;

    const timer = window.setInterval(() => {
      void (async () => {
        try {
          const latest = await fetchProcessingJob(job!.task_id, job!.job_id);
          setJob(latest);
        } catch (pollError) {
          setError(pollError instanceof Error ? pollError.message : String(pollError));
        }
      })();
    }, 2000);

    return () => window.clearInterval(timer);
  }, [job]);

  const missingKeys = useMemo(() => new Set(preview?.missing.map((field) => field.key) ?? []), [preview]);
  const allPrimaryFields = useMemo(
    () => [...(defaults?.required_inputs ?? []), ...(defaults?.visible_optional_inputs ?? [])],
    [defaults],
  );
  const basicFields = useMemo(() => fieldsByKeys(allPrimaryFields, BASIC_INPUT_KEYS), [allPrimaryFields]);
  const slcFields = useMemo(() => fieldsByKeys(allPrimaryFields, SLC_INPUT_KEYS), [allPrimaryFields]);
  const methodFields = useMemo(() => fieldsByKeys(allPrimaryFields, METHOD_INPUT_KEYS), [allPrimaryFields]);
  const isCropEnabled = (inputs.enable_crop ?? "").trim().toLowerCase() !== "false";
  const requiredProgressKeys = useMemo(() => {
    if (!defaults) return [];

    const keys = defaults.required_inputs.map((field) => field.key);
    if (isCropEnabled) {
      keys.push(...defaults.crop_inputs.map((field) => field.key));
    }

    return keys;
  }, [defaults, isCropEnabled]);
  const completedRequiredCount = useMemo(
    () => requiredProgressKeys.filter((key) => hasInputValue(inputs[key])).length,
    [inputs, requiredProgressKeys],
  );
  const configProgress = requiredProgressKeys.length
    ? Math.round((completedRequiredCount / requiredProgressKeys.length) * 100)
    : 0;
  const progressLabel = createdTask
    ? "配置草稿已保存"
    : preview?.status === "ready"
      ? "配置可保存"
      : "配置待补全";
  const displayProgress = job ? job.progress_percent : configProgress;
  const displayProgressLabel = job ? `真实处理：${JOB_STATUS_LABELS[job.status]}` : progressLabel;
  const advancedGroups = useMemo(() => {
    if (!defaults) return [];

    const primaryKeys = new Set([
      ...BASIC_INPUT_KEYS,
      ...SLC_INPUT_KEYS,
      ...METHOD_INPUT_KEYS,
      ...defaults.crop_inputs.map((field) => field.key),
    ]);

    return defaults.default_groups
      .map((group) => ({
        ...group,
        parameters: group.parameters.filter(
          (parameter) => !primaryKeys.has(parameter.key) && !HIDDEN_ADVANCED_PARAMETER_KEYS.has(parameter.key),
        ),
      }))
      .filter((group) => group.parameters.length > 0);
  }, [defaults]);

  function updateInput(key: string, value: string) {
    setInputs((current) => ({ ...current, [key]: value }));
    setCreatedTask(null);
    setJob(null);
  }

  async function refreshPreview() {
    try {
      setError("");
      setIsSubmitting(true);
      setPreview(await previewProcessingConfig(inputs));
    } catch (previewError) {
      setError(previewError instanceof Error ? previewError.message : String(previewError));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function saveDraftTask() {
    try {
      setError("");
      setIsSubmitting(true);
      const task = await createProcessingTask(inputs);
      setCreatedTask(task);
      setJob(null);
      onTaskSaved?.(task);
      setPreview({
        status: task.missing.length ? "needs_input" : "ready",
        missing: task.missing,
        config: preview?.config ?? {},
        effective_parameters: preview?.effective_parameters ?? {},
        config_yaml: task.config_yaml,
        execution_enabled: task.execution_enabled,
        safety_notice: task.safety_notice,
      });
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : String(saveError));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function startProcessingJob() {
    if (!createdTask) return;

    try {
      setError("");
      setIsSubmitting(true);
      const nextJob = await createProcessingJob(createdTask.task_id);
      setJob(nextJob);
      onJobStarted?.(nextJob);
    } catch (jobError) {
      setError(jobError instanceof Error ? jobError.message : String(jobError));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function stopProcessingJob() {
    if (!job) return;

    try {
      setError("");
      setIsSubmitting(true);
      setJob(await cancelProcessingJob(job.task_id, job.job_id));
    } catch (stopError) {
      setError(stopError instanceof Error ? stopError.message : String(stopError));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function copyYaml() {
    if (!preview?.config_yaml) return;
    await navigator.clipboard.writeText(preview.config_yaml);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="数据处理任务配置">
      <section className="processing-modal">
        <header className="processing-header">
          <div>
            <h2>Linux 数据处理任务</h2>
            <p>生成 gamma_dinsar 配置草稿，真实处理留给 Linux worker。</p>
          </div>
          <button className="icon-button subtle" type="button" onClick={onClose} title="关闭">
            <X size={18} />
          </button>
        </header>

        {isLoading ? (
          <div className="processing-loading">
            <Loader2 size={18} />
            正在读取默认参数
          </div>
        ) : (
          <div className="processing-body">
            <section className="processing-form-panel">
              <div className="processing-notice">
                <AlertTriangle size={16} />
                <span>{defaults?.safety_notice}</span>
              </div>

              <div className="processing-section-heading">
                <ServerCog size={17} />
                <h3>基础输入</h3>
              </div>
              <div className="processing-field-grid">
                {basicFields.map((field) => (
                  <div className={missingKeys.has(field.key) ? "missing-field-wrap" : ""} key={field.key}>
                    <FieldControl field={field} value={inputs[field.key] ?? ""} onChange={(value) => updateInput(field.key, value)} />
                  </div>
                ))}
              </div>

              <div className="processing-section-heading">
                <FileCheck2 size={17} />
                <h3>SLC 与 Burst 选择</h3>
              </div>
              <div className="processing-field-grid">
                {slcFields.map((field) => (
                  <div className={missingKeys.has(field.key) ? "missing-field-wrap" : ""} key={field.key}>
                    <FieldControl field={field} value={inputs[field.key] ?? ""} onChange={(value) => updateInput(field.key, value)} />
                  </div>
                ))}
              </div>

              <div className="processing-section-heading">
                <FileCheck2 size={17} />
                <h3>处理路线</h3>
              </div>
              <div className="processing-field-grid">
                {methodFields.map((field) => (
                  <FieldControl field={field} value={inputs[field.key] ?? ""} onChange={(value) => updateInput(field.key, value)} key={field.key} />
                ))}
              </div>

              <div className="processing-section-heading">
                <FileCheck2 size={17} />
                <h3>裁剪参数</h3>
              </div>
              <p className="section-help">启用裁剪时必须填写。它们应来自裁剪预览或人工判断，不再提供默认裁剪范围。</p>
              <div className="processing-field-grid compact">
                {defaults?.crop_inputs.map((field) => (
                  <div className={missingKeys.has(field.key) ? "missing-field-wrap" : ""} key={field.key}>
                    <FieldControl field={field} value={inputs[field.key] ?? ""} onChange={(value) => updateInput(field.key, value)} />
                  </div>
                ))}
              </div>

              <details className="defaults-details">
                <summary>高级默认参数，可展开修改</summary>
                <div className="defaults-groups">
                  {advancedGroups.map((group) => (
                    <section key={group.name}>
                      <h4>{group.name}</h4>
                      <div className="processing-field-grid">
                        {group.parameters.map((parameter) => (
                          <FieldControl
                            allowDefault
                            field={parameter}
                            key={parameter.key}
                            value={inputs[parameter.key] ?? ""}
                            onChange={(value) => updateInput(parameter.key, value)}
                          />
                        ))}
                      </div>
                    </section>
                  ))}
                </div>
              </details>
            </section>

            <aside className="processing-preview-panel">
              <div className="preview-status-row">
                <span className={`status-pill ${preview?.status === "ready" ? "ready" : "needs-input"}`}>
                  {preview?.status === "ready" ? "配置已完整" : "仍需补充"}
                </span>
                <button className="icon-text-button" type="button" onClick={refreshPreview} disabled={isSubmitting}>
                  {isSubmitting ? <Loader2 size={15} /> : <FileCheck2 size={15} />}
                  生成预览
                </button>
              </div>

              <div className="processing-progress-card">
                <div className="processing-progress-heading">
                  <strong>{displayProgressLabel}</strong>
                  <span>{displayProgress}%</span>
                </div>
                <div className="progress-track" aria-label="配置准备进度">
                  <div className="progress-fill" style={{ width: `${displayProgress}%` }} />
                </div>
                {job ? (
                  <p>
                    当前步骤：{job.current_step ?? "无"}；已完成 {job.progress_current}/{job.progress_total}。
                  </p>
                ) : (
                  <p>
                    已填写 {completedRequiredCount}/{requiredProgressKeys.length} 个必要参数；保存并确认后才会提交 Linux worker。
                  </p>
                )}
              </div>

              {preview?.missing.length ? (
                <div className="missing-list">
                  <strong>缺少字段</strong>
                  {preview.missing.map((field) => (
                    <p key={field.key}>
                      <code>{field.key}</code>：{field.description}
                    </p>
                  ))}
                </div>
              ) : null}

              {createdTask ? (
                <div className="created-task-box">
                  <strong>任务草稿已保存</strong>
                  <p>task_id：{createdTask.task_id}</p>
                  <p>config：{createdTask.config_path}</p>
                  <p>metadata：{createdTask.metadata_path}</p>
                </div>
              ) : null}

              {job ? (
                <div className="processing-job-box">
                  <strong>处理任务</strong>
                  <p>job_id：{job.job_id}</p>
                  <p>status：{JOB_STATUS_LABELS[job.status]}</p>
                  <p>log：{job.log_path}</p>
                  {job.error ? <p>error：{job.error}</p> : null}
                  {job.log_tail ? <pre>{job.log_tail}</pre> : null}
                </div>
              ) : null}

              <div className="yaml-preview-toolbar">
                <span>task.yaml</span>
                <button className="icon-button subtle" type="button" onClick={copyYaml} title="复制 YAML">
                  {copied ? <Check size={15} /> : <Copy size={15} />}
                </button>
              </div>
              <pre className="yaml-preview">{preview?.config_yaml ?? ""}</pre>

              {error ? (
                <div className="processing-error">
                  <AlertTriangle size={15} />
                  {error}
                </div>
              ) : null}

              <button className="primary-action" type="button" onClick={saveDraftTask} disabled={isSubmitting}>
                {isSubmitting ? <Loader2 size={16} /> : <Save size={16} />}
                保存任务草稿
              </button>
              <button
                className="primary-action processing-run-action"
                type="button"
                onClick={startProcessingJob}
                disabled={
                  isSubmitting ||
                  !createdTask ||
                  !createdTask.execution_enabled ||
                  createdTask.missing.length > 0 ||
                  Boolean(job && job.status !== "failed" && job.status !== "cancelled")
                }
                title={!defaults?.execution_enabled ? "后端未开启真实处理执行" : "确认后提交 Linux worker"}
              >
                {isSubmitting ? <Loader2 size={16} /> : <ServerCog size={16} />}
                确认开始处理
              </button>
              {isActiveJob(job) ? (
                <button className="icon-text-button stop-job-button" type="button" onClick={stopProcessingJob}>
                  <X size={15} />
                  停止处理
                </button>
              ) : null}
            </aside>
          </div>
        )}
      </section>
    </div>
  );
}
