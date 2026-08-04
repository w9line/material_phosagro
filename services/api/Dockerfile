FROM python:3.12-slim
WORKDIR /app
COPY services/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/api/app.py ./app.py
COPY services/api/tests ./tests
COPY apps/web ./web
COPY scripts/run_agent_eval.py ./scripts/run_agent_eval.py
COPY tests/evals ./tests/evals
EXPOSE 8009
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8009"]
