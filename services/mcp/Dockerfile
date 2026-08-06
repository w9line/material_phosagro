FROM python:3.12-slim
WORKDIR /app
COPY services/api/requirements.txt services/api/requirements.txt
COPY services/mcp/requirements.txt services/mcp/requirements.txt
RUN pip install --no-cache-dir -r services/mcp/requirements.txt
COPY services/api/app.py services/api/app.py
COPY services/mcp/server.py services/mcp/server.py
COPY services/mcp/tests services/mcp/tests
EXPOSE 8011
CMD ["python", "services/mcp/server.py"]
