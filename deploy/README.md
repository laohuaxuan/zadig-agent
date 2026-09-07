# 部署说明

参考 [mse-domain-binding](https://github.com/kubeedge/mse-domain-binding) 的 `Dockerfile` 与 `deploy/` 目录结构。

## 0. 初始化数据库（可选）

应用启动时会自动建库、建表并同步内置 skills/templates；也可预先导入 SQL：

```bash
mysql -h <host> -u <user> -p < deploy/sql/schema.sql
mysql -h <host> -u <user> -p < deploy/sql/auth.sql
```

## 1. 构建镜像

在项目根目录执行（根目录 `Dockerfile` 与 `deploy/Dockerfile` 一致）：

```bash
docker build -t your-registry/zadig-agent:latest .
# 或
docker build -f deploy/Dockerfile -t your-registry/zadig-agent:latest .
docker push your-registry/zadig-agent:latest
```

镜像内已包含前端 `web/dist` 与 Python 依赖；容器监听 **8088**，同时提供 API 与静态页面。

## 2. 修改部署参数

请先根据环境修改：

- `deploy/yamls/configmap.yaml`
  - `mysql.host` / `mysql.user` / `mysql.database`
  - `auth.jwt_secret`、初始 root 账号
  - `feishu.*`（若启用飞书登录）
- `deploy/yamls/secret.yaml`
  - `DB_PASSWORD`
- `deploy/yamls/deployment.yaml`
  - `image: your-registry/zadig-agent:latest`
  - `namespace`（默认 `devops`）
- `deploy/values/dev.yaml`（Zadig Helm 发布时使用）
  - 与上述 ConfigMap 挂载方式一致

## 3. 应用 Kubernetes 资源

```bash
kubectl apply -f deploy/yamls/secret.yaml
kubectl apply -f deploy/yamls/configmap.yaml
kubectl apply -f deploy/yamls/deployment.yaml
kubectl apply -f deploy/yamls/service.yaml
```

## 4. 检查状态

```bash
kubectl -n devops get pods -l app=zadig-agent
kubectl -n devops get svc zadig-agent
kubectl -n devops logs deploy/zadig-agent
```

## 5. 本地访问（临时）

```bash
kubectl -n devops port-forward svc/zadig-agent 18088:8088
```

访问 `http://127.0.0.1:18088`。

## 6. 清空审批流测试数据

```bash
mysql -h <host> -u <user> -p zadig_agent < deploy/sql/clear_workflow_data.sql
```

## 注意事项

- 程序通过环境变量 `CONFIG_FILE` 读取配置（默认 `/app/config.yaml`）。
- `mysql.password` 为空时，从环境变量 `DB_PASSWORD` 读取。
- **Pod 重启 / 探针失败**：Uvicorn 会在 `lifespan` 完成前不监听 8088。若日志停在 `Waiting for application startup`，通常是 MySQL 连接/初始化阻塞或失败。请检查 `DB_PASSWORD`、MySQL 地址可达性；部署后日志应出现 `应用启动：开始监听 HTTP 请求`。readiness/liveness 已放宽初始等待时间。
- Agent、Zadig 实例、技能与模板等业务数据保存在 MySQL，不在镜像内。
- **Agent 会话 checkpoint**：Web 平台与 CLI 一样，将 LangGraph 对话状态写入 `/app/checkpoints/<instance_id>/`（PVC 挂载，见 `deploy/values/dev.yaml`）。Pod 重启后，状态为「执行中」且 checkpoint 存在的申请可点「恢复连接」继续，无需从头执行。可通过环境变量 `CHECKPOINTS_DIR` 覆盖目录。
- 首次启动会根据 `auth.root_initial_*` 自动创建超级管理员（若库中尚无 root 本地账号）。
- 若集群 Ingress/网关会校验 `Authorization: Bearer`，前端已通过 `X-Access-Token` 传递登录态（与 `mse-domain-binding` 一致）；不要改回仅使用 Bearer。
- 生产环境请将 ConfigMap 中 `feishu.app_base_url` 设为实际访问域名（如 `https://zadig-agent.openxlab.org.cn`），并填写飞书 `app_id` / `app_secret`。
- **飞书审批卡片**：在飞书开放平台启用机器人能力，开通 `im:message`、通讯录只读等权限；事件订阅选择 `card.action.trigger`，回调 URL 设为 `https://<你的域名>/api/feishu/card/callback`（必须 HTTPS，避免 301/302）。配置 `feishu.verification_token` 与 `feishu.encrypt_key`（若启用加密）。
- **与 mse-domain-binding 共用飞书 App**：配置 `feishu.app_namespace: zadig-agent` 与 `feishu.peer_app_base_urls.mse-domain-binding`（指向域名绑定服务公网地址）。卡片按钮会携带 `app` 标识；若回调落在本服务但审批属于对端，会自动转发到 `/api/feishu/card/callback/process`。两端的 `auth.jwt_secret` 建议设为不同值，避免旧 token 串用。
- **Agent 模型 API 与 IP 白名单**：Agent 执行时会从 Pod 内访问 `base_url`（如 free-router、OpenRouter）。若报错 `ip_not_allowed` / `proxy_forbidden` / HTTP 457，说明当前集群出口 IP 不在模型网关白名单内。若报错 `session_id_required` / HTTP 456，说明网关仅接受带 `session_id` 的 Agent 请求（新版本已自动附带）。处理方式：（1）向模型网关管理员申请加入集群 NAT 出口 IP；（2）改用无 IP 限制的 Agent（如 OpenRouter）；（3）在 `deploy/yamls/deployment.yaml` 为容器增加 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量，经允许网段的代理访问。可在 Pod 内执行 `curl -s https://ifconfig.me` 查看出口 IP，并在「Agent 管理」保存时由服务端探测（会发起一次最小 chat 请求）。
