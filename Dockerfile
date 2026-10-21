FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV DATABASE_PATH=/data/onboarding.db PORT=5000
EXPOSE 5000
CMD ["python", "-c", "from app import create_app; create_app().run(host='0.0.0.0', port=5000)"]
