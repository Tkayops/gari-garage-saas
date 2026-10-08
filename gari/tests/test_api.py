import os, sys, tempfile, unittest, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = create_app(os.path.join(self.tmp, "t.db"), "test-secret-test-secret-test-secret")
        self.c = self.app.test_client()
        self.owner = self.register("Kamau Motors", "owner@kamau.co.ke")
    def req(self, m, url, tok=None, json=None, client=None):
        h = {"Authorization": "Bearer " + tok} if tok else {}
        r = getattr(client or self.c, m)(url, json=json, headers=h)
        return r.status_code, (r.get_json() if r.is_json else None)
    def register(self, name, email, phone="0712345678"):
        s, d = self.req("post", "/api/auth/register", json=dict(garage_name=name, name="Owner", email=email, password="Secret123", phone=phone, kra_pin="A123456789Z"))
        self.assertEqual(s, 201, d); return d["token"]
    def mk(self, role, email, tok=None):
        s, d = self.req("post", "/api/users", tok or self.owner, dict(name=role.title(), email=email, phone="0722000111", password="Secret123", role=role))
        self.assertEqual(s, 201, d)
        s, l = self.req("post", "/api/auth/login", json=dict(email=email, password="Secret123")); self.assertEqual(s, 200)
        return l["token"], d["id"]
    def vehicle(self, plate="KDA 123A", phone="0700111222", tok=None):
        s, d = self.req("post", "/api/vehicles", tok or self.owner, dict(plate=plate, phone=phone, customer_name="Wanjiku", make="Toyota", model="Axio", year=2015, mileage=80000))
        self.assertEqual(s, 201, d); return d["id"]
    def part(self, sku="OIL-5W30", qty=10, tok=None):
        s, d = self.req("post", "/api/parts", tok or self.owner, dict(sku=sku, name="Engine oil 5W-30 1L", unit_cost=800, sell_price=1200, qty=qty, reorder_level=3))
        self.assertEqual(s, 201, d); return d["id"]

class TestAuth(Base):
    def test_validation(self):
        s, d = self.req("post", "/api/auth/register", json=dict(garage_name="X", name="A", email="bad", password="Secret123", phone="0712345678"))
        self.assertEqual((s, d["field"]), (400, "email"))
        s, d = self.req("post", "/api/auth/register", json=dict(garage_name="X", name="A", email="a@b.co", password="short", phone="0712345678")); self.assertEqual(d["field"], "password")
        s, d = self.req("post", "/api/auth/register", json=dict(garage_name="X", name="A", email="a@b.co", password="Secret123", phone="12345")); self.assertEqual(d["field"], "phone")
        s, d = self.req("post", "/api/auth/register", json=dict(garage_name="X", name="A", email="owner@kamau.co.ke", password="Secret123", phone="0712345678")); self.assertEqual(s, 409)
    def test_login_and_me(self):
        s, d = self.req("get", "/api/me", self.owner); self.assertEqual(s, 200); self.assertEqual(d["user"]["role"], "owner"); self.assertEqual(d["garage"]["name"], "Kamau Motors")
        self.assertEqual(self.req("get", "/api/me")[0], 401)
        self.assertEqual(self.req("get", "/api/me", "garbage")[0], 401)
        self.assertEqual(self.req("post", "/api/auth/login", json=dict(email="owner@kamau.co.ke", password="wrong"))[0], 401)
    def test_rate_limit(self):
        codes = [self.req("post", "/api/auth/login", json=dict(email="owner@kamau.co.ke", password="bad"))[0] for _ in range(10)]
        self.assertEqual(codes[:8], [401] * 8); self.assertEqual(codes[8], 429)
        self.assertEqual(self.req("post", "/api/auth/login", json=dict(email="owner@kamau.co.ke", password="Secret123"))[0], 429)
    def test_disabled_user_blocked(self):
        t, uid = self.mk("mechanic", "m@k.co")
        self.assertEqual(self.req("patch", f"/api/users/{uid}", self.owner, dict(active=False))[0], 200)
        self.assertEqual(self.req("get", "/api/me", t)[0], 401)
    def test_security_headers_and_bad_json(self):
        r = self.c.get("/api/health"); self.assertEqual(r.headers["X-Frame-Options"], "DENY"); self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])
        self.assertEqual(self.req("post", "/api/vehicles", self.owner, None)[0], 400)
    def test_sql_injection_is_inert(self):
        self.vehicle()
        s, d = self.req("get", "/api/vehicles?q=' OR 1=1 --", self.owner); self.assertEqual((s, d), (200, []))
        s, d = self.req("get", "/api/parts?q=%25'; DROP TABLE parts;--", self.owner); self.assertEqual(s, 200)
        self.assertEqual(self.req("get", "/api/parts", self.owner)[0], 200)

class TestTenancy(Base):
    def test_isolation(self):
        v = self.vehicle(); p = self.part()
        s, j = self.req("post", "/api/jobs", self.owner, dict(vehicle_id=v, complaint="Noise")); self.assertEqual(s, 201)
        other = self.register("Other Garage", "o@other.co.ke", "0733000111")
        for m, u in (("get", f"/api/jobs/{j['id']}"), ("get", f"/api/vehicles/{v}"), ("post", f"/api/parts/{p}/adjust"), ("get", f"/api/parts/{p}/moves"), ("post", f"/api/jobs/{j['id']}/status")):
            s, _ = self.req(m, u, other, {"delta": 1, "reason": "received", "status": "diagnosing"} if m == "post" else None); self.assertEqual(s, 404, u)
        self.assertEqual(self.req("get", "/api/jobs", other)[1], []); self.assertEqual(self.req("get", "/api/parts", other)[1], [])
        s, d = self.req("post", "/api/jobs", other, dict(vehicle_id=v, complaint="x")); self.assertEqual(s, 404)
        s, d = self.req("post", "/api/vehicles", other, dict(plate="KDA 123A", phone="0700111222", customer_name="Z")); self.assertEqual(s, 201)  # plates unique per garage only

class TestStock(Base):
    def test_adjust_rules_and_ledger(self):
        p = self.part(qty=5)
        s, d = self.req("post", f"/api/parts/{p}/adjust", self.owner, dict(delta=10, reason="received", unit_cost=850)); self.assertEqual((s, d["qty"], d["unit_cost"]), (200, 15, 850))
        s, d = self.req("post", f"/api/parts/{p}/adjust", self.owner, dict(delta=-20, reason="damaged")); self.assertEqual(s, 409)
        s, d = self.req("post", f"/api/parts/{p}/adjust", self.owner, dict(delta=5, reason="damaged")); self.assertEqual(s, 400)
        s, d = self.req("post", f"/api/parts/{p}/adjust", self.owner, dict(delta=0, reason="received")); self.assertEqual(s, 400)
        s, d = self.req("post", f"/api/parts/{p}/adjust", self.owner, dict(delta=-3, reason="damaged")); self.assertEqual(d["qty"], 12)
        s, mv = self.req("get", f"/api/parts/{p}/moves", self.owner); self.assertEqual(sum(m["delta"] for m in mv), 12)
    def test_low_stock_and_duplicates(self):
        p = self.part(qty=2)
        s, d = self.req("get", "/api/parts?low=1", self.owner); self.assertEqual(len(d), 1); self.assertTrue(d[0]["low"])
        self.assertEqual(self.req("post", "/api/parts", self.owner, dict(sku="oil-5w30", name="dup", unit_cost=1, sell_price=2))[0], 409)
        self.assertEqual(self.req("post", "/api/parts", self.owner, dict(sku="X", name="neg", unit_cost=-1, sell_price=2))[0], 400)
        self.assertEqual(self.req("post", "/api/parts", self.owner, dict(sku="Y", name="frac", unit_cost=1.5, sell_price=2))[0], 400)
    def test_concurrent_use_never_oversells(self):
        p = self.part(qty=5); res = []
        jobs = []
        for i in range(8):
            v = self.vehicle(f"KDB{100+i}A", f"07001110{i:02d}")
            s, j = self.req("post", "/api/jobs", self.owner, dict(vehicle_id=v, complaint="x")); jobs.append(j["id"])
        def go(jid):
            c = self.app.test_client(); res.append(self.req("post", f"/api/jobs/{jid}/items", self.owner, dict(kind="part", part_id=p, qty=1), client=c)[0])
        ts = [threading.Thread(target=go, args=(j,)) for j in jobs]; [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(res.count(201), 5); self.assertEqual(res.count(409), 3)
        self.assertEqual(self.req("get", "/api/parts", self.owner)[1][0]["qty"], 0)

class TestWorkflow(Base):
    def setUp(self):
        super().setUp()
        self.mt, self.mid = self.mk("mechanic", "mech@k.co"); self.mt2, self.mid2 = self.mk("mechanic", "mech2@k.co")
        self.v = self.vehicle(); self.p = self.part(qty=10)
    def status(self, jid, st, tok=None): return self.req("post", f"/api/jobs/{jid}/status", tok or self.owner, dict(status=st))
    def new_job(self, mech=True):
        s, j = self.req("post", "/api/jobs", self.owner, dict(vehicle_id=self.v, complaint="Brakes squeal", mileage_in=81000, mechanic_id=self.mid if mech else None)); self.assertEqual(s, 201, j); return j
    def test_full_lifecycle(self):
        j = self.new_job(); jid = j["id"]; self.assertEqual(j["number"], "JC-00001")
        self.assertEqual(self.req("post", "/api/jobs", self.owner, dict(vehicle_id=self.v, complaint="again"))[0], 409)  # one open job per vehicle
        self.assertEqual(self.status(jid, "ready")[0], 409)  # illegal jump
        self.assertEqual(self.status(jid, "diagnosing", self.mt)[0], 200)
        self.assertEqual(self.status(jid, "quoted", self.mt)[0], 409)  # nothing to quote yet
        s, d = self.req("post", f"/api/jobs/{jid}/items", self.mt, dict(kind="part", part_id=self.p, qty=2)); self.assertEqual(s, 201)
        self.assertNotIn("totals", d); self.assertNotIn("unit_cost", d["items"][0])  # mechanic can't see money/cost
        self.assertEqual(self.req("post", f"/api/jobs/{jid}/items", self.mt, dict(kind="labour", description="Brake service", qty=1, unit_price=2500))[0], 403)
        s, d = self.req("post", f"/api/jobs/{jid}/items", self.owner, dict(kind="labour", description="Brake service", qty=1, unit_price=2500)); self.assertEqual(d["totals"], dict(subtotal=4900, vat=784, total=5684))
        self.assertEqual(self.req("get", "/api/parts", self.owner)[1][0]["qty"], 8)
        s, d = self.status(jid, "quoted", self.mt); self.assertEqual(s, 200); tok = d.get("approval_token")
        self.assertEqual(self.status(jid, "in_progress")[0], 409)  # not approved yet
        # customer approves from public link
        s, q = self.req("get", f"/api/public/quote/{tok}"); self.assertEqual((s, q["total"], q["garage"]), (200, 5684, "Kamau Motors")); self.assertNotIn("unit_cost", str(q))
        self.assertEqual(self.req("post", f"/api/public/quote/{tok}/approve")[0], 200)
        self.assertEqual(self.req("get", f"/api/public/quote/{tok}")[0], 404)  # single use
        self.assertEqual(self.status(jid, "in_progress", self.mt)[0], 200)
        # extra work after approval needs re-approval
        s, d = self.req("post", f"/api/jobs/{jid}/items", self.owner, dict(kind="labour", description="Rotor skim", qty=1, unit_price=1000)); self.assertTrue(d["needs_reapproval"])
        self.assertEqual(self.status(jid, "qa", self.mt)[0], 409)  # needs diagnosis notes
        self.req("patch", f"/api/jobs/{jid}", self.mt, dict(diagnosis="Pads worn, rotors skimmed"))
        self.assertEqual(self.status(jid, "qa", self.mt)[0], 200)
        self.assertEqual(self.status(jid, "ready", self.mt)[0], 403)  # mechanic can't sign off
        self.assertEqual(self.status(jid, "ready")[0], 409)  # unapproved extra
        self.assertEqual(self.req("post", f"/api/jobs/{jid}/approve", self.owner, dict(method="phone"))[0], 200)
        self.assertEqual(self.status(jid, "ready")[0], 200)
        s, inv = self.req("post", f"/api/jobs/{jid}/invoice", self.owner); self.assertEqual((s, inv["total"], inv["number"]), (201, 6844, "INV-00001"))
        self.assertEqual(self.req("post", f"/api/jobs/{jid}/invoice", self.owner)[0], 409)
        self.assertEqual(self.req("post", f"/api/jobs/{jid}/items", self.owner, dict(kind="labour", description="x", qty=1, unit_price=1))[0], 409)  # locked
        # payments
        pay = lambda **k: self.req("post", f"/api/invoices/{inv['id']}/pay", self.owner, k)
        self.assertEqual(pay(method="cash", amount=999999)[0], 409)
        self.assertEqual(pay(method="mpesa", amount=1000, reference="bad")[0], 400)
        s, d = pay(method="mpesa", amount=4000, reference="sgh7k2l9qp"); self.assertEqual((s, d["status"], d["balance"]), (200, "partial", 2844))
        self.assertEqual(pay(method="mpesa", amount=100, reference="SGH7K2L9QP")[0], 409)  # duplicate code
        s, d = pay(method="cash", amount=2844); self.assertEqual((d["status"], d["balance"]), ("paid", 0))
        self.assertEqual(pay(method="cash", amount=1)[0], 409)
        s, d = self.req("patch", f"/api/invoices/{inv['id']}", self.owner, dict(etims_ref="KRACU0100001234/5678")); self.assertEqual(d["etims_ref"], "KRACU0100001234/5678")
        # reports reflect it
        s, r = self.req("get", "/api/reports/summary?days=7", self.owner)
        self.assertEqual((r["collected"], r["invoiced"], r["outstanding"], r["vat_collected"]), (6844, 6844, 0, 944))
        self.assertEqual(r["gross_profit"], 6844 - 944 - 1600)
        self.assertEqual(r["mechanics"][0]["jobs"], 1); self.assertEqual(r["top_parts"][0]["qty"], 2)
        # history
        s, d = self.req("get", f"/api/vehicles/{self.v}", self.owner); self.assertEqual(d["jobs"][0]["status"], "invoiced")
    def test_mechanic_scope(self):
        j = self.new_job(); jid = j["id"]
        self.assertEqual(self.req("get", f"/api/jobs/{jid}", self.mt2)[0], 403)
        self.assertEqual(self.req("get", "/api/jobs", self.mt2)[1], [])
        self.assertEqual(len(self.req("get", "/api/jobs", self.mt)[1]), 1)
        for u in ("/api/reports/summary", "/api/invoices", "/api/users", "/api/audit"): self.assertEqual(self.req("get", u, self.mt)[0], 403, u)
        s, d = self.req("get", "/api/parts", self.mt); self.assertNotIn("unit_cost", d[0])
        self.assertEqual(self.req("post", "/api/parts", self.mt, dict(sku="Z", name="n", unit_cost=1, sell_price=2))[0], 403)
        self.assertEqual(self.req("patch", f"/api/jobs/{jid}", self.mt, dict(mechanic_id=self.mid2))[0], 403)
    def test_cancel_returns_stock(self):
        j = self.new_job(); jid = j["id"]
        self.req("post", f"/api/jobs/{jid}/items", self.owner, dict(kind="part", part_id=self.p, qty=4)); self.assertEqual(self.req("get", "/api/parts", self.owner)[1][0]["qty"], 6)
        self.assertEqual(self.status(jid, "cancelled")[0], 200); self.assertEqual(self.req("get", "/api/parts", self.owner)[1][0]["qty"], 10)
        self.assertEqual(self.req("post", "/api/jobs", self.owner, dict(vehicle_id=self.v, complaint="new"))[0], 201)  # vehicle free again
    def test_remove_line_returns_stock(self):
        j = self.new_job(); jid = j["id"]
        s, d = self.req("post", f"/api/jobs/{jid}/items", self.owner, dict(kind="part", part_id=self.p, qty=3)); iid = d["items"][0]["id"]
        s, d = self.req("delete", f"/api/jobs/{jid}/items/{iid}", self.owner); self.assertEqual(d["items"], [])
        self.assertEqual(self.req("get", "/api/parts", self.owner)[1][0]["qty"], 10)
    def test_cannot_start_unassigned_and_bad_inputs(self):
        j = self.new_job(mech=False); self.assertEqual(self.status(j["id"], "diagnosing")[0], 409)
        self.assertEqual(self.req("patch", f"/api/jobs/{j['id']}", self.owner, dict(mechanic_id=999))[0], 404)
        self.assertEqual(self.req("patch", f"/api/jobs/{j['id']}", self.owner, dict(mechanic_id=self.mid))[0], 200)
        self.assertEqual(self.status(j["id"], "diagnosing")[0], 200)
        self.assertEqual(self.req("post", f"/api/jobs/{j['id']}/items", self.owner, dict(kind="part", part_id=self.p, qty=0))[0], 400)
        self.assertEqual(self.req("post", f"/api/jobs/{j['id']}/items", self.owner, dict(kind="part", part_id=self.p, qty=99))[0], 409)
        self.assertEqual(self.req("post", f"/api/jobs/{j['id']}/items", self.owner, dict(kind="weird", qty=1))[0], 400)
        v2 = self.vehicle("KDC 456B", "0700999888"); self.assertEqual(self.req("post", "/api/jobs", self.owner, dict(vehicle_id=v2, complaint=""))[0], 400)
    def test_vehicle_validation(self):
        self.assertEqual(self.req("post", "/api/vehicles", self.owner, dict(plate="KDA 123A", phone="0700111222", customer_name="x"))[0], 409)
        self.assertEqual(self.req("post", "/api/vehicles", self.owner, dict(plate="!!", phone="0700111222", customer_name="x"))[0], 400)
        s, d = self.req("get", "/api/vehicles?q=kda123", self.owner); self.assertEqual(d[0]["phone"], "+254700111222")
        s, d = self.req("get", "/api/vehicles?q=wanj", self.owner); self.assertEqual(len(d), 1)

if __name__ == "__main__": unittest.main(verbosity=1)
