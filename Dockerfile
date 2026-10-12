FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt && python sim/simulator.py && python eval/run_eval.py
EXPOSE 8000
CMD ["python", "web/server.py"]
