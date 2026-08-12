import { useEffect, useMemo, useState } from "react";
import {
  Archive,
  AlertTriangle,
  Check,
  Copy,
  FileCheck2,
  FolderOpen,
  Loader2,
  Save,
  ServerCog,
  X,
} from "lucide-react";
import {
  archiveCropDependentOutputs,
  browseProcessingFiles,
  cancelProcessingJob,
  createProcessingTask,
  createProcessingJob,
  fetchProcessingDefaults,
  fetchProcessingJob,
  previewProcessingConfig,
  type ProcessingJobResponse,
  type ProcessingConfigPreviewResponse,
  type ProcessingCropResetResponse,
  type ProcessingDefaultsResponse,
  type ProcessingFileBrowserEntry,
  type ProcessingFileBrowserResponse,
  type ProcessingFieldInfo,
  type ProcessingStepInfo,
  type ProcessingTaskResponse,
} from "./services/processingApi";

interface ProcessingTaskModalProps {
  onClose: () => void;
  initialInputs?: Record<string, string>;
  onTaskSaved?: (task: ProcessingTaskResponse) => void;
  onJobStarted?: (job: ProcessingJobResponse) => void;
}

const FIELD_LABELS: Record<string, string> = {
  task_id: "任务编号",
  workflow_start: "起始步骤",
  workflow_end: "结束步骤",
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
const PATH_FIELD_MODES: Record<string, "file" | "directory" | "any"> = {
  task_root: "directory",
  raw_zip_dir: "any",
  dem_file: "file",
  env_scripts: "file",
  matlab_func_dir: "directory",
};
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

const FALLBACK_PROCESSING_STEPS: ProcessingStepInfo[] = [
  { key: "unzip_s1", title: "解压 Sentinel-1 ZIP", description: "从原始 ZIP 数据解压。", required_inputs: ["task_root", "raw_zip_dir"] },
  { key: "generate_slc", title: "生成 SLC", description: "生成 SLC 数据。", required_inputs: ["task_root", "env_scripts", "satellite", "polarization", "swath"] },
  { key: "extract_burst", title: "提取 Burst", description: "提取 burst 范围。", required_inputs: ["task_root", "env_scripts", "polarization", "swath", "bn_start1", "bn_end1"], default_inputs: ["bn_start2", "bn_end2", "bn_start3", "bn_end3"] },
  { key: "slc_geo", title: "主影像地理编码", description: "生成主影像地理编码结果。", required_inputs: ["task_root", "env_scripts", "dem_file", "master_date"], default_inputs: ["range_looks", "azimuth_looks", "lat_ovr", "lon_ovr"] },
  { key: "coregistration", title: "主从影像配准", description: "进行主从影像配准。", required_inputs: ["task_root", "env_scripts", "polarization", "swath"] },
  { key: "crop_rslc", title: "RSLC 裁剪", description: "裁剪 RSLC。", required_inputs: ["task_root", "env_scripts", "master_date", "polarization", "swath"], default_inputs: ["enable_crop", "data_format", "scale_factor"] },
  { key: "write_rslc_tab", title: "生成 RSLC_tab", description: "生成 RSLC_tab。", required_inputs: ["task_root"], default_inputs: ["rslc_template", "rslc_par_template"] },
  { key: "base_calc", title: "生成基线和 itab", description: "生成基线和 itab。", required_inputs: ["task_root", "env_scripts", "master_date"], default_inputs: ["itab_type", "base_calc_plot_flag", "bperp_min", "bperp_max", "delta_t_min", "delta_t_max", "delta_n_max"] },
  { key: "mk_mli_all", title: "生成 RMLI 强度图", description: "生成多视强度图。", required_inputs: ["task_root", "env_scripts"], default_inputs: ["rlks", "azlks"] },
  { key: "diff_workflow", title: "生成差分干涉图", description: "生成差分干涉图。", required_inputs: ["task_root", "env_scripts", "dem_file", "master_date", "diff_method"], default_inputs: ["rlks", "azlks", "diff_param_1", "diff_s_value", "diff_e_value"] },
  { key: "select_shp", title: "SHP 同质像元选取", description: "选取同质像元。", required_inputs: ["task_root", "env_scripts", "master_date", "matlab_func_dir", "shp_method"], default_inputs: ["cal_win_range", "cal_win_azimuth", "alpha", "matlab_command"] },
  { key: "phase_optimization", title: "相位优化", description: "进行相位优化。", required_inputs: ["task_root", "env_scripts", "matlab_func_dir", "phase_opt_method", "shp_method"], default_inputs: ["fit_threshold", "ref_id", "block_size", "phase_opt_output_name", "matlab_command"] },
  { key: "file_construct", title: "组织 StaMPS 时序文件", description: "组织时序文件。", required_inputs: ["task_root", "env_scripts", "master_date"], default_inputs: ["ts_flag"] },
  { key: "point_selection", title: "候选点选取", description: "选取候选点。", required_inputs: ["task_root", "env_scripts", "master_date", "point_selection_method"], default_inputs: ["psc_da_thresh", "rg_patches", "az_patches", "rg_overlap", "az_overlap", "fit_threshold", "phase_opt_output_name", "matlab_command", "mt_prep_gamma_addds_command"] },
  { key: "stamps_processing", title: "StaMPS 处理", description: "执行 StaMPS 处理。", required_inputs: ["task_root", "env_scripts", "stamps_mode"], default_inputs: ["matlab_command"] },
];

function processingSteps(defaults: ProcessingDefaultsResponse) {
  return defaults.processing_steps?.length ? defaults.processing_steps : FALLBACK_PROCESSING_STEPS;
}

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

function addUnique(target: string[], key: string) {
  if (!target.includes(key)) target.push(key);
}

function canBrowseField(fieldKey: string) {
  return fieldKey in PATH_FIELD_MODES;
}

function firstPathLine(value: string) {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find((line) => line && !isPlaceholder(line));
}

function appendPathLine(value: string, path: string) {
  const lines = value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.includes(path)) lines.push(path);
  return lines.join("\n");
}

function selectedSteps(defaults: ProcessingDefaultsResponse, inputs: Record<string, string>) {
  const steps = processingSteps(defaults);
  const start = inputs.workflow_start || steps[0]?.key;
  const end = inputs.workflow_end || steps.at(-1)?.key;
  const startIndex = steps.findIndex((step) => step.key === start);
  const endIndex = steps.findIndex((step) => step.key === end);

  if (startIndex < 0 || endIndex < startIndex) {
    return steps;
  }

  return steps.slice(startIndex, endIndex + 1);
}

function requiredKeysForSelectedSteps(
  defaults: ProcessingDefaultsResponse,
  inputs: Record<string, string>,
  isCropEnabled: boolean,
) {
  const keys: string[] = [];
  const steps = selectedSteps(defaults, inputs);

  for (const step of steps) {
    step.required_inputs.forEach((key) => addUnique(keys, key));

    if (step.key === "crop_rslc" && isCropEnabled) {
      defaults.crop_inputs.forEach((field) => addUnique(keys, field.key));
    }

    if (step.key === "point_selection") {
      const method = (inputs.point_selection_method || "dsc_pds").toLowerCase();
      if (["dsc_select", "dsc", "dsc_pds", "pds", "ds"].includes(method)) {
        addUnique(keys, "matlab_func_dir");
      }
    }
  }

  return keys;
}

function defaultKeysForSelectedSteps(defaults: ProcessingDefaultsResponse, inputs: Record<string, string>) {
  const keys: string[] = [];
  const steps = selectedSteps(defaults, inputs);

  for (const step of steps) {
    (step.default_inputs ?? []).forEach((key) => addUnique(keys, key));

    if (step.key === "diff_workflow") {
      const method = (inputs.diff_method || "initial").toLowerCase();
      if (method === "unwrapped_ls") {
        ["adf_alpha", "adf_window", "unw_alpha"].forEach((key) => addUnique(keys, key));
      }
    }

    if (step.key === "point_selection") {
      const method = (inputs.point_selection_method || "dsc_pds").toLowerCase();
      if (["dsc_select", "dsc", "dsc_pds", "pds", "ds"].includes(method)) {
        addUnique(keys, "matlab_func_dir");
      }
    }
  }

  return keys;
}

function FieldControl({
  field,
  value,
  onChange,
  onBrowse,
  allowDefault = false,
}: {
  field: ProcessingFieldInfo;
  value: string;
  onChange: (value: string) => void;
  onBrowse?: (field: ProcessingFieldInfo) => void;
  allowDefault?: boolean;
}) {
  const label = FIELD_LABELS[field.key] ?? field.key;
  const defaultText = formatValue(field.default_value);
  const placeholder = allowDefault && field.default_value !== undefined ? `默认：${defaultText}` : `填写 ${field.key}`;

  const showBrowse = canBrowseField(field.key) && onBrowse;

  if (field.key === "env_scripts") {
    return (
      <label className="processing-field wide">
        <span className="field-title-row">
          {label}
          {showBrowse ? (
            <button className="browse-path-button" type="button" onClick={() => onBrowse(field)}>
              <FolderOpen size={14} />
              浏览
            </button>
          ) : null}
        </span>
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
        <span className="field-title-row">
          {label}
          {showBrowse ? (
            <button className="browse-path-button" type="button" onClick={() => onBrowse(field)}>
              <FolderOpen size={14} />
              浏览
            </button>
          ) : null}
        </span>
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
      <span className="field-title-row">
        {label}
        {showBrowse ? (
          <button className="browse-path-button" type="button" onClick={() => onBrowse(field)}>
            <FolderOpen size={14} />
            浏览
          </button>
        ) : null}
      </span>
      <input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} />
      <small>{field.description}</small>
    </label>
  );
}

function isActiveJob(job: ProcessingJobResponse | null) {
  return Boolean(job && ["queued", "running", "cancel_requested"].includes(job.status));
}

function formatMissingFields(fields: ProcessingFieldInfo[]) {
  return fields.map((field) => `${field.key}（${field.description}）`).join("\n");
}

const JOB_STATUS_LABELS: Record<ProcessingJobResponse["status"], string> = {
  queued: "排队中",
  running: "处理中",
  succeeded: "已完成",
  failed: "失败",
  cancel_requested: "正在停止",
  cancelled: "已停止",
};

type BrowserTarget = {
  fieldKey: string;
  label: string;
  mode: "file" | "directory" | "any";
};

export function ProcessingTaskModal({ onClose, initialInputs, onTaskSaved, onJobStarted }: ProcessingTaskModalProps) {
  const [defaults, setDefaults] = useState<ProcessingDefaultsResponse | null>(null);
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<ProcessingConfigPreviewResponse | null>(null);
  const [createdTask, setCreatedTask] = useState<ProcessingTaskResponse | null>(null);
  const [job, setJob] = useState<ProcessingJobResponse | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResettingCropOutputs, setIsResettingCropOutputs] = useState(false);
  const [cropReset, setCropReset] = useState<ProcessingCropResetResponse | null>(null);
  const [browserTarget, setBrowserTarget] = useState<BrowserTarget | null>(null);
  const [browserData, setBrowserData] = useState<ProcessingFileBrowserResponse | null>(null);
  const [browserPath, setBrowserPath] = useState("");
  const [browserError, setBrowserError] = useState("");
  const [isBrowserLoading, setIsBrowserLoading] = useState(false);

  useEffect(() => {
    let alive = true;

    async function loadDefaults() {
      try {
        setIsLoading(true);
        const response = await fetchProcessingDefaults();
        if (!alive) return;
        const nextInputs = { ...buildInitialInputs(response), ...(initialInputs ?? {}) };
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
  }, [initialInputs]);

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

  useEffect(() => {
    if (!defaults || isLoading) return undefined;

    const timer = window.setTimeout(() => {
      void (async () => {
        try {
          setPreview(await previewProcessingConfig(inputs));
        } catch (previewError) {
          setError(previewError instanceof Error ? previewError.message : String(previewError));
        }
      })();
    }, 350);

    return () => window.clearTimeout(timer);
  }, [defaults, inputs, isLoading]);

  const missingKeys = useMemo(() => new Set(preview?.missing.map((field) => field.key) ?? []), [preview]);
  const allPrimaryFields = useMemo(
    () => [...(defaults?.required_inputs ?? []), ...(defaults?.visible_optional_inputs ?? [])],
    [defaults],
  );
  const isCropEnabled = (inputs.enable_crop ?? "").trim().toLowerCase() !== "false";
  const activeSteps = useMemo(() => (defaults ? selectedSteps(defaults, inputs) : []), [defaults, inputs]);
  const activeStepKeys = useMemo(() => new Set(activeSteps.map((step) => step.key)), [activeSteps]);
  const workflowSteps = useMemo(() => (defaults ? processingSteps(defaults) : []), [defaults]);
  const requiredProgressKeys = useMemo(() => {
    if (!defaults) return [];

    return requiredKeysForSelectedSteps(defaults, inputs, isCropEnabled);
  }, [defaults, inputs, isCropEnabled]);
  const activeDefaultKeys = useMemo(() => {
    if (!defaults) return [];

    return defaultKeysForSelectedSteps(defaults, inputs);
  }, [defaults, inputs]);
  const activeFieldKeys = useMemo(() => {
    const keys = [...requiredProgressKeys];

    addUnique(keys, "task_id");
    addUnique(keys, "env_scripts");

    if (activeStepKeys.has("crop_rslc")) addUnique(keys, "enable_crop");

    return keys;
  }, [activeStepKeys, requiredProgressKeys]);
  const basicFields = useMemo(
    () => fieldsByKeys(allPrimaryFields, BASIC_INPUT_KEYS.filter((key) => activeFieldKeys.includes(key))),
    [activeFieldKeys, allPrimaryFields],
  );
  const slcFields = useMemo(
    () => fieldsByKeys(allPrimaryFields, SLC_INPUT_KEYS.filter((key) => activeFieldKeys.includes(key))),
    [activeFieldKeys, allPrimaryFields],
  );
  const methodFields = useMemo(
    () => fieldsByKeys(allPrimaryFields, METHOD_INPUT_KEYS.filter((key) => activeFieldKeys.includes(key))),
    [activeFieldKeys, allPrimaryFields],
  );
  const cropFields = useMemo(
    () => (activeStepKeys.has("crop_rslc") && isCropEnabled ? (defaults?.crop_inputs ?? []) : []),
    [activeStepKeys, defaults, isCropEnabled],
  );
  const workflowStartIndex = workflowSteps.findIndex((step) => step.key === inputs.workflow_start);
  const workflowEndOptions = workflowSteps.filter((_, index) => index >= Math.max(0, workflowStartIndex));
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
      "workflow_start",
      "workflow_end",
      "workflow_preset",
    ]);

    return defaults.default_groups
      .map((group) => ({
        ...group,
        parameters: group.parameters.filter(
          (parameter) =>
            activeDefaultKeys.includes(parameter.key) &&
            !primaryKeys.has(parameter.key) &&
            !HIDDEN_ADVANCED_PARAMETER_KEYS.has(parameter.key),
        ),
      }))
      .filter((group) => group.parameters.length > 0);
  }, [activeDefaultKeys, defaults]);

  function updateInput(key: string, value: string) {
    setInputs((current) => ({ ...current, [key]: value }));
    setCreatedTask(null);
    setJob(null);
    setCropReset(null);
  }

  function updateWorkflowStart(value: string) {
    if (!defaults) {
      updateInput("workflow_start", value);
      return;
    }

    const steps = processingSteps(defaults);
    const nextStartIndex = steps.findIndex((step) => step.key === value);
    const currentEnd = inputs.workflow_end || steps.at(-1)?.key || value;
    const currentEndIndex = steps.findIndex((step) => step.key === currentEnd);
    const nextEnd = currentEndIndex >= nextStartIndex ? currentEnd : value;

    setInputs((current) => ({ ...current, workflow_start: value, workflow_end: nextEnd }));
    setCreatedTask(null);
    setJob(null);
  }

  async function loadBrowserPath(path?: string) {
    try {
      setBrowserError("");
      setIsBrowserLoading(true);
      const data = await browseProcessingFiles(path);
      setBrowserData(data);
      setBrowserPath(data.current_path);
    } catch (browseError) {
      setBrowserError(browseError instanceof Error ? browseError.message : String(browseError));
    } finally {
      setIsBrowserLoading(false);
    }
  }

  function openPathBrowser(field: ProcessingFieldInfo) {
    const initialPath = field.key === "env_scripts" ? firstPathLine(inputs[field.key] ?? "") : firstPathLine(inputs[field.key] ?? "");
    setBrowserTarget({
      fieldKey: field.key,
      label: FIELD_LABELS[field.key] ?? field.key,
      mode: PATH_FIELD_MODES[field.key] ?? "any",
    });
    setBrowserData(null);
    void loadBrowserPath(initialPath);
  }

  function closePathBrowser() {
    setBrowserTarget(null);
    setBrowserData(null);
    setBrowserPath("");
    setBrowserError("");
  }

  function canSelectBrowserEntry(entry: ProcessingFileBrowserEntry) {
    if (!browserTarget) return false;
    return browserTarget.mode === "any" || (browserTarget.mode === "directory" ? entry.is_dir : !entry.is_dir);
  }

  function selectBrowserPath(path: string) {
    if (!browserTarget) return;
    const currentValue = inputs[browserTarget.fieldKey] ?? "";
    const nextValue = browserTarget.fieldKey === "env_scripts" ? appendPathLine(currentValue, path) : path;
    updateInput(browserTarget.fieldKey, nextValue);
    closePathBrowser();
  }

  function applySavedTask(task: ProcessingTaskResponse) {
    setCreatedTask(task);
    setJob(null);
    onTaskSaved?.(task);
    setPreview({
      status: task.missing.length ? "needs_input" : "ready",
      missing: task.missing,
      config: preview?.config ?? {},
      effective_parameters: preview?.effective_parameters ?? {},
      config_yaml: task.config_yaml,
      workflow: task.workflow,
      workflow_start: task.workflow_start,
      workflow_end: task.workflow_end,
      selected_steps: task.selected_steps,
      required_field_keys: task.required_field_keys,
      execution_enabled: task.execution_enabled,
      safety_notice: task.safety_notice,
    });
  }

  async function saveTaskFromInputs() {
    const task = await createProcessingTask(inputs);
    applySavedTask(task);
    return task;
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
      await saveTaskFromInputs();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : String(saveError));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function startProcessingJob() {
    try {
      setError("");
      setIsSubmitting(true);
      const task = createdTask ?? (await saveTaskFromInputs());

      if (task.missing.length > 0) {
        throw new Error(`配置还不完整，不能开始处理。请先补全：\n${formatMissingFields(task.missing)}`);
      }

      if (!task.execution_enabled) {
        throw new Error(
          "后端还没有开启真实处理执行。请在 Linux 的 .env.local 中设置 PROCESSING_EXECUTION_ENABLED=true，并重启 FastAPI 后端。",
        );
      }

      const nextJob = await createProcessingJob(task.task_id);
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

  async function archiveCropOutputs() {
    const taskRoot = (inputs.task_root ?? "").trim();
    if (!taskRoot || isPlaceholder(taskRoot)) {
      setError("请先填写 Linux 任务根目录，再归档裁剪后的结果。");
      return;
    }

    const confirmed = window.confirm(
      "将把 SLC_copy、RSLC_tab、RMLI、GEO_seg、DIFF 等裁剪后结果移动到 task_root/archive/ 中。\n\n"
        + "不会删除文件，也不会改动 SLC、SLC_select、GEO、RSLC 或 logs。\n\n"
        + "归档后请从“RSLC 裁剪”开始重新运行。是否继续？",
    );
    if (!confirmed) return;

    try {
      setError("");
      setIsResettingCropOutputs(true);
      setCropReset(await archiveCropDependentOutputs(taskRoot));
      setCreatedTask(null);
      setJob(null);
    } catch (resetError) {
      setError(resetError instanceof Error ? resetError.message : String(resetError));
    } finally {
      setIsResettingCropOutputs(false);
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
                <h3>处理范围</h3>
              </div>
              <div className="processing-field-grid">
                <label className="processing-field">
                  <span>起始步骤</span>
                  <select value={inputs.workflow_start ?? ""} onChange={(event) => updateWorkflowStart(event.target.value)}>
                    {workflowSteps.map((step) => (
                      <option key={step.key} value={step.key}>
                        {step.title}
                      </option>
                    ))}
                  </select>
                  <small>从这个步骤开始执行；前面的结果需要已经存在。</small>
                </label>
                <label className="processing-field">
                  <span>结束步骤</span>
                  <select value={inputs.workflow_end ?? ""} onChange={(event) => updateInput("workflow_end", event.target.value)}>
                    {workflowEndOptions.map((step) => (
                      <option key={step.key} value={step.key}>
                        {step.title}
                      </option>
                    ))}
                  </select>
                  <small>运行到这个步骤后停止；只重跑某一步时起止步骤选同一个。</small>
                </label>
              </div>
              <div className="selected-step-strip" aria-label="本次会执行的步骤">
                {activeSteps.map((step) => (
                  <span key={step.key}>{step.title}</span>
                ))}
              </div>

              <div className="processing-section-heading">
                <ServerCog size={17} />
                <h3>基础输入</h3>
              </div>
              {basicFields.length ? (
                <div className="processing-field-grid">
                  {basicFields.map((field) => (
                    <div className={missingKeys.has(field.key) ? "missing-field-wrap" : ""} key={field.key}>
                      <FieldControl field={field} value={inputs[field.key] ?? ""} onBrowse={openPathBrowser} onChange={(value) => updateInput(field.key, value)} />
                    </div>
                  ))}
                </div>
              ) : null}

              {slcFields.length ? (
                <>
                  <div className="processing-section-heading">
                    <FileCheck2 size={17} />
                    <h3>SLC 与 Burst 选择</h3>
                  </div>
                  <div className="processing-field-grid">
                    {slcFields.map((field) => (
                      <div className={missingKeys.has(field.key) ? "missing-field-wrap" : ""} key={field.key}>
                        <FieldControl field={field} value={inputs[field.key] ?? ""} onBrowse={openPathBrowser} onChange={(value) => updateInput(field.key, value)} />
                      </div>
                    ))}
                  </div>
                </>
              ) : null}

              {methodFields.length ? (
                <>
                  <div className="processing-section-heading">
                    <FileCheck2 size={17} />
                    <h3>处理方法</h3>
                  </div>
                  <div className="processing-field-grid">
                    {methodFields.map((field) => (
                      <FieldControl field={field} value={inputs[field.key] ?? ""} onBrowse={openPathBrowser} onChange={(value) => updateInput(field.key, value)} key={field.key} />
                    ))}
                  </div>
                </>
              ) : null}

              {cropFields.length ? (
                <>
                  <div className="processing-section-heading">
                    <FileCheck2 size={17} />
                    <h3>裁剪参数</h3>
                  </div>
                  <p className="section-help">启用裁剪时必须填写。它们应来自裁剪预览或人工判断，不再提供默认裁剪范围。</p>
                  <div className="processing-field-grid compact">
                    {cropFields.map((field) => (
                      <div className={missingKeys.has(field.key) ? "missing-field-wrap" : ""} key={field.key}>
                        <FieldControl field={field} value={inputs[field.key] ?? ""} onBrowse={openPathBrowser} onChange={(value) => updateInput(field.key, value)} />
                      </div>
                    ))}
                  </div>
                </>
              ) : null}

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
                            onBrowse={openPathBrowser}
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

              {cropReset ? (
                <div className="crop-reset-result">
                  <strong>{cropReset.status === "archived" ? "裁剪后结果已归档" : "无需归档"}</strong>
                  <p>{cropReset.message}</p>
                  {cropReset.archive_path ? <p>archive: {cropReset.archive_path}</p> : null}
                  {cropReset.moved_items.length ? <p>已移动: {cropReset.moved_items.join("、")}</p> : null}
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
                className="icon-text-button archive-crop-button"
                type="button"
                onClick={archiveCropOutputs}
                disabled={isSubmitting || isResettingCropOutputs || isActiveJob(job)}
                title="归档当前裁剪范围产生的下游结果，保留原始和配准结果"
              >
                {isResettingCropOutputs ? <Loader2 size={15} /> : <Archive size={15} />}
                归档裁剪后结果
              </button>
              <button
                className="primary-action processing-run-action"
                type="button"
                onClick={startProcessingJob}
                disabled={isSubmitting || isActiveJob(job)}
                title={!defaults?.execution_enabled ? "点击后会提示如何开启真实处理执行" : "保存配置并提交 Linux worker"}
              >
                {isSubmitting ? <Loader2 size={16} /> : <ServerCog size={16} />}
                {createdTask ? "确认开始处理" : "保存并开始处理"}
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
        {browserTarget ? (
          <div className="file-browser-layer">
            <section className="file-browser-modal" aria-label="选择 Linux 路径">
              <header className="file-browser-header">
                <div>
                  <h3>选择 {browserTarget.label}</h3>
                  <p>浏览的是后端 Linux worker 可访问的文件系统路径。</p>
                </div>
                <button className="icon-button subtle" type="button" onClick={closePathBrowser} title="关闭">
                  <X size={16} />
                </button>
              </header>

              <div className="file-browser-path-row">
                <input
                  value={browserPath}
                  onChange={(event) => setBrowserPath(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") void loadBrowserPath(browserPath);
                  }}
                  placeholder="/home/yu"
                />
                <button className="icon-text-button" type="button" onClick={() => void loadBrowserPath(browserPath)}>
                  {isBrowserLoading ? <Loader2 size={15} /> : <FolderOpen size={15} />}
                  打开
                </button>
              </div>

              {browserData?.roots.length ? (
                <div className="file-browser-roots">
                  {browserData.roots.map((root) => (
                    <button type="button" key={root.path} onClick={() => void loadBrowserPath(root.path)}>
                      {root.name}
                    </button>
                  ))}
                </div>
              ) : null}

              {browserError ? (
                <div className="processing-error compact-error">
                  <AlertTriangle size={15} />
                  {browserError}
                </div>
              ) : null}

              <div className="file-browser-list">
                {browserData?.parent_path ? (
                  <button className="file-browser-parent" type="button" onClick={() => void loadBrowserPath(browserData.parent_path ?? undefined)}>
                    <FolderOpen size={15} />
                    上一级
                  </button>
                ) : null}
                {browserData?.entries.map((entry) => (
                  <div className={`file-browser-entry ${entry.is_dir ? "is-dir" : ""}`} key={entry.path}>
                    <button
                      className="file-browser-entry-main"
                      type="button"
                      onClick={() => {
                        if (entry.is_dir) {
                          void loadBrowserPath(entry.path);
                        } else if (canSelectBrowserEntry(entry)) {
                          selectBrowserPath(entry.path);
                        }
                      }}
                    >
                      {entry.is_dir ? <FolderOpen size={16} /> : <FileCheck2 size={16} />}
                      <span>
                        <strong>{entry.name}</strong>
                        <small>{entry.path}</small>
                      </span>
                    </button>
                    {canSelectBrowserEntry(entry) ? (
                      <button className="file-browser-select" type="button" onClick={() => selectBrowserPath(entry.path)}>
                        选择
                      </button>
                    ) : null}
                  </div>
                ))}
                {!isBrowserLoading && browserData && browserData.entries.length === 0 ? <p className="file-browser-empty">这个目录里没有可显示的项目。</p> : null}
                {isBrowserLoading ? (
                  <p className="file-browser-empty">
                    <Loader2 size={15} />
                    正在读取目录
                  </p>
                ) : null}
              </div>

              <footer className="file-browser-footer">
                {(browserTarget.mode === "directory" || browserTarget.mode === "any") && browserData ? (
                  <button className="primary-action" type="button" onClick={() => selectBrowserPath(browserData.current_path)}>
                    使用当前文件夹
                  </button>
                ) : null}
                <button className="icon-text-button" type="button" onClick={closePathBrowser}>
                  取消
                </button>
              </footer>
            </section>
          </div>
        ) : null}
      </section>
    </div>
  );
}
