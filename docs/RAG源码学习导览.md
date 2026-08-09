# RAG 源码学习导览

这份文档不是运行手册，而是帮助你看懂“我到底做了什么”的学习导览。

可以先记住一句话：

```text
前端负责聊天界面；
后端负责保管密钥、检索知识库、调用大模型；
向量库负责从 GAMMA 手册和处理代码里找证据；
DeepSeek 负责把证据组织成中文回答。
```

## 1. 整体流程

用户在网页里输入问题后，程序会按下面的顺序工作：

```text
1. 前端收到你的问题
2. 前端把问题发给本地 FastAPI 后端
3. 后端先用规则判断问题类型和默认回答模式
4. 如果问题比较复杂或模糊，后端让 DeepSeek 先生成一个 JSON 检索计划
5. 后端调用 SiliconFlow，把“问题 + 检索计划关键词”转成向量
6. 后端把问题向量和 GAMMA 手册向量、处理代码向量做相似度比较
7. 后端找出最相关的几个手册片段和代码片段
8. 如果本地证据不足，或用户明确要求联网，后端执行受控网页搜索
9. 后端把“用户问题 + 查询规划 + RAG 证据 + 网页补充 + 回答规则”拼成 prompt
10. 后端调用 DeepSeek 生成最终回答
11. 后端把回答和引用来源返回给前端
12. 前端中间显示回答，右侧显示来源
```

## 2. 为什么需要前端和后端

前端就是你看到的网页界面。

前端适合做：

```text
聊天窗口
会话列表
Markdown 渲染
代码块复制按钮
右侧引用来源展示
```

前端不适合做：

```text
保存 API Key
读取本地 .npy 向量文件
直接调用付费模型 API
管理 RAG 检索流程
```

所以我新增了后端。后端运行在：

```text
http://127.0.0.1:8000
```

前端运行在：

```text
http://127.0.0.1:5173
```

前端只知道后端地址，不知道 DeepSeek 和 SiliconFlow 的密钥。

## 3. Embedding 和 DeepSeek 的分工

这里最容易混淆。

Embedding 模型负责“找资料”：

```text
问题：SLC_intf 如何生成干涉图？
↓
转成一串数字向量
↓
和手册 chunk 的向量比较
↓
找到相关手册片段
```

DeepSeek 负责“写回答”：

```text
用户问题 + 检索到的手册片段
↓
DeepSeek 阅读这些证据
↓
生成中文说明、表格、代码模板和引用
```

所以当前分工是：

```text
SiliconFlow / BAAI/bge-m3：embedding 检索
DeepSeek / deepseek-chat：回答生成
```

## 4. 知识库文件是什么

当前知识库分成两类：GAMMA 中文手册库和处理代码库。

先解析成按页文本：

```text
knowledge/gamma/parsed/gamma_new_user_manual_cn_2019.pages.jsonl
knowledge/gamma/parsed/gamma_new_user_manual_cn_2019.full_text.txt
knowledge/gamma/parsed/gamma_new_user_manual_cn_2019.manifest.json
```

再切块：

```text
knowledge/gamma/chunks/gamma_new_user_manual_cn_2019.sections.jsonl
knowledge/gamma/chunks/gamma_new_user_manual_cn_2019.chunks.jsonl
knowledge/gamma/chunks/gamma_new_user_manual_cn_2019.command_candidates.jsonl
knowledge/gamma/chunks/gamma_new_user_manual_cn_2019.chunk_manifest.json
```

最后生成向量：

```text
knowledge/gamma/index/gamma_new_user_manual_cn_2019.embeddings.npy
knowledge/gamma/index/gamma_new_user_manual_cn_2019.embedding_records.jsonl
knowledge/gamma/index/gamma_new_user_manual_cn_2019.embedding_manifest.json
```

处理代码库来自：

```text
I:\zhushou\处理代码\version2.0.2
```

切块结果：

```text
knowledge/code/processing/processing_code_v2_0_2.chunks.jsonl
knowledge/code/processing/processing_code_v2_0_2.chunk_manifest.json
```

向量结果：

```text
knowledge/code/index/processing_code_v2_0_2.embeddings.npy
knowledge/code/index/processing_code_v2_0_2.embedding_records.jsonl
knowledge/code/index/processing_code_v2_0_2.embedding_manifest.json
```

可以这样理解：

| 文件 | 像什么 | 作用 |
|---|---|---|
| `chunks.jsonl` | 一本书或一组代码被拆成的小卡片 | 存每个手册片段或代码片段的文字 |
| `embeddings.npy` | 每张卡片的数字指纹 | 用于相似度检索 |
| `embedding_records.jsonl` | 卡片编号对照表 | 知道向量对应哪个 chunk |
| `sections.jsonl` | 小节全文 | 用于 small-to-big 回溯上下文 |
| `manifest.json` | 生成说明 | 记录模型、维度、数量和路径 |

## 5. 后端代码怎么看

建议按这个顺序看：

```text
backend/main.py
backend/config.py
backend/rag_index.py
backend/api_clients.py
backend/prompt_builder.py
backend/schemas.py
```

### 5.1 `backend/main.py`

这是后端入口，相当于总调度室。

它提供两个接口：

```text
GET  /api/health
POST /api/chat
```

`/api/chat` 做的事情是：

```text
接收问题
→ 分类问题类型
→ 生成问题向量
→ 检索手册片段
→ 构造 prompt
→ 调用 DeepSeek
→ 返回回答和引用
```

### 5.2 `backend/config.py`

这个文件只负责读配置。

例如：

```text
SILICONFLOW_API_KEY
DEEPSEEK_API_KEY
RAG_TOP_K
RAG_MAX_CONTEXT_CHARS
```

它的意义是：密钥和可调参数不要写死在代码里。

### 5.3 `backend/rag_index.py`

这是 RAG 检索核心。

它会加载手册库：

```text
embeddings.npy
embedding_records.jsonl
chunks.jsonl
sections.jsonl
```

然后根据用户问题的向量找最相似的手册片段。

现在它还会加载代码库：

```text
knowledge/code/index/processing_code_v2_0_2.embeddings.npy
knowledge/code/processing/processing_code_v2_0_2.chunks.jsonl
```

代码库引用会标成：

```text
code_reference
```

它只能说明“项目脚本中如何写”，不能替代手册确认 GAMMA 官方命令格式。

这里还加了一个关键词加权，因为 GAMMA 里有很多命令名：

```text
SLC_intf
SLC_mosaic_S1_TOPS
create_offset
```

如果用户问题里明确写了命令名，程序会额外提高包含该命令片段的排名。

### 5.4 `backend/api_clients.py`

这个文件负责调用外部模型 API。

里面有两个客户端：

```text
SiliconFlowEmbeddingClient
DeepSeekChatClient
```

第一个把用户问题转成向量。

第二个把检索证据交给 DeepSeek，让它生成回答。

### 5.5 `backend/prompt_builder.py`

这个文件决定“怎么问 DeepSeek”。

它会把内容组织成：

```text
系统规则
用户问题
问题类型
回答格式要求
检索到的手册证据
```

这里最重要的规则是：

```text
没有手册证据，不许编造命令、参数、页码和精确顺序。
```

### 5.6 `backend/schemas.py`

这个文件定义前后端通信的数据结构。

比如后端返回给前端的内容包括：

```text
content：助手回答
queryTypes：问题类型
citations：引用来源
mode：当前模式
```

## 6. 前端代码怎么看

建议按这个顺序看：

```text
src/config/assistantConfig.ts
src/services/assistantEngine.ts
src/App.tsx
src/types.ts
src/data/mockKnowledge.ts
src/styles.css
```

### 6.1 `src/config/assistantConfig.ts`

这个文件读取前端配置。

现在前端配置是：

```text
VITE_ASSISTANT_PROVIDER=rag_api
VITE_RAG_API_URL=http://127.0.0.1:8000/api/chat
```

意思是：前端不要自己调用 DeepSeek，改为调用本地 RAG 后端。

### 6.2 `src/services/assistantEngine.ts`

这是前端的“问答服务层”。

它现在支持三种模式：

```text
mock：模拟数据
llm_api：浏览器直接调用 LLM
rag_api：调用本地 RAG 后端
```

真正适合当前项目的是：

```text
rag_api
```

### 6.3 `src/App.tsx`

这是页面主体。

它负责：

```text
左侧会话列表
中间聊天窗口
右侧引用来源
发送问题
显示回答
复制代码块
```

它本身不懂 GAMMA，也不做检索，只负责界面。

## 7. 一句话理解每层

```text
App.tsx：网页长什么样，怎么交互
assistantEngine.ts：前端把问题发给谁
main.py：后端收到问题后怎么调度
query_planner.py：判断是否需要先让 LLM 生成检索计划
rag_index.py：从手册库和代码库里找证据
web_search.py：本地证据不足时做受控网页搜索
api_clients.py：调用 SiliconFlow 和 DeepSeek
prompt_builder.py：把证据整理成给 DeepSeek 的问题
schemas.py：规定前后端传什么格式的数据
```

## 8. 当前程序没有做什么

当前程序仍然不会：

```text
执行 GAMMA
执行 Shell
用 SSH 连接服务器
修改用户数据文件
自动跑真实影像处理流程
```

它现在做的是：

```text
读手册
检索手册库和代码库
必要时执行网页搜索
引用手册片段和代码片段
必要时先用 DeepSeek 生成检索计划
让 DeepSeek 基于 RAG 证据回答
```

## 9. 建议学习顺序

如果你是刚开始看这个项目，建议按下面顺序学：

```text
第一天：理解前端怎么发送问题
第二天：理解后端 /api/chat 怎么接收问题
第三天：理解 embedding 是怎么检索手册片段的
第四天：理解 prompt 是怎么约束 DeepSeek 的
第五天：理解 citations 是怎么显示到右侧栏的
```

不要一开始就看所有文件。先把“一个问题从输入框到回答显示”的路线走通，其他文件就会慢慢变清楚。

## 10. 本次交互与回答控制更新

这次主要改的是“真正像一个 RAG 助手那样回答”，不是重新生成知识库。

### 10.1 数据处理问题优先回答封装脚本

当你问“怎么进行数据处理”“预处理怎么用”“从两景 SLC 生成干涉图的流程是什么”这类数据处理问题时，程序会默认优先走代码库封装回答模式。

关键文件：

```text
backend/prompt_builder.py
backend/main.py
backend/rag_index.py
```

`backend/prompt_builder.py` 里的 `wants_project_code_answer()` 会判断问题是不是数据处理或项目代码问题。如果命中 `数据处理`、`预处理`、`脚本`、`封装`、`代码`、`version`、`pre_process`、`s1_slc`、`coreg`，或者问题本身是“流程/步骤/怎么处理/生成干涉图”这类处理目标，就进入 `project_code_wrapper` 回答模式。

这个模式要求模型优先回答：

```text
推荐使用哪个封装脚本或函数
它是做什么的
适合什么场景
输入参数是什么
主要输出是什么
最小占位符调用示例
注意事项
引用来源
```

它不会默认展开完整内部 GAMMA 流程，也不会贴出封装脚本内部的 GAMMA/辅助命令名称、完整命令行或参数串。只有你明确问“内部流程是什么”“展开内部步骤”“原理是什么”时，才会解释脚本内部调用。

如果模型仍然写出了“前置条件”“处理步骤”“步骤 1/2/3”或 `create_diff_par`、`base_calc`、`mk_diff_2d` 这类内部命令，`backend/main.py` 会触发一次重写，让模型改回封装入口说明。

### 10.2 手册库和代码库的分工

现在后端会同时检索两个库：

```text
GAMMA 手册库：确认官方命令、参数、输入输出、页码和章节
处理代码库：说明 version2.0.2 里封装脚本怎么组织流程
```

如果问题偏向数据处理或封装脚本使用，`backend/main.py` 会把代码库证据排在更靠前的位置，并让 `backend/rag_index.py` 给代码库更多上下文预算。`expand_code_search_query()` 还会给“干涉图/差分/Sentinel-1/StaMPS”等问题补充 D-InSAR、DIFF、S1、file_construct 等封装入口关键词，减少检索只命中手册内部步骤的情况。

代码库解析结果有两种查看方式：

```text
knowledge/code/processing/processing_code_v2_0_2.chunks.jsonl
knowledge/code/processing/processing_code_v2_0_2.parsed_text.txt
```

`chunks.jsonl` 是程序检索用的结构化 JSONL；`parsed_text.txt` 是给人检查用的纯文本版，里面按 chunk 显示 source、行号、语言、识别到的命令和原始片段。

但要注意：代码库证据只是辅助。涉及 GAMMA 官方命令格式和精确参数顺序时，仍然必须以手册证据为准。

### 10.3 规则路由和 LLM 查询规划

现在后端不是把原始问题直接拿去检索，而是先做一层规划。

关键文件：

```text
backend/query_planner.py
backend/main.py
backend/prompt_builder.py
```

第一层是规则路由。它很便宜，不调用大模型，主要负责保底：

```text
问官方 GAMMA 命令参数 -> manual_command，优先搜手册
问数据处理怎么做 -> project_code_wrapper，优先搜处理代码
问内部流程/原理/展开步骤 -> internal_workflow，可以解释内部步骤
问概念或目录 -> concept / file_layout，按普通知识问答处理
```

第二层是可选的 LLM 查询规划。只有问题比较模糊或复杂时才启用，例如“我有 S1 数据想预处理然后生成干涉图，应该用哪个封装脚本”。这一步调用 DeepSeek，但它只输出 JSON 检索计划，不输出最终答案。

规划 JSON 大致包含：

```text
answer_mode：最终回答模式
manual_queries：用于检索 GAMMA 手册的查询词
code_queries：用于检索处理代码库的查询词
prefer_sources：优先看 manual 还是 code
avoid_terms：最终回答里应避免的内部命令或结构词
```

这样做的好处是：复杂问题可以先被拆成更适合检索的关键词；简单问题不用多花一次大模型调用；官方命令参数问题仍然被硬规则锁定在手册证据上。

### 10.4 网页搜索兜底

网页搜索在这里：

```text
backend/web_search.py
backend/main.py
```

它不是默认每次都搜索。触发条件主要有两种：

```text
1. 用户明确说“联网、网页、网上、搜索、最新、查一下”
2. 问题属于概念/普通指导类，而本地手册库和代码库证据分数偏弱
```

网页搜索默认使用 `duckduckgo_lite`，只抓取搜索结果标题、链接和摘要，不抓整页正文。这样 token 成本比较低，也避免把大量不可靠网页内容塞给模型。

重要边界：

```text
GAMMA 官方命令、参数顺序、输入输出关系：仍然只信手册证据
version2.0.2 封装脚本：仍然优先信代码库证据
网页搜索：只做 SAR/InSAR 通用背景、最新资料或本地证据不足时的补充
```

右侧引用中，网页来源会显示为 `web_reference`。如果回答只依赖网页搜索，模型会被要求写清“网页补充，未由本地手册验证”。

### 10.5 输出变短

输出长度主要由两处控制：

```text
backend/prompt_builder.py
backend/config.py
```

`backend/prompt_builder.py` 会告诉模型少写背景铺垫、少写重复免责声明、少展开内部流程。

`backend/config.py` 里新增了：

```text
DEEPSEEK_MAX_TOKENS
QUERY_PLANNER_ENABLED
QUERY_PLANNER_MAX_TOKENS
WEB_SEARCH_ENABLED
WEB_SEARCH_PROVIDER
WEB_SEARCH_MAX_RESULTS
```

`DEEPSEEK_MAX_TOKENS` 控制 DeepSeek 单次最终回答最多生成多少 token。`QUERY_PLANNER_ENABLED` 控制是否启用可选查询规划；`QUERY_PLANNER_MAX_TOKENS` 控制规划 JSON 的最大 token。`WEB_SEARCH_ENABLED` 控制是否允许网页兜底，`WEB_SEARCH_MAX_RESULTS` 控制最多给模型多少条网页摘要。当前本地启动后端时使用的是临时环境变量，不会写进源码文件。

### 10.6 Enter 发送和等待提示

前端交互在这里：

```text
src/App.tsx
src/styles.css
```

`src/App.tsx` 里新增了 `handleComposerKeyDown()`：

```text
Enter：发送问题
Shift + Enter：换行
中文输入法正在组词时：不误发送
```

同时新增了 `PendingMessage`。后端还没返回完整答案时，中间聊天区会显示“正在检索知识库并生成回答，已等待 N 秒”。

这不是严格意义上的流式输出。当前采用的是等待计时提示，优点是实现简单、稳定，用户不会误以为页面卡住。真正流式输出以后需要后端改成 streaming response，前端再用流式读取逐字更新。

### 10.7 记忆不是全部塞给 LLM

界面左侧历史会话会保存在浏览器 `localStorage` 中，这是为了让你刷新页面后还能看到历史聊天。

但是发给 LLM 的上下文不是完整历史。

前端在：

```text
src/services/assistantEngine.ts
```

使用 `toCompactHistory()`，只取最近 8 条消息，并把每条消息压缩到约 700 字以内。

后端在：

```text
backend/prompt_builder.py
```

使用 `trim_history()`，再次只保留最近 4 条有效对话，并压缩每条文本。

所以可以这样理解：

```text
浏览器 localStorage：保存完整会话，用于页面显示
发送给后端的 messages：最近少量压缩历史
发送给 DeepSeek 的 history：更短的最近上下文
RAG 证据：由当前问题重新检索，不靠把全部历史塞进去
```

这样做的目的，是避免历史越聊越长导致 token 浪费、费用上升和模型注意力分散。
