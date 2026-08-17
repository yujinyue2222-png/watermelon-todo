# 西瓜todo 同步服务 —— 京东云 DevCloud 部署镜像
#
# 服务本身只用 Python 标准库，无需 pip 安装任何依赖。
# 说明：
#   - 基础镜像用原生 python:3.11-slim，DevCloud 预处理器会自动改写为内网镜像并注入 pip/apt 源，
#     所以这里不手动配置任何镜像源。
#   - DevCloud 的 K8s ingress 只暴露容器的 8080 端口，故服务监听 8080。
#   - 服务绑定 0.0.0.0，容器外才能访问。
#   - 同时把 web/ 目录挂上，手机端 PWA 可直接通过同一地址访问。
#
# ⚠️ 数据持久化：当前用 SQLite 存 /data/sync.db，容器重建会丢数据。
#    正式使用请改用 DevCloud 托管 MySQL（见 README 的部署说明）。
FROM python:3.11-slim

WORKDIR /app

# 只拷贝服务运行必需的目录，镜像更小
COPY server/ ./server/
COPY web/ ./web/

# SQLite 数据文件目录（容器内，非持久）
ENV WATERMELON_DB=/data/sync.db
RUN mkdir -p /data

# DevCloud 只路由 8080 端口
EXPOSE 8080

# 绑定 0.0.0.0:8080，并把 web 目录一起对外提供（手机端 PWA）
CMD ["python", "-m", "server", "--host", "0.0.0.0", "--port", "8080", "--web", "/app/web"]