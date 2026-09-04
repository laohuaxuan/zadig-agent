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
- Agent、Zadig 实例、技能与模板等业务数据保存在 MySQL，不在镜像内。
- 首次启动会根据 `auth.root_initial_*` 自动创建超级管理员（若库中尚无 root 本地账号）。
- 若集群 Ingress/网关会校验 `Authorization: Bearer`，前端已通过 `X-Access-Token` 传递登录态（与 `mse-domain-binding` 一致）；不要改回仅使用 Bearer。
- 生产环境请将 ConfigMap 中 `feishu.app_base_url` 设为实际访问域名（如 `https://zadig-agent.openxlab.org.cn`），并填写飞书 `app_id` / `app_secret`。
