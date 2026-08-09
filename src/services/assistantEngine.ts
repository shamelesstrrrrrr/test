import type { ChatMessage, Citation, MockAnswer, QueryType } from "../types";
import { classifyQuestion, selectMockAnswer } from "../data/mockKnowledge";
import { assistantRuntimeConfig } from "../config/assistantConfig";

export type AssistantEngineMode = "mock" | "llm_api" | "rag_api";

export interface AssistantRequest {
  question: string;
  sessionId: string;
  messages: ChatMessage[];
}

export interface AssistantResponse {
  content: string;
  queryTypes: QueryType[];
  citations: Citation[];
  mode: AssistantEngineMode;
}

export interface AssistantProvider {
  mode: AssistantEngineMode;
  answer(request: AssistantRequest): Promise<AssistantResponse>;
}

interface ChatCompletionResponse {
  choices?: Array<{
    message?: {
      content?: string;
    };
  }>;
  error?: {
    message?: string;
  };
}

interface RagApiResponse {
  content?: string;
  queryTypes?: QueryType[];
  citations?: Citation[];
  mode?: "rag_api";
  detail?: string;
}

const llmApiCitation: Citation = {
  id: "src-llm-api-01",
  source: "Configured LLM API",
  page: "N/A",
  command_name: "N/A",
  section: "LLM response without retrieved manual chunks",
  verification_status: "insufficient_evidence",
  retrieval_score: 0,
  excerpt:
    "当前回答来自用户配置的 LLM API。Phase 1 尚未接入真实 GAMMA 手册检索，因此不能把它视为已验证手册证据。",
};

function mergeQueryTypes(primary: QueryType[], secondary: QueryType[]) {
  return Array.from(new Set([...primary, ...secondary]));
}

function toAssistantResponse(classifiedTypes: QueryType[], answer: MockAnswer): AssistantResponse {
  return {
    content: answer.answer,
    queryTypes: mergeQueryTypes(classifiedTypes, answer.queryTypes),
    citations: answer.citations,
    mode: "mock",
  };
}

export const mockAssistantProvider: AssistantProvider = {
  mode: "mock",
  async answer(request) {
    const classifiedTypes = classifyQuestion(request.question);
    const matchedAnswer = selectMockAnswer(request.question);

    return toAssistantResponse(classifiedTypes, matchedAnswer);
  },
};

function buildSystemPrompt() {
  return [
    "你是面向学生的 SAR/GAMMA 影像处理知识与流程指导助手。",
    "你只能提供知识解释、流程指导、目录建议和代码模板，不执行 GAMMA、不执行 Shell、不使用 SSH、不连接 MCP Server。",
    "如果没有检索到真实 GAMMA 手册片段，不要编造命令参数、页码、章节或精确参数顺序。",
    "当证据不足时，明确说明无法确认，并建议用户提供手册片段或具体命令上下文。",
    "代码模板必须使用占位符，例如 <PROJECT_ROOT>、<REFERENCE_SLC>、<OUTPUT_INTERFEROGRAM>，不得伪造用户真实路径。",
    "回答使用中文，必要时用 Markdown 表格和代码块。",
  ].join("\n");
}

function toChatMessages(messages: ChatMessage[], question: string) {
  const history = messages
    .slice(-8)
    .filter((message) => message.role === "user" || message.role === "assistant")
    .map((message) => ({
      role: message.role,
      content: message.content,
    }));

  return [
    { role: "system", content: buildSystemPrompt() },
    ...history,
    { role: "user", content: question },
  ];
}

function compactContent(content: string, maxChars = 700) {
  const compact = content.trim().replace(/\s+/g, " ");
  if (compact.length <= maxChars) return compact;
  return `${compact.slice(0, maxChars - 12)}... [截断]`;
}

function toCompactHistory(messages: ChatMessage[]) {
  return messages
    .slice(-8)
    .filter((message) => message.role === "user" || message.role === "assistant")
    .map((message) => ({
      role: message.role,
      content: compactContent(message.content),
    }));
}

function createMissingConfigResponse(missingFields: string[], classifiedTypes: QueryType[]): AssistantResponse {
  const fields = missingFields.map((field) => `- \`${field}\``).join("\n");

  return {
    content: `## LLM 尚未配置

当前已预留真实 LLM 接入入口，但还缺少必要配置：

${fields}

请在项目根目录创建 \`.env.local\`，参考 \`.env.example\` 填写接口地址和模型名称。若你的接口需要密钥，也填写 \`VITE_LLM_API_KEY\`；如果你使用本地后端代理注入密钥，可以留空。

## 当前不会生成真实答案

为了避免在未连接模型时误导你，系统不会伪造 SAR/GAMMA 命令、参数或手册引用。`,
    queryTypes: classifiedTypes,
    citations: [
      {
        ...llmApiCitation,
        id: "src-llm-config-missing",
        source: ".env.local",
        section: "Missing LLM configuration",
        excerpt: `缺少配置：${missingFields.join(", ")}`,
      },
    ],
    mode: "llm_api",
  };
}

function createLlmErrorResponse(errorMessage: string, classifiedTypes: QueryType[]): AssistantResponse {
  return {
    content: `## LLM 调用失败

已尝试连接你配置的 LLM 接口，但请求没有成功。

## 错误信息

\`\`\`text
${errorMessage}
\`\`\`

请检查 \`.env.local\` 中的接口地址、模型名称、密钥和跨域设置。`,
    queryTypes: classifiedTypes,
    citations: [
      {
        ...llmApiCitation,
        id: "src-llm-api-error",
        section: "LLM API error",
        excerpt: errorMessage,
      },
    ],
    mode: "llm_api",
  };
}

function createRagErrorResponse(errorMessage: string, classifiedTypes: QueryType[]): AssistantResponse {
  return {
    content: `## RAG 调用失败

已尝试连接本地 RAG 后端，但请求没有成功。

## 错误信息

\`\`\`text
${errorMessage}
\`\`\`

请确认 FastAPI 后端已经启动，并且后端环境变量中已经配置 \`SILICONFLOW_API_KEY\` 和 \`DEEPSEEK_API_KEY\`。`,
    queryTypes: classifiedTypes,
    citations: [
      {
        id: "src-rag-api-error",
        source: "Local RAG API",
        page: "N/A",
        command_name: "N/A",
        section: "RAG backend error",
        verification_status: "insufficient_evidence",
        retrieval_score: 0,
        excerpt: errorMessage,
      },
    ],
    mode: "rag_api",
  };
}

export const llmApiAssistantProvider: AssistantProvider = {
  mode: "llm_api",
  async answer(request): Promise<AssistantResponse> {
    const classifiedTypes = classifyQuestion(request.question);
    const { llm, missingFields } = assistantRuntimeConfig;

    if (missingFields.length > 0) {
      return createMissingConfigResponse(missingFields, classifiedTypes);
    }

    try {
      const response = await fetch(`${llm.baseUrl}${llm.endpointPath}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(llm.apiKey ? { Authorization: `Bearer ${llm.apiKey}` } : {}),
        },
        body: JSON.stringify({
          model: llm.model,
          messages: toChatMessages(request.messages, request.question),
          temperature: llm.temperature,
        }),
      });

      const payload = (await response.json().catch(() => ({}))) as ChatCompletionResponse;

      if (!response.ok) {
        return createLlmErrorResponse(payload.error?.message ?? `HTTP ${response.status}`, classifiedTypes);
      }

      const content = payload.choices?.[0]?.message?.content?.trim();

      if (!content) {
        return createLlmErrorResponse("LLM 响应中没有 choices[0].message.content。", classifiedTypes);
      }

      return {
        content,
        queryTypes: classifiedTypes,
        citations: [llmApiCitation],
        mode: "llm_api",
      };
    } catch (error) {
      return createLlmErrorResponse(error instanceof Error ? error.message : String(error), classifiedTypes);
    }
  },
};

export const ragApiAssistantProvider: AssistantProvider = {
  mode: "rag_api",
  async answer(request): Promise<AssistantResponse> {
    const classifiedTypes = classifyQuestion(request.question);
    const { rag, missingFields } = assistantRuntimeConfig;

    if (missingFields.length > 0) {
      return {
        content: `## RAG 后端尚未配置

当前已预留本地 RAG 后端入口，但还缺少必要配置：

${missingFields.map((field) => `- \`${field}\``).join("\n")}

请在项目根目录创建 \`.env.local\`，并设置 \`VITE_ASSISTANT_PROVIDER=rag_api\` 与 \`VITE_RAG_API_URL\`。`,
        queryTypes: classifiedTypes,
        citations: [
          {
            id: "src-rag-config-missing",
            source: ".env.local",
            page: "N/A",
            command_name: "N/A",
            section: "Missing RAG frontend configuration",
            verification_status: "insufficient_evidence",
            retrieval_score: 0,
            excerpt: `缺少配置：${missingFields.join(", ")}`,
          },
        ],
        mode: "rag_api",
      };
    }

    try {
      const response = await fetch(rag.apiUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          question: request.question,
          sessionId: request.sessionId,
          messages: toCompactHistory(request.messages),
        }),
      });

      const payload = (await response.json().catch(() => ({}))) as RagApiResponse;

      if (!response.ok) {
        return createRagErrorResponse(payload.detail ?? `HTTP ${response.status}`, classifiedTypes);
      }

      if (!payload.content) {
        return createRagErrorResponse("RAG 后端响应中没有 content 字段。", classifiedTypes);
      }

      return {
        content: payload.content,
        queryTypes: payload.queryTypes?.length ? payload.queryTypes : classifiedTypes,
        citations: payload.citations ?? [],
        mode: "rag_api",
      };
    } catch (error) {
      return createRagErrorResponse(error instanceof Error ? error.message : String(error), classifiedTypes);
    }
  },
};

export const activeAssistantProvider =
  assistantRuntimeConfig.provider === "mock"
    ? mockAssistantProvider
    : assistantRuntimeConfig.provider === "rag_api"
      ? ragApiAssistantProvider
      : llmApiAssistantProvider;

export async function answerStudentQuestion(request: AssistantRequest) {
  return activeAssistantProvider.answer(request);
}
