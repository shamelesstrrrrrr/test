# SAR/GAMMA RAG 后端

这个目录提供最小可用的 FastAPI RAG 后端，用于把前端问题接入：

```text
用户问题
→ 规则路由判断问题类型和默认回答模式
→ 必要时 DeepSeek 生成 JSON 检索计划
→ SiliconFlow BAAI/bge-m3 query embedding
→ 本地 GAMMA 手册向量库检索
→ 本地处理代码向量库检索
→ 本地证据不足或用户明确要求时，执行受控网页搜索
→ 构造带查询规划和引用证据的 RAG Prompt
→ DeepSeek Chat API 生成回答
→ 返回回答和右侧引用来源
```

## 安装依赖

```powershell
python -m pip install -r .\backend\requirements.txt
```

## 启动后端

不要把真实 API Key 写进源码。建议用当前 PowerShell 会话的临时环境变量：

```powershell
$env:SILICONFLOW_API_KEY="你的 SiliconFlow API Key"
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
$env:DEEPSEEK_CHAT_MODEL="deepseek-chat"
$env:QUERY_PLANNER_ENABLED="true"
$env:QUERY_PLANNER_MAX_TOKENS="500"
$env:WEB_SEARCH_ENABLED="true"
$env:WEB_SEARCH_PROVIDER="duckduckgo_lite"
$env:WEB_SEARCH_MAX_RESULTS="3"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

前端 `.env.local` 指向：

```text
VITE_ASSISTANT_PROVIDER=rag_api
VITE_RAG_API_URL=http://127.0.0.1:8000/api/chat
```

当前后端会同时加载两个知识库：

```text
manual_index:
  knowledge/gamma/index/gamma_new_user_manual_cn_2019.embeddings.npy

code_index:
  knowledge/code/index/processing_code_v2_0_2.embeddings.npy
```

手册证据用于确认 GAMMA 命令、参数顺序和输入输出关系；代码证据只作为项目脚本、流程封装和模板组织方式的辅助参考；网页搜索证据只用于通用 SAR/InSAR 背景和本地证据不足时的补充，不能替代 GAMMA 手册。

## 健康检查

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

## 聊天接口

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/chat `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"question":"SLC_intf 生成干涉图需要哪些输入输出？","sessionId":"demo","messages":[]}'
```

## 安全边界

后端只读取知识库文件、调用 embedding API 和 chat API。它不会执行 GAMMA，不会执行 Shell，不会使用 SSH，也不会连接 MCP Server。
