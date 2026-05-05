# Chapter 2 — Literature Review

This chapter examines existing research across three domains directly relevant to the design of VAAS: the failure of RFID-based attendance systems in electromagnetically congested environments; the state of the art in Automatic Licence Plate Recognition; and approaches to vehicle attendance management and audit integrity in industrial settings. The review is structured to trace the gap that VAAS was designed to fill.

---

## 2.1 RFID Reliability in Industrial Environments

RFID technology has been widely adopted for access control and attendance verification in industrial facilities due to its low unit cost and contactless operation. However, reliability in electromagnetically dense environments has been a persistent concern. Knapp and Uckelmann (2022) conducted a systematic review of RFID interference sources in complex logistics and production environments, identifying three categories of failure: (i) metallic infrastructure causing multipath signal reflections that reduce read reliability; (ii) high-power industrial machinery generating broadband RF noise that masks tag responses; and (iii) adjacent RF systems operating on overlapping or harmonically related frequency bands. In port and harbour environments — where multiple independent operators run access control, cargo tracking, and vessel identification systems on the same industrial UHF bands (860–960 MHz) — the third failure mode is particularly acute. Rezaie et al. (2023) demonstrated that even with TDMA-based anti-collision protocols, simultaneous reader activation in dense environments generates reader-to-reader interference that no software-layer mitigation can fully resolve without a coordinated spectrum management agreement between the independent operators — an agreement that is organisationally infeasible in mixed-authority port environments.

Beyond technical degradation, RFID systems carry a structural vulnerability: they authenticate the credential token, not the physical object it is assigned to. This distinction enables proxy attendance fraud, in which a credential holder triggers the system without the associated vehicle being present. In industrial settings where RFID failure rates have already eroded stakeholder confidence in the system's accuracy, proxy fraud is particularly difficult to detect because fraudulent scans are statistically indistinguishable from legitimate hardware-induced false positives. The consequence is a compounding failure: unreliable hardware creates noise, and noise provides cover for deliberate exploitation.

---

## 2.2 Automatic Licence Plate Recognition

### 2.2.1 Deep Learning Pipeline Architecture

The evolution of ALPR has followed the broader trajectory of object detection research. Single-stage detection architectures — and specifically the YOLO family — have become the dominant approach for real-time plate detection due to their favourable accuracy-to-latency trade-off on edge hardware (Jocher et al., 2023). Al-Dabbagh et al. (2024) demonstrated that integrating YOLOv8 with an OCR post-processing stage achieves high-precision identification under variable real-world conditions, validating the two-stage (detect → recognise) pipeline architecture. Sabir et al. (2023) evaluated YOLOv8 on licence plate detection tasks and reported a mean Average Precision at IoU 0.5 of 94.7 percent, confirming its suitability for gate deployment where detection speed and robustness are both critical. Safran et al. (2024) found that a multistage pipeline combining YOLOv8 plate detection with a CNN character recognition module outperformed single-stage end-to-end approaches, achieving an overall accuracy of 96.1 percent versus 83.9 percent.

### 2.2.2 Image Preprocessing for Difficult Conditions

Industrial gate environments introduce extreme lighting variability: direct tropical sunlight, shadow transitions between structures, and artificial lighting during night shifts. Raw plate crops from these conditions exhibit overexposed highlights and underexposed shadow regions that degrade character classifier performance. Suleman et al. (2022) demonstrated that applying Contrast Limited Adaptive Histogram Equalisation (CLAHE) exclusively to the luminance channel of the LAB colour space — rather than to all channels or to the RGB space — produces an 8.4 percentage-point improvement in recognition accuracy on underexposed and overexposed plate crops, while avoiding the colour saturation artefacts introduced by global histogram equalisation. The LAB-based CLAHE approach has since been validated across multiple ALPR studies as the preferred preprocessing step for adverse lighting scenarios (Al-Dabbagh et al., 2024).

### 2.2.3 Post-Correction for Regional Plate Conventions

Even high-accuracy character classifiers produce errors on visually confusable character pairs — a problem that is more severe for Sri Lankan plates, which use a non-standard alphanumeric format combining provincial prefix codes with numeric sequences, and which exhibit font inconsistencies across manufacturing batches and plate generations. Kechagias-Stamatis et al. (2022) proposed an edit-distance post-correction approach in which raw classifier output is matched against a registered plate database using a weighted Levenshtein distance, where confusion-pair substitutions — character pairs with high visual similarity — are assigned a reduced penalty cost. This approach recovered a significant proportion of plates that the classifier had misread, without introducing false acceptances, because the weighted distance penalises non-confusion substitutions heavily. The approach is particularly relevant for Sri Lankan plates, where pairs such as {0, O}, {1, I}, {5, S}, and {8, B} appear frequently in provincial codes and serial numbers and are the primary source of classifier error.

---

## 2.3 Vehicle Attendance and Industrial Workforce Management

### 2.3.1 Shift-Based Attendance Systems

Shift-based industrial facilities impose attendance tracking requirements that generic time-and-attendance platforms do not address. Rahman et al. (2023) identified that accurate dwell-time computation — the interval between a recorded ENTRY event and a corresponding EXIT event — is foundational to fair payroll calculation in shift-structured environments, and that systems which record only arrival without capturing departure produce systematically biased compliance rates. The study further noted that grace-period logic — allowable lateness windows calibrated to the operational context — is a critical parameter for employee acceptance of automated systems, particularly where external factors outside the employee's control (such as traffic congestion on access roads) create unavoidable variance in arrival times.

### 2.3.2 Vehicle-Based Attendance in Heavy Industry

Pawar et al. (2021) examined fleet and vehicle management in heavy industrial contexts, observing that vehicle-borne workers create an attendance verification requirement fundamentally different from pedestrian employees: the vehicle, rather than the person, is the operational unit that must be tracked, assigned to specific work zones, and reconciled against project billing records. The study identified that the absence of vehicle-to-project attribution — the inability to link a vehicle's on-site presence to a specific work contract — is the principal cause of subcontractor billing disputes in facilities with concurrent multi-project operations.

### 2.3.3 Audit Integrity for Payroll Data

Attendance records that directly determine financial disbursements — fuel allowances, payroll claims, subcontractor invoices — are high-value targets for retrospective manipulation by privileged system users. Traditional relational databases provide no inherent tamper evidence: a record can be deleted, modified, or reordered without leaving a detectable trace. Hash-chaining — in which each record's cryptographic hash incorporates the hash of the immediately preceding record — provides a computationally inexpensive and architecturally simple tamper-evidence mechanism that does not require a distributed ledger or external timestamp authority (Mykletun et al., 2021). Any modification to a historical record invalidates the hash of every subsequent record, making retrospective tampering algorithmically detectable during a routine integrity verification pass. For attendance systems used as the basis of payroll calculation, this property transforms the audit log from a passive record into an active evidentiary instrument.

---

## 2.4 Summary and Identified Gap

The literature establishes that RFID is structurally unreliable for vehicle attendance in electromagnetically congested port environments, and that ALPR using YOLOv8 with CLAHE preprocessing and weighted post-correction achieves the accuracy and latency required for industrial gate deployment. However, existing ALPR research focuses primarily on traffic management and law enforcement applications; there is limited published work on deploying ALPR as a payroll-grade vehicle attendance system, and no published work specifically addressing Sri Lankan plate conventions, multi-project vessel-drydock attribution, or shift-based attendance analytics in a maritime industrial context. VAAS was designed to address these gaps in the specific operational context of Colombo Dockyard PLC.
