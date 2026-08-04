FROM python:3.12-slim
WORKDIR /app
COPY services/data-generator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/data-generator/app.py .
EXPOSE 8010
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8010"]

