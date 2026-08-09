import { type KeyboardEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
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
  const [isCropPreviewOpen, setIsCropPreviewOpen] = useState(false);
  const [isProcessingTaskOpen, setIsProcessingTaskOpen] = useState(false);

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

  async function sendQuestion(questionText = input) {
    const question = questionText.trim();
    if (!question || !activeSession || isResponding) return;

    const now = new Date().toISOString();
    const sessionId = activeSession.id;
    const requestMessages = activeSession.messages;
    const userMessage: ChatMessage = {
      id: makeId("user"),
      role: "user",
      content: question,
    };

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
      });

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
    } finally {
      setIsResponding(false);
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;

    event.preventDefault();
    void sendQuestion();
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
          className="composer"
          onSubmit={(event) => {
            event.preventDefault();
            void sendQuestion();
          }}
        >
          <div className="composer-alert">
            <AlertTriangle size={15} />
            当前版本不会执行 GAMMA、Shell、SSH、MCP 或任何真实处理任务；RAG 仅检索知识库并调用对话模型生成说明。
          </div>
          <div className="composer-box">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              placeholder="输入 SAR/InSAR 概念、流程、命令、参数、目录或代码模板问题..."
              rows={3}
            />
            <button className="send-button" type="submit" title="发送问题" disabled={isResponding}>
              <Send size={18} />
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
      {isProcessingTaskOpen && <ProcessingTaskModal onClose={() => setIsProcessingTaskOpen(false)} />}
      {isCropPreviewOpen && <CropPreviewModal onClose={() => setIsCropPreviewOpen(false)} />}
    </>
  );
}

export default App;
