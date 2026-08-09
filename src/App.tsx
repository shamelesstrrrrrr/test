import { type DragEvent, type KeyboardEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  AlertTriangle,
  BookOpen,
  Check,
  Copy,
  Crop,
  FileText,
  FolderTree,
  Maximize2,
  MessageSquare,
  Move,
  PanelRight,
  Plus,
  Radar,
  RotateCcw,
  Search,
  Send,
  ServerCog,
  Square,
  Trash2,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { ProcessingTaskModal } from "./ProcessingTaskModal";
import type { ChatMessage, ChatSession, Citation, QueryType } from "./types";
import {
  initialAssistantMessage,
  queryTypeLabels,
  quickQuestions,
  seedSessions,
  verificationLabels,
} from "./data/mockKnowledge";
import { activeAssistantProvider, answerStudentQuestion } from "./services/assistantEngine";
import { assistantRuntimeConfig } from "./config/assistantConfig";
import {
  createProcessingJob,
  fetchProcessingJob,
  type ProcessingJobResponse,
  type ProcessingTaskResponse,
} from "./services/processingApi";

const STORAGE_KEY = "sar-gamma-phase1-sessions-v1";

function makeId(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }

  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function readStoredSessions() {
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return seedSessions;

  try {
    const parsed = JSON.parse(raw) as ChatSession[];
    return Array.isArray(parsed) && parsed.length > 0 ? parsed : seedSessions;
  } catch {
    return seedSessions;
  }
}

function shortenTitle(text: string) {
  const compact = text.trim().replace(/\s+/g, " ");
  return compact.length > 18 ? `${compact.slice(0, 18)}...` : compact || "未命名会话";
}

type DroppedPath = {
  value: string;
  isExact: boolean;
};

function droppedFilePath(file: File): DroppedPath {
  const nativePath = (file as File & { path?: string }).path;
  if (nativePath) return { value: nativePath, isExact: true };

  if (file.webkitRelativePath) {
    return { value: file.webkitRelativePath, isExact: false };
  }

  return { value: `<请补全绝对路径>/${file.name}`, isExact: false };
}

function buildDroppedFilesText(files: File[]) {
  const paths = files.map(droppedFilePath);
  const text = paths.map((path) => path.value).join("\n");
  const hasOnlyPlaceholders = paths.every((path) => !path.isExact);

  return {
    text,
    notice: hasOnlyPlaceholders
      ? "浏览器没有暴露文件绝对路径，已插入文件名占位符；执行前请补全 Linux 绝对路径。"
      : "已把拖入文件的路径插入输入框。",
  };
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

function isProcessingStartCommand(text: string) {
  const compact = text.replace(/\s+/g, "").toLowerCase();
  return (
    compact === "开始处理" ||
    compact === "进行数据处理" ||
    compact.includes("确认开始处理") ||
    compact.includes("确认进行数据处理") ||
    compact.includes("确认执行处理")
  );
}

function isProcessingStatusCommand(text: string) {
  const compact = text.replace(/\s+/g, "").toLowerCase();
  return compact.includes("处理进度") || compact.includes("任务进度") || compact.includes("处理状态") || compact.includes("任务状态");
}

function isProcessingSetupCommand(text: string) {
  const compact = text.replace(/\s+/g, "").toLowerCase();
  const hasProcessingGoal =
    compact.includes("数据处理") ||
    compact.includes("处理数据") ||
    compact.includes("dinsar") ||
    compact.includes("insar") ||
    compact.includes("gamma") ||
    compact.includes("哨兵") ||
    compact.includes("sentinel") ||
    compact.includes("slc") ||
    compact.includes("dem") ||
    compact.includes("差分") ||
    compact.includes("裁剪") ||
    compact.includes("配准") ||
    compact.includes("burst") ||
    compact.includes("stamps");
  const hasRuntimeCommand =
    compact.includes("确认开始处理") ||
    compact.includes("开始处理") ||
    compact.includes("处理进度") ||
    compact.includes("任务状态");

  return hasProcessingGoal && !hasRuntimeCommand;
}

function extractTaskId(text: string) {
  const match = text.match(/\b([A-Za-z0-9_.-]{3,})\b/);
  return match?.[1];
}

function extractDate(text: string) {
  return text.match(/\b(20\d{6})\b/)?.[1];
}

function extractFirstNumberAfter(text: string, keywords: string[]) {
  for (const keyword of keywords) {
    const index = text.toLowerCase().indexOf(keyword.toLowerCase());
    if (index < 0) continue;

    const rest = text.slice(index + keyword.length);
    const match = rest.match(/[:：=\s]*(\d+)/);
    if (match) return match[1];
  }

  return undefined;
}

function extractAbsolutePaths(text: string) {
  return Array.from(
    new Set([
      ...Array.from(text.matchAll(/(?:~|\/)[^\s，,。；;]+/g)).map((match) => match[0]),
      ...Array.from(text.matchAll(/(?:^|[\s，,：:=])([A-Za-z]:[\\/][^\s，,。；;]+)/g)).map((match) => match[1]),
    ]),
  );
}

const PROCESSING_STEP_ORDER = [
  "unzip_s1",
  "generate_slc",
  "extract_burst",
  "slc_geo",
  "coregistration",
  "crop_rslc",
  "write_rslc_tab",
  "base_calc",
  "mk_mli_all",
  "diff_workflow",
  "select_shp",
  "phase_optimization",
  "file_construct",
  "point_selection",
  "stamps_processing",
] as const;

const PROCESSING_STEP_TITLES: Record<(typeof PROCESSING_STEP_ORDER)[number], string> = {
  unzip_s1: "解压 Sentinel-1 ZIP",
  generate_slc: "生成 SLC",
  extract_burst: "提取 Burst",
  slc_geo: "主影像地理编码",
  coregistration: "主从影像配准",
  crop_rslc: "RSLC 裁剪",
  write_rslc_tab: "生成 RSLC_tab",
  base_calc: "生成基线和 itab",
  mk_mli_all: "生成 RMLI 强度图",
  diff_workflow: "生成差分干涉图",
  select_shp: "SHP 同质像元选取",
  phase_optimization: "相位优化",
  file_construct: "组织 StaMPS 时序文件",
  point_selection: "候选点选取",
  stamps_processing: "StaMPS 处理",
};

const WORKFLOW_REQUIRED_KEYS: Record<(typeof PROCESSING_STEP_ORDER)[number], string[]> = {
  unzip_s1: ["task_root", "raw_zip_dir"],
  generate_slc: ["task_root", "satellite", "polarization", "swath"],
  extract_burst: ["task_root", "polarization", "swath", "bn_start1", "bn_end1"],
  slc_geo: ["task_root", "dem_file", "master_date"],
  coregistration: ["task_root", "polarization", "swath"],
  crop_rslc: ["task_root", "master_date", "polarization", "swath", "crop_roff", "crop_nr", "crop_loff", "crop_nl"],
  write_rslc_tab: ["task_root"],
  base_calc: ["task_root", "master_date"],
  mk_mli_all: ["task_root"],
  diff_workflow: ["task_root", "dem_file", "master_date", "diff_method"],
  select_shp: ["task_root", "master_date", "matlab_func_dir", "shp_method"],
  phase_optimization: ["task_root", "matlab_func_dir", "phase_opt_method", "shp_method"],
  file_construct: ["task_root", "master_date"],
  point_selection: ["task_root", "master_date", "point_selection_method", "matlab_func_dir"],
  stamps_processing: ["task_root", "stamps_mode"],
};

function inferWorkflowRange(text: string) {
  const compact = text.replace(/\s+/g, "").toLowerCase();
  const wantsSingleStep = /只|仅|重新|重跑|再进行|单独/.test(text);

  let start: (typeof PROCESSING_STEP_ORDER)[number] = "unzip_s1";
  let end: (typeof PROCESSING_STEP_ORDER)[number] = "stamps_processing";

  if (/完整|全流程|全部|从头/.test(text)) {
    return { start, end };
  }

  const matchers: Array<[RegExp, (typeof PROCESSING_STEP_ORDER)[number]]> = [
    [/解压|zip/i, "unzip_s1"],
    [/生成slc|slc生成|slc/i, "generate_slc"],
    [/burst|切片|子带|提取/i, "extract_burst"],
    [/地理编码|geo/i, "slc_geo"],
    [/配准|coreg/i, "coregistration"],
    [/裁剪|crop/i, "crop_rslc"],
    [/rslc[_\s-]?tab/i, "write_rslc_tab"],
    [/基线|itab|base/i, "base_calc"],
    [/rmli|mli/i, "mk_mli_all"],
    [/差分|干涉图|diff/i, "diff_workflow"],
    [/shp|同质/i, "select_shp"],
    [/相位优化|phase/i, "phase_optimization"],
    [/file_construct|组织.*时序|时序文件/i, "file_construct"],
    [/点选取|候选点|point|dsc|pds|mt_prep/i, "point_selection"],
    [/stamps/i, "stamps_processing"],
  ];

  const matched = matchers.find(([pattern]) => pattern.test(compact) || pattern.test(text));
  if (!matched) return { start, end };

  end = matched[1];
  start = wantsSingleStep ? end : start;

  if (/到.*burst|直到.*burst|做到.*burst/.test(compact)) {
    start = "unzip_s1";
    end = "extract_burst";
  }

  if (/从.*裁剪|裁剪后|已有.*裁剪/.test(compact) && !wantsSingleStep) {
    start = "write_rslc_tab";
    end = "stamps_processing";
  }

  return { start, end };
}

function requiredKeysForWorkflowRange(inputs: Record<string, string>) {
  const start = inputs.workflow_start;
  const end = inputs.workflow_end;
  const startIndex = PROCESSING_STEP_ORDER.indexOf(start as (typeof PROCESSING_STEP_ORDER)[number]);
  const endIndex = PROCESSING_STEP_ORDER.indexOf(end as (typeof PROCESSING_STEP_ORDER)[number]);
  const keys: string[] = [];

  if (startIndex < 0 || endIndex < startIndex) return keys;

  for (const step of PROCESSING_STEP_ORDER.slice(startIndex, endIndex + 1)) {
    for (const key of WORKFLOW_REQUIRED_KEYS[step]) {
      if (step === "crop_rslc" && inputs.enable_crop === "false" && key.startsWith("crop_")) continue;
      if (!keys.includes(key)) keys.push(key);
    }
  }

  return keys;
}

function buildProcessingDraftFromText(text: string) {
  const inputs: Record<string, string> = {};
  const notes: string[] = [];
  const paths = extractAbsolutePaths(text);
  const lower = text.toLowerCase();
  const workflowRange = inferWorkflowRange(text);

  inputs.workflow_start = workflowRange.start;
  inputs.workflow_end = workflowRange.end;

  if (/不裁剪|无需裁剪|不要裁剪|跳过裁剪/.test(text)) {
    inputs.enable_crop = "false";
  }

  for (const path of paths) {
    const before = text.slice(0, Math.max(0, text.indexOf(path))).slice(-24).toLowerCase();
    const pathLower = path.toLowerCase();

    if (before.includes("dem") || pathLower.includes("dem") || /\.(tif|tiff|hgt|dem)$/i.test(path)) {
      inputs.dem_file = path;
      if (!/\.(tif|tiff|hgt|dem)$/i.test(path)) {
        notes.push("你给出的 DEM 看起来像目录，我先填入 DEM 文件路径字段；如果实际是目录，请改成具体 DEM 文件。");
      }
      continue;
    }

    if (before.includes("zip") || before.includes("数据") || pathLower.includes("zip") || /\.(zip)$/i.test(path)) {
      inputs.raw_zip_dir = path;
      continue;
    }

    if (before.includes("输出") || before.includes("任务") || pathLower.includes("task") || pathLower.includes("work")) {
      inputs.task_root = path;
      continue;
    }
  }

  const masterDate = extractDate(text);
  if (masterDate) {
    inputs.master_date = masterDate;
  }

  const bnStart = extractFirstNumberAfter(text, ["bn_start1", "burst起始", "burst 起始", "起始burst"]);
  const bnEnd = extractFirstNumberAfter(text, ["bn_end1", "burst结束", "burst 结束", "结束burst"]);
  if (bnStart) inputs.bn_start1 = bnStart;
  if (bnEnd) inputs.bn_end1 = bnEnd;

  if (lower.includes("s1b")) inputs.satellite = "S1B";
  if (lower.includes("s1a")) inputs.satellite = "S1A";
  if (lower.includes("vh")) inputs.polarization = "VH";
  if (lower.includes("vv")) inputs.polarization = "VV";

  const swathMatch = lower.match(/\biw[123]\b/);
  if (swathMatch) inputs.swath = swathMatch[0].toUpperCase();

  return { inputs, notes };
}

function formatProcessingSetupGuide(question: string, inputs: Record<string, string>, notes: string[]) {
  const provided = Object.entries(inputs).filter(([key]) => !["workflow_start", "workflow_end"].includes(key));
  const requiredKeys = requiredKeysForWorkflowRange(inputs);
  const missing = requiredKeys.filter((key) => !inputs[key]);
  const looksLikeTwoScene = /二轨|两轨|两景|二景|2景|2轨/.test(question);
  const workflowStart = inputs.workflow_start as (typeof PROCESSING_STEP_ORDER)[number];
  const workflowEnd = inputs.workflow_end as (typeof PROCESSING_STEP_ORDER)[number];

  return [
    "## 已切换到数据处理引导",
    "",
    `我理解你这次是要配置 ${looksLikeTwoScene ? "两景/二轨" : "Sentinel-1"} D-InSAR 数据处理任务。`,
    "",
    "拟执行的流程范围：",
    "",
    "```text",
    `${PROCESSING_STEP_TITLES[workflowStart] ?? workflowStart} → ${PROCESSING_STEP_TITLES[workflowEnd] ?? workflowEnd}`,
    "```",
    "",
    "如果这个范围不对，可以在左侧表单顶部改“起始步骤”和“结束步骤”。",
    "",
    provided.length
      ? ["我已从你的描述中识别并预填：", "", ...provided.map(([key, value]) => `- \`${key}\`：\`${value}\``)].join("\n")
      : "我还没有从这句话里识别到可直接预填的路径或日期。",
    "",
    missing.length
      ? ["还需要你补充：", "", ...missing.map((key) => `- \`${key}\``)].join("\n")
      : "基础必填项已经基本齐了，仍建议你在表单里检查每个参数。",
    "",
    "我已经打开“处理任务”面板。你可以在表单里检查/修改参数；裁剪参数仍然需要通过预览或人工判断后填写。",
    notes.length ? ["", "注意：", "", ...notes.map((note) => `- ${note}`)].join("\n") : "",
    "",
    "保存任务草稿后，可以点击 `确认开始处理`，也可以在对话框输入 `确认开始处理`。",
  ]
    .filter(Boolean)
    .join("\n");
}

function formatProcessingJob(job: ProcessingJobResponse) {
  return [
    "## 处理任务已提交",
    "",
    `- task_id：\`${job.task_id}\``,
    `- job_id：\`${job.job_id}\``,
    `- 状态：\`${job.status}\``,
    `- 进度：${job.progress_percent}% (${job.progress_current}/${job.progress_total})`,
    `- 当前步骤：\`${job.current_step ?? "无"}\``,
    `- 日志：\`${job.log_path}\``,
    "",
    "可以输入 `处理进度` 查询最新状态，也可以在处理任务面板查看日志。",
  ].join("\n");
}

function formatProcessingJobStatus(job: ProcessingJobResponse) {
  return [
    "## 处理进度",
    "",
    `- task_id：\`${job.task_id}\``,
    `- job_id：\`${job.job_id}\``,
    `- 状态：\`${job.status}\``,
    `- 进度：${job.progress_percent}% (${job.progress_current}/${job.progress_total})`,
    `- 当前步骤：\`${job.current_step ?? "无"}\``,
    job.error ? `- 错误：${job.error}` : "",
    "",
    job.log_tail
      ? ["### 日志片段", "", "```text", job.log_tail.slice(-2500), "```"].join("\n")
      : "暂无日志片段。",
  ]
    .filter(Boolean)
    .join("\n");
}

function CodeBlock({ className, children }: { className?: string; children: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const language = /language-(\w+)/.exec(className || "")?.[1] || "text";
  const code = String(children ?? "").replace(/\n$/, "");

  async function copyCode() {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }

  return (
    <div className="code-frame">
      <div className="code-toolbar">
        <span>{language === "gamma" ? "GAMMA" : language}</span>
        <button className="icon-button subtle" type="button" onClick={copyCode} title="复制代码">
          {copied ? <Check size={16} /> : <Copy size={16} />}
        </button>
      </div>
      <pre>
        <code>{code}</code>
      </pre>
    </div>
  );
}

function MarkdownMessage({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        code(props) {
          const { children, className } = props as { children: ReactNode; className?: string };

          if (!className) {
            return <code className="inline-code">{String(children ?? "")}</code>;
          }

          return <CodeBlock className={className} children={children} />;
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

function QueryTypePills({ types }: { types?: QueryType[] }) {
  if (!types || types.length === 0) return null;

  return (
    <div className="pill-row">
      {types.map((type) => (
        <span className="query-pill" key={type}>
          {queryTypeLabels[type]}
        </span>
      ))}
    </div>
  );
}

function SourceCard({ citation }: { citation: Citation }) {
  return (
    <article className="source-card">
      <div className="source-card-header">
        <BookOpen size={16} />
        <strong>{citation.command_name}</strong>
      </div>
      <dl className="source-meta">
        <div>
          <dt>source</dt>
          <dd>{citation.source}</dd>
        </div>
        <div>
          <dt>page</dt>
          <dd>{citation.page}</dd>
        </div>
        <div>
          <dt>section</dt>
          <dd>{citation.section}</dd>
        </div>
        <div>
          <dt>verification_status</dt>
          <dd>{verificationLabels[citation.verification_status]}</dd>
        </div>
        <div>
          <dt>retrieval_score</dt>
          <dd>{citation.retrieval_score.toFixed(2)}</dd>
        </div>
      </dl>
      <blockquote>{citation.excerpt}</blockquote>
    </article>
  );
}

function PendingMessage({ waitSeconds }: { waitSeconds: number }) {
  return (
    <article className="message assistant pending-message">
      <div className="message-heading">
        <div>
          <span className="message-role">助手</span>
        </div>
      </div>
      <div className="pending-body">
        <span className="pending-dot" />
        <span>正在检索知识库并生成回答，已等待 {waitSeconds} 秒</span>
      </div>
    </article>
  );
}

function engineDescription() {
  if (activeAssistantProvider.mode === "mock") {
    return "只提供知识与流程指导；当前回答来自本地模拟数据。";
  }
  if (activeAssistantProvider.mode === "rag_api") {
    return "只提供知识与流程指导；当前通过本地 RAG 后端检索手册并调用 LLM。";
  }
  return "只提供知识与流程指导；当前直接调用已配置的 LLM API，未经过手册检索。";
}

type CropMode = "crop" | "pan";

interface CropRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface DragState {
  mode: CropMode;
  startClientX: number;
  startClientY: number;
  startImageX: number;
  startImageY: number;
  startPanX: number;
  startPanY: number;
}

const DEFAULT_PREVIEW_SIZE = {
  width: 5200,
  height: 3600,
};

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function CropPreviewModal({ onClose }: { onClose: () => void }) {
  const surfaceRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [mode, setMode] = useState<CropMode>("crop");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [copied, setCopied] = useState(false);
  const [drag, setDrag] = useState<DragState | null>(null);
  const [previewImage, setPreviewImage] = useState<{ url: string; name: string } | null>(null);
  const [previewSize, setPreviewSize] = useState(DEFAULT_PREVIEW_SIZE);
  const [cropRect, setCropRect] = useState<CropRect>({
    x: 520,
    y: 360,
    width: 2600,
    height: 1600,
  });

  useEffect(() => {
    return () => {
      if (previewImage) {
        URL.revokeObjectURL(previewImage.url);
      }
    };
  }, [previewImage]);

  const cropValues = {
    crop_roff: Math.round(cropRect.x),
    crop_nr: Math.round(cropRect.width),
    crop_loff: Math.round(cropRect.y),
    crop_nl: Math.round(cropRect.height),
  };

  function zoomBy(delta: number) {
    setZoom((current) => clamp(Number((current + delta).toFixed(2)), 0.35, 4));
  }

  function resetView() {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }

  function screenToImage(event: React.PointerEvent<HTMLDivElement>) {
    const rect = surfaceRef.current?.getBoundingClientRect();

    if (!rect) {
      return { x: 0, y: 0 };
    }

    return {
      x: clamp(((event.clientX - rect.left) / rect.width) * previewSize.width, 0, previewSize.width),
      y: clamp(((event.clientY - rect.top) / rect.height) * previewSize.height, 0, previewSize.height),
    };
  }

  function handlePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    event.currentTarget.setPointerCapture(event.pointerId);

    const point = screenToImage(event);
    setDrag({
      mode,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startImageX: point.x,
      startImageY: point.y,
      startPanX: pan.x,
      startPanY: pan.y,
    });

    if (mode === "crop") {
      setCropRect({ x: point.x, y: point.y, width: 1, height: 1 });
    }
  }

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!drag) return;

    if (drag.mode === "pan") {
      setPan({
        x: drag.startPanX + event.clientX - drag.startClientX,
        y: drag.startPanY + event.clientY - drag.startClientY,
      });
      return;
    }

    const point = screenToImage(event);
    const x = Math.min(drag.startImageX, point.x);
    const y = Math.min(drag.startImageY, point.y);
    const width = Math.max(1, Math.abs(point.x - drag.startImageX));
    const height = Math.max(1, Math.abs(point.y - drag.startImageY));

    setCropRect({ x, y, width, height });
  }

  function handlePointerUp(event: React.PointerEvent<HTMLDivElement>) {
    event.currentTarget.releasePointerCapture(event.pointerId);
    setDrag(null);
  }

  async function copyCropValues() {
    await navigator.clipboard.writeText(
      [
        `crop_roff: "${cropValues.crop_roff}"`,
        `crop_nr: "${cropValues.crop_nr}"`,
        `crop_loff: "${cropValues.crop_loff}"`,
        `crop_nl: "${cropValues.crop_nl}"`,
      ].join("\n"),
    );
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }

  function handlePreviewFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith("image/")) {
      event.target.value = "";
      return;
    }

    const nextUrl = URL.createObjectURL(file);
    setPreviewImage((current) => {
      if (current) {
        URL.revokeObjectURL(current.url);
      }
      return { url: nextUrl, name: file.name };
    });
    setCopied(false);
    resetView();
  }

  function handlePreviewImageLoad(event: React.SyntheticEvent<HTMLImageElement>) {
    const image = event.currentTarget;
    const nextSize = {
      width: image.naturalWidth || DEFAULT_PREVIEW_SIZE.width,
      height: image.naturalHeight || DEFAULT_PREVIEW_SIZE.height,
    };

    setPreviewSize(nextSize);
    setCropRect({
      x: Math.round(nextSize.width * 0.1),
      y: Math.round(nextSize.height * 0.1),
      width: Math.round(nextSize.width * 0.5),
      height: Math.round(nextSize.height * 0.45),
    });
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="裁剪预览">
      <section className="crop-preview-modal">
        <header className="crop-preview-header">
          <div>
            <h2>裁剪预览</h2>
            <p>裁剪前检查点</p>
          </div>
          <button className="icon-button subtle" type="button" onClick={onClose} title="关闭">
            <X size={18} />
          </button>
        </header>

        <div className="crop-preview-toolbar" aria-label="裁剪工具">
          <input
            accept="image/png,image/jpeg,image/bmp,image/webp"
            className="hidden-file-input"
            ref={fileInputRef}
            type="file"
            onChange={handlePreviewFileChange}
          />
          <button className="icon-text-button" type="button" onClick={() => fileInputRef.current?.click()}>
            <FileText size={15} />
            选择预览图
          </button>
          <div className="segmented-control">
            <button
              className={mode === "crop" ? "active" : ""}
              type="button"
              onClick={() => setMode("crop")}
              title="框选裁剪范围"
            >
              <Crop size={16} />
              框选
            </button>
            <button
              className={mode === "pan" ? "active" : ""}
              type="button"
              onClick={() => setMode("pan")}
              title="平移预览图"
            >
              <Move size={16} />
              平移
            </button>
          </div>

          <div className="tool-button-row">
            <button className="icon-button" type="button" onClick={() => zoomBy(-0.2)} title="缩小">
              <ZoomOut size={17} />
            </button>
            <span className="zoom-readout">{Math.round(zoom * 100)}%</span>
            <button className="icon-button" type="button" onClick={() => zoomBy(0.2)} title="放大">
              <ZoomIn size={17} />
            </button>
            <button className="icon-button" type="button" onClick={resetView} title="重置视图">
              <RotateCcw size={17} />
            </button>
          </div>
        </div>

        <div className="crop-preview-body">
          <div
            className="crop-preview-canvas"
            onWheel={(event) => {
              event.preventDefault();
              zoomBy(event.deltaY < 0 ? 0.12 : -0.12);
            }}
          >
            <div
              className={`crop-preview-surface ${mode === "pan" ? "is-panning" : "is-cropping"}`}
              ref={surfaceRef}
              style={{
                aspectRatio: `${previewSize.width} / ${previewSize.height}`,
                transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
              }}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerCancel={() => setDrag(null)}
            >
              {previewImage ? (
                <img
                  alt="裁剪预览图"
                  className="crop-preview-image"
                  src={previewImage.url}
                  draggable={false}
                  onLoad={handlePreviewImageLoad}
                />
              ) : (
                <div className="sar-preview-texture" />
              )}
              <span className="preview-chip">
                {previewImage
                  ? `${previewImage.name} · ${previewSize.width} x ${previewSize.height}`
                  : "未选择图片"}
              </span>
              <div
                className="crop-selection"
                style={{
                  left: `${(cropRect.x / previewSize.width) * 100}%`,
                  top: `${(cropRect.y / previewSize.height) * 100}%`,
                  width: `${(cropRect.width / previewSize.width) * 100}%`,
                  height: `${(cropRect.height / previewSize.height) * 100}%`,
                }}
              />
            </div>
          </div>

          <aside className="crop-params-panel">
            <div className="param-panel-title">
              <Maximize2 size={16} />
              裁剪参数
            </div>
            <dl className="crop-param-list">
              {Object.entries(cropValues).map(([key, value]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
            <button className="primary-action compact" type="button" onClick={copyCropValues}>
              {copied ? <Check size={16} /> : <Copy size={16} />}
              复制参数
            </button>
          </aside>
        </div>
      </section>
    </div>
  );
}

function App() {
  const [sessions, setSessions] = useState<ChatSession[]>(readStoredSessions);
  const [activeSessionId, setActiveSessionId] = useState(() => readStoredSessions()[0]?.id ?? "session-demo");
  const [input, setInput] = useState("");
  const [activeSourceMessageId, setActiveSourceMessageId] = useState<string | null>(null);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [isResponding, setIsResponding] = useState(false);
  const [waitSeconds, setWaitSeconds] = useState(0);
  const [isComposerDragOver, setIsComposerDragOver] = useState(false);
  const [dropNotice, setDropNotice] = useState("");
  const [isCropPreviewOpen, setIsCropPreviewOpen] = useState(false);
  const [isProcessingTaskOpen, setIsProcessingTaskOpen] = useState(false);
  const [processingDraftInputs, setProcessingDraftInputs] = useState<Record<string, string>>({});
  const [latestProcessingTask, setLatestProcessingTask] = useState<ProcessingTaskResponse | null>(null);
  const [latestProcessingJob, setLatestProcessingJob] = useState<ProcessingJobResponse | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  }, [sessions]);

  useEffect(() => {
    if (!isResponding) {
      setWaitSeconds(0);
      return undefined;
    }

    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      setWaitSeconds(Math.max(1, Math.floor((Date.now() - startedAt) / 1000)));
    }, 500);

    return () => window.clearInterval(timer);
  }, [isResponding]);

  const activeSession = useMemo(() => {
    return sessions.find((session) => session.id === activeSessionId) ?? sessions[0];
  }, [activeSessionId, sessions]);

  const activeCitations = useMemo(() => {
    if (!activeSession) return [];

    const selected = activeSession.messages.find((message) => message.id === activeSourceMessageId);
    if (selected?.citations?.length) return selected.citations;

    return (
      [...activeSession.messages].reverse().find((message) => message.role === "assistant" && message.citations?.length)
        ?.citations ?? []
    );
  }, [activeSession, activeSourceMessageId]);

  function updateSession(updated: ChatSession) {
    setSessions((current) => current.map((session) => (session.id === updated.id ? updated : session)));
  }

  function createSession() {
    const now = new Date().toISOString();
    const session: ChatSession = {
      id: makeId("session"),
      title: "新建学习会话",
      createdAt: now,
      updatedAt: now,
      messages: [{ ...initialAssistantMessage, id: makeId("assistant") }],
    };

    setSessions((current) => [session, ...current]);
    setActiveSessionId(session.id);
    setActiveSourceMessageId(null);
  }

  function deleteSession(sessionId: string) {
    setSessions((current) => {
      const next = current.filter((session) => session.id !== sessionId);

      if (next.length === 0) {
        const now = new Date().toISOString();
        const replacement: ChatSession = {
          id: makeId("session"),
          title: "新建学习会话",
          createdAt: now,
          updatedAt: now,
          messages: [{ ...initialAssistantMessage, id: makeId("assistant") }],
        };
        setActiveSessionId(replacement.id);
        return [replacement];
      }

      if (activeSessionId === sessionId) {
        setActiveSessionId(next[0].id);
      }

      return next;
    });
  }

  function appendAssistantExchange(sessionId: string, question: string, content: string) {
    const now = new Date().toISOString();
    const userMessage: ChatMessage = {
      id: makeId("user"),
      role: "user",
      content: question,
    };
    const assistantMessage: ChatMessage = {
      id: makeId("assistant"),
      role: "assistant",
      content,
      queryTypes: ["workflow"],
    };

    setInput("");
    setSessions((current) =>
      current.map((session) =>
        session.id === sessionId
          ? {
              ...session,
              title: session.messages.length <= 1 ? shortenTitle(question) : session.title,
              updatedAt: now,
              messages: [...session.messages, userMessage, assistantMessage],
            }
          : session,
      ),
    );
  }

  async function handleProcessingStartFromChat(question: string) {
    if (!activeSession || isResponding) return;

    const sessionId = activeSession.id;
    const explicitTaskId = extractTaskId(question);
    const taskId = explicitTaskId ?? latestProcessingTask?.task_id;
    setInput("");
    setIsResponding(true);

    try {
      if (!taskId) {
        appendAssistantExchange(
          sessionId,
          question,
          "还没有可执行的处理配置。请先打开 `处理任务`，填写并保存一份完整配置，然后再输入 `确认开始处理`。",
        );
        return;
      }

      if (!explicitTaskId && latestProcessingTask?.missing.length) {
        appendAssistantExchange(
          sessionId,
          question,
          `最近保存的配置还不完整，不能开始处理。缺少：${latestProcessingTask.missing.map((field) => `\`${field.key}\``).join("、")}`,
        );
        return;
      }

      const job = await createProcessingJob(taskId);
      setLatestProcessingJob(job);
      appendAssistantExchange(sessionId, question, formatProcessingJob(job));
    } catch (error) {
      appendAssistantExchange(
        sessionId,
        question,
        `## 无法开始处理\n\n\`\`\`text\n${error instanceof Error ? error.message : String(error)}\n\`\`\``,
      );
    } finally {
      setIsResponding(false);
    }
  }

  async function handleProcessingStatusFromChat(question: string) {
    if (!activeSession || isResponding) return;

    const sessionId = activeSession.id;
    setInput("");
    setIsResponding(true);

    try {
      if (!latestProcessingJob) {
        appendAssistantExchange(sessionId, question, "当前会话还没有提交过处理任务。");
        return;
      }

      const job = await fetchProcessingJob(latestProcessingJob.task_id, latestProcessingJob.job_id);
      setLatestProcessingJob(job);
      appendAssistantExchange(sessionId, question, formatProcessingJobStatus(job));
    } catch (error) {
      appendAssistantExchange(
        sessionId,
        question,
        `## 无法查询处理进度\n\n\`\`\`text\n${error instanceof Error ? error.message : String(error)}\n\`\`\``,
      );
    } finally {
      setIsResponding(false);
    }
  }

  function handleProcessingSetupFromChat(question: string) {
    if (!activeSession || isResponding) return;

    const { inputs, notes } = buildProcessingDraftFromText(question);
    setProcessingDraftInputs(inputs);
    setIsProcessingTaskOpen(true);
    appendAssistantExchange(activeSession.id, question, formatProcessingSetupGuide(question, inputs, notes));
  }

  async function sendQuestion(questionText = input) {
    const question = questionText.trim();
    if (!question || !activeSession || isResponding) return;

    if (isProcessingStartCommand(question)) {
      await handleProcessingStartFromChat(question);
      return;
    }

    if (isProcessingStatusCommand(question)) {
      await handleProcessingStatusFromChat(question);
      return;
    }

    if (isProcessingSetupCommand(question)) {
      handleProcessingSetupFromChat(question);
      return;
    }

    const now = new Date().toISOString();
    const sessionId = activeSession.id;
    const requestMessages = activeSession.messages;
    const controller = new AbortController();
    const userMessage: ChatMessage = {
      id: makeId("user"),
      role: "user",
      content: question,
    };

    abortControllerRef.current = controller;
    setInput("");
    setIsResponding(true);
    setWaitSeconds(0);
    setSessions((current) =>
      current.map((session) =>
        session.id === sessionId
          ? {
              ...session,
              title: session.messages.length <= 1 ? shortenTitle(question) : session.title,
              updatedAt: now,
              messages: [...session.messages, userMessage],
            }
          : session,
      ),
    );

    try {
      const assistantResponse = await answerStudentQuestion({
        question,
        sessionId,
        messages: requestMessages,
        signal: controller.signal,
      });

      if (controller.signal.aborted) return;

      const assistantMessage: ChatMessage = {
        id: makeId("assistant"),
        role: "assistant",
        content: assistantResponse.content,
        queryTypes: assistantResponse.queryTypes,
        citations: assistantResponse.citations,
      };

      setSessions((current) =>
        current.map((session) =>
          session.id === sessionId
            ? {
                ...session,
                updatedAt: new Date().toISOString(),
                messages: [...session.messages, assistantMessage],
              }
            : session,
        ),
      );
      setActiveSourceMessageId(assistantMessage.id);
    } catch (sendError) {
      const stopped = controller.signal.aborted || isAbortError(sendError);
      const assistantMessage: ChatMessage = {
        id: makeId("assistant"),
        role: "assistant",
        content: stopped
          ? "已停止当前回答生成。"
          : `## 问答请求失败\n\n\`\`\`text\n${sendError instanceof Error ? sendError.message : String(sendError)}\n\`\`\``,
      };

      setSessions((current) =>
        current.map((session) =>
          session.id === sessionId
            ? {
                ...session,
                updatedAt: new Date().toISOString(),
                messages: [...session.messages, assistantMessage],
              }
            : session,
        ),
      );
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
      }
      setIsResponding(false);
    }
  }

  function stopCurrentResponse() {
    abortControllerRef.current?.abort();
    setIsResponding(false);
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;

    event.preventDefault();
    void sendQuestion();
  }

  function appendToComposer(text: string) {
    setInput((current) => {
      const trimmed = current.trimEnd();
      return trimmed ? `${trimmed}\n${text}` : text;
    });
  }

  function handleComposerDragOver(event: DragEvent<HTMLFormElement>) {
    if (![...event.dataTransfer.types].includes("Files")) return;

    event.preventDefault();
    setIsComposerDragOver(true);
  }

  function handleComposerDragLeave(event: DragEvent<HTMLFormElement>) {
    const relatedTarget = event.relatedTarget;
    if (relatedTarget instanceof Node && event.currentTarget.contains(relatedTarget)) return;

    setIsComposerDragOver(false);
  }

  function handleComposerDrop(event: DragEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsComposerDragOver(false);

    const files = Array.from(event.dataTransfer.files);
    if (files.length === 0) return;

    const dropped = buildDroppedFilesText(files);
    appendToComposer(dropped.text);
    setDropNotice(dropped.notice);
  }

  async function copyMessage(message: ChatMessage) {
    await navigator.clipboard.writeText(message.content);
    setCopiedMessageId(message.id);
    window.setTimeout(() => setCopiedMessageId(null), 1200);
  }

  if (!activeSession) {
    return null;
  }

  return (
    <>
      <main className="app-shell">
      <aside className="left-rail">
        <div className="brand">
          <div className="brand-mark">
            <Radar size={20} />
          </div>
          <div>
            <h1>SAR/GAMMA 助手</h1>
            <p>RAG 学习助手</p>
          </div>
        </div>

        <button className="primary-action" type="button" onClick={createSession}>
          <Plus size={16} />
          新建会话
        </button>

        <div className="rail-section-title">
          <MessageSquare size={15} />
          历史会话
        </div>

        <nav className="session-list" aria-label="历史会话">
          {sessions.map((session) => (
            <div className={`session-row ${session.id === activeSessionId ? "active" : ""}`} key={session.id}>
              <button
                className="session-select"
                type="button"
                onClick={() => {
                  setActiveSessionId(session.id);
                  setActiveSourceMessageId(null);
                }}
              >
                <span>{session.title}</span>
                <small>{new Date(session.updatedAt).toLocaleDateString("zh-CN")}</small>
              </button>
              <button
                className="icon-button subtle"
                type="button"
                onClick={() => deleteSession(session.id)}
                title="删除会话"
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </nav>
      </aside>

      <section className="center-stage">
        <header className="top-bar">
          <div>
            <h2>{activeSession.title}</h2>
            <p>{engineDescription()}</p>
          </div>
          <div className="top-actions">
            <button className="icon-text-button" type="button" onClick={() => setIsProcessingTaskOpen(true)}>
              <ServerCog size={15} />
              处理任务
            </button>
            <button className="icon-text-button" type="button" onClick={() => setIsCropPreviewOpen(true)}>
              <Crop size={15} />
              裁剪预览
            </button>
            <div className="agent-flow" aria-label="Agent 流程">
              <span>assistant_engine: {activeAssistantProvider.mode}</span>
              {activeAssistantProvider.mode === "llm_api" && (
                <span>
                  llm_config: {assistantRuntimeConfig.missingFields.length > 0 ? "missing" : "ready"}
                </span>
              )}
              {activeAssistantProvider.mode === "rag_api" && <span>rag_endpoint: local_fastapi</span>}
              <span>classify_query</span>
              <span>retrieve_documents</span>
              <span>validate_grounding</span>
            </div>
          </div>
        </header>

        <div className="quick-strip" aria-label="快捷问题">
          {quickQuestions.map((question) => (
            <button type="button" key={question} onClick={() => void sendQuestion(question)} disabled={isResponding}>
              {question}
            </button>
          ))}
        </div>

        <div className="message-stream" aria-live="polite">
          {activeSession.messages.map((message) => (
            <article className={`message ${message.role}`} key={message.id}>
              <div className="message-heading">
                <div>
                  <span className="message-role">{message.role === "user" ? "学生" : "助手"}</span>
                  <QueryTypePills types={message.queryTypes} />
                </div>
                {message.role === "assistant" && (
                  <div className="message-actions">
                    {message.citations && message.citations.length > 0 && (
                      <button
                        className="icon-text-button"
                        type="button"
                        onClick={() => setActiveSourceMessageId(message.id)}
                      >
                        <PanelRight size={15} />
                        引用
                      </button>
                    )}
                    <button
                      className="icon-button subtle"
                      type="button"
                      title="复制回答"
                      onClick={() => copyMessage(message)}
                    >
                      {copiedMessageId === message.id ? <Check size={15} /> : <Copy size={15} />}
                    </button>
                  </div>
                )}
              </div>
              <div className="markdown-body">
                <MarkdownMessage content={message.content} />
              </div>
            </article>
          ))}
          {isResponding && <PendingMessage waitSeconds={waitSeconds} />}
        </div>

        <form
          className={`composer ${isComposerDragOver ? "drag-over" : ""}`}
          onDragOver={handleComposerDragOver}
          onDragLeave={handleComposerDragLeave}
          onDrop={handleComposerDrop}
          onSubmit={(event) => {
            event.preventDefault();
            void sendQuestion();
          }}
        >
          <div className="composer-alert">
            <AlertTriangle size={15} />
            当前版本不会执行 GAMMA、Shell、SSH、MCP 或任何真实处理任务；RAG 仅检索知识库并调用对话模型生成说明。
          </div>
          {dropNotice ? <div className="composer-drop-note">{dropNotice}</div> : null}
          <div className="composer-box">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              placeholder="输入 SAR/InSAR 概念、流程、命令、参数、目录或代码模板问题..."
              rows={3}
            />
            <button
              className={`send-button ${isResponding ? "stop-button" : ""}`}
              type={isResponding ? "button" : "submit"}
              title={isResponding ? "停止回答" : "发送问题"}
              onClick={isResponding ? stopCurrentResponse : undefined}
            >
              {isResponding ? <Square size={16} /> : <Send size={18} />}
            </button>
          </div>
        </form>
      </section>

      <aside className="right-rail">
        <div className="source-panel-heading">
          <div>
            <h2>文档来源</h2>
            <p>source / page / command_name / section</p>
          </div>
          <Search size={18} />
        </div>

        {activeCitations.length === 0 ? (
          <div className="empty-source">
            <FileText size={24} />
            <p>选择带引用的回答后显示手册来源。</p>
          </div>
        ) : (
          <div className="source-list">
            {activeCitations.map((citation) => (
              <SourceCard citation={citation} key={citation.id} />
            ))}
          </div>
        )}

        <div className="folder-note">
          <FolderTree size={16} />
          路径示例始终使用占位符，例如 &lt;PROJECT_ROOT&gt;。
        </div>
      </aside>
      </main>
      {isProcessingTaskOpen && (
        <ProcessingTaskModal
          onClose={() => setIsProcessingTaskOpen(false)}
          initialInputs={processingDraftInputs}
          onTaskSaved={setLatestProcessingTask}
          onJobStarted={setLatestProcessingJob}
        />
      )}
      {isCropPreviewOpen && <CropPreviewModal onClose={() => setIsCropPreviewOpen(false)} />}
    </>
  );
}

export default App;
