########################
# Frontend build stage #
########################
FROM acr-openxlab-prod-registry-vpc.cn-shanghai.cr.aliyuncs.com/public/node:18-alpine AS frontend-builder

WORKDIR /src/web
COPY web/package.json web/package-lock.json ./

RUN npm ci --registry=https://registry.npmmirror.com

COPY web/ ./
RUN npm run build

#######################
# Backend build stage #
#######################
FROM acr-openxlab-prod-registry-vpc.cn-shanghai.cr.aliyuncs.com/public/python:3.13-slim AS builder

WORKDIR /src

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
COPY README.md ./
RUN pip install --no-cache-dir uv -i https://pypi.tuna.tsinghua.edu.cn/simple \
    && uv sync --frozen

RUN /src/.venv/bin/python -c "import bcrypt; print('bcrypt imported successfully')" || \
    (echo "bcrypt not found, installing manually..." && \
     /src/.venv/bin/pip install bcrypt -i https://pypi.tuna.tsinghua.edu.cn/simple)

COPY agent ./agent
COPY model ./model
COPY tools ./tools
COPY utils ./utils
COPY webapi ./webapi
COPY zadig_mcp ./zadig_mcp
COPY skills ./skills
COPY templates ./templates
COPY --from=frontend-builder /src/web/dist ./web/dist

#################
# Runtime stage #
#################
FROM acr-openxlab-prod-registry-vpc.cn-shanghai.cr.aliyuncs.com/public/python:3.13-slim

RUN ln -snf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo Asia/Shanghai > /etc/timezone

WORKDIR /app

COPY --from=builder /src /app
ENV PATH="/app/.venv/bin:${PATH}" \
    TZ=Asia/Shanghai \
    CONFIG_FILE=/app/config.yaml \
    PYTHONUNBUFFERED=1

EXPOSE 8088

CMD ["python", "-m", "webapi", "--host", "0.0.0.0", "--port", "8088"]
