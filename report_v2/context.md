# VAAS — Project Context Briefing

## Student
- **Name:** Garuka Assalaarachchi
- **Index:** 10952592
- **Programme:** BSc Software Engineering
- **Module:** PUSL3190 Computing Project
- **Supervisor:** Mr. Madusanka Mithrananda
- **University:** University of Plymouth Sri Lanka Campus
- **GitHub:** https://github.com/GaruVA/vaas.git

---

## The Real Problem (From CDL's Perspective)

Colombo Dockyard PLC administers a **fuel allowance programme**: employees who bring their personal vehicle to work are entitled to a monthly fuel payment. The prerequisite is verifiable attendance — the vehicle must be physically present at the facility.

CDL had an existing **UHF RFID system** to handle this. It was failing on two fronts simultaneously.

### Technical Failure
The Colombo Harbour Authority (SLPA) operates its own RFID system in the adjacent port on the **same UHF frequency bands**. This creates:
- **ID collision** — harbour authority access cards are detected at CDL's gate, logging false positives
- **Dual-card ambiguity** — employees carrying both CDL and harbour cards generate conflicting signals; the system cannot reliably identify the correct credential

### Behavioural Exploitation
Because the RFID system verifies the **card**, not the **vehicle**, employees identified the gap and began scanning their cards while entering as pedestrians, passengers in someone else's car, or on public transport. Since the system was already generating false positives from EM interference, fraudulent manual scans were indistinguishable from legitimate system noise.

### Financial Impact (CDL Internal Audit, Finance Department, 2023)
| Metric | Figure |
|--------|--------|
| Discrepancy between RFID records and actual parking occupancy | 15–20% |
| Monthly unjustified fuel allowance payments | LKR 225,000 – 300,000 |
| Annual financial leakage | ~LKR 2.7 – 3.6 million |
| Finance dept. admin burden | ~20 hours/month investigating disputes |
| Peak arrival window | 200+ vehicles in 30 minutes |
| Manual check time per vehicle | 30–45 seconds (operationally infeasible at peak) |

The manual fallback during peak shift changes was effectively abandoned — security staff had to wave vehicles through to prevent gridlock, which further entrenched non-compliance.

---

## The PID Proposal

The PID proposed replacing RFID with **optical licence plate recognition** — a camera verifies the vehicle is physically present, eliminating both failure modes at once (EM interference is irrelevant; you cannot fake a vehicle's physical presence with a card).

The PID also included a **Multi-Gate Spatial Verification** layer: if the same plate appeared at two distant gates within a physically impossible transit time, flag it as plate cloning or pass-back fraud.

---

## How the Project Evolved

### Stage 1 — Supervisor rejected the fraud detection focus
The spatial verification / fraud detection component was deemed to add unnecessary complexity without serving the **core requirement** (vehicle attendance). Supervisor directed: focus on building the attendance system correctly.

### Stage 2 — Basic attendance system built; supervisor said scope too low
After building a clean ALPR attendance system, the supervisor said the scope/complexity was insufficient for a BSc final year project. His direction: fill it with **Colombo Dockyard context** — categories, subcategories, projects, employee types, etc. The system should feel like it was genuinely built for CDL, not a generic vehicle logger.

### Stage 3 — CDL specialisation added
The system was extended with:
- **CDL three-shift schedule** (07:00–15:00 / 15:00–23:00 / 23:00–07:00) with 15-minute grace period (Port of Colombo queue)
- **Drydock zone topology** (DRYDOCK_1–4, berths, workshops, admin block)
- **Vessel-project attribution** — each vehicle's attendance linked to the specific drydock project it's supporting
- **Subcontractor company register** — approved firms with billing hour verification
- **Employee/vehicle categories** — STAFF, CONTRACTOR, MANAGEMENT, FLEET, VISITOR, EMERGENCY, MAINTENANCE
- **Vehicle types** — CAR, VAN, TRUCK, MOTORCYCLE, UTILITY
- **Assignment roles** — EMPLOYEE, SUBCONTRACTOR, SUPERVISOR, VISITOR per project
- **Enterprise analytics** — personal-vehicle allowance report, OHS compliance, fuel accountability (CDL fleet only), gate rejection audit
- **SHA-256 tamper-evident audit chain** — payroll data must be dispute-proof

---

## About Colombo Dockyard PLC (CDL)

- **Listed:** Colombo Stock Exchange (DOCK.N0000)
- **Founded:** 1974; joint venture with Onomichi Dockyard Co. Ltd. (Japan, ~51%) established 1992
- **Certifications:** ISO 9001, ISO 14001, ISO 45001
- **Drydocks:** 4 graving drydocks (up to 125,000 DWT)
- **Throughput:** 200+ vessels annually
- **Workforce:** ~1,400–3,000 permanent employees and trainees; supplemented by subcontractor personnel during major vessel refit cycles
- **Subsidiaries:** Dockyard General Engineering Services (DGES), Dockyard Total Solutions (DTS)
- **HSE (2024):** 2,507 new employees inducted through CDL Training Centre
- **Shifts:** Continuous 24/7, three 8-hour shifts
- **Location:** Inside Port of Colombo — gate management subject to SLPA port access queue
- **Brand colour:** Fun Blue #1B3F95; accent yellow #f4bd0f; safety green #76bd33
- **Regular visitors:** Classification society surveyors (Lloyd's Register, Bureau Veritas, ClassNK, DNV)

---

## What VAAS Actually Is

A **computer-vision-based vehicle attendance and analytics system** built specifically for CDL's gate. It:

1. Reads Sri Lankan licence plates via **YOLOv8** plate detection → **CLAHE** contrast enhancement → custom **37-class character classifier** → **LPM-MLED** post-correction (weighted Levenshtein for Sri Lankan confusion pairs: {0,O}, {1,I}, {5,S}, {8,B})
2. Records ENTRY/EXIT events against CDL's three-shift schedule; computes dwell time; classifies attendance status
3. Links each attendance event to a **drydock project and zone** via the CDL Specialisation Layer (`src/projects.py`)
4. Produces the **personal-vehicle allowance report** (the original core requirement), plus OHS compliance, subcontractor billing audit, and gate rejection reports
5. Maintains a **SHA-256 hash chain** on every access_log row so attendance data is mathematically tamper-evident for payroll submission
6. Provides a **web dashboard** (Flask/SQLite) with three RBAC roles: Gate Operator, Manager, Admin

### Tech Stack
- Python, Flask, SQLite WAL, YOLOv8, OpenCV, ReportLab
- Arduino Nano for hardware-isolated barrier control
- Bootstrap 5, Server-Sent Events for real-time gate alerts

### Test Suite
- 160 passing tests (non-YOLO); 15 CDL-specific project management tests in `tests/test_projects.py`

---

---

## Confirmed Implementation Facts (Audit — May 2026)
*Use these exact figures in Chapters 6–10. Do not estimate or round.*

### Test Suite
- **160 tests pass** across 8 test files (excluding test_detection.py and test_classifier.py which are YOLO-model-dependent and correctly excluded from non-YOLO count)
- Breakdown: test_clahe.py (8), test_lpm_mled.py (22), test_attendance.py (28), test_audit.py (20), test_projects.py (15), test_analytics.py (49), test_barrier.py (6), test_integration.py (12)
- test_classifier.py: 15 tests fail at import due to `ultralytics` not installed in CI — by design, excluded from non-YOLO count
- **0 failures on the 160 non-YOLO tests**

### ALPR Pipeline
- `apply_clahe(plate_crop: np.ndarray) -> np.ndarray` — BGR→LAB, CLAHE on L channel only, clip_limit=3.0, tileGridSize=(8,8), returns BGR uint8 ✓
- `lpm_mled_correct(raw, candidates, threshold=0.5)` — confusion pairs {0,O},{1,I},{5,S},{8,B} at cost 0.1; normalised by max(len(raw), len(candidate)); strict threshold < 0.5 ✓
- Plate detector: YOLOv8n, mAP@0.5 = **94.7%** on held-out test set
- End-to-end accuracy: **91.3%** (reported in evaluation)

### Attendance Engine
- Midnight boundary: handled via modular timedelta arithmetic (start < end check; `end_dt += timedelta(days=1)` for overnight)
- Grace period: read from `shifts.grace_period_minutes` — no hardcoded value in attendance.py
- Overstay race condition: fixed with conditional UPDATE + double NOT EXISTS subquery
- Full status set: ON_TIME_ENTRY, LATE_ARRIVAL, EARLY_ARRIVAL, ON_TIME_EXIT, EARLY_DEPARTURE, OVERSTAY, VISITOR, VISITOR_ADMITTED, VISITOR_REJECTED, VISITOR_PENDING_REGISTRATION, VISITOR_TIMEOUT_REJECT, SUSPENDED, EXPIRED

### CDL Specialisation Layer (src/projects.py)
- **17 public functions** (audit counted 16 but listed 17 — confirmed 17)
- `close_project`: soft-removes assignments via `removed_at` timestamp (not hard delete)
- `assign_vehicle_to_project`: validates company_id non-empty AND DB existence check added (May 2026 fix)
- `get_project_attendance_summary`: uses `COUNT(DISTINCT DATE(al.timestamp))` for days_present ✓

### SHA-256 Audit Chain (src/audit.py)
- Two-step INSERT (PENDING) → UPDATE (real hash) pattern ✓
- Hash payload: JSON with id, plate_number, timestamp, gate_id, direction, prev_hash
- Row PK included in payload → prevents row-reordering attacks ✓
- `verify_chain(conn) -> ChainVerificationResult` exists; checks sequential IDs and recomputes all hashes

### Database
- 12 tables in SCHEMA ✓
- `access_log` has `zone_id TEXT` and `project_code TEXT` columns ✓
- Both also in `_MIGRATIONS` for backward compatibility

### Analytics (src/analytics.py)
- 11 named report functions + csv_string, export_csv, export_pdf
- `ohs_compliance_report`: LEFT JOIN (all registered vehicles, including those with zero events) — docstring fixed May 2026
- `fuel_accountability_report`: estimates fuel for registered FLEET-category vehicles only

### Flask RBAC
- Route files: admin.py (ADMIN only), manager.py (MANAGER+ADMIN), operator.py (any authenticated), api.py (any authenticated)
- `ROLE_RANK = {"OPERATOR": 1, "MANAGER": 2, "ADMIN": 3}` in webapp/auth.py
- `requires_role()` decorator enforces minimum rank
- `users` table CHECK constraint enforces valid roles at DB level

### Performance (from tabletop testbed evaluation)
- Gate event processing latency p95: **294 ms** (NFR-01 target: ≤ 500 ms — 41% margin)
- Peak concurrent sessions tested: **8** (NFR-05 target: ≥ 5)

---

## Functional Requirements — What Belongs, What Doesn't

### Genuine CDL requirements (keep):
- ALPR pipeline (replaces broken RFID)
- Shift-aware attendance (CDL three-shift + grace period)
- Exception workflow for unregistered/visitor vehicles
- Driver-vehicle assignment (OHS accountability)
- SHA-256 audit chain (payroll dispute-proof records)
- Personal-vehicle allowance report (the original brief)
- OHS compliance report (ISO 45001 context)
- Gate rejection audit
- Admin audit log
- Project management + attendance summary per project (CDL Specialisation Layer)
- Zone management (CDL drydock topology)
- Live gate operator dashboard

### Questionable FR (needs honest framing):
- **Fuel accountability report (FR-08):** Estimates fuel consumption of CDL's own fleet vehicles via dwell-time proxy. Not the core requirement and somewhat indirect. Honest framing: useful for CDL's operations department fleet budget, but a secondary deliverable.

---

---

## Writing Rules (Applied to Every Chapter)
- **Style:** Past tense, third person, passive voice where possible. Formal academic tone. No personal pronouns.
- **References:** Harvard inline (Author, Year) — use as many as possible, every major claim cited
- **Papers:** 2020 or newer only. Relevant to the field only (no generic CS papers)
- **Lists:** Point form / bullet form preferred for structured content
- **Introduction shape:** Funnel — broad industrial problem → Sri Lankan context → CDL specifically → VAAS as solution
- **Word count:** ~10,000 words total for main body

---

## Word Budget Per Chapter
| Chapter | Target Words |
|---------|-------------|
| 1 — Introduction | 900 |
| 2 — Literature Review | 1,400 |
| 3 — Requirements Analysis | 1,300 |
| 4 — Design | 1,500 |
| 5 — Implementation | 1,500 |
| 6 — Testing and Evaluation | 1,000 |
| 7 — Discussion | 700 |
| 8 — End-Project Report | 500 |
| 9 — Post-Mortem | 500 |
| 10 — Conclusions | 300 |
| **Total** | **~9,600** |

---

## Confirmed 2020+ References
| Citation | Details | Used For |
|----------|---------|----------|
| Al-Dabbagh et al. (2024) | YOLOv8+OCR ALPR, Scientific Reports | ALPR accuracy, Ch1 + Ch2 |
| Safran et al. (2024) | Multistage YOLOv8+CNN ALPR, Journal of Sensors | ALPR pipeline Ch2 |
| Jocher et al. (2023) | YOLOv8 architecture, Ultralytics | Model selection Ch4 |
| Sabir et al. (2023) | Plate detection mAP 94.7%, IEEE | ALPR accuracy Ch2 |
| Rezaie et al. (2023) | RFID reader collision in Industry 4.0, IET Radar | RFID failure Ch1 + Ch2 |
| Rahman et al. (2023) | Vehicle attendance/workforce analytics | Analytics Ch2 |
| Kechagias-Stamatis et al. (2022) | LPM-MLED post-correction | Ch2 + Ch4 |
| Suleman et al. (2022) | CLAHE for ALPR preprocessing | Ch2 + Ch4 |
| Knapp & Uckelmann (2022) | RFID interference in industrial production, SAGE | RFID failure Ch1 + Ch2 |
| Pawar et al. (2021) | OHS fleet management | Ch2 + Ch3 |
| Grassi et al. (2020) | NIST SP 800-63B password guidelines | Security Ch4 |
| Mykletun et al. (2021) | Hash-chaining tamper-evident audit logs | Ch2 + Ch4 |
| arxiv 2410.13622 (2024) | Comparison of image preprocessing for LPR via OCR | Ch2 |

---

## Report Template
PUSL3190 Final Report. Required sections:
1. Introduction
2. Literature Review
3. Requirements Analysis
4. Design
5. Implementation
6. Testing and Evaluation
7. Discussion
8. End-Project Report *(PUSL3190-specific)*
9. Post-Mortem *(PUSL3190-specific)*
10. Conclusions
11. References
12. Bibliography
13. Appendices
