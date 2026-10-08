# Gari: garage management SaaS for Nairobi

## 1. Research findings (what Nairobi garages deal with)

| Finding | Source type | Design response |
|---|---|---|
| Customers distrust garages: swapped/stolen parts, charges for parts never fitted, fake parts, inflated prices | Kenyan press (The Star, Kenyans.co.ke, Money254), Kemra (Kenya Motor Repairers Assoc.) on counterfeit parts | Every part used is logged against a job and a stock ledger; customer approves an itemised quote by link; belongings and fuel recorded at check-in; timeline of who did what |
| Paper job cards: parts used but not billed, "is my car ready?" calls, lost service history | Garage-software vendor material (Kolonell, Softhealer, Auto+) | Digital job cards, auto stock deduction, plate-based history, status board |
| Extra work found mid-repair is the main source of disputes | GetAFix workflow (customer confirmation of excess over estimate) | Approved total is locked; any added line sets "needs approval"; job cannot be marked ready/invoiced until re-approved |
| eTIMS: only eTIMS-backed expenses are deductible; Finance Act 2026 raised penalties; KRA now validates returns against eTIMS data; eTIMS had an outage in 2026 | Business Daily, CM Advocates, Beancount | Invoice carries VAT 16% and an eTIMS reference field. Direct eTIMS API submission is roadmap, with offline queueing because KRA can be down |
| ODPC registration and 72-hour breach notification under the Data Protection Act 2019; renewals enforced in Aug-Sep 2026 | ODPC, Capital FM, CMS Law | Per-garage tenant isolation, audit log, consent flag, minimal PII, role-based access. Register the company with ODPC as a processor before launch |
| M-Pesa is the dominant payment method | Industry practice | M-Pesa code captured and validated (10 chars), unique per garage so a code can't be reused. Daraja STK Push is roadmap |

**Caveat:** I could not observe garages first-hand, and vendor blogs are marketing. Before building further, shadow 5-8 garages (Industrial Area, Ngong Rd, Kariobangi/Jua Kali, a brand dealership) and validate the pain points and willingness to pay.

## 2. Workflow implemented

```
Check-in -> Diagnosing -> Quoted -> Approved -> In repair -> Quality check -> Ready -> Invoiced -> Paid
   |            |           |  ^customer link / phone / WhatsApp / in person
   +---------- Cancelled (parts return to stock)     In repair <-> Quoted (new quote for extra work)
```
Rules enforced server-side (not just in the UI): legal transitions only; a mechanic must be assigned before starting; at least one line before quoting; diagnosis notes before QA; only managers sign off "ready"; no invoicing with unapproved extra work; one open job per vehicle; one invoice per job.

## 3. Architecture

```
 Browser (vanilla JS SPA, no build step)         Customer phone (public quote page)
          | HTTPS + JWT                                    | HTTPS + single-use token
          v                                                v
   +------------------ Reverse proxy / TLS (Caddy or nginx) ------------------+
          v
   Flask API (stateless, gunicorn workers)  --- audit log, RBAC, validation
          v
   SQLite (WAL) today  ->  PostgreSQL when >~200 garages   (same SQL; tenant column on every table)
          v
   Nightly encrypted backups (Litestream/pg_dump) to off-site storage in Africa/EU
```

**Multi-tenancy:** every row carries `garage_id`; every query filters on the authenticated user's garage. Tested: a second garage gets 404 on every foreign resource.

**Security:** scrypt password hashing; JWT (HS256, 12 h) re-checked against the DB each request so disabling a user is immediate; roles owner/manager/mechanic; mechanics see only their jobs and never see prices or costs; login throttling; parameterised SQL everywhere (injection test passes); UI built with a DOM builder that never uses innerHTML (XSS test passes); CSP, X-Frame-Options, nosniff, no-store on API; request size limit; audit trail of sensitive actions; single-use unguessable quote tokens.

**Speed:** one round-trip per screen; indexes on tenant/status/plate/job; no framework or build, so a few tens of KB of JS; fits low-bandwidth mobile data.

**Scalability:** stateless API workers scale horizontally. The first bottleneck is SQLite's single writer; move to PostgreSQL and add a read replica for reports. Reports are plain aggregates today, so add materialised daily summaries past ~50k jobs per garage.

**Reliability:** transactions per request (rollback on error); atomic stock decrement (`UPDATE ... WHERE qty>=?`) proven under concurrent load; stock is a ledger so counts can be audited and rebuilt; unique constraints block duplicate invoices/M-Pesa codes; `/api/health` for monitoring.

## 4. Known gaps (be honest before launch)
1. **No offline mode.** Nairobi connectivity is uneven, so this is the top follow-up (service worker + local queue for job notes and stock use).
2. **M-Pesa is manual entry** of the confirmation code. Next step: Daraja STK Push + C2B confirmation callbacks.
3. **eTIMS is a reference field**, not an integration. Needs KRA OSCU/VSCU or a certified provider.
4. **No SMS/WhatsApp sending.** Quote link is shared via copy or a WhatsApp deep link; add Africa's Talking for automated SMS and service reminders.
5. JWT is stored in localStorage (mitigated by CSP and no innerHTML); move to httpOnly cookies + CSRF token for production. No password reset, 2FA, or email verification yet.
6. Rate limiting is in-process memory; use Redis behind multiple workers.
7. Not yet covered: purchase orders and suppliers, insurance-claim split jobs, sublet work, vehicle inspection photos, multi-branch, VAT-exempt items.

## 5. Run it
```
pip install -r requirements.txt
export GARI_SECRET=$(python3 -c "import secrets;print(secrets.token_hex(32))")
python3 app.py                         # dev, http://localhost:5000
gunicorn -w 3 -b 0.0.0.0:8000 "app:create_app()"   # production
python3 -m unittest discover -s tests  # 16 API tests
tests/run_e2e.sh                       # 52 browser checks (needs: pip install playwright && playwright install chromium)
```
