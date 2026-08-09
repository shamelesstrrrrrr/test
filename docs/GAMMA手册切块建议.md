# GAMMA 手册知识库切块建议

## 推荐原则

GAMMA 手册不是普通连续文章，里面同时包含概念说明、处理流程、命令格式、参数表、示例命令和注意事项。因此不建议只按固定字数切块。更适合采用“结构优先 + 命令优先 + 页码保留”的混合切块方式。

## 建议的切块层级

### 1. 页级原始层

先保存逐页文本，不切块。这一层用于保留 PDF 物理页码、原始来源和人工检查依据。

适合字段：

```json
{
  "source": "GAMMA软件新用户手册中文版-2019.pdf",
  "pdf_page": 74,
  "text": "该页抽取的原始文本..."
}
```

### 2. 章节层

根据目录、标题编号和模块名切出章节，例如 ISP、DIFF&GEO、MSP、LAT、IPTA、Sentinel-1 数据处理等。

章节层适合回答概念类和流程类问题，因为学生通常会问“这个处理目标怎么做”。

### 3. 命令层

凡是出现明确 GAMMA 命令名、命令格式、参数说明和示例的地方，应优先切成“一个命令一个主块”。

命令块建议保留：

```json
{
  "command_name": "SLC_intf",
  "section": "Interferogram generation",
  "pages": [74, 75],
  "synopsis": "...",
  "parameters_text": "...",
  "examples_text": "...",
  "notes_text": "..."
}
```

这样更适合回答“某个命令参数怎么解释”“给我代码模板”这类问题。

### 4. 滑窗补充层

对长章节可以再做 800 到 1200 中文字符左右的滑窗块，重叠 100 到 200 字符。它适合作为召回补充，但不应替代命令层。

## 更适合本项目的方案

建议最终采用：

```text
页级文本
  -> 章节识别
  -> 命令块抽取
  -> 长章节滑窗补充
  -> 检索结果去重与引用验证
```

优先级建议：

1. 命令/参数问题：优先检索命令块。
2. 流程问题：优先检索章节层和流程表附近文本。
3. 概念问题：优先检索章节层和滑窗块。
4. 代码模板问题：必须有命令格式或参数表证据，否则只输出占位符框架，并说明未确认。

## 暂不建议的方式

1. 不建议把整本手册塞进 `mockKnowledge.ts`。
2. 不建议只按固定长度粗暴切块。
3. 不建议丢掉页码，因为你的回答要求必须显示手册名称和页码。
4. 不建议把命令格式、参数表和示例命令切散到互相找不到的块里。

## 当前已做的前置步骤

当前只做 PDF 逐页解析，不做切片。输出位于：

```text
knowledge/gamma/parsed/
```

后续你可以先检查逐页文本质量，再选择切块方法。

## 已执行的切片方案

现已按讨论后的方案执行切片：

```text
Small-to-Big + 标题分层 + 命令优先层 + 长小节语义滑窗
```

输出位于：

```text
knowledge/gamma/chunks/
  gamma_new_user_manual_cn_2019.sections.jsonl
  gamma_new_user_manual_cn_2019.chunks.jsonl
  gamma_new_user_manual_cn_2019.command_candidates.jsonl
  gamma_new_user_manual_cn_2019.chunk_manifest.json
```

当前统计：

| 项目 | 数量 |
|---|---:|
| PDF 页数 | 405 |
| section 父层 | 491 |
| 检索 chunks | 2049 |
| command blocks | 1369 |
| section blocks | 408 |
| semantic blocks | 272 |
| command candidates | 445 |

### 实际规则

1. `sections.jsonl` 保存标题分层父级上下文，用于 small-to-big 扩展。
2. `chunks.jsonl` 保存真正参与检索的小块。
3. `command_candidates.jsonl` 保存命令候选，默认 `review_status` 为 `pending`，后续需要人工复核。
4. 带下划线的英文 token 是命令识别的高置信证据。
5. 无下划线 token 默认不作为命令，只有少量白名单例外，例如 `adf`、`geocode`、`dismph`、`rasmph`、`dis2SLC`。
6. 命令块不使用 overlap，而是通过 `parent_section_id` 和 `recommended_neighbors` 回溯上下文。
7. 小节短于 1200 字符时生成 `section_block`。
8. 小节较长时生成 `semantic_block`，目标长度约 1000 字符，overlap 为 150 字符。

### 核心字段

`chunks.jsonl` 中每条记录包含：

```json
{
  "chunk_id": "gamma_new_user_manual_cn_2019_cmd_0214_...",
  "chunk_type": "command_block",
  "module": "干涉 SAR 处理器(ISP)模块",
  "section_id": "gamma_new_user_manual_cn_2019_sec_0098",
  "section_title": "A.9 干涉图滤波",
  "heading_path": ["14 附加工具", "A.9 干涉图滤波"],
  "pages": [58],
  "command_name": "adf",
  "confidence_score": 10,
  "evidence": ["line_start", "command_context_before", "parameter_like_tail"],
  "parent_expansion": {
    "strategy": "small_to_big",
    "parent_section_id": "gamma_new_user_manual_cn_2019_sec_0098",
    "recommended_neighbors": 1
  },
  "text": "..."
}
```

后续 RAG 检索时建议：

```text
命令/参数问题：
  先检索 command_block
  再通过 parent_section_id 找 section_parent
  只扩展相邻 1 个块和标题路径

流程/概念问题：
  先检索 section_block 和 semantic_block
  同时召回相关 command_block

证据不足：
  不输出精确参数顺序
  标记为 insufficient_evidence
```
