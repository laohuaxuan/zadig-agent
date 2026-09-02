# zadig-agent

把 Zadig OpenAPI 封装成 MCP 工具，供 Cursor 或其他 Agent 调用。也包含一个本地 LangGraph Agent。

默认 **stdio**（Cursor / 本机进程拉起）。需要外部 Agent 访问时，再开 **SSE**。

## 准备

Python 3.13+。

```bash
cd zadig-agent
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp config.example.yaml config.yaml
```

编辑 `config.yaml`：

- `zadig.base_url` / `zadig.api_token`：Zadig 地址和 API Token（必填）
- `openrouter.*`：仅本地 LangGraph Agent 需要
- `mcp.*`：可选。不写则默认 `stdio` + `127.0.0.1:8000`

不要把 `config.yaml` 提交到仓库。

## 启动 MCP 服务器

优先级：命令行 > 环境变量 > `config.yaml` > 默认值。

### 本地 stdio（默认）

给 Cursor 或本仓库 Agent 用。**不要自己前台常驻**，客户端会按需拉起进程。

手动试跑（会占用标准输入，一般不用）：

```bash
.venv/bin/python zadig_mcp/server.py
# 或
.venv/bin/python zadig_mcp/server.py --transport stdio
```

stdio 模式下不要往 stdout 打日志，协议走标准输入输出。

### SSE（本机调试或公网）

```bash
.venv/bin/python zadig_mcp/server.py --transport sse --host 127.0.0.1 --port 8000
```

- 端点：`http://127.0.0.1:8000/sse`
- 健康检查：`http://127.0.0.1:8000/health`

绑定 `0.0.0.0` 等非本机地址时必须带 Token：

```bash
.venv/bin/python zadig_mcp/server.py \
  --transport sse \
  --host 0.0.0.0 \
  --port 8000 \
  --token '替换成足够长的随机串'
```

等价环境变量：`ZADIG_MCP_TRANSPORT`、`ZADIG_MCP_HOST`、`ZADIG_MCP_PORT`、`ZADIG_MCP_TOKEN`。

也可写在 `config.yaml`：

```yaml
mcp:
  transport: sse
  host: 0.0.0.0
  port: 8000
  token: "替换成足够长的随机串"
```

## Cursor 加载

### 方式 A：本地 stdio（推荐）

编辑 `~/.cursor/mcp.json`（全局）或项目 `.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "zadig": {
      "command": "/Users/Zhuanz/projects/zadig-agent/.venv/bin/python",
      "args": [
        "/Users/Zhuanz/projects/zadig-agent/zadig_mcp/server.py"
      ]
    }
  }
}
```

`command` / `args` 换成你机器上的绝对路径。保存后执行 **Developer: Reload Window**，到 **Settings → MCP** 确认 `zadig` 已连接。

### 方式 B：远程 / 公网 SSE

先按上一节启动 SSE，再配：

```json
{
  "mcpServers": {
    "zadig": {
      "type": "sse",
      "url": "https://你的域名/sse",
      "headers": {
        "Authorization": "Bearer 你的Token"
      }
    }
  }
}
```

本机未开鉴权时，可先用 `http://127.0.0.1:8000/sse`，且不要加 `headers`。

## 公网暴露给外部 Agent

stdio 不能被外网访问。流程：本机 SSE → HTTPS 反代或隧道 → 客户端填 URL。

1. 本机监听并开启 Token：

   ```bash
   ZADIG_MCP_TOKEN='替换成足够长的随机串' \
   .venv/bin/python zadig_mcp/server.py --transport sse --host 127.0.0.1 --port 8000
   ```

2. 挂到公网（任选）：

   - 快速试用：`cloudflared tunnel --url http://127.0.0.1:8000` 或 ngrok
   - 正式环境：Nginx / Caddy 反代到 `127.0.0.1:8000`，只开放 443

3. 外部 Cursor / Agent 使用：

   ```json
   {
     "mcpServers": {
       "zadig": {
         "type": "sse",
         "url": "https://你的域名/sse",
         "headers": {
           "Authorization": "Bearer 你的Token"
         }
       }
     }
   }
   ```

这些工具能改 Zadig 项目、环境和流水线。公网必须 HTTPS + Bearer Token，不要把 Token 或 `config.yaml` 写进仓库。

## 本地 LangGraph Agent

读 `config.yaml` 里的 OpenRouter 和 Zadig，通过 stdio 拉起同一套 MCP 工具：

```bash
.venv/bin/python agent/zadig_agent.py
```

输入 `exit` 结束。

## 工具覆盖

统一服务器会注册项目、环境、服务、构建、工作流、集群、镜像仓库、模板、权限、用户、系统日志、协作模式等 OpenAPI 能力。单域文件仍可单独调试，例如：

```bash
.venv/bin/python zadig_mcp/workflows_tools.py
```
