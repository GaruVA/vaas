# Chapter 4 — System Design

## 4.1 Architectural Overview

VAAS follows a four-layer architecture: a hardware layer responsible for video capture and physical barrier actuation; a computer vision pipeline performing plate detection, enhancement, and character recognition; an application layer encompassing the attendance engine, analytics engine, CDL Specialisation Layer, and web dashboard; and a data layer comprising the SQLite WAL database and SHA-256 audit chain.

The design is deliberately edge-first. All processing — ALPR inference, attendance decision logic, exception handling, and the web dashboard — executes on a gate-side edge compute node. No cloud connectivity is required during normal operation. This decision was driven by CDL's operational context: the facility is located inside the Port of Colombo, where intermittent network outages occur independently of CDL's internal infrastructure, and a gate system that fails when connectivity is lost is operationally unacceptable in a 24/7 three-shift environment.

---

## 4.2 Hardware Architecture

Each gate node comprises three physical components:

- **IP camera** (1080p minimum, Wide Dynamic Range, ≥ 15 fps) mounted at approximately 45° to the vehicle approach lane. WDR is required to handle CDL's mixed lighting: direct tropical sunlight on the day shift, artificial fluorescent gate lighting on the night shift, and the high-contrast glare reflected from vessel hulls and wet concrete.
- **Edge compute device** (development: laptop with NVIDIA RTX 3050; production target: NVIDIA Jetson Nano or equivalent NPU-equipped embedded device). All ALPR inference runs locally on the edge node.
- **Arduino Nano microcontroller** acting as a hardware-isolated barrier controller, receiving binary OPEN/CLOSE commands over a 9600-baud serial link from the application layer. Hardware isolation is a safety requirement: a software fault or network event must not leave the barrier permanently open or dangerously actuating mid-transit. The physical serial air-gap ensures that barrier state is always under hardware-layer control.

---

## 4.3 ALPR Pipeline Design

The pipeline processes each video frame through four sequential stages, corresponding to FR-01:

**Stage 1 — Plate Detection.** A YOLOv8n model localises the licence plate bounding box within the full camera frame. The nano variant was selected for its inference speed on edge hardware without meaningful accuracy loss for the plate detection sub-task, which requires only bounding box localisation rather than fine-grained classification (Jocher et al., 2023). Detections with confidence below a configurable threshold (default: 0.70) are discarded to prevent low-quality crops from entering the character pipeline.

**Stage 2 — Contrast Enhancement.** The plate crop is converted from BGR to LAB colour space; CLAHE (clip limit 3.0, tile grid 8 × 8) is applied exclusively to the L (luminance) channel; the image is converted back to BGR. Applying CLAHE only to the luminance channel preserves colour information while correcting exposure, avoiding the saturation artefacts introduced by channel-wise RGB equalisation (Suleman et al., 2022). The clip limit of 3.0 was calibrated against CDL's night-gate scenario, where underexposure is the dominant failure mode.

**Stage 3 — Character Classification.** A second YOLOv8 model, trained on 37 character classes covering the Latin alphabet (A–Z), digits (0–9), and the Sri Lankan provincial prefix characters used in CDL's registered fleet, classifies individual character crops. Characters are sorted by horizontal bounding box position to reconstruct the plate string. The choice of a dedicated character-level YOLOv8 classifier over an end-to-end sequence model (CRNN/CTC) was made on accuracy grounds: CRNN architectures require large, consistently formatted sequence datasets, whereas the character-level classifier requires only individual character crops and generalises well across Sri Lanka's multi-format plate conventions (Safran et al., 2024).

**Stage 4 — LPM-MLED Post-Correction.** The raw classifier output is matched against all registered plates in the database using a weighted Levenshtein edit distance. Confusion-pair substitutions — {0, O}, {1, I}, {5, S}, {8, B} — are assigned a penalty cost of 0.1; all other substitutions cost 1.0. The raw distance is normalised by the length of the longer string, producing a value in [0.0, 1.0]. If the minimum normalised distance is below 0.5, the matched registered plate replaces the raw string. This approach, following Kechagias-Stamatis et al. (2022), recovers plates that the classifier misread on visually similar characters without introducing false acceptances.

---

## 4.4 Attendance Engine Design

The attendance engine (FR-02) evaluates each recognised plate against CDL's shift schedule. The design addresses three specific challenges from CDL's operational context:

- **Three-shift continuous operation.** Shifts are stored as records in the `shifts` table with start time, end time, permitted gates, and grace period minutes. The night shift (23:00–07:00) crosses the calendar day boundary; the engine compares event timestamps using modular time arithmetic rather than calendar-date comparison to correctly attribute night-shift entries made after midnight.
- **15-minute grace period.** Calibrated to the Port of Colombo external entry-queue processing time, the grace period prevents employees from receiving LATE_ARRIVAL penalties for delays caused by SLPA gate congestion outside CDL's control. The grace period is stored per-shift and is configurable without code changes.
- **Status classification.** Each ENTRY event is classified as ON_TIME_ENTRY, LATE_ARRIVAL, or NOT_IN_SHIFT. EXIT events are classified as EARLY_DEPARTURE, ON_TIME_EXIT, or OVERSTAY. Overstay detection uses a conditional UPDATE with a NOT EXISTS guard to prevent race conditions when multiple threads process simultaneous exit events for the same vehicle.

---

## 4.5 CDL Specialisation Layer Design

The CDL Specialisation Layer (`src/projects.py`) implements the three analytical requirements identified in §3.1 that elevate VAAS beyond a generic attendance logger:

**Zone Topology (`cdl_zones` table).** Each row encodes a named physical zone (e.g., DRYDOCK_1, BERTH_NORTH, WORKSHOP_ENGINEERING), its type (DRYDOCK, BERTH, WORKSHOP, ADMIN, SECURITY), a JSON list of the gate IDs serving it, and a vehicle capacity. Zone occupancy is computed dynamically by counting ENTRY events with no matching EXIT in the zone's associated gates — enabling the Drydock Manager to verify live contractor headcount without manual counting (FR-12).

**Vessel-Project Attribution (`projects`, `project_vehicle_assignments` tables).** Each project record carries a project code, vessel name, linked zone, start and end dates, status, and project manager. Vehicles are assigned to projects with a role (EMPLOYEE, SUBCONTRACTOR, SUPERVISOR, VISITOR) and, for subcontractor roles, a mandatory company ID. The `get_project_attendance_summary()` function returns, for each assigned vehicle over a specified date range, the count of distinct attendance days and total dwell hours — the direct computational input to CDL's per-project personal-vehicle fuel allowance calculation (FR-11, FR-07).

**Subcontractor Billing Audit (`subcontractor_companies` table).** Approved subcontractor firms are registered with company ID, name, contact details, and approval status (APPROVED, SUSPENDED, EXPIRED). The `get_subcontractor_hours()` function produces a per-project, per-vehicle breakdown of total gate-derived dwell hours for any company over a date range, enabling the Subcontractor Liaison to reconcile against the firm's submitted invoice.

---

## 4.6 Database Schema Design

The database uses SQLite in Write-Ahead Logging (WAL) mode, providing concurrent read access without blocking gate writes — critical when multiple gate nodes or dashboard users query simultaneously. SQLite was selected over PostgreSQL because the edge deployment model requires a zero-administration, file-based database engine that operates correctly on an embedded device without a server process; at CDL's single-site scale (fewer than ten gate nodes), SQLite WAL's practical concurrency ceiling is not a constraint (Rahman et al., 2023).

The schema comprises twelve tables across two logical groups: core tables (registered_vehicles, shifts, vehicle_shifts, vehicle_assignments, access_log, users, gate_rejections, admin_audit_log) and CDL Specialisation tables (cdl_zones, subcontractor_companies, projects, project_vehicle_assignments). The `access_log` table carries `zone_id` and `project_code` columns, enabling project and zone attribution at the point of event recording without requiring subsequent joins for the common-case analytics queries.

The SHA-256 audit chain (FR-06) is implemented via a two-step INSERT/UPDATE pattern: each row is inserted with a PENDING placeholder; the application retrieves the auto-assigned primary key and computes the final hash incorporating that key, plate number, timestamp, gate ID, direction, and the previous row's hash; the hash is written in a subsequent UPDATE. Including the primary key in the hash payload prevents row-reordering attacks, in which an adversary swaps two legitimate records to fabricate a different attendance sequence without altering any individual field value.

---

## 4.7 Web Interface and Security Design

The web interface (Flask, Jinja2, Bootstrap 5) provides three role-specific views:

- **Gate Operator (OPERATOR role):** Tablet-optimised single-screen tactical view comprising a live annotated camera feed, a recognition result panel showing vehicle registration status and project assignment, and an SSE-driven exception queue with one-tap Approve/Reject controls (FR-13). All interactive elements use minimum 48 × 48 pixel touch targets to accommodate gloved industrial operation.
- **Management dashboard (MANAGER role):** Zone occupancy cards, project attendance summary table, and access to all four report types (FR-07 through FR-09). Reports are not accessible to OPERATOR-role users.
- **Administration (ADMIN role):** Full user management, vehicle registration CRUD, shift configuration, and audit chain integrity verification.

Security design follows NIST SP 800-63B guidelines (Grassi et al., 2020): passwords are stored using bcrypt with a cost factor of 12; session timeout is set to eight hours, aligned with CDL's shift duration; all database queries use parameterised statements; and input is validated at the API boundary before any database write.
