# =============================================================================
# 中国城市生活成本与幸福感分析可视化 —— 生产镜像
# 使用：docker build -t city-insight . && docker run -p 8501:8501 city-insight
# =============================================================================
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先安装依赖以利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目源码与数据
COPY . .

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=3)" || exit 1

CMD ["streamlit", "run", "src/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
