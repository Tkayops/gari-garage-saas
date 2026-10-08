PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS garages(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, kra_pin TEXT, phone TEXT,
  job_seq INTEGER NOT NULL DEFAULT 0, inv_seq INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, garage_id INTEGER NOT NULL REFERENCES garages(id),
  name TEXT NOT NULL, phone TEXT, email TEXT NOT NULL UNIQUE, pw_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN('owner','manager','mechanic')),
  active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS customers(
  id INTEGER PRIMARY KEY, garage_id INTEGER NOT NULL REFERENCES garages(id),
  name TEXT NOT NULL, phone TEXT NOT NULL, email TEXT, consent_sms INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')), UNIQUE(garage_id,phone));
CREATE TABLE IF NOT EXISTS vehicles(
  id INTEGER PRIMARY KEY, garage_id INTEGER NOT NULL REFERENCES garages(id),
  customer_id INTEGER NOT NULL REFERENCES customers(id), plate TEXT NOT NULL,
  make TEXT, model TEXT, year INTEGER, mileage INTEGER DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')), UNIQUE(garage_id,plate));
CREATE TABLE IF NOT EXISTS parts(
  id INTEGER PRIMARY KEY, garage_id INTEGER NOT NULL REFERENCES garages(id),
  sku TEXT NOT NULL, name TEXT NOT NULL, category TEXT, supplier TEXT,
  unit_cost INTEGER NOT NULL DEFAULT 0, sell_price INTEGER NOT NULL DEFAULT 0,
  qty INTEGER NOT NULL DEFAULT 0 CHECK(qty>=0), reorder_level INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1, UNIQUE(garage_id,sku));
CREATE TABLE IF NOT EXISTS stock_moves(
  id INTEGER PRIMARY KEY, garage_id INTEGER NOT NULL, part_id INTEGER NOT NULL REFERENCES parts(id),
  delta INTEGER NOT NULL, reason TEXT NOT NULL, ref TEXT, user_id INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY, garage_id INTEGER NOT NULL REFERENCES garages(id),
  number TEXT NOT NULL, vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
  customer_id INTEGER NOT NULL REFERENCES customers(id), mechanic_id INTEGER REFERENCES users(id),
  status TEXT NOT NULL DEFAULT 'intake', complaint TEXT NOT NULL, diagnosis TEXT,
  mileage_in INTEGER, fuel_level TEXT, belongings TEXT, promised_at TEXT,
  approved_at TEXT, approved_total INTEGER, approval_method TEXT, approval_token TEXT, created_by INTEGER, created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')), UNIQUE(garage_id,number));
CREATE TABLE IF NOT EXISTS job_items(
  id INTEGER PRIMARY KEY, garage_id INTEGER NOT NULL, job_id INTEGER NOT NULL REFERENCES jobs(id),
  kind TEXT NOT NULL CHECK(kind IN('labour','part')), part_id INTEGER REFERENCES parts(id),
  description TEXT NOT NULL, qty INTEGER NOT NULL CHECK(qty>0), unit_price INTEGER NOT NULL CHECK(unit_price>=0),
  unit_cost INTEGER NOT NULL DEFAULT 0, added_by INTEGER, created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS job_events(
  id INTEGER PRIMARY KEY, garage_id INTEGER NOT NULL, job_id INTEGER NOT NULL REFERENCES jobs(id),
  user_id INTEGER, text TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS invoices(
  id INTEGER PRIMARY KEY, garage_id INTEGER NOT NULL, job_id INTEGER NOT NULL UNIQUE REFERENCES jobs(id),
  number TEXT NOT NULL, subtotal INTEGER NOT NULL, vat INTEGER NOT NULL, total INTEGER NOT NULL,
  paid INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'unpaid',
  etims_ref TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')), UNIQUE(garage_id,number));
CREATE TABLE IF NOT EXISTS payments(
  id INTEGER PRIMARY KEY, garage_id INTEGER NOT NULL, invoice_id INTEGER NOT NULL REFERENCES invoices(id),
  method TEXT NOT NULL CHECK(method IN('cash','mpesa','card','bank')), amount INTEGER NOT NULL CHECK(amount>0),
  reference TEXT, user_id INTEGER, created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE UNIQUE INDEX IF NOT EXISTS ux_pay_ref ON payments(garage_id,method,reference) WHERE reference IS NOT NULL;
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY, garage_id INTEGER, user_id INTEGER, action TEXT NOT NULL, detail TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE INDEX IF NOT EXISTS ix_jobs_g ON jobs(garage_id,status);
CREATE INDEX IF NOT EXISTS ix_items_job ON job_items(job_id);
CREATE INDEX IF NOT EXISTS ix_moves_part ON stock_moves(part_id);
CREATE INDEX IF NOT EXISTS ix_veh_plate ON vehicles(garage_id,plate);
