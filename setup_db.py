"""สร้างตาราง DB ใหม่ทั้งหมด (drop + create) แล้วตรวจสอบ import errors"""
import os, traceback

os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@127.0.0.1:5432/postgres"

try:
    from app.models import Base, engine
    print("โมเดล import OK")
    Base.metadata.drop_all(bind=engine)
    print("Drop tables OK")
    Base.metadata.create_all(bind=engine)
    print("Create tables OK")
    from app.main import app
    print("App import OK — พร้อมรัน uvicorn")
except Exception as e:
    traceback.print_exc()
