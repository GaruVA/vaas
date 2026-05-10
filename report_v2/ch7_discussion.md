# Chapter 7 — Discussion

## 7.1 Achievement Against Objectives

The five objectives stated in §1.3 were each addressed:

- **O1 — Build an ALPR pipeline capable of reading Sri Lankan plates under CDL's gate conditions.** Achieved. The pipeline achieved 91.3% end-to-end accuracy across four lighting conditions, with a 95th-percentile latency of 294 ms — well within the 500 ms operational budget. The LPM-MLED post-correction step was the decisive factor in closing the gap between raw character classifier output (approximately 83%) and the reported figure; without confusion-pair correction, 8.3% of recognitions that were correctable remained as raw misreads.

- **O2 — Implement a shift-aware attendance engine calibrated to CDL's three-shift schedule.** Achieved. The midnight boundary handling, configurable grace period, and full thirteen-status classification set cover CDL's documented attendance scenarios. The NOT EXISTS overstay guard, identified as necessary only during load testing, demonstrates that the engine is robust under the concurrent gate-event throughput CDL experiences at shift-change peaks (200+ vehicles in 30 minutes).

- **O3 — Provide a CDL-contextualised analytics layer producing actionable reports for management and finance.** Achieved. The personal-vehicle allowance report (FR-07) directly satisfies the original business requirement from CDL's Finance Department. The OHS compliance report, subcontractor billing audit, and gate rejection audit each serve a named CDL stakeholder and are exportable to PDF for submission to CDL's relevant department heads.

- **O4 — Implement a tamper-evident audit chain suitable for payroll dispute resolution.** Achieved. The SHA-256 hash chain withstands both field-value tampering and row-reordering attacks, as confirmed by the audit unit tests. The two-step INSERT/UPDATE pattern ensures that the database-assigned primary key is bound into every hash, eliminating the reordering attack vector that was absent from the initial design.

- **O5 — Deliver a multi-role web dashboard operable by gate security staff on tablet hardware.** Achieved. The Operator dashboard was designed with 48 × 48 px minimum touch targets and a single-screen tactical layout. The three-role RBAC system prevents gate operators from accessing financial reports, maintaining information compartmentalisation consistent with CDL's security classification requirements.

---

## 7.2 Limitations

**Hardware dependency.** The 294 ms latency figure was measured on development hardware (NVIDIA RTX 3050). The production target — an NVIDIA Jetson Nano or equivalent NPU-embedded device — offers significantly lower GPU throughput. Benchmarking on the production hardware was not possible within the project timeline; the latency margin (41% against the 500 ms budget) provides a reasonable buffer, but field validation on the actual gate node is required before operational deployment.

**Dataset scope.** The 2,400-image training dataset was assembled under CDL's gate conditions but does not represent the full range of plate condition degradation encountered over multi-year operation: paint fade, plate warping from vehicle incidents, and aftermarket plate fonts are underrepresented. The 91.3% end-to-end accuracy should be treated as a best-case figure for newly registered vehicles under CDL's current gate setup, not a guaranteed operational floor.

**Single-site SQLite.** SQLite WAL was selected for its zero-administration edge deployment characteristics. If CDL expands VAAS to a multi-gate, multi-site topology — for example, integrating the DGES or DTS subsidiary facilities — the current single-file database model would require migration to a client-server engine (PostgreSQL or MariaDB) and the ALPR processing architecture would need to be distributed. The application layer is designed with this transition in mind (all database access is mediated through the `transaction()` context manager), but the migration itself is a non-trivial undertaking.

**Driver self-service absent.** In the current system, employees have no mechanism to review their own attendance records or fuel allowance accrual. All attendance disputes must be raised through HR, who query the Manager dashboard on the employee's behalf. A read-only driver portal — accessible via employee number and a registered vehicle plate — would reduce HR administrative burden and is a natural next iteration.

---

## 7.3 Comparison with Related Work

Al-Dabbagh et al. (2024) reported 92.4% accuracy on an Iraqi ALPR dataset using a YOLOv8+OCR pipeline without post-correction. VAAS achieves 91.3% on Sri Lankan plates with LPM-MLED post-correction applied; without post-correction the comparable figure is approximately 83%, confirming that confusion-pair correction is essential for Sri Lanka's character set and is not fully compensated by the base classifier. Safran et al. (2024) demonstrated that character-level YOLOv8 classifiers generalise better than CRNN/CTC models on multi-format plate datasets — an observation directly confirmed by the character classifier's performance across CDL's three-generation plate convention range. The SHA-256 hash-chain approach follows Mykletun et al. (2021), who demonstrate that append-only hash chains are computationally sufficient for audit log integrity in operational environments where full cryptographic non-repudiation is not required.
