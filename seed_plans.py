"""Seed sample subscription plans. Safe to run multiple times (skips existing)."""
from app.models import SessionLocal, SubscriptionPlan

PLANS = [
    {
        "name": "Starter",
        "description": "เหมาะสำหรับร้านค้าขนาดเล็ก เพิ่งเริ่มต้นใช้งาน",
        "price_monthly": 299.0,
        "price_yearly": 2990.0,
        "max_members": 200,
        "max_staff": 3,
        "max_receipts_per_month": 500,
        "max_products": 30,
    },
    {
        "name": "Business",
        "description": "สำหรับร้านค้าขนาดกลาง ต้องการฟีเจอร์ครบถ้วน",
        "price_monthly": 699.0,
        "price_yearly": 6990.0,
        "max_members": 1000,
        "max_staff": 10,
        "max_receipts_per_month": 2000,
        "max_products": 100,
    },
    {
        "name": "Pro",
        "description": "สำหรับร้านค้าขนาดใหญ่ ไม่จำกัดการใช้งาน (0 = ไม่จำกัด)",
        "price_monthly": 1499.0,
        "price_yearly": 14990.0,
        "max_members": 0,
        "max_staff": 0,
        "max_receipts_per_month": 0,
        "max_products": 0,
    },
]

db = SessionLocal()
try:
    count = 0
    for p in PLANS:
        exists = db.query(SubscriptionPlan).filter(SubscriptionPlan.name == p["name"]).first()
        if not exists:
            db.add(SubscriptionPlan(**p))
            count += 1
            print(f"Added: {p['name']}")
        else:
            print(f"Skip (exists): {p['name']}")
    db.commit()
    print(f"Done — {count} plans inserted")
finally:
    db.close()
