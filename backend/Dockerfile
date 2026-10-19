FROM python:3.14-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY migrate.py ./migrate.py
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/api/ready', timeout=4)" || exit 1
CMD ["sh", "-c", "python migrate.py && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
