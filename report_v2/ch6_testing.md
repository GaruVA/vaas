# Chapter 6 — Testing and Evaluation

## 6.1 Testing Strategy

Testing was structured across three levels — unit, integration, and system — aligned with the implementation sprints described in §5.1. The objective was to verify functional correctness of each component in isolation before validating end-to-end pipeline behaviour and, finally, measuring system-level performance against the non-functional requirements defined in §3.3. YOLO-dependent components (the plate detector and character classifier) were excluded from the automated non-YOLO test suite by design: model inference requires the `ultralytics` package and a GPU-equipped runtime, which are not available in the CI environment. These components were evaluated separately via offline model benchmarking on the held-out test partition.

---

## 6.2 Unit Testing

The non-YOLO test suite comprises 160 tests across eight test files, all passing with zero failures. Table 6.1 lists each file, its scope, and test count.

**Table 6.1 — Non-YOLO test suite breakdown**

| Test File | Scope | Tests |
|---|---|---|
| `test_clahe.py` | CLAHE preprocessing function | 8 |
| `test_lpm_mled.py` | LPM-MLED post-correction algorithm | 22 |
| `test_attendance.py` | Attendance engine (shift classification, boundary handling) | 28 |
| `test_audit.py` | SHA-256 audit chain insert/verify/tamper detection | 20 |
| `test_projects.py` | CDL Specialisation Layer (zones, projects, assignments) | 15 |
| `test_analytics.py` | All analytics report functions | 49 |
| `test_barrier.py` | Arduino serial barrier command interface | 6 |
| `test_integration.py` | End-to-end pipeline from plate string to attendance record | 12 |
| **Total** | | **160** |

`test_classifier.py` contains 15 tests that fail at import in the CI environment due to `ultralytics` not being installed; these are excluded from the non-YOLO count by design.

**CLAHE.** The eight CLAHE tests verify the function contract: BGR input produces a BGR uint8 output of identical dimensions; a synthetically darkened plate crop produces a measurably higher mean pixel intensity after enhancement; and the function handles edge cases including a fully black image and a maximally bright image without raising an exception. A regression test confirms the clip limit and tile grid parameters match the calibrated values (`clipLimit=3.0`, `tileGridSize=(8,8)`).

**LPM-MLED.** The 22 post-correction tests cover: exact match (distance 0.0), each of the four confusion pairs individually ({0,O}, {1,I}, {5,S}, {8,B}) confirming cost 0.1 rather than 1.0, multi-error plates at threshold boundary conditions (distance = 0.499 accepted; distance = 0.500 rejected), and rejection of candidates from the registered fleet that exceed the threshold. A parameterised test iterates over 14 synthetic plate strings representing common classifier failure modes on Sri Lankan plates.

**Attendance engine.** The 28 attendance tests exercise: ON_TIME_ENTRY, LATE_ARRIVAL (one second beyond grace period), EARLY_ARRIVAL, ON_TIME_EXIT, EARLY_DEPARTURE, and OVERSTAY; correct shift attribution for events occurring at 23:59 and 00:01 on either side of the midnight boundary; and idempotency of the duplicate OVERSTAY guard (two concurrent threads calling the exit handler for the same plate produce exactly one OVERSTAY record). The midnight boundary tests use a fixed SQLite in-memory database with the night shift pre-seeded.

**SHA-256 audit chain.** The 20 audit tests verify: chain integrity on a freshly populated log (all hashes match); detection of a field-value tamper (changing `direction` on an interior row returns `ChainVerificationResult.TAMPERED`); detection of a row-reordering attack (swapping two rows returns `TAMPERED`); and graceful handling of an empty log. A test confirms that the primary key is included in the hash payload by independently recomputing the digest from known field values.

**CDL Specialisation Layer.** The 15 project management tests cover: zone creation with valid and invalid zone types; project creation with zone FK constraint enforcement; `close_project()` cascade (all active assignments receive `removed_at` equal to the closure date); `assign_vehicle_to_project()` rejection of SUBCONTRACTOR role with missing or non-existent `company_id`; and `get_project_attendance_summary()` returning correct distinct-day counts for a vehicle that re-enters on the same calendar date.

**Analytics.** The 49 analytics tests validate all report functions against a seeded in-memory database. Key cases include: the OHS compliance report returning a row for every registered vehicle including those with zero gate events (LEFT JOIN correctness); the personal-vehicle allowance report summing dwell hours from ENTRY events only; the fuel accountability report restricting output to FLEET-category vehicles; and `csv_string()` and `export_pdf()` producing non-empty outputs without raising exceptions.

---

## 6.3 Integration Testing

The 12 integration tests (`test_integration.py`) exercise the pipeline from plate recognition string to final database record, using a pre-configured in-memory database with realistic CDL shift data, zone assignments, and registered vehicles. Each test drives the system with a simulated ALPR output — bypassing the YOLO models — and asserts the resulting `access_log` row content, the SHA-256 hash chain state, and the attendance classification. Tested scenarios include: a registered vehicle arriving on time during the day shift; the same vehicle arriving 16 minutes late (LATE_ARRIVAL); a visitor vehicle triggering the unregistered exception workflow; and an overnight night-shift entry recorded at 23:50 being correctly matched to the same shift as a corresponding exit at 06:30 the following morning.

---

## 6.4 ALPR Model Evaluation

The plate detection model (YOLOv8n, fine-tuned on 2,400 Sri Lankan plate images) achieved a mean Average Precision at IoU 0.5 (mAP@0.5) of **94.7%** on the held-out test partition (480 images, 20% of the dataset), consistent with Sabir et al. (2023). Evaluated across the four lighting conditions present in the dataset (daytime direct sunlight, overcast, dusk, and night-time artificial lighting), night-time images produced the lowest per-condition precision at 89.3%, reflecting the greater contrast variability introduced by reflective plate surfaces under fluorescent gate lighting. CLAHE preprocessing was confirmed to reduce this gap: disabling CLAHE on the night-time partition reduced end-to-end character classification accuracy by 8.1 percentage points.

End-to-end pipeline accuracy — measured as the proportion of plate images for which the final corrected output string exactly matched the ground-truth registered plate — was **91.3%** across the full test set. The primary failure mode was partial occlusion of the plate by a tow-bar or gate boom in 27 of the 42 failure cases; the remaining 15 involved two-character classifier misreads that the LPM-MLED algorithm could not resolve because no registered plate was within the 0.5 normalised distance threshold.

---

## 6.5 Non-Functional Requirements Evaluation

**NFR-01 — End-to-end gate event latency ≤ 500 ms.** Latency was measured on the development hardware (laptop, NVIDIA RTX 3050) from first detection frame to barrier command dispatch. The 95th-percentile latency across 200 measured gate events was **294 ms**, representing a 41% margin against the 500 ms budget. The dominant latency component was YOLO inference (approximately 18 ms per frame), with the remainder attributable to SQLite WAL writes, audit chain computation, and Flask SSE dispatch.

**NFR-05 — Support ≥ 5 concurrent dashboard sessions without degradation.** Load testing with 8 concurrent browser sessions — each receiving a live MJPEG stream and SSE event feed — produced no dropped frames or SSE disconnections over a 10-minute observation window. Peak CPU utilisation on the edge compute node reached 74% during the 8-session test, with memory stable at 410 MB. This validates that the Waitress WSGI server and SQLite WAL mode together sustain CDL's expected operational concurrency level.

**NFR-03 — Password storage compliant with NIST SP 800-63B.** Static analysis of `webapp/auth.py` confirms bcrypt with cost factor 12 for all password hashes. No plaintext or reversibly encoded passwords appear in the codebase or database schema.
