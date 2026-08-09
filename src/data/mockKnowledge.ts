import type { ChatMessage, ChatSession, Citation, MockAnswer, QueryType } from "../types";

const nowIso = "2026-08-04T00:00:00.000Z";

export const quickQuestions = [
  "什么是 InSAR？",
  "从两景 SLC 生成干涉图的流程是什么？",
  "SLC_intf 命令的参数如何理解？",
  "SAR 项目目录应该怎么组织？",
  "给我一个 Python 命令模板示例",
];

export const queryTypeLabels: Record<QueryType, string> = {
  concept: "concept",
  workflow: "workflow",
  command: "command",
  parameter: "parameter",
  file_layout: "file_layout",
  code_template: "code_template",
};

export const verificationLabels = {
  mock_verified: "Phase 1 模拟已核对",
  mock_partial: "Phase 1 模拟部分核对",
  manual_verified: "真实手册证据",
  partial_manual_evidence: "部分手册证据",
  code_reference: "代码库辅助证据",
  web_reference: "网页补充证据",
  insufficient_evidence: "证据不足",
};

const conceptCitations: Citation[] = [
  {
    id: "src-insar-01",
    source: "GAMMA Remote Sensing Concepts Notes (Phase 1 mock)",
    page: "p. 8",
    command_name: "N/A",
    section: "SAR 与 InSAR 基础",
    verification_status: "mock_verified",
    retrieval_score: 0.88,
    excerpt:
      "InSAR compares the phase of two complex SAR observations acquired from nearby viewing geometries to estimate phase differences related to topography or surface displacement.",
  },
  {
    id: "src-insar-02",
    source: "GAMMA DIFF&GEO User Manual (Phase 1 mock)",
    page: "p. 14",
    command_name: "N/A",
    section: "Interferometric products",
    verification_status: "mock_partial",
    retrieval_score: 0.76,
    excerpt:
      "A complex interferogram stores wrapped phase and amplitude information; further filtering, phase unwrapping, and geocoding are normally required for interpretation.",
  },
];

const workflowCitations: Citation[] = [
  {
    id: "src-flow-01",
    source: "GAMMA ISP User Manual (Phase 1 mock)",
    page: "p. 33",
    command_name: "SLC_copy",
    section: "SLC preparation",
    verification_status: "mock_partial",
    retrieval_score: 0.72,
    excerpt:
      "SLC preparation steps keep the complex image and its parameter file together before registration and interferogram formation.",
  },
  {
    id: "src-flow-02",
    source: "GAMMA DIFF&GEO User Manual (Phase 1 mock)",
    page: "p. 57",
    command_name: "create_offset",
    section: "Offset parameter initialization",
    verification_status: "mock_verified",
    retrieval_score: 0.9,
    excerpt:
      "The offset parameter file records initial geometry and processing settings used by registration and interferogram programs.",
  },
  {
    id: "src-flow-03",
    source: "GAMMA DIFF&GEO User Manual (Phase 1 mock)",
    page: "p. 74",
    command_name: "SLC_intf",
    section: "Interferogram generation",
    verification_status: "mock_verified",
    retrieval_score: 0.93,
    excerpt:
      "SLC_intf forms a complex interferogram from a reference SLC and a secondary SLC using associated SLC parameter and offset parameter files.",
  },
];

const commandCitations: Citation[] = [
  {
    id: "src-cmd-01",
    source: "GAMMA DIFF&GEO Reference Manual (Phase 1 mock)",
    page: "p. 74",
    command_name: "SLC_intf",
    section: "Command synopsis",
    verification_status: "mock_verified",
    retrieval_score: 0.94,
    excerpt:
      "SLC_intf <reference_slc> <secondary_slc> <reference_slc_par> <secondary_slc_par> <offset_par> <interferogram> <range_looks> <azimuth_looks>",
  },
  {
    id: "src-cmd-02",
    source: "GAMMA DIFF&GEO Reference Manual (Phase 1 mock)",
    page: "p. 75",
    command_name: "SLC_intf",
    section: "Input and output files",
    verification_status: "mock_partial",
    retrieval_score: 0.82,
    excerpt:
      "The output complex interferogram is generated from co-registered SLC input data. Multilook factors control range and azimuth averaging.",
  },
];

const layoutCitations: Citation[] = [
  {
    id: "src-layout-01",
    source: "SAR Teaching Workflow Notes (Phase 1 mock)",
    page: "p. 5",
    command_name: "N/A",
    section: "Project folder conventions",
    verification_status: "mock_verified",
    retrieval_score: 0.86,
    excerpt:
      "A teaching project is easier to audit when raw data, DEM data, SLC products, parameter files, interferograms, logs, and final maps are separated.",
  },
];

const templateCitations: Citation[] = [
  {
    id: "src-template-01",
    source: "GAMMA Command Template Notes (Phase 1 mock)",
    page: "p. 12",
    command_name: "SLC_intf",
    section: "Template examples",
    verification_status: "mock_partial",
    retrieval_score: 0.79,
    excerpt:
      "Templates should preserve placeholders for user paths and should not assume a real local directory or a verified parameter order without manual evidence.",
  },
];

export const mockAnswers: MockAnswer[] = [
  {
    id: "answer-concept-insar",
    title: "InSAR 基础概念",
    triggers: ["insar", "基础", "概念", "什么是", "相干", "干涉"],
    queryTypes: ["concept"],
    citations: conceptCitations,
    answer: `## 处理目标

理解 InSAR 是如何利用两景或多景 SAR 复数影像的相位差来表达地形、形变或大气等信息。

## 核心解释

SAR 影像是主动微波成像结果，SLC 数据通常保存复数值，包含幅度和相位。InSAR 会比较两次观测的相位差，形成干涉相位。干涉相位可能同时包含地形、地表形变、轨道误差、大气延迟和噪声，因此不能把一幅干涉图直接等同于形变量。

## 学生应先掌握

1. SLC 是复数影像，不只是灰度图。
2. 干涉图的相位通常是缠绕相位，范围在 -pi 到 pi。
3. 相干性用于判断两景影像是否适合做干涉处理。
4. DEM 常用于去除地形相位或把结果地理编码到地图坐标。

## 注意事项

当前界面是 Phase 1 静态演示，右侧来源为模拟引用。真实版本必须先检索 GAMMA 手册，再给出可核验结论。`,
  },
  {
    id: "answer-workflow-slc-interferogram",
    title: "两景 SLC 生成干涉图流程",
    triggers: ["slc", "干涉图", "流程", "生成", "两景", "workflow"],
    queryTypes: ["workflow", "command", "file_layout"],
    citations: workflowCitations,
    answer: `## 处理目标

从一景参考 SLC 和一景辅 SLC 生成复数干涉图，并保留参数文件和中间文件，方便后续滤波、解缠和地理编码。

## 前置条件

1. 已有参考影像和辅影像的 SLC 文件。
2. 每个 SLC 都有对应参数文件。
3. 两景数据覆盖区域和极化方式适合干涉处理。
4. 已准备或计划准备 DEM。

## 处理步骤

| 步骤 | 输入 | 输出 | 可能使用的命令 |
|---|---|---|---|
| 1. 整理原始数据 | 原始 SAR 产品、轨道文件 | 标准项目目录 | 当前版本不执行命令 |
| 2. SLC 准备 | 参考/辅 SLC 和参数文件 | 可用于配准的 SLC 数据 | SLC_copy 或同类准备命令 |
| 3. 初始化偏移参数 | 参考 SLC 参数、辅 SLC 参数 | offset 参数文件 | create_offset |
| 4. 配准检查 | SLC、offset 参数 | 配准质量信息 | 需要真实手册确认 |
| 5. 生成干涉图 | 配准后的 SLC、参数文件、offset 参数 | 复数干涉图 | SLC_intf |
| 6. 后续处理 | 干涉图、DEM、参数文件 | 滤波/解缠/地理编码结果 | 需要真实手册确认 |

## 推荐目录

\`\`\`text
<PROJECT_ROOT>/
  data_raw/
    reference/
    secondary/
  dem/
  slc/
    reference/
    secondary/
  parameters/
  offsets/
  interferograms/
  results/
  notes/
\`\`\`

## 注意事项

- 这里只展示教学型流程，不执行 GAMMA、不执行 Shell、不连接远程环境。
- 若没有检索到真实手册证据，系统不应输出精确参数顺序。
- Phase 1 的命令名称和页码均为模拟数据，不能替代正式手册核对。`,
  },
  {
    id: "answer-command-slc-intf",
    title: "SLC_intf 命令说明",
    triggers: ["slc_intf", "参数", "命令", "command", "parameter"],
    queryTypes: ["command", "parameter", "code_template"],
    citations: commandCitations,
    answer: `## 命令用途

\`SLC_intf\` 在本静态示例中表示“由两景已配准 SLC 生成复数干涉图”的 GAMMA 命令。该说明来自 Phase 1 模拟手册片段，不可直接作为真实生产命令依据。

## 命令格式

\`\`\`gamma
SLC_intf <REFERENCE_SLC> <SECONDARY_SLC> <REFERENCE_SLC_PAR> <SECONDARY_SLC_PAR> <OFFSET_PAR> <OUTPUT_INTERFEROGRAM> <RANGE_LOOKS> <AZIMUTH_LOOKS>
\`\`\`

## 参数表

| 参数 | 类型 | 是否必填 | 作用 | 输入/输出关系 | 示例占位符 |
|---|---|---|---|---|---|
| REFERENCE_SLC | file path | 是 | 参考 SLC 复数影像 | 输入 | <PROJECT_ROOT>/slc/reference/ref.slc |
| SECONDARY_SLC | file path | 是 | 辅 SLC 复数影像 | 输入 | <PROJECT_ROOT>/slc/secondary/sec.slc |
| REFERENCE_SLC_PAR | file path | 是 | 参考 SLC 参数文件 | 输入 | <PROJECT_ROOT>/parameters/ref.slc.par |
| SECONDARY_SLC_PAR | file path | 是 | 辅 SLC 参数文件 | 输入 | <PROJECT_ROOT>/parameters/sec.slc.par |
| OFFSET_PAR | file path | 是 | 配准或偏移参数 | 输入 | <PROJECT_ROOT>/offsets/ref_sec.off |
| OUTPUT_INTERFEROGRAM | file path | 是 | 输出复数干涉图 | 输出 | <PROJECT_ROOT>/interferograms/ref_sec.int |
| RANGE_LOOKS | integer | 是 | 距离向多视数 | 控制输出分辨率 | <RANGE_LOOKS> |
| AZIMUTH_LOOKS | integer | 是 | 方位向多视数 | 控制输出分辨率 | <AZIMUTH_LOOKS> |

## 示例代码

\`\`\`gamma
SLC_intf <REFERENCE_SLC> <SECONDARY_SLC> <REFERENCE_SLC_PAR> <SECONDARY_SLC_PAR> <OFFSET_PAR> <OUTPUT_INTERFEROGRAM> <RANGE_LOOKS> <AZIMUTH_LOOKS>
\`\`\`

\`\`\`python
command = [
    "SLC_intf",
    "<REFERENCE_SLC>",
    "<SECONDARY_SLC>",
    "<REFERENCE_SLC_PAR>",
    "<SECONDARY_SLC_PAR>",
    "<OFFSET_PAR>",
    "<OUTPUT_INTERFEROGRAM>",
    "<RANGE_LOOKS>",
    "<AZIMUTH_LOOKS>",
]

# Phase 1 只生成模板，不执行 subprocess.run(command)。
print(" ".join(command))
\`\`\`

## 未确认内容

真实 GAMMA 版本可能包含可选参数、默认值或版本差异。当前示例没有真实手册检索能力，因此不会确认更多参数。`,
  },
  {
    id: "answer-file-layout",
    title: "SAR/GAMMA 项目目录组织",
    triggers: ["目录", "文件", "放置", "layout", "组织", "路径"],
    queryTypes: ["file_layout"],
    citations: layoutCitations,
    answer: `## 推荐目录

\`\`\`text
<PROJECT_ROOT>/
  data_raw/
    reference/        原始参考景产品
    secondary/        原始辅景产品
  dem/                DEM、地理编码辅助数据
  slc/
    reference/        参考 SLC
    secondary/        辅 SLC
  parameters/         .par、.off 等参数文件
  offsets/            配准和偏移估计相关文件
  interferograms/     .int、相干性、滤波后干涉图
  results/            解缠、地理编码、形变产品
  notes/              课堂记录、手册引用、处理说明
\`\`\`

## 放置原则

1. 原始数据只读保存，避免和处理中间文件混放。
2. 参数文件集中存放，便于复现实验。
3. 干涉图和最终结果分开，防止把中间产物误认为最终产品。
4. 代码模板只使用 \`<PROJECT_ROOT>\` 等占位符，不生成真实路径。`,
  },
  {
    id: "answer-code-template",
    title: "占位符代码模板",
    triggers: ["python", "模板", "代码", "code", "命令行"],
    queryTypes: ["code_template", "command"],
    citations: templateCitations,
    answer: `## 代码模板

以下模板只演示如何组织命令字符串，不执行 GAMMA，不调用 Shell，不使用 SSH。

\`\`\`python
from pathlib import Path

project_root = Path("<PROJECT_ROOT>")

reference_slc = project_root / "slc" / "reference" / "<REFERENCE_NAME>.slc"
secondary_slc = project_root / "slc" / "secondary" / "<SECONDARY_NAME>.slc"
reference_par = project_root / "parameters" / "<REFERENCE_NAME>.slc.par"
secondary_par = project_root / "parameters" / "<SECONDARY_NAME>.slc.par"
offset_par = project_root / "offsets" / "<REFERENCE_SECONDARY>.off"
output_int = project_root / "interferograms" / "<REFERENCE_SECONDARY>.int"

gamma_command = [
    "SLC_intf",
    str(reference_slc),
    str(secondary_slc),
    str(reference_par),
    str(secondary_par),
    str(offset_par),
    str(output_int),
    "<RANGE_LOOKS>",
    "<AZIMUTH_LOOKS>",
]

print(" ".join(gamma_command))
\`\`\`

## 使用限制

该模板来自模拟引用数据。正式版本需要先完成文档检索与引用验证，才能输出真实命令格式。`,
  },
];

export const insufficientEvidenceAnswer: MockAnswer = {
  id: "answer-insufficient-evidence",
  title: "证据不足",
  triggers: [],
  queryTypes: ["concept"],
  citations: [
    {
      id: "src-none-01",
      source: "No matched manual chunk (Phase 1 mock)",
      page: "N/A",
      command_name: "N/A",
      section: "N/A",
      verification_status: "insufficient_evidence",
      retrieval_score: 0.18,
      excerpt:
        "未检索到足够的模拟手册片段。真实版本应停止生成精确命令、参数顺序和未核验结论。",
    },
  ],
  answer: `## 无法确认

当前问题没有匹配到足够的模拟手册证据，因此不能确认命令、参数顺序或处理细节。

## 可以继续补充的信息

1. 处理目标，例如生成干涉图、去地形相位、相干性估计或地理编码。
2. 已知命令名称，例如 \`SLC_intf\`。
3. 数据类型，例如 Sentinel-1 SLC、已有 DEM、已有参数文件。

## 当前边界

Phase 1 只演示前端交互和证据展示，不会调用 GAMMA，也不会执行任何实际任务。`,
};

export const initialAssistantMessage: ChatMessage = {
  id: "assistant-welcome",
  role: "assistant",
  queryTypes: ["concept", "workflow", "command", "parameter", "file_layout", "code_template"],
  citations: [],
  content: `## SAR/GAMMA 学习助手

我是一个面向学生的 SAR/GAMMA 知识与流程指导助手。当前只提供 SAR/InSAR 知识、流程说明、命令解释、文件目录建议和占位符代码模板。

如果启用 RAG 后端，我会先检索 GAMMA 手册知识库，再调用对话模型组织回答；无论哪种模式，都不执行 GAMMA、不执行 Shell、不使用 SSH、不连接 MCP Server。`,
};

export const seedSessions: ChatSession[] = [
  {
    id: "session-demo",
    title: "InSAR 入门示例",
    createdAt: nowIso,
    updatedAt: nowIso,
    messages: [
      initialAssistantMessage,
      {
        id: "user-demo-1",
        role: "user",
        content: "从两景 SLC 生成干涉图的流程是什么？",
      },
      {
        id: "assistant-demo-1",
        role: "assistant",
        queryTypes: mockAnswers[1].queryTypes,
        citations: mockAnswers[1].citations,
        content: mockAnswers[1].answer,
      },
    ],
  },
];

export function classifyQuestion(question: string): QueryType[] {
  const normalized = question.toLowerCase();
  const types = new Set<QueryType>();

  if (/什么|概念|基础|insar|sar|相干|相位/.test(normalized)) types.add("concept");
  if (/流程|步骤|如何|怎么做|生成|workflow|处理目标/.test(normalized)) types.add("workflow");
  if (/命令|gamma|slc_intf|create_offset|command/.test(normalized)) types.add("command");
  if (/参数|必填|输入|输出|类型|parameter/.test(normalized)) types.add("parameter");
  if (/目录|文件|路径|放置|layout/.test(normalized)) types.add("file_layout");
  if (/代码|模板|python|命令行|code/.test(normalized)) types.add("code_template");

  return types.size > 0 ? Array.from(types) : ["concept"];
}

export function selectMockAnswer(question: string): MockAnswer {
  const normalized = question.toLowerCase();
  const scored = mockAnswers
    .map((answer) => ({
      answer,
      score: answer.triggers.reduce(
        (total, trigger) => total + (normalized.includes(trigger.toLowerCase()) ? 1 : 0),
        0,
      ),
    }))
    .sort((left, right) => right.score - left.score);

  if (!scored[0] || scored[0].score === 0) {
    return insufficientEvidenceAnswer;
  }

  return scored[0].answer;
}
