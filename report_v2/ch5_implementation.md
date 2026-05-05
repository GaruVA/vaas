# Chapter 5 — Implementation

## 5.1 Development Methodology

Development followed an iterative Agile approach across thirteen two-week sprints spanning October 2025 to April 2026. Sprint planning and retrospective meetings were held fortnightly with the project supervisor. Three interim reports were submitted at sprint milestones — covering Sprints 1–5 (November 2025), Sprints 6–10 (January 2026), and Sprints 11–13 (March 2026) — providing structured checkpoints at which scope changes were agreed. The primary scope change during the project occurred at the Sprint 6 review, when the multi-gate spatial verification component from the original PID was formally descoped and replaced with a CDL-contextualised attendance analytics approach. Sprint responsibilities were allocated as follows:

| Sprints | Focus Area | Key Deliverables |
|---|---|---|
| 1–2 | Dataset and environment | 2,400 Sri Lankan plate images collected; YOLOv8 training pipeline established |
| 3–4 | ALPR pipeline | Plate detector (mAP 94.7%); 37-class character classifier |
| 5 | Post-correction | LPM-MLED algorithm; end-to-end accuracy reached 90%+ |
| 6–7 | Attendance engine and audit chain | `src/attendance.py`; `src/audit.py`; `access_log` schema with SHA-256 chain |
| 8–9 | Analytics and web dashboard | `src/analytics.py`; Flask routes; CSV and PDF export via ReportLab |
| 10 | Security | RBAC authentication; bcrypt password storage; session management |
| 11 | Testing | Test suite expanded to 120 tests; integration tests added |
| 12 | CDL Specialisation Layer | `src/projects.py`; `cdl_zones`, `projects`, `project_vehicle_assignments`, `subcontractor_companies` tables |
| 13 | Enterprise analytics and finalisation | Four enterprise report types; 160 passing non-YOLO tests |

---

## 5.2 ALPR Pipeline Implementation

**Dataset collection.** A dataset of 2,400 Sri Lankan licence plate images was assembled across CDL's gate conditions, covering daytime direct sunlight, overcast, dusk, and night-time artificial lighting scenarios. Images were captured at the gate approach angle (approximately 45°) at distances of 2 to 6 metres, reflecting the range at which vehicles present themselves at CDL's security checkpoint.

**Plate detection model.** The YOLOv8n model was fine-tuned on the plate detection dataset using transfer learning from the COCO pre-trained weights. Training ran for 100 epochs with early stopping at patience 20. The resulting model achieved a mean Average Precision at IoU 0.5 of 94.7 percent on the held-out test set (20 percent of the dataset), consistent with Sabir et al. (2023). Inference runs at approximately 18 ms per frame on the development hardware, satisfying NFR-01's 500 ms end-to-end latency budget.

**CLAHE implementation.** CLAHE preprocessing was implemented in `src/clahe.py`. The function converts the plate crop from BGR to LAB colour space using OpenCV's `cvtColor`, applies `createCLAHE(clipLimit=3.0, tileGridSize=(8,8))` to the L channel only, reconstructs the LAB image, and converts back to BGR. The function always returns a BGR uint8 array, preserving the interface contract expected by the character classifier. The clip limit of 3.0 was selected following empirical testing against CDL's night-gate scenario, where values below 2.5 produced insufficient enhancement and values above 4.0 introduced halo artefacts around plate edges.

**Character classifier.** A second YOLOv8 model was trained on individual character crops spanning 37 classes. Characters are sorted by the x-coordinate of their bounding box centre to reconstruct the plate string in reading order. This character-level detection approach was preferred over a CRNN sequence model because the diverse plate formats in CDL's registered fleet — spanning three generations of Sri Lankan plate conventions — produced inconsistent sequence lengths that destabilised CTC-loss training on the available dataset size (Safran et al., 2024).

**LPM-MLED post-correction.** The algorithm, implemented in `src/lpm_mled.py`, computes a weighted edit distance between the raw classifier output and every plate in the registered vehicle database. The confusion-pair cost matrix assigns a substitution cost of 0.1 to {0, O}, {1, I}, {5, S}, and {8, B}, and 1.0 to all other substitutions. Insertion and deletion costs are fixed at 1.0. The raw distance is normalised by `max(len(raw), len(candidate))` to produce a value in [0.0, 1.0]. A match is accepted if the normalised distance is below 0.5. This threshold was calibrated empirically: values above 0.5 produced false acceptances on plates with two or more genuine errors; values below 0.3 rejected legitimate corrections on heavily soiled plates.

---

## 5.3 Attendance Engine Implementation

The attendance engine (`src/attendance.py`) translates a recognised plate event into a structured database record with a classified attendance status. Three implementation challenges required non-trivial solutions:

**Midnight boundary handling.** CDL's night shift (23:00–07:00) spans the calendar day boundary. A naïve comparison of event timestamp against shift start and end times using calendar dates would split night-shift entries (23:00–23:59) from exits (00:00–07:00) into different calendar days, producing incorrect dwell-time calculations and broken shift attribution. The implementation uses modular time representation: times are expressed in minutes since midnight, and the night shift's end time is represented as 07:00 + 1440 (one calendar day in minutes) when the start time is 23:00. Comparison arithmetic is then performed modulo 1440, correctly bridging the midnight boundary.

**Grace period enforcement.** The 15-minute grace period is stored in the `shifts` table as `grace_period_minutes` and is applied at runtime: an event occurring within `start_time + grace_period_minutes` is classified as ON_TIME_ENTRY; one occurring after that window is LATE_ARRIVAL. This design allows CDL to recalibrate the grace period — for example, on days when SLPA reports unusually heavy port traffic — without modifying application code.

**Overstay race condition.** During load testing with concurrent gate events, a race condition was identified in which two processing threads simultaneously classified the same vehicle as OVERSTAY on exit, writing duplicate status records. The fix uses a conditional SQL UPDATE with a NOT EXISTS subquery: the UPDATE only executes if no OVERSTAY record for the plate already exists in the target time window, making the operation idempotent under concurrent execution.

---

## 5.4 CDL Specialisation Layer Implementation

The CDL Specialisation Layer was implemented in Sprint 12 as the module `src/projects.py`, containing seventeen public functions across three logical groups: zone management, project management, and subcontractor management. Key implementation decisions:

**Project closure cascade.** When `close_project()` is called, all active vehicle assignments for the project are automatically removed by setting `removed_at` to the closure timestamp. This prevents stale assignment records from appearing in future occupancy counts or attendance summaries without requiring the caller to manage assignment state separately.

**Subcontractor role validation.** The `assign_vehicle_to_project()` function enforces two checks at the application layer before any database write: (i) a vehicle assigned with role SUBCONTRACTOR must provide a non-empty `company_id`, and (ii) that `company_id` must exist in the `subcontractor_companies` table. Both checks raise a descriptive `ValueError` on failure, providing a clear diagnostic for the caller rather than surfacing a database foreign-key violation message.

**Attendance summary calculation.** `get_project_attendance_summary()` computes attendance days as the count of distinct calendar dates on which a vehicle has at least one ENTRY event linked to the project's zone gates within the project's active date range. Total dwell hours are summed from paired ENTRY/EXIT events. Distinct date counting — rather than summing all events — prevents duplicate attendance credits for vehicles that exit and re-enter within the same calendar day, which is common for CDL employees on split-duty shifts.

---

## 5.5 SHA-256 Audit Chain Implementation

The audit chain (`src/audit.py`) implements a two-step INSERT/UPDATE pattern. Each gate event is first inserted into `access_log` with a PENDING placeholder in the `row_hash` column. The application then reads back the auto-assigned primary key, constructs a hash payload comprising the row ID, plate number, timestamp, gate ID, direction, and the hash of the immediately preceding row, and computes the SHA-256 digest. A subsequent UPDATE replaces the placeholder with the computed hash.

The inclusion of the row primary key in the hash payload is a deliberate security property: it binds the hash to the database-assigned position of the row, so that an adversary who reorders two legitimate rows — leaving all field values unchanged — produces a detectable hash mismatch on the reordered records. This row-reordering attack vector was identified during a security review in Sprint 10 and was absent from the initial audit chain design.

---

## 5.6 Analytics and Reporting

The analytics engine (`src/analytics.py`) implements four report functions corresponding to FR-07 through FR-09 and the fuel accountability function:

- **Personal-vehicle allowance report** (FR-07): queries `access_log` joined to `project_vehicle_assignments` to produce a per-driver, per-project summary of attendance days, total dwell hours, and compliance rate.
- **OHS compliance report** (FR-08): queries `registered_vehicles` left-joined to `vehicle_assignments` and `access_log`, classifying each vehicle as UNASSIGNED, SUSPENDED, EXPIRED, HIGH_OVERSTAY (> 2 hours beyond shift end), or OK.
- **Gate rejection audit** (FR-09): queries `gate_rejections` with date-range filtering and returns records ordered newest-first.
- **Administrative audit log** (FR-10): queries `admin_audit_log` with optional user and entity-type filters.

All reports support export to CSV via `csv_string()` and to PDF via `export_pdf()`, which uses ReportLab's `SimpleDocTemplate` with CDL's corporate colour scheme (Fun Blue #1B3F95).
