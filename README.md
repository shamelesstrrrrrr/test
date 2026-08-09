# SAR/GAMMA 影像处理知识与流程指导助手

这是一个面向学生的 SAR/GAMMA 影像处理知识与流程指导助手。当前前端已经预留并实现 OpenAI-compatible LLM API 调用入口，但接口地址、模型名和密钥需要你在本地配置文件中填写。

当前仍不包含 FastAPI、文档解析、RAG、LangGraph、GAMMA 执行、Shell 执行、SSH 或 MCP 连接。

## 快速运行

```bash
npm install
npm run dev
```

然后打开终端输出中的本地地址，通常是 `http://127.0.0.1:5173/`。

## 配置真实 LLM

复制 `.env.example` 为 `.env.local`，然后填写：

```text
VITE_LLM_API_BASE_URL=
VITE_LLM_MODEL=
VITE_LLM_API_KEY=
```

如果使用本地后端代理注入密钥，可以让 `VITE_LLM_API_KEY` 保持为空。

## 构建

```bash
npm run build
```

## 使用手册

完整中文说明见 [docs/使用手册.md](docs/使用手册.md)。

GAMMA 手册切块建议和已执行方案见 [docs/GAMMA手册切块建议.md](docs/GAMMA手册切块建议.md)。已解析的逐页文本位于 `knowledge/gamma/parsed/`，切片产物位于 `knowledge/gamma/chunks/`。
