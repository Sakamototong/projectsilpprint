FROM python:3.11-slim

WORKDIR /app

# ติดตั้ง dependencies ก่อน copy code เพื่อ cache layer
COPY requirements.txt .
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r requirements.txt

# copy source code
COPY . .

# สร้างโฟลเดอร์ tmp สำหรับ PDF receipts
RUN mkdir -p /app/tmp

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
