from app.models import engine, Base
from sqlalchemy import text

with engine.connect() as conn:
    rows = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='stores'"))
    cols = {r[0] for r in rows}
    print("Existing stores cols:", sorted(cols))
    alters = []
    if 'address'     not in cols: alters.append('ADD COLUMN address TEXT')
    if 'tax_id'      not in cols: alters.append('ADD COLUMN tax_id VARCHAR')
    if 'phone'       not in cols: alters.append('ADD COLUMN phone VARCHAR')
    if 'email'       not in cols: alters.append('ADD COLUMN email VARCHAR')
    if 'vat_rate'    not in cols: alters.append('ADD COLUMN vat_rate FLOAT DEFAULT 7.0')
    if 'include_vat' not in cols: alters.append('ADD COLUMN include_vat BOOLEAN DEFAULT TRUE')
    if alters:
        conn.execute(text('ALTER TABLE stores ' + ', '.join(alters)))
        conn.commit()
        print('Added columns:', alters)
    else:
        print('stores table already up to date')

    # Migrate staff_users.role values: old 'staff' -> 'user', old 'owner' -> 'admin'
    rows = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='staff_users'"))
    staff_cols = {r[0] for r in rows}
    if 'role' in staff_cols:
        result = conn.execute(text("UPDATE staff_users SET role='user' WHERE role='staff'"))
        print(f"Migrated {result.rowcount} staff_users role: 'staff' -> 'user'")
        result = conn.execute(text("UPDATE staff_users SET role='admin' WHERE role='owner'"))
        print(f"Migrated {result.rowcount} staff_users role: 'owner' -> 'admin'")
        conn.commit()

    # Audit trail columns for receipts
    rows = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='receipts'"))
    receipt_cols = {r[0] for r in rows}
    print("Existing receipts cols:", sorted(receipt_cols))
    receipt_alters = []
    if 'created_by_name' not in receipt_cols: receipt_alters.append('ADD COLUMN created_by_name VARCHAR')
    if 'created_by_id'   not in receipt_cols: receipt_alters.append('ADD COLUMN created_by_id INTEGER')
    if 'edit_log'        not in receipt_cols: receipt_alters.append('ADD COLUMN edit_log JSON')
    if 'deleted_at'      not in receipt_cols: receipt_alters.append('ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE')
    if 'deleted_by_name' not in receipt_cols: receipt_alters.append('ADD COLUMN deleted_by_name VARCHAR')
    if 'deleted_by_id'   not in receipt_cols: receipt_alters.append('ADD COLUMN deleted_by_id INTEGER')
    if receipt_alters:
        conn.execute(text('ALTER TABLE receipts ' + ', '.join(receipt_alters)))
        conn.commit()
        print('Added receipts columns:', receipt_alters)
    else:
        print('receipts table already up to date')

Base.metadata.create_all(bind=engine)
print('create_all done (new tables created if needed)')
