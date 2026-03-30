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

Base.metadata.create_all(bind=engine)
print('create_all done (new tables created if needed)')
