# Chapter 3 — Requirements Analysis

Requirements were elicited through two primary methods: direct operational observation conducted during an internship at CDL (2024), and analysis of the CDL Finance Department's internal audit findings (CDL Internal Audit, Finance Department, 2023). The elicitation followed a stakeholder-driven approach in which each stakeholder group's operational need was identified before requirements were formalised, ensuring that no functional requirement exists without a traceable business justification.

---

## 3.1 Stakeholder Analysis

The following primary stakeholders were identified from CDL's operational structure:

| Stakeholder | Department | Primary Need | Key Risk Without System |
|---|---|---|---|
| Gate Security Operator | Security | Instant plate status; real-time exception alerts for unregistered vehicles | Manual queue bottlenecks at peak shift change; security gaps when verification abandoned |
| HR / Payroll Manager | Finance | Auditable per-vehicle attendance days and hours for personal-vehicle fuel allowance calculation | Unjustified allowance payments; unresolvable disputes (CDL Internal Audit, 2023) |
| Drydock / Project Manager | Vessel Project Management | Project-level vehicle attendance — which vehicles attended which drydock project and for how long | Inability to verify contractor headcount per project; no basis for project cost attribution |
| Subcontractor Liaison | Procurement | Gate-log-derived billing hours per approved subcontractor company | Invoice inflation; unapproved companies' vehicles admitted undetected |
| OHS Compliance Officer | Safety / HR | Per-vehicle compliance flags; driver–vehicle assignment records; ISO 45001 audit support | Unassigned vehicles on-site creating unattributable incident liability (Pawar et al., 2021) |
| Security Manager | Security | Gate rejection audit; overall gate event log | Post-incident inability to reconstruct vehicle movements |
| System Administrator | IT | CRUD audit trail; user account management; system integrity verification | Insider tampering with attendance records; unaccountable privilege escalation |
| External Auditor | Finance / Regulatory | SHA-256 hash chain integrity; complete admin change log | Retrospective data manipulation invalidating payroll evidence |

---

## 3.2 Functional Requirements

Functional requirements are presented using MoSCoW prioritisation. Requirements classified as Must represent the minimum viable system for CDL's stated business objective; Should requirements represent CDL-specific analytical value that directly informed the scope expansion directed by the project supervisor.

| ID | Requirement | Priority | Source Stakeholder |
|---|---|---|---|
| FR-01 | ALPR pipeline: detect and crop plate region from live video; apply CLAHE contrast enhancement; classify characters via a 37-class Sri Lankan plate model; apply LPM-MLED weighted post-correction against the registered vehicle database; achieve ≥ 90% end-to-end accuracy. | Must | Gate Operator |
| FR-02 | Shift-aware attendance engine: record ENTRY and EXIT events; compute dwell time in seconds; classify each event as ON_TIME_ENTRY, LATE_ARRIVAL, EARLY_DEPARTURE, OVERSTAY, NOT_IN_SHIFT, or VISITOR; enforce CDL's three-shift schedule (07:00–15:00, 15:00–23:00, 23:00–07:00) with a configurable 15-minute grace period. | Must | HR Manager, Drydock Manager |
| FR-03 | Exception workflow: classify unregistered plates as UNKNOWN; push a real-time SSE alert (< 200 ms) to the gate operator dashboard showing plate crop image, best-match candidate, and confidence score; record operator disposition (Approve as Visitor / Reject) with timestamp. | Must | Gate Operator, Security Manager |
| FR-04 | Vehicle registration and categorisation: maintain a registered vehicle database with category (STAFF, CONTRACTOR, MANAGEMENT, FLEET, VISITOR, EMERGENCY, MAINTENANCE), vehicle type (CAR, VAN, TRUCK, MOTORCYCLE, UTILITY), registration status (ACTIVE, SUSPENDED, EXPIRED), contractor name, department, and company assignment. | Must | HR Manager, Gate Operator |
| FR-05 | Driver–vehicle assignment: many-to-many assignment table linking drivers (users) to vehicles with an is_active flag, assigned_at timestamp, and full assignment history; supports OHS incident attribution and payroll reconciliation. | Must | OHS Officer, HR Manager |
| FR-06 | SHA-256 tamper-evident audit chain: each access_log row hashes plate number, timestamp, gate ID, direction of travel, previous row hash, and row primary key; chain integrity verifiable on demand; any modified or reordered row produces a detectable hash mismatch. | Must | Auditor, HR Manager |
| FR-07 | Personal-vehicle allowance report: per-driver summary of attendance days, total dwell hours, compliance rate (on-time entries as a proportion of total entries), and per-project attendance days; exportable as CSV and PDF; primary financial output of the system. | Must | HR Manager |
| FR-08 | OHS compliance report: per-vehicle risk classification (UNASSIGNED, SUSPENDED, EXPIRED, HIGH_OVERSTAY, OK); sorted with non-compliant vehicles first; supports ISO 45001 audit evidence requirements (Pawar et al., 2021). | Must | OHS Officer |
| FR-09 | Gate rejection audit report: complete log of denied or flagged gate events with reason code, plate string, timestamp, gate ID, and confidence score; filterable by date range. | Must | Security Manager |
| FR-10 | Administrative audit log: records every CREATE, UPDATE, DELETE, and ASSIGN operation performed by any user, with username, timestamp, affected entity, and a JSON delta of changed values; immutable to all non-admin roles. | Must | System Administrator, Auditor |
| FR-11 | CDL project management: create and close vessel–drydock projects; assign registered vehicles to projects with role (EMPLOYEE, SUBCONTRACTOR, SUPERVISOR, VISITOR) and optional subcontractor company link; generate attendance summary per project per date range (days present and total dwell hours per vehicle) as direct input to the personal-vehicle allowance calculation. | Must | Drydock Manager, Subcontractor Liaison |
| FR-12 | Zone management: define and maintain CDL's physical zone topology (DRYDOCK, BERTH, WORKSHOP, ADMIN, SECURITY) with associated gate IDs and vehicle capacity; compute real-time zone occupancy from unpaired ENTRY events. | Should | Drydock Manager |
| FR-13 | Live gate operator dashboard: real-time annotated camera feed with YOLOv8 bounding box overlays; SSE-driven exception queue with one-tap Approve / Reject controls; current shift status indicator; active vehicle count per zone; tablet-optimised layout for gate security post use. | Must | Gate Operator |

---

## 3.3 Non-Functional Requirements

| ID | Quality Attribute | Requirement | Justification |
|---|---|---|---|
| NFR-01 | Performance | Gate event processing latency ≤ 500 ms at p95 | Peak throughput of 200+ vehicles per 30 minutes requires sub-second gate response to prevent queue formation |
| NFR-02 | Accuracy | End-to-end plate recognition ≥ 90% | Below this threshold, the manual exception rate exceeds what a single gate operator can process during peak windows |
| NFR-03 | Privacy | Plate-crop image retention ≤ 90 days | Alignment with Sri Lanka Personal Data Protection Act No. 9 of 2022 (PDPA, 2022) data minimisation requirements |
| NFR-04 | Availability | System availability ≥ 99.5% during CDL shift hours | CDL operates 24/7 continuously; gate downtime has immediate operational cost |
| NFR-05 | Concurrency | Web dashboard supports ≥ 5 simultaneous authenticated users | CDL operational control room configuration; multiple managers may run reports concurrently |
| NFR-06 | Recoverability | SQLite WAL mode with automated daily backup | Ensures CDL attendance records are recoverable after hardware failure without data loss |
| NFR-07 | Security | Role-based access control with three roles: ADMIN, MANAGER, OPERATOR | Separation of duties: gate operators must not access payroll reports; managers must not modify audit logs |

---

## 3.4 Requirements Scope and Boundaries

The system was scoped to the CDL main security gate as a single-site deployment. The following items were explicitly excluded from scope following supervisor review:

- **Multi-gate spatial verification** (proposed in the original PID): rejected as adding architectural complexity without serving the primary attendance objective
- **Biometric or card-based secondary authentication**: RFID is the system being replaced, not augmented
- **SLPA customs integration and weighbridge interfacing**: identified as valid future extensions (Section 7.3) but beyond the scope of a single academic project cycle
