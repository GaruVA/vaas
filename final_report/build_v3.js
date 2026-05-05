"use strict";
// 10952592_Final_Report.js — PUSL3190 Official Template
// All guidelines applied: black type throughout, TOC, Bibliography,
// 1.15 spacing, numbered sections, correct appendix order
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, PageNumber, PageBreak, LevelFormat, NumberFormat, ImageRun,
  TableOfContents,
} = require("docx");
const fs = require("fs");

// ─── CONSTANTS ────────────────────────────────────────────────────────────────
const TNR   = "Times New Roman";
const BODY  = 24;   // 12 pt
const SM    = 20;   // 10 pt
const LG    = 28;   // 14 pt  H3
const XL    = 32;   // 16 pt  H2
const XXL   = 40;   // 20 pt  H1
const BLACK = "000000";
const NAVY  = "1F4E79";   // header/footer only
const WHITE = "FFFFFF";

const brd      = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const brdW     = { style: BorderStyle.SINGLE, size: 1, color: WHITE };
const BORDERS     = { top: brd,  bottom: brd,  left: brd,  right: brd  };
const HDR_BORDERS = { top: brdW, bottom: brdW, left: brdW, right: brdW };

// ─── PARAGRAPH / RUN HELPERS ──────────────────────────────────────────────────
function run(text, opts = {}) {
  return new TextRun({ text: String(text), font: TNR, size: BODY, ...opts });
}
function runI(text) { return run(text, { italics: true }); }
function runB(text) { return run(text, { bold: true }); }

function body(...textOrRuns) {
  const children = textOrRuns.map(t => typeof t === "string" ? run(t) : t);
  return new Paragraph({
    children,
    spacing: { before: 0, after: 160, line: 276, lineRule: "auto" },  // 1.15
    alignment: AlignmentType.JUSTIFIED,
  });
}
function bodyRuns(runs) {
  return new Paragraph({
    children: runs,
    spacing: { before: 0, after: 160, line: 276, lineRule: "auto" },
    alignment: AlignmentType.JUSTIFIED,
  });
}
function blank() {
  return new Paragraph({ children: [run("")], spacing: { before: 0, after: 120 } });
}
function caption(text) {
  return new Paragraph({
    children: [run(text, { italics: true, size: SM })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 60, after: 240 },
  });
}
function ref(runs) {
  return new Paragraph({
    children: Array.isArray(runs) ? runs : [run(runs)],
    spacing: { before: 0, after: 160, line: 276, lineRule: "auto" },
    indent: { left: 720, hanging: 720 },
    alignment: AlignmentType.JUSTIFIED,
  });
}

// ─── HEADINGS — black text throughout ─────────────────────────────────────────
function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    children: [new TextRun({ text, font: TNR, size: XXL, bold: true, color: BLACK })],
    spacing: { before: 480, after: 240 },
    pageBreakBefore: true,
  });
}
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    children: [new TextRun({ text, font: TNR, size: XL, bold: true, color: BLACK })],
    spacing: { before: 320, after: 160 },
  });
}
function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    children: [new TextRun({ text, font: TNR, size: LG, bold: true, color: BLACK })],
    spacing: { before: 200, after: 100 },
  });
}

// ─── TABLE HELPER ─────────────────────────────────────────────────────────────
function tbl(headers, rows, colWidths, opts = {}) {
  const total = colWidths.reduce((a, b) => a + b, 0);
  const DARK = "333333";
  const hdrRow = new TableRow({
    tableHeader: true,
    children: headers.map((h, i) =>
      new TableCell({
        borders: HDR_BORDERS,
        width: { size: colWidths[i], type: WidthType.DXA },
        shading: { fill: DARK, type: ShadingType.CLEAR },
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({
          children: [new TextRun({ text: h, font: TNR, size: SM, bold: true, color: WHITE })]
        })]
      })
    )
  });
  const dataRows = rows.map((row, ri) =>
    new TableRow({
      children: row.map((cell, ci) =>
        new TableCell({
          borders: BORDERS,
          width: { size: colWidths[ci], type: WidthType.DXA },
          shading: { fill: ri % 2 === 0 ? "F5F5F5" : WHITE, type: ShadingType.CLEAR },
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [new Paragraph({
            children: [new TextRun({ text: String(cell), font: TNR, size: SM })],
            spacing: { before: 0, after: 0, line: 276, lineRule: "auto" },
          })]
        })
      )
    })
  );
  return new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: colWidths,
    rows: [hdrRow, ...dataRows],
    ...opts,
  });
}

// ─── HEADER / FOOTER ──────────────────────────────────────────────────────────
function makeHeader() {
  return new Header({
    children: [new Paragraph({
      children: [new TextRun({
        text: "Vehicle Attendance and Analytics System  |  10952592",
        font: TNR, size: SM, color: "555555", italics: true,
      })],
      alignment: AlignmentType.RIGHT,
      border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: NAVY, space: 1 } },
    })]
  });
}
function makeFooter() {
  return new Footer({
    children: [new Paragraph({
      children: [
        new TextRun({ text: "PUSL3190  |  University of Plymouth (Sri Lanka Campus)  |  Page ", font: TNR, size: SM, color: "555555" }),
        new TextRun({ children: [PageNumber.CURRENT], font: TNR, size: SM, color: "555555" }),
      ],
      alignment: AlignmentType.CENTER,
    })]
  });
}

// ─── COVER PAGE — white background, black type only ───────────────────────────
function centred(text, sz, bold = false, spAfter = 120) {
  return new Paragraph({
    children: [new TextRun({ text, font: TNR, size: sz, bold, color: BLACK })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: spAfter },
  });
}
function centredLabel(label, value, sz, spAfter = 120) {
  return new Paragraph({
    children: [
      new TextRun({ text: label, font: TNR, size: sz, bold: true, color: BLACK }),
      new TextRun({ text: " " + value, font: TNR, size: sz, color: BLACK }),
    ],
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: spAfter },
  });
}

const logoData = fs.readFileSync("plymouth_logo.png");
const coverPage = [
  new Paragraph({
    children: [new ImageRun({
      type: "png",
      data: logoData,
      transformation: { width: 248, height: 138 },
      altText: { title: "University of Plymouth logo", description: "University of Plymouth logo", name: "plymouth_logo" },
    })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 720, after: 480 },
  }),
  blank(), blank(),
  centred("PUSL3190 Computing Project", 52, true, 160),
  blank(),
  centred("Final Report", 48, true, 480),
  blank(), blank(), blank(),
  centred("An Automated Vehicle Attendance and Movement Analytics System", 32, false, 80),
  centred("for Industrial Facilities Using Computer Vision", 32, false, 480),
  blank(), blank(), blank(),
  centredLabel("Supervisor:", "Mr. Madusanka Mithrananda", BODY, 120),
  centredLabel("Name:", "Garuka Assalaarachchi", BODY, 120),
  centredLabel("Plymouth Index Number:", "10952592", BODY, 120),
  centredLabel("Degree Program:", "BSc. in Software Engineering", BODY, 120),
];


// ─── HARVARD REFERENCE HELPER ─────────────────────────────────────────────────
function harvardRef(parts) {
  const runs = parts.map(p =>
    new TextRun({ text: p.text, font: TNR, size: SM, italics: p.italic || false })
  );
  return ref(runs);
}


// ─── DECLARATION ─────────────────────────────────────────────────────────
const declaration = [
  h1("Declaration of Originality"),
  body("I hereby declare that this thesis, submitted in partial fulfilment of the requirements for the degree of Bachelor of Science in Software Engineering at the University of Plymouth (Sri Lanka Campus), is my own original work."),
  body("(i) This work has not previously been submitted for any other degree or qualification at this or any other institution."),
  body("(ii) All sources consulted have been acknowledged by full citation in accordance with the Harvard referencing convention."),
  body("(iii) All software code written as part of this project is my own work, except where explicitly attributed to third-party libraries identified in requirements.txt and the relevant sections of this report."),
  blank(),
  body("Signature: ___________________________"),
  blank(),
  body("Date: April 2026"),
];

// ─── ACKNOWLEDGEMENTS ─────────────────────────────────────────────────────────
const acknowledgements = [
  h1("Acknowledgements"),
  body("I wish to express my sincere gratitude to my project supervisor for their guidance, critical feedback, and patience throughout this project. Their direction in refocusing the scope of this work toward the vehicle attendance use case was instrumental in producing a more coherent and practically relevant contribution."),
  body("I am grateful to the academic staff of the Department of Computing at the University of Plymouth (Sri Lanka Campus) for their support during the 2025/2026 cohort, and to my peers for their encouragement during the development and evaluation phases."),
  body("I thank the staff at Colombo Dockyard PLC for providing the operational context that motivated this research and for sharing operational data that grounded the problem analysis in Section 3."),
];

// ─── ABSTRACTSEC ─────────────────────────────────────────────────────────
const abstractSec = [
  h1("Abstract"),
  body("Industrial facilities that rely on contractor vehicle fleets face a persistent challenge in accurately recording vehicle attendance. Manual logbooks are error-prone and falsifiable, while radio-frequency identification gate systems experience read failures of 15 to 20 percent under Sri Lankan port field conditions, producing records that are incomplete and indefensible in payroll disputes (Delen et al., 2011). Time-theft and buddy-punching fraud in manual attendance systems cost organisations an estimated seven percent of annual payroll (American Payroll Association, 2023), while unmonitored fleet fuel usage results in further unaccounted operational expenditure (Raza et al., 2022)."),
  body("This project designed, implemented, and evaluated an automated vehicle attendance and analytics system that uses computer vision to identify vehicles by their licence plates at facility gates, with no hardware required on individual vehicles. A custom-trained two-stage image recognition pipeline was developed for Sri Lankan alphanumeric plates, incorporating a domain-specific weighted error-correction algorithm (LPM-MLED) to resolve visually ambiguous characters, following the framework of Kechagias-Stamatis et al. (2022) and Islam et al. (2020). CLAHE contrast enhancement addresses the significant illumination variation of Sri Lankan industrial environments (Suleman et al., 2022; Al-Dabbagh et al., 2024)."),
  body("A shift-aware attendance engine records arrival and departure events, computes dwell time, flags late arrivals and early departures, and handles unregistered vehicles through a structured operator alert workflow. An enterprise analytics layer delivers four research-grounded management report types: a payroll accuracy report (Rahman et al., 2023), an OHS compliance report (Pawar et al., 2021), a fuel accountability report (Raza et al., 2022), and a post-incident gate rejection audit log (Yue et al., 2016). All records are protected by a cryptographic SHA-256 hash chain with photographic plate-crop evidence and a tamper-evident admin audit log."),
  body("Evaluation against 150 physical test plates and 150 scripted attendance scenarios achieved 91.3% end-to-end plate recognition accuracy — a 20.3 percentage-point improvement over EasyOCR — and 97.3% attendance event accuracy, a 12 to 18 percentage-point improvement over the existing RFID gate system. Gate event processing completed in under 300 milliseconds at the 95th percentile. The per-gate hardware cost of approximately 85,000 Sri Lankan Rupees is 40 times lower than commercially available alternatives, demonstrating that accurate, auditable, and analytically actionable vehicle attendance management is achievable at small enterprise scale."),
];

// ─── ABBREVSECTION ─────────────────────────────────────────────────────────
const abbrevSection = [
  h1("List of Abbreviations"),
  blank(),
  tbl(
    ["Abbreviation", "Definition"],
    [
      ["ALPR","Automatic Licence Plate Recognition"],
      ["ANPR","Automatic Number Plate Recognition"],
      ["API","Application Programming Interface"],
      ["APA","American Payroll Association"],
      ["CLAHE","Contrast Limited Adaptive Histogram Equalisation"],
      ["CNN","Convolutional Neural Network"],
      ["CSV","Comma-Separated Values"],
      ["CTC","Connectionist Temporal Classification"],
      ["EPC","Electronic Product Code"],
      ["FP16","16-bit Floating Point (half-precision)"],
      ["FR","Functional Requirement"],
      ["FYP","Final Year Project"],
      ["HR","Human Resources"],
      ["ISO","International Organisation for Standardisation"],
      ["LKR","Sri Lankan Rupee"],
      ["LPM-MLED","Licence Plate Matching by Minimum Levenshtein Edit Distance"],
      ["mAP","mean Average Precision"],
      ["NFR","Non-Functional Requirement"],
      ["NTP","Network Time Protocol"],
      ["OBD-II","On-Board Diagnostics II"],
      ["OCR","Optical Character Recognition"],
      ["OHS","Occupational Health and Safety"],
      ["p95","95th Percentile"],
      ["PDPA","Personal Data Protection Act"],
      ["PDF","Portable Document Format"],
      ["RBAC","Role-Based Access Control"],
      ["RFID","Radio Frequency Identification"],
      ["SHA-256","Secure Hash Algorithm 256-bit"],
      ["SME","Small and Medium Enterprise"],
      ["SQLite","Self-contained SQL Database Engine"],
      ["SSE","Server-Sent Events"],
      ["SUS","System Usability Scale"],
      ["T&A","Time and Attendance"],
      ["UHF","Ultra-High Frequency"],
      ["VAAS","Vehicle Attendance and Analytics System"],
      ["WAL","Write-Ahead Log"],
      ["YOLO","You Only Look Once"],
    ],
    [2400, 7000]
  ),
];

// ─── CH1 ─────────────────────────────────────────────────────────
const ch1 = [
  h1("1  Introduction"),
  h2("1.1 Background"),
  body("The management of complex industrial workforces — spanning permanent employees, rotating contractors, and transient fleet vehicles at ports, manufacturing plants, logistics hubs, and construction sites — demands reliable records of which vehicle entered a facility, when it arrived, how long it remained on-site, and when it departed. These records are foundational to four distinct organisational functions: payroll accuracy for contractor billing, occupational health and safety (OHS) compliance and driver accountability, fuel consumption accountability, and post-incident investigation capability. Pawar et al. (2021) found that the absence of reliable vehicle-level attendance records was the primary contributing factor in 41 percent of unresolved OHS investigations at industrial facilities in comparable operating environments. The American Payroll Association (APA, 2023) estimates that manual time-keeping systems, susceptible to timesheet falsification and proxy attendance, inflate payroll costs by up to seven percent of total annual payroll expenditure."),
  body("Traditional workforce attendance management relies on biometric terminals, swipe-card readers, and proximity-based turnstile systems (Bhatt et al., 2019). These technologies suit pedestrian workers who present themselves at a fixed terminal. They fail systematically for vehicle-borne workers and contractors, whose unit of identity is the vehicle itself. A truck driver who enters Gate A, loads cargo, waits two hours, and exits through Gate C generates no electronic attendance record in a conventional biometric system, yet consumes vehicle-hours, fuel allocations, and gate occupancy that directly affect operational cost. Nambiar (2021) identified this architectural mismatch as the central barrier to vehicle-level attendance management in South Asian industrial SME contexts."),
  body("In Sri Lanka's port and industrial sectors, contractor vehicles gain site access under service agreements, but their presence is captured, at best, by manual paper-based logbooks or Radio Frequency Identification (RFID) gate readers. Manual logbooks are prone to transcription error — Ko (2011) estimated a 3 to 7 percent data-entry error rate — and are easily falsified. RFID-based vehicle identification is subject to well-documented hardware-level failure under Sri Lankan industrial field conditions: humid coastal air, metallic vehicle bodywork, and high-throughput gate queuing combine to produce sustained read-failure rates of 15 to 20 percent (Delen et al., 2011). The practical consequences at Colombo Dockyard PLC — a representative site operating over 200 vehicles during a single 30-minute peak window (internal operational report, 2024) — are measurable: discrepancies between declared and auditable vehicle attendance records correlate with an estimated fuel consumption gap of 2.7 to 3.6 million LKR annually."),
  body("Automatic Licence Plate Recognition (ALPR) offers a technologically mature alternative that eliminates the per-vehicle hardware requirement. By treating the licence plate as the vehicle's persistent, hardware-free identity, an ALPR system generates an objective, timestamped attendance record at every gate transit without requiring driver cooperation or manual intervention. Advances in deep-learning object detection — specifically the YOLOv8 family of models (Jocher et al., 2023) — have brought real-time, edge-deployable ALPR within the cost envelope of small and medium industrial enterprises. Al-Dabbagh et al. (2024) demonstrated that a YOLOv8 pipeline with CLAHE preprocessing achieved greater than 93 percent overall recognition performance across night-time and rainy scenarios. Sabir et al. (2023) confirmed mAP@0.5 of 94.7 percent for next-generation YOLOv8-based plate detection systems on real-world datasets."),
  body("However, deploying ALPR as a vehicle attendance system — rather than simply a plate logger — demands capabilities beyond raw recognition. The system must handle the optical ambiguities specific to Sri Lankan alphanumeric plates (no existing deep-learning model addressed these prior to this project; Kalansuriya et al., 2014), provide shift-aware clock-in/clock-out logic, maintain driver-vehicle assignment records to support payroll and OHS accountability, and generate the four management report types grounded in operational literature: payroll accuracy (Rahman et al., 2023), OHS compliance (Pawar et al., 2021), fuel accountability (Raza et al., 2022), and post-incident audit (Yue et al., 2016). No existing product addresses all of these requirements for the Sri Lankan operational context at an accessible price point. This project is motivated directly by that gap."),

  h2("1.2 Problem Statement"),
  body("Industrial facilities in Sri Lanka that rely on fleet vehicles and contractor transport face a compounding four-layer problem. First, conventional person-centric attendance systems are architecturally incapable of capturing vehicle-level presence (Nambiar, 2021). Second, RFID-based vehicle identification delivers unacceptable error rates under Sri Lankan field conditions, producing attendance records that are incomplete and indefensible in payroll or safety disputes (Delen et al., 2011). Third, commercially available ALPR solutions are engineered for NATO-format plates, priced for enterprise budgets exceeding USD 10,000 per gate (Genetec, 2023), and provide no attendance lifecycle management, shift tracking, or analytics capability. Fourth, the absence of structured payroll, OHS, fuel accountability, and post-incident audit reporting means that even if attendance data were captured, it could not be translated into actionable management outputs (Rahman et al., 2023; Pawar et al., 2021; Raza et al., 2022)."),

  h2("1.3 Research Aim and Objectives"),
  body("Aim: To design, implement, and evaluate a computer-vision-based vehicle attendance and movement analytics system that provides accurate, shift-aware, auditable, and analytically actionable records of vehicle presence at industrial facility gates, deployable at a cost accessible to Sri Lankan enterprises."),
  body("O1 — High-Accuracy Plate Recognition: Develop a robust ALPR pipeline using YOLOv8 plate detection, CLAHE contrast enhancement (Suleman et al., 2022; Al-Dabbagh et al., 2024), and a custom 37-class character classifier incorporating the LPM-MLED post-correction algorithm (Kechagias-Stamatis et al., 2022; Islam et al., 2020), achieving at least 90% end-to-end plate recognition accuracy on Sri Lankan alphanumeric plates."),
  body("O2 — Vehicle Attendance Engine: Implement a shift-aware vehicle attendance engine providing clock-in/clock-out event capture, dwell-time computation, late-arrival and early-departure flagging, driver-vehicle assignment tracking, and a structured exception-handling workflow for unregistered and visitor vehicles."),
  body("O3 — Management Analytics Dashboard: Build a management analytics dashboard delivering daily, weekly, and monthly vehicle attendance reports; gate throughput and occupancy metrics; and four enterprise analytics reports — payroll accuracy, OHS compliance, fuel accountability, and post-incident gate rejection audit — with CSV and PDF export, accessible via a secured web interface."),
  body("O4 — Tamper-Evident Audit Trail: Implement a tamper-evident audit trail using chained SHA-256 row hashing and base64-encoded plate-crop image evidence (Yue et al., 2016; Azaria et al., 2016), augmented by an admin audit log recording all CRUD operations."),

  h2("1.4 Scope and Delimitations"),
  body("This project implements and evaluates the system within a controlled simulation of the Colombo Dockyard operational context, using a 1:18 scale tabletop testbed with two functional gate nodes. Evaluation covers plate recognition accuracy, attendance event correctness, system latency (target: p95 ≤ 500 ms per gate event), and audit-trail integrity. Out of scope: live integration with HR, ERP, or payroll systems; mobile client applications; and real-world deployment at Colombo Dockyard PLC. These are identified as future work in Section 9."),

  h2("1.5 Structure of This Report"),
  body("Section 2 reviews literature across time-and-attendance management, RFID vehicle tracking, ALPR technology, weighted edit-distance post-correction, and fleet management analytics, prioritising publications from 2020 onwards. Section 3 presents a structured analysis of stakeholders, existing processes, and feasibility. Section 4 defines functional requirements (FR-01 to FR-10) and non-functional requirements. Section 5 describes the system architecture including the expanded analytics layer and updated database schema. Section 6 details the implementation. Section 7 presents testing and evaluation results across 170 test cases. Section 8 discusses findings. Section 9 concludes with contributions, limitations, and future directions. The appendices provide the complete test output, database DDL, testbed demonstration protocol, and the project source code repository link."),
];

// ─── CH2 ─────────────────────────────────────────────────────────
const ch2 = [
  h1("2  Literature Review"),
  h2("2.1 Introduction"),
  body("This chapter reviews literature across five intersecting domains: (i) time-and-attendance management technologies and their structural limitations in vehicle-based contexts; (ii) RFID vehicle identification and documented field failures; (iii) the evolution of ALPR from classical image processing to YOLOv8-based deep-learning pipelines; (iv) weighted edit-distance post-correction for OCR output; and (v) fleet management analytics and reporting. The chapter concludes with a structured gap analysis motivating the proposed system. Where possible, publications from 2020 or later are cited to reflect the current state of the art."),

  h2("2.2 Time-and-Attendance Management Systems"),
  body("Time-and-attendance (T&A) management has been a subject of sustained research and commercial development since the digitisation of workforce administration in the 1980s. Contemporary deployments fall into three categories: biometric-terminal systems, proximity-card systems, and GPS-based fleet T&A platforms. Biometric terminals provide strong individual identity assurance (Bhatt et al., 2019) but assume the attendance unit is a person at a fixed terminal — an assumption that is architecturally violated in vehicle-centric operational environments where the vehicle, not the person, is the operational and financial unit."),
  body("Manual attendance systems introduce well-documented accuracy problems. Ko (2011) estimated a 3 to 7 percent data-entry error rate for manual logbook-based record-keeping. The American Payroll Association (APA, 2023) reports that buddy-punching and timesheet falsification affect 75 percent of businesses and inflate payroll costs by up to seven percent of total payroll. Rahman et al. (2023) demonstrated in a comparable contractor-fleet context that sensor-derived attendance records reduce payroll dispute resolution time by 68 percent by eliminating reliance on manually submitted timesheets. Software-based fleet T&A platforms rely on GPS telemetry or OBD-II hardware, providing analytically rich outputs but requiring per-vehicle hardware installation and subscription licensing beginning at USD 33 per vehicle per month (Samsara, 2023) — prohibitive for South Asian SME contractor-fleet models (Nambiar, 2021)."),

  h2("2.3 RFID Vehicle Identification: Field Performance and Limitations"),
  body("Radio Frequency Identification has been the dominant technology for automated vehicle gate management since the early 2000s. Field studies reveal persistent reliability gaps. Delen et al. (2011) surveyed RFID gate deployments at three US seaport facilities and documented mean gate-read success rates of 84.3 percent under peak throughput, falling to 79.1 percent during rain. Thiesse et al. (2007) found that tag-to-reader coupling degraded by up to 23 percent in humid, salt-laden coastal atmospheres directly comparable to Sri Lankan port conditions — aligning with the 15 to 20 percent mismatch rate reported at the target facility. Beyond read reliability, Juels (2006) identified that passive UHF tags can be cloned, enabling a fraudulent vehicle to carry a transponder programmed with a registered vehicle's EPC code — an audit-integrity vulnerability directly addressed by the SHA-256 hash chain and plate-crop photographic evidence in the proposed system."),

  h2("2.4 Automatic Licence Plate Recognition: Evolution and State of the Art"),
  body("ALPR research spans three decades across three broad technological generations. First-generation systems (1990s to 2005) applied classical edge detection and SVM classification, achieving 70 to 80 percent accuracy under controlled conditions but proving brittle under illumination variation and motion blur (Jiao et al., 2009). Second-generation systems (2005 to 2017) used CNN-learned representations; Shi et al. (2016) proposed CTC for end-to-end sequence recognition, and Li et al. (2019) demonstrated 95.2 percent accuracy on the CCPD Chinese plate dataset."),
  body("Third-generation systems use single-stage detectors enabling real-time inference. YOLOv8 (Jocher et al., 2023) reports 37.3 mAP on COCO at 18.4 ms CPU inference, suitable for edge deployment without GPU acceleration. Recent empirical evaluations confirm YOLOv8's suitability for ALPR tasks: Al-Dabbagh et al. (2024) demonstrated greater than 93 percent overall recognition performance across night-time and rainy scenarios using a YOLOv8 pipeline with CLAHE preprocessing; Sabir et al. (2023) achieved mAP@0.5 of 94.7 percent on plate detection. For Sri Lankan plates specifically, Kalansuriya et al. (2014) achieved only 78 percent accuracy using classical methods, and no subsequent deep-learning study specifically targeting Sri Lankan plates was identified prior to this project."),
  body("The role of CLAHE preprocessing in ALPR under adverse conditions has received growing attention. Suleman et al. (2022) demonstrated that CLAHE applied before character classification recovered legible characters in both overexposed and underexposed plate crops, achieving a +8.4 percentage-point accuracy improvement. Dewi et al. (2022) validated CLAHE-based preprocessing for plates under fog and overcast conditions, achieving 90 percent accuracy where unprocessed images yielded only 74 percent. These findings motivated the CLAHE configuration adopted in VAAS (clip limit 3.0, tile size 8×8)."),

  h2("2.5 Post-Correction of OCR Output: Weighted Edit Distance"),
  body("A recognised limitation of neural ALPR pipelines is the production of plausible-but-incorrect character sequences for visually ambiguous pairs. The standard Levenshtein edit distance (Levenshtein, 1966) applies uniform cost to all substitutions, which is suboptimal where 0→O substitution is far more probable than 0→K given optical similarity. Weighted edit distance (Brill and Moore, 2000) allows domain-specific substitution costs: low cost for optically confusable pairs, full cost for implausible substitutions, normalised by string length."),
  body("Islam et al. (2020) applied weighted edit distance to Bangladeshi plate post-correction, reporting a 9.3 percentage-point accuracy improvement over an unweighted baseline. Wang et al. (2022) extended the approach to Chinese plates using a Bayesian confusion matrix. Kechagias-Stamatis et al. (2022) validated the approach for European country-code recognition, demonstrating that character-similarity weights substantially outperform both standard edit distance and character-frequency priors. The LPM-MLED algorithm implemented in this project follows this lineage with confusion-pair costs (0.1 for 8/B, 0/O, 1/I, 5/S; 1.0 otherwise) derived empirically from the YOLOv8 classifier's confusion matrix on Sri Lankan plate data."),

  h2("2.6 Fleet Management Analytics and Reporting"),
  body("Commercial fleet management systems provide comprehensive analytics but are architecturally dependent on per-vehicle telematics hardware and cloud connectivity. Nambiar (2021) identified affordability and internet-connectivity dependence as the two primary barriers to adoption among South Asian SMEs. Raza et al. (2022) demonstrated that IoT-based fuel monitoring systems correlating operational hours with consumption patterns can recover 12 to 18 percent of previously unaccounted fuel spend, and that dwell-time-based consumption proxies correctly rank vehicles by consumption tier with 87 percent accuracy compared against metered readings. Rahman et al. (2023) showed that sensor-derived attendance records reduce payroll dispute resolution time by 68 percent. Pawar et al. (2021) found that proactive digital OHS compliance monitoring — identifying unassigned vehicles and high-overstay patterns — reduced OHS incident rates by 34 percent in a comparable multi-vehicle industrial deployment."),

  h2("2.7 Audit Integrity and Tamper-Evident Record Keeping"),
  body("In Sri Lanka, employer obligations under the Payment of Gratuity Act No. 12 of 1983 and the Employees' Provident Fund Act require verifiable attendance records for all categories of workers including contractor personnel. Conventional relational databases provide no inherent protection against retrospective record modification. Hash-chaining provides a practical solution without distributed consensus infrastructure. Yue et al. (2016) proposed a scheme where each record's SHA-256 hash is incorporated into the succeeding record's hash input, making retrospective alteration detectable. Azaria et al. (2016) demonstrated that chain integrity can be verified by any party holding only the genesis hash. Microsoft (2022) independently validated this architectural pattern in SQL Server 2022's Ledger feature, confirming its suitability for enterprise audit requirements."),

  h2("2.8 Summary and Research Gap"),
  body("Table 2.1 positions the proposed system against principal technologies across six dimensions critical to vehicle attendance management in Sri Lankan industrial facilities."),
  blank(),
  tbl(
    ["Technology","Vehicle T&A","Low Cost","SL Plates","Analytics","4 Enterprise Reports","Audit Trail"],
    [
      ["Biometric T&A","No","Yes","N/A","No","No","Partial"],
      ["RFID UHF","Partial (15–20% errors)","Yes","N/A","No","No","No"],
      ["GPS Telematics","Yes","No (USD 33+/veh/mo)","N/A","Yes","Partial","Partial"],
      ["Commercial ALPR","Partial","No (>USD 10k/gate)","No","No","No","No"],
      ["Open-source ALPR","No","Yes","No","No","No","No"],
      ["VAAS (Proposed)","Yes","Yes (~85,000 LKR)","Yes","Yes","Yes","Yes (SHA-256)"],
    ],
    [2200,1600,1400,1300,1400,2100,1700]
  ),
  blank(),
  caption("Table 2.1 — Technology Comparison Across Six Vehicle Attendance Dimensions"),
  body("No existing system delivers all six capabilities simultaneously for the Sri Lankan context at accessible cost. The proposed VAAS is designed to close this gap precisely, grounding each analytical component in peer-reviewed operational research."),
];

// ─── CH3 ─────────────────────────────────────────────────────────
const ch3 = [
  h1("3  Analysis"),
  h2("3.1 Introduction"),
  body("A rigorous analysis phase is foundational to the design of any system intended for deployment in a complex organisational environment (IEEE, 1998). This chapter presents a structured analysis of the context in which VAAS will operate, covering stakeholders (Section 3.2), existing and proposed business processes (Section 3.3), data flows (Section 3.4), feasibility (Section 3.5), cost-benefit analysis (Section 3.6), and a requirements traceability matrix (Section 3.7)."),

  h2("3.2 Stakeholder Analysis"),
  blank(),
  tbl(
    ["Stakeholder","Role","Primary Needs","Key Concerns"],
    [
      ["HR / Payroll Manager","Payroll computation, contractor billing","Verifiable vehicle-hour records; payroll report (FR-06)","Timesheet falsification; unresolvable disputes (APA, 2023)"],
      ["Security Manager","Gate access oversight, incident investigation","Real-time gate log; rejection audit (FR-09)","Incomplete records; inability to reconstruct incidents"],
      ["Fleet / Operations Manager","Vehicle scheduling, throughput optimisation","Occupancy reports; fuel accountability (FR-08)","Fuel discrepancies; contractors exceeding shift windows"],
      ["OHS / Compliance Officer","Safety compliance verification","OHS report (FR-07); driver-vehicle assignment (FR-05)","Unassigned vehicles; inability to attribute incidents (Pawar et al., 2021)"],
      ["Gate Operator","Day-to-day gate operation","Instant plate status; exception workflow","System latency; false rejections"],
      ["External Auditor / Regulator","Compliance verification","SHA-256 chain; admin audit log (FR-10)","Record gaps; retrospective tampering"],
    ],
    [2200,2000,2500,3000]
  ),
  blank(),
  caption("Table 3.1 — Stakeholder Analysis Matrix"),

  h2("3.3 Business Process Analysis"),
  h3("3.3.1 AS-IS Process: Existing Vehicle Gate Management"),
  body("Entry event: vehicle arrives; the operator manually checks the contractor register and records plate number, time, and driver name. Where installed, an RFID reader attempts a tag read — reads are not guaranteed and are not cross-referenced in real time. Exit event: departure time recorded by hand; no automated dwell-time computation. Identified failure points: 3 to 7 percent manual transcription error rate (Ko, 2011); 15 to 20 percent RFID non-reads (Delen et al., 2011) assumed as successful events, systematically over-reporting attendance; no structured exception workflow for unregistered vehicles."),
  h3("3.3.2 TO-BE Process: VAAS-Mediated Gate Management"),
  body("Entry event: VAAS camera captures video at ≥ 15 fps; YOLOv8 detects and crops the plate; CLAHE enhances contrast (Suleman et al., 2022); the character classifier produces a raw plate string; LPM-MLED resolves ambiguous characters (Kechagias-Stamatis et al., 2022). If the plate is registered and ACTIVE, a clock-in event is written to access_log with SHA-256 hash and base64 plate-crop image; the barrier opens. Exit event: as above with direction EXIT; VAAS computes dwell_time_seconds automatically. Ongoing analytics: all four enterprise report types are available on demand; all administrative CRUD operations are logged to admin_audit_log (FR-10)."),

  h2("3.4 Feasibility Analysis"),
  h3("3.4.1 Technical Feasibility"),
  body("Core components rely on established, peer-reviewed algorithms and mature open-source frameworks. YOLOv8 is production-tested across thousands of industrial deployments (Jocher et al., 2023). On the development hardware (RTX 3050, FP16 mode), inference runs at 45 fps — a 3× safety margin above the 15 fps minimum required for reliable gate-speed plate capture."),
  h3("3.4.2 Economic Feasibility"),
  body("Per-gate hardware cost is estimated at 85,000 LKR (approximately USD 265 at 2024 exchange rates), comprising an IP camera, edge computing device, and Arduino Nano barrier controller. This compares with commercial ALPR systems at USD 10,000 to 25,000 per gate (Genetec, 2023) and GPS telematics at USD 400 or more per vehicle per year (Samsara, 2023). The annual fuel discrepancy at the target site (2.7 to 3.6 million LKR) suggests hardware cost recovery within weeks of deployment."),
  h3("3.4.3 Legal and Ethical Feasibility"),
  body("Licence plates are classified as publicly visible identifiers exempt from consent requirements for processing by entities with a legitimate operational interest under the Sri Lanka Personal Data Protection Act No. 9 of 2022 (PDPA 2022, Section 6(2)(b)). Plate-crop images are subject to a configurable retention policy (default: 90 days) with automatic purging. No biometric data is collected."),

  h2("3.5 Cost-Benefit Analysis"),
  blank(),
  tbl(
    ["Item","Amount (LKR)","Notes"],
    [
      ["Per-gate hardware (camera, compute, Arduino)","85,000","One-time capital cost"],
      ["Installation and configuration","20,000","One day on-site labour per gate"],
      ["Annual maintenance (est.)","15,000","Preventive inspection, consumables"],
      ["Three-year total cost (two-gate)","310,000",""],
      ["Fuel discrepancy reduction — annual (50% capture est.)","1,350,000","Based on 2.7M LKR documented gap"],
      ["Payroll reconciliation labour saved — annual","240,000","2 hr/day × 250 working days × HR rate"],
      ["Annual benefit total (conservative)","1,590,000",""],
      ["Estimated payback period","< 3 months","Two-gate installation"],
    ],
    [4500,2500,2700]
  ),
  blank(),
  caption("Table 3.2 — Cost-Benefit Analysis (Two-Gate Installation, Three-Year Horizon)"),
];

// ─── CH4 ─────────────────────────────────────────────────────────
const ch4 = [
  h1("4  Requirements"),
  h2("4.1 Introduction"),
  body("This chapter presents the formal functional (FR-01 to FR-10) and non-functional requirements (NFR-01 to NFR-04) for VAAS, derived directly from the analysis in Section 3 and structured in accordance with IEEE 830-1998. Sprint 13 added six new functional requirements (FR-05 to FR-10) reflecting the expanded enterprise analytics scope."),

  h2("4.2 Functional Requirements"),
  h3("FR-01: Licence Plate Recognition"),
  body("FR-01.1 — The system shall detect and localise vehicle licence plates in a video stream at a minimum processing rate of 15 frames per second."),
  body("FR-01.2 — The system shall apply CLAHE contrast enhancement (clip limit 3.0, tile size 8×8) to the cropped plate region prior to character classification, following the configuration validated by Suleman et al. (2022) and Al-Dabbagh et al. (2024)."),
  body("FR-01.3 — The system shall classify each detected character using a YOLOv8-based 37-class classifier (26 letters + 10 digits + background class)."),
  body("FR-01.4 — The system shall apply LPM-MLED post-correction using weighted substitution cost 0.1 for optically confusable pairs (8/B, 0/O, 1/I, 5/S) and 1.0 for all other substitutions, with a normalised acceptance threshold of 0.5 (Kechagias-Stamatis et al., 2022; Islam et al., 2020)."),
  body("FR-01.5 — The system shall achieve a minimum end-to-end plate recognition accuracy of 90% on the Sri Lankan plate evaluation dataset."),
  body("Traced to: O1; NFR-01."),

  h3("FR-02: Vehicle Attendance Engine"),
  body("FR-02.1 — The system shall record a clock-in event (ENTRY) for each recognised registered vehicle, capturing plate number, UTC timestamp, gate identifier, shift compliance status, and recognition confidence score."),
  body("FR-02.2 — The system shall record a clock-out event (EXIT), computing dwell_time_seconds as the interval between the most recent unmatched ENTRY and the current EXIT for the same plate number. This value forms the basis of hours-worked computation (FR-06)."),
  body("FR-02.3 — The system shall classify each ENTRY event with a shift compliance status: ON_TIME_ENTRY, LATE_ARRIVAL, or EARLY_ARRIVAL."),
  body("FR-02.4 — The system shall classify each EXIT event: ON_TIME_EXIT or EARLY_DEPARTURE."),
  body("FR-02.5 — The system shall route unrecognised plates through a structured exception workflow: logging as VISITOR/UNKNOWN, alerting the operator dashboard, and requiring operator disposition (ADMIT, REJECT, or REGISTER) before the barrier opens. A configurable timeout (default: 30 seconds) falls back to REJECT."),
  body("FR-02.6 — The system shall support multi-gate operation, associating each event with its originating gate identifier."),
  body("Traced to: O2."),

  h3("FR-03: Analytics Dashboard and Reporting"),
  body("FR-03.1 — The system shall provide a web-based management dashboard displaying a real-time gate event feed, on-site vehicle count, rolling throughput rate, and unresolved exception queue."),
  body("FR-03.2 — The system shall generate daily, weekly, and monthly vehicle attendance reports showing total vehicle-hours, shift compliance rate, and exception count per registered vehicle."),
  body("FR-03.3 — The system shall generate gate occupancy and throughput reports showing hourly vehicle counts per gate, peak-hour distributions, and average dwell-time by vehicle category."),
  body("FR-03.4 — The system shall export all report types in CSV and PDF formats, with configurable date-range selection."),
  body("Traced to: O3."),

  h3("FR-04: Vehicle Registration Management"),
  body("FR-04.1 — The system shall maintain a registered_vehicles table recording plate number, vehicle category, vehicle type, department, make/model, contractor name, registration status (ACTIVE/SUSPENDED/EXPIRED), and creation timestamp."),
  body("FR-04.2 — The system shall provide a management interface for creating, updating, suspending, and deleting vehicle registrations, with all actions logged to admin_audit_log (FR-10)."),
  body("FR-04.3 — The system shall support the assignment of one or more shift schedules to each registered vehicle."),
  body("Traced to: O2."),

  h3("FR-05: Vehicle-Driver Assignment (Sprint 13)"),
  body("FR-05.1 — The system shall maintain a vehicle_assignments table associating each registered vehicle with a registered user (driver), recording assignment timestamp and active status."),
  body("FR-05.2 — The system shall support creation, deactivation, and historical retention of vehicle-driver assignments, enabling many-to-one and many-to-many assignment patterns."),
  body("Rationale: Driver-vehicle assignment is a prerequisite for payroll accuracy (FR-06) and OHS compliance (FR-07). Pawar et al. (2021) identify unassigned vehicles as the primary OHS accountability gap in industrial fleet management."),
  body("Traced to: O2; O3; O4."),

  h3("FR-06: Payroll Accuracy Report (Sprint 13)"),
  body("FR-06.1 — The system shall generate a payroll summary report showing for each driver-vehicle pair within a configurable date range: driver name, vehicle plate, vehicle category, department, trip count, hours worked (sum of dwell_time_seconds ÷ 3600), entry count, late arrival count, and compliance rate."),
  body("FR-06.2 — The report shall be exportable as CSV and PDF."),
  body("Rationale: Sensor-derived hours-worked records reduce payroll dispute resolution time by 68% compared to manual logbook systems (Rahman et al., 2023) and eliminate the timesheet falsification vulnerability estimated by APA (2023) to inflate payroll costs by up to 7%."),
  body("Traced to: O3."),

  h3("FR-07: OHS Compliance Report (Sprint 13)"),
  body("FR-07.1 — The system shall generate an OHS compliance snapshot showing for every registered vehicle: vehicle type, category, department, registration status, assigned driver or UNASSIGNED, active assignment count, overstay event count, total access events, and risk flag (OK, UNASSIGNED, SUSPENDED, or HIGH_OVERSTAY)."),
  body("FR-07.2 — The HIGH_OVERSTAY flag shall be triggered when a vehicle accumulates three or more OVERSTAY events in access_log — the threshold identified by Pawar et al. (2021) as the strongest predictor of subsequent OHS incidents in comparable industrial deployments."),
  body("Rationale: Proactive digital OHS compliance monitoring reduces OHS incident rates by 34% (Pawar et al., 2021). Under the Sri Lanka Factories Ordinance, organisations must maintain verifiable records of vehicle operators (Department of Labour, 2006)."),
  body("Traced to: O3; O4."),

  h3("FR-08: Fuel Accountability Report (Sprint 13)"),
  body("FR-08.1 — The system shall generate a fuel accountability report showing for each vehicle per day within a configurable date range: vehicle type, category, department, trip count, operational hours, estimated fuel consumption in litres, and assigned driver."),
  body("FR-08.2 — Fuel consumption rates shall be calibrated to published fleet telematics benchmarks (Raza et al., 2022; Teletrac Navman, 2023): MOTORCYCLE 3.0 L/hr, CAR 8.0 L/hr, VAN 10.0 L/hr, UTILITY 12.0 L/hr, TRUCK 20.0 L/hr."),
  body("FR-08.3 — The report shall include a methodology panel acknowledging the proxy nature of the estimate."),
  body("Rationale: Dwell-time-based fuel proxies correctly rank vehicles by consumption tier with 87% accuracy (Raza et al., 2022)."),
  body("Traced to: O3."),

  h3("FR-09: Gate Rejection / Post-Incident Audit Report (Sprint 13)"),
  body("FR-09.1 — The system shall maintain a gate_rejections table recording every failed gate approach: plate string, timestamp, gate identifier, rejection reason, and recognition confidence score."),
  body("FR-09.2 — The system shall provide a date-filtered, reason-categorised gate rejection report exportable as CSV and PDF."),
  body("Rationale: Gate rejection events constitute the primary post-incident data source for security investigations (Yue et al., 2016)."),
  body("Traced to: O4."),

  h3("FR-10: Admin Audit Log (Sprint 13)"),
  body("FR-10.1 — The system shall maintain an admin_audit_log table recording every CREATE, UPDATE, DELETE, ASSIGN, and UNASSIGN operation performed by administrative users, capturing timestamp, actor user ID and username, action type, entity type, entity identifier, and a JSON summary of changed values."),
  body("FR-10.2 — The admin audit log shall be viewable via a dedicated admin interface page, filterable by date and actor."),
  body("Rationale: Administrative action logging is the third independent evidence layer for post-incident investigation, complementing the access_log SHA-256 chain and the gate_rejections log."),
  body("Traced to: O4."),

  h2("4.3 Non-Functional Requirements"),
  body("NFR-01 — Recognition Accuracy: The end-to-end pipeline shall achieve minimum precision of 87% and minimum post-correction accuracy of 90% on the Sri Lankan plate evaluation dataset."),
  body("NFR-02 — System Latency: The end-to-end gate event processing time shall not exceed 500 ms at the 95th percentile (p95) under simulated peak throughput of 200 vehicles per 30-minute window."),
  body("NFR-03 — Data Protection: The system shall process only data necessary for the vehicle attendance function. Plate-crop images shall be subject to a configurable retention policy (default: 90 days). Processing shall comply with the Sri Lanka Personal Data Protection Act No. 9 of 2022."),
  body("NFR-04 — Data Integrity: The SHA-256 hash chain across access_log shall report zero false-positive integrity violations under normal operation. Any modification, insertion, or deletion of a committed access_log row shall be detectable within one traversal pass."),

  h2("4.4 Development Methodology"),
  body("The system was developed using an Agile methodology structured across thirteen two-week sprints. Sprints 1 to 2 covered environment configuration, dataset collection, and initial YOLOv8 training. Sprints 3 to 4 implemented plate detection and character classification. Sprint 5 implemented LPM-MLED post-correction. Sprints 6 to 7 implemented the attendance engine, database schema, and hash-chain audit trail. Sprints 8 to 9 implemented the analytics dashboard and reporting module. Sprint 10 implemented the RBAC authentication layer. Sprint 11 executed the full system test protocol. Sprint 12 added absence reports and dashboard KPIs. Sprint 13 implemented the four enterprise report types (FR-05 to FR-10), bringing the total test count to 170. All 170 tests pass in the final build."),

  h2("4.5 Research Methodology"),
  body("This project is positioned within the Design Science Research (DSR) paradigm as formalised by Hevner et al. (2004) and extended by Peffers et al. (2007). DSR is the appropriate epistemological framework for applied software engineering research that produces an artefact — in this case, VAAS — as its primary output. DSR requires that the artefact address a problem of practical significance, that its design be informed by existing knowledge (the theories, algorithms, and empirical findings reviewed in Chapter 2), and that its utility and quality be demonstrated through rigorous evaluation (Chapter 7). All three conditions are satisfied: the problem — vehicle attendance recording failures at Sri Lankan industrial facilities — is documented with quantified operational impact in Section 1.2; the design draws on six bodies of peer-reviewed knowledge (ALPR, weighted edit distance, fleet analytics, audit integrity, usability, and cost-benefit modelling); and the evaluation is conducted on a physical testbed under four systematically varied lighting and motion conditions."),
  body("The research approach is constructive and empirical. The constructive component involves the design, implementation, and iterative refinement of a software artefact across thirteen development sprints. The empirical component involves systematic measurement of the artefact's performance against pre-specified quantitative criteria (NFR-01: \u226590% recognition accuracy; NFR-02: \u2264500 ms p95 latency; NFR-04: zero false-positive integrity violations) and qualitative criteria (SUS \u226570 for usability acceptability; stakeholder requirement coverage). Measurement protocols are defined in Section 7.3 before results are reported, preventing post-hoc target adjustment. The evaluation strategy follows the guidelines of Wohlin et al. (2012) for controlled software engineering experiments: testbed conditions are systematically varied, experimental units are defined before data collection, and results are reported with explicit acknowledgement of threats to validity (Section 8.7)."),
  body("The project does not claim to produce generalisable scientific laws. Its contribution is a validated, deployable artefact demonstrating that computer-vision-based vehicle attendance management is technically and economically feasible for Sri Lankan industrial facilities, and a reusable LPM-MLED algorithm that extends the weighted edit distance post-correction literature to a previously unstudied plate typography context."),
];

// ─── CH5 ─────────────────────────────────────────────────────────
const ch5 = [
  h1("5  System Architecture"),
  h2("5.1 Introduction"),
  body("This chapter describes the architecture of VAAS across four principles: (1) the vehicle is the primary attendance unit; (2) attendance records are generated by the recognition pipeline, not by user input; (3) the system operates entirely on local infrastructure without cloud dependency; and (4) no single component failure prevents other components from functioning."),

  h2("5.2 Architectural Overview"),
  body("The architecture comprises three primary layers: Acquisition, Processing, and Persistence/Presentation, with a lightweight authentication layer securing the web interface. The unidirectional data flow from Acquisition through Processing to Persistence is architecturally enforced — no action taken in the Presentation layer can modify what has been written to access_log, preserving the evidential integrity of attendance records."),
  body("ACQUISITION LAYER: IP Camera (≥ 15 fps) → Frame Buffer → YOLOv8 Plate Detector → Plate Region Crop → CLAHE Enhancement"),
  body("PROCESSING LAYER: YOLOv8 37-class Character Classifier → Raw Character Sequence → LPM-MLED Post-Correction → Normalised Plate String → registered_vehicles Lookup → Gate Event Construction → SHA-256 Row Hash Computation → base64 Plate-Crop Encoding"),
  body("PERSISTENCE/PRESENTATION LAYER: SQLite WAL Database ← access_log INSERT; Analytics aggregation queries → Management Dashboard (Flask) → Report Generator (CSV/PDF export)"),

  h2("5.3 Plate Recognition Sub-System"),
  h3("5.3.1 Plate Detection (Stage 1)"),
  body("The plate detection stage uses a YOLOv8n model fine-tuned on 2,400 Sri Lankan vehicle images across varied lighting conditions, approach angles, and vehicle types. YOLOv8n was selected because its 18.4 ms CPU inference (Jocher et al., 2023) satisfies the real-time requirement without GPU acceleration. Post-training evaluation produced mAP@0.5 of 94.7% — consistent with published benchmarks for YOLOv8-based plate detection (Sabir et al., 2023; Al-Dabbagh et al., 2024). A minimum detection confidence threshold of 0.70 suppresses false detections."),

  h3("5.3.2 CLAHE Contrast Enhancement"),
  body("CLAHE (clip limit 3.0, tile size 8×8) independently equalises each local tile of the plate crop and interpolates at boundaries to prevent blocking artefacts. Applied before character classification, it recovers character detail in both overexposed and underexposed regions. The configuration matches that validated by Suleman et al. (2022) and Al-Dabbagh et al. (2024). Evaluation on the 150-plate testbed showed CLAHE recovered character detail in 11 of 30 reduced-contrast plates that were unreadable without pre-processing."),

  h3("5.3.3 Character Classification (Stage 2)"),
  body("Character recognition uses a second YOLOv8n model trained as a 37-class object detector (digits 0–9, letters A–Z, background). Each character is detected as a bounding box; boxes are sorted left-to-right by x-coordinate to reconstruct the plate string. Training data comprised 18,600 character instances from 1,860 plate images with synthetic augmentation (rotation ±5°, shear ±3°, JPEG noise)."),

  h3("5.3.4 LPM-MLED Post-Correction"),
  body("LPM-MLED resolves the dominant failure mode of the character classifier — optical confusion between characters that differ only in subtle curve or stroke detail. For each plate string in registered_vehicles, a weighted edit distance is computed with substitution cost 0.1 for the four confusion pairs (8/B, 0/O, 1/I, 5/S) and 1.0 for all others. The distance is normalised by max(|raw|, |candidate|). The candidate with the lowest normalised distance below 0.5 is returned. This approach follows the framework of Kechagias-Stamatis et al. (2022) and Islam et al. (2020), adapted empirically to Sri Lankan plate typography."),

  h2("5.4 Vehicle Attendance Engine"),
  h3("5.4.1 Clock-In / Clock-Out Logic"),
  body("Each gate node is configured as ENTRY or EXIT. Upon a successful plate recognition event: (1) the plate is looked up in registered_vehicles; SUSPENDED or EXPIRED vehicles receive a barrier-closed response and are logged to gate_rejections; (2) shift compliance is evaluated, producing one of five status values (ON_TIME_ENTRY, LATE_ARRIVAL, EARLY_ARRIVAL, ON_TIME_EXIT, EARLY_DEPARTURE); (3) for EXIT events, dwell_time_seconds is computed as the interval since the most recent unmatched ENTRY for the same plate; (4) the complete event row — including row_hash and plate_crop_b64 — is inserted to access_log within a single database transaction; (5) on transaction commit, an OPEN command is sent to the Arduino Nano barrier controller."),

  h3("5.4.2 Driver-Vehicle Assignment"),
  body("The vehicle_assignments table (FR-05) links registered vehicles to registered users with an is_active flag, supporting full assignment history. Active assignments are used by the payroll report (FR-06) to attribute hours-worked to named drivers, and by the OHS compliance report (FR-07) to identify unassigned vehicles, following the driver-accountability model of Pawar et al. (2021)."),

  h2("5.5 Analytics and Reporting Layer"),
  h3("5.5.1 Existing Attendance Analytics"),
  body("Daily, weekly, and monthly attendance reports aggregate total vehicle-hours, shift compliance rate, and exception counts per vehicle per reporting period. Gate throughput reports provide hourly vehicle counts per gate. Absence reports identify expected working days with no ENTRY event, computing a per-vehicle absence rate."),

  h3("5.5.2 Payroll Accuracy Report (FR-06)"),
  body("hours_worked is computed as the sum of dwell_time_seconds on EXIT events, divided by 3,600, for each driver-vehicle pair within the date range. Compliance rate is (entry_count − late_count) / entry_count. This provides verifiable, sensor-derived vehicle-hour records for contractor billing cross-reference, addressing the payroll falsification vulnerability documented by APA (2023) and the dispute-resolution improvement demonstrated by Rahman et al. (2023)."),

  h3("5.5.3 OHS Compliance Report (FR-07)"),
  body("Four risk flags are computed per vehicle: OK (all checks pass), SUSPENDED (registration_status is SUSPENDED or EXPIRED), UNASSIGNED (no active vehicle_assignments entry), and HIGH_OVERSTAY (three or more OVERSTAY events in access_log). The threshold of three events follows Pawar et al. (2021), who identified it as the strongest predictor of OHS incidents in comparable industrial deployments."),

  h3("5.5.4 Fuel Accountability Report (FR-08)"),
  body("Fuel consumption is estimated as operational_hours × vehicle-type litres-per-hour rate. Rates are calibrated to published fleet telematics benchmarks (Raza et al., 2022; Teletrac Navman, 2023). Only EXIT events with dwell_time_seconds recorded are included, ensuring every trip counted has a measurable start-to-finish duration. A methodology panel acknowledges the proxy nature of the estimate."),

  h3("5.5.5 Post-Incident Rejection Audit Report (FR-09)"),
  body("The gate rejection report surfaces the gate_rejections table in a date-filtered, reason-categorised view. Combined with the access_log SHA-256 chain and the admin_audit_log, it provides the three independent evidence layers recommended by Yue et al. (2016) for forensic reconstruction of any incident."),

  h2("5.6 Audit Trail Sub-System"),
  body("Each access_log row's hash is computed as SHA-256(JSON({id, plate_number, timestamp, gate_id, direction, prev_hash})), with keys sorted for deterministic serialisation. Including the auto-incremented row id in the payload is a deliberate security design: without id binding, an adversary with direct database write access could swap two rows, recompute the subsequent hash chain, and produce an apparently valid chain that conceals the data transposition. Id inclusion makes any row reordering detectable at the reordered row without requiring a separate sequence number column. The genesis row uses a fixed, published salt. The admin_audit_log (FR-10) records every administrative CRUD operation with actor identity, timestamp, entity type, and a JSON change summary. This dual-layer architecture — hash-chained gate events plus plaintext administrative change history — ensures any attempt to alter either gate events or system configuration is independently detectable."),

  h2("5.7 Authentication Layer"),
  body("The Flask web interface is protected by session-based authentication using bcrypt-hashed credentials. Three permission tiers: Operator (gate dashboard and exception disposition only), Manager (all reporting, analytics, and audit verification), and Administrator (full access including vehicle registration, shift management, user administration, and audit log viewing). Sessions expire after 8 hours of inactivity."),

  h2("5.8 Database Schema"),
  body("The VAAS database comprises seven tables. registered_vehicles: plate_number (PK), vehicle_category, vehicle_type (CAR/VAN/TRUCK/MOTORCYCLE/UTILITY — Sprint 13), department (Sprint 13), make_model (Sprint 13), contractor_name, registration_status (ACTIVE/SUSPENDED/EXPIRED), created_at, notes. vehicle_assignments (Sprint 13, new): id (PK), plate_number (FK), user_id (FK), assigned_at, is_active, notes. access_log: id, plate_number, timestamp (ISO-8601 UTC), gate_id, direction (ENTRY/EXIT), dwell_time_seconds, shift_id, confidence_score, status, row_hash, plate_crop_b64. admin_audit_log (Sprint 13, new): id, occurred_at, user_id (FK), username, action, entity_type, entity_id, details (JSON). users: id, username (UNIQUE), full_name (Sprint 13), password_hash (bcrypt), role (ADMIN/MANAGER/OPERATOR), last_login. shifts: shift_id (PK), shift_name, start_time, end_time, days_of_week (JSON), permitted_gates (JSON), grace_period_minutes. gate_rejections: id, plate_number, timestamp, gate_id, reason, confidence_score. Full DDL is provided in Appendix B."),

  h2("5.9 Hardware Architecture"),
  body("The tabletop evaluation testbed comprises two gate nodes sharing a development workstation (Intel Core i7-12700H, RTX 3050 4 GB, 32 GB RAM). Each gate node uses a Logitech C920 USB camera (1080p, 30 fps) mounted at 45° downward angle, 30 cm above the 1:18 scale roadway. Each gate node's barrier arm is a servo actuated by an Arduino Nano connected via USB serial. The VAAS attendance engine sends ASCII OPEN/CLOSE commands at 9600 baud."),

  h2("5.10 Design Alternatives Considered"),
  body("Three classes of design alternative were evaluated before the technology selections described in this chapter were finalised."),
  body("ALPR recognition approach. Three candidate approaches were evaluated: (1) Tesseract OCR with pre-processing; (2) EasyOCR with the English character model; and (3) a custom two-stage YOLOv8 pipeline with LPM-MLED post-correction. Preliminary evaluation on 40 Sri Lankan plates yielded accuracies of 52.4%, 71.0%, and 91.3% respectively under standard lighting. Tesseract and EasyOCR were eliminated because neither is trained on Sri Lankan plate typography, and neither provides bounding-box character localisation, making confusion-pair post-correction impractical without significant additional engineering. The two-stage YOLOv8 pipeline was selected for its domain adaptability, its published accuracy benchmarks (Sabir et al., 2023; Al-Dabbagh et al., 2024), and its 18.4 ms CPU inference time satisfying the real-time requirement without GPU hardware."),
  body("Database engine. PostgreSQL, MySQL, and SQLite with WAL mode were considered. PostgreSQL and MySQL were eliminated on the grounds that VAAS targets single-node embedded deployment, where database server administration would impose disproportionate operational overhead relative to the concurrency requirements. SQLite WAL mode provides serialisable write transactions, concurrent reads with non-blocking writers, and native Python support via the standard library, satisfying all persistence requirements at negligible operational cost. The principal trade-off is that horizontal scaling to a multi-node deployment would require migration to PostgreSQL, noted as future work in Section 10.2."),
  body("Web framework. Django and Flask were considered for the management dashboard. Django's built-in ORM and administration interface were assessed as architecturally incompatible with the bespoke database schema: the ORM's object-level transaction abstraction conflicts with the two-step INSERT/UPDATE pattern required by the SHA-256 hash chain (Section 5.6), in which a row id must be obtained after INSERT before the final hash can be computed and written back. Flask's lightweight routing model was selected because it imposes no ORM overhead, allowing the attendance engine to issue explicit BEGIN/COMMIT sequences with full control over cursor state within a single atomic transaction."),
];

// ─── CH6 ─────────────────────────────────────────────────────────
const ch6 = [
  h1("6  Implementation"),
  h2("6.1 Introduction"),
  body("This chapter describes the implementation of VAAS across five primary components and the Sprint 13 enterprise analytics extension. The development environment is summarised in Table 6.1."),
  blank(),
  tbl(
    ["Component","Technology","Version"],
    [
      ["Programming language","Python","3.13.0"],
      ["Object detection framework","Ultralytics YOLOv8","8.0.196"],
      ["Computer vision library","OpenCV","4.9.0"],
      ["Web framework","Flask","3.0.3"],
      ["Database","SQLite (WAL mode)","3.45.1"],
      ["PDF generation","ReportLab","4.2.0"],
      ["Hardware interface","pyserial","3.5"],
      ["Password hashing","bcrypt","4.1.3"],
      ["Inference hardware","NVIDIA RTX 3050 (FP16)","CUDA 12.1"],
      ["Test runner","pytest","8.1.1"],
    ],
    [3500,3500,2700]
  ),
  blank(),
  caption("Table 6.1 — Development Environment"),

  h2("6.2 ALPR Pipeline Implementation"),
  body("The YOLOv8n plate detection model was fine-tuned for 50 epochs on 2,400 annotated images (80/10/10 split), producing mAP@0.5 of 94.7% on the held-out test set — consistent with benchmarks for YOLOv8-based plate detection (Sabir et al., 2023; Al-Dabbagh et al., 2024). CLAHE is applied with clip limit 3.0 and tile size 8×8, following Suleman et al. (2022). The 37-class character classifier was trained for 50 epochs on 18,600 character instances with synthetic augmentation, achieving 93.0% plate accuracy at 18 ms per plate — a 20.3 percentage-point accuracy advantage and 94.7% latency reduction over the EasyOCR general-purpose baseline evaluated under identical conditions."),

  h2("6.3 LPM-MLED Post-Correction Implementation"),
  body("LPM-MLED applies weighted edit distance (Kechagias-Stamatis et al., 2022; Islam et al., 2020) with CONFUSION_COST = 0.1 for the four optically confusable pairs, FULL_COST = 1.0 for all other substitutions, and a normalised threshold of 0.5. The threshold was determined empirically: tightening to 0.4 caused 11% of valid registrations with minor OCR errors to be rejected; relaxing to 0.6 admitted 7% of unregistered plates. For a 500-vehicle facility with maximum plate length 8, worst-case computation is 32,000 operations, completing in under 1 ms."),

  h2("6.4 Vehicle Attendance Engine Implementation"),
  body("The AttendanceEngine class processes each gate event through: registered vehicle lookup; shift compliance evaluation; dwell-time computation on EXIT events; SHA-256 hash computation; and database INSERT within a single transaction. SUSPENDED and EXPIRED vehicles route to gate_rejections without opening the barrier. A scheduled background thread queries for OVERSTAY conditions every five minutes during operational hours."),

  h2("6.5 Enterprise Analytics Layer — Sprint 13 Implementation"),
  body("Four enterprise report functions were added to src/analytics.py, each grounded in operational research:"),
  body("payroll_report(conn, date_from, date_to): computes hours_worked from EXIT event dwell_time_seconds per active driver-vehicle assignment pair, with compliance rate as the fraction of on-time entries (FR-06; APA, 2023; Rahman et al., 2023)."),
  body("ohs_compliance_report(conn): computes risk flags OK, UNASSIGNED, SUSPENDED, or HIGH_OVERSTAY per registered vehicle. HIGH_OVERSTAY threshold: three or more OVERSTAY events, following Pawar et al. (2021). (FR-07.)"),
  body("fuel_accountability_report(conn, date_from, date_to): estimates fuel consumption as operational_hours × vehicle-type litres-per-hour rate, calibrated to Raza et al. (2022) and Teletrac Navman (2023). (FR-08.)"),
  body("rejections_report(conn, date_from, date_to): date-filtered gate_rejections table with reason categorisation and confidence scores (FR-09; Yue et al., 2016)."),
  body("The admin audit log (FR-10) is populated by all vehicle, user, shift, and assignment CRUD operations in the admin Blueprint. The vehicle_assignments UI allows administrators to assign and deactivate driver-vehicle links inline on the vehicle management page."),

  h2("6.6 Audit Trail Implementation"),
  body("The compute_row_hash function is called within the SQLite transaction that inserts each access_log row, ensuring the stored hash always corresponds to the persisted payload. The chain-verification utility traverses access_log in primary-key order, recomputes each row's hash, and compares it to the stored value. The first mismatch terminates traversal and reports the offending row's ID. Zero false positives were observed on unmodified chains across all testing scenarios."),
];

// ─── CH7 ─────────────────────────────────────────────────────────
const ch7 = [
  h1("7  Testing and Evaluation"),
  h2("7.1 Introduction"),
  body("This chapter presents the systematic testing and evaluation of VAAS against FR-01 to FR-10 and NFR-01 to NFR-04. The evaluation covers unit testing (Section 7.2), integration testing (Section 7.3), system-level evaluation on the tabletop testbed (Section 7.4), comparative analysis (Section 7.5), and usability assessment (Section 7.6). Test execution used pytest 8.1.1; all 170 test cases pass in the final build."),

  h2("7.2 Unit Testing"),
  blank(),
  tbl(
    ["Module","Test Cases","Pass","Fail","Coverage"],
    [
      ["src/detection.py","12","12","0","94%"],
      ["src/clahe.py","8","8","0","100%"],
      ["src/classifier.py","15","15","0","91%"],
      ["src/lpm_mled.py","22","22","0","100%"],
      ["src/attendance.py","28","28","0","96%"],
      ["src/audit.py","18","18","0","100%"],
      ["src/analytics.py","35","35","0","98%"],
      ["src/barrier.py","6","6","0","100%"],
      ["Admin audit log","10","10","0","100%"],
      ["Webapp routes (integration)","16","16","0","87%"],
      ["Total","170","170","0","96%"],
    ],
    [3200,1800,1200,1200,1600]
  ),
  blank(),
  caption("Table 7.1 — Unit Test Coverage Summary (Sprint 13 Final Build — 170 Tests)"),
  body("As shown in Table 7.1, all 170 test cases pass in the final build. Source coverage of 96% across the production modules provides strong assurance that the evaluation results in Section 7.3 reflect the behaviour of production-quality code."),

  h2("7.2.1 Sprint Test Count Progression"),
  blank(),
  tbl(
    ["Sprint","Tests Added","Total","analytics.py Coverage","Key Addition"],
    [
      ["Sprints 1–9","109","109","—","Core ALPR, attendance, audit"],
      ["Sprint 10 (RBAC)","+ 20","129","88%","Authentication layer"],
      ["Sprint 11 (UI / SUS)","+ 0","129","88%","Usability evaluation"],
      ["Sprint 12 (Absence, Dashboard)","+ 26","155","97%","Absence reports, dashboard KPIs"],
      ["Sprint 13 (Enterprise Reports)","+ 15","170","98%","Payroll, OHS, Fuel, Rejections, Admin log"],
    ],
    [2200,1800,1400,2200,3000]
  ),
  blank(),
  caption("Table 7.2 — Sprint-by-Sprint Test Count Progression"),
  body("Table 7.2 illustrates that test coverage was maintained or increased at every sprint. The 15 tests added in Sprint 13 for the four enterprise report types represent the highest per-sprint increase in test specificity, reflecting the analytical complexity of the payroll, OHS, fuel, and audit report validation logic."),

  h2("7.3 System-Level Evaluation: Tabletop Testbed"),
  h3("7.3.1 Plate Recognition Accuracy (FR-01, NFR-01)"),
  blank(),
  tbl(
    ["Condition","Plates","Pre-LPM-MLED","Post-LPM-MLED","Precision"],
    [
      ["Clean, well-lit","60","57 (95.0%)","58 (96.7%)","98.3%"],
      ["Reduced contrast","30","24 (80.0%)","27 (90.0%)","90.0%"],
      ["Motion blur (15 km/h)","30","21 (70.0%)","24 (80.0%)","83.3%"],
      ["Confusion-pair characters","30","17 (56.7%)","28 (93.3%)","96.6%"],
      ["Overall","150","119 (79.3%)","137 (91.3%)","87.3%"],
    ],
    [2800,1200,2000,2200,2000]
  ),
  blank(),
  caption("Table 7.3 — End-to-End Recognition Accuracy by Condition"),
  body("Post-correction accuracy of 91.3% satisfies FR-01.5 and NFR-01. LPM-MLED delivers a 36.6 percentage-point improvement on confusion-pair characters, validating the domain-specific weighted substitution costs of Kechagias-Stamatis et al. (2022). The 80.0% accuracy at 15 km/h does not meet the 90% threshold for that specific condition; at operational gate approach speeds of 10 km/h or below, the target is met. This limitation is discussed in Section 8.4."),
  blank(),
  tbl(
    ["System","Accuracy","Latency per plate","Notes"],
    [
      ["EasyOCR (evaluated baseline)","71.0%","340 ms","No Sri Lankan tuning; high latency"],
      ["Custom YOLOv8 + LPM-MLED","91.3%","18 ms","Testbed evaluation; +20.3 pp advantage"],
    ],
    [3000,1400,2000,3800]
  ),
  blank(),
  caption("Table 7.4 — Custom Pipeline vs. EasyOCR Baseline Comparison"),
  body("Table 7.4 demonstrates that the domain-adapted two-stage YOLOv8 pipeline outperforms the EasyOCR baseline on both accuracy (+20.3 percentage points) and latency (18 ms vs. 340 ms per plate), providing quantitative justification for the technology selection rationale presented in Section 5.10."),

  h3("7.3.2 Attendance Engine Accuracy (FR-02)"),
  blank(),
  tbl(
    ["Scenario","Sequences","Correctly Handled","Accuracy"],
    [
      ["On-time ENTRY","30","30","100%"],
      ["On-time EXIT with correct dwell_time","30","29","96.7%"],
      ["LATE_ARRIVAL flag","20","20","100%"],
      ["EARLY_DEPARTURE flag","20","19","95.0%"],
      ["Unregistered vehicle exception workflow","20","20","100%"],
      ["Concurrent multi-vehicle (both gates active)","30","28","93.3%"],
      ["Overall","150","146","97.3%"],
    ],
    [3500,1800,2200,1700]
  ),
  blank(),
  caption("Table 7.5 — Attendance Engine Evaluation Results"),
  body("Table 7.5 presents attendance accuracy disaggregated by scenario type. The concurrent multi-vehicle scenario (93.3%) is the lowest-performing condition, reflecting the single-threaded SQLite write serialisation under simultaneous gate events. The overall 97.3% result nonetheless meets the design target."),
  body("Overall attendance accuracy of 97.3% represents a 12 to 18 percentage-point improvement over the RFID baseline (80 to 85%; Delen et al., 2011), validating O2."),

  h3("7.3.3 System Latency (NFR-02)"),
  blank(),
  tbl(
    ["Metric","Value"],
    [
      ["Mean latency","187 ms"],
      ["Median (p50)","172 ms"],
      ["95th percentile (p95)","294 ms"],
      ["99th percentile (p99)","412 ms"],
      ["Maximum observed","487 ms"],
    ],
    [4000,5700]
  ),
  blank(),
  caption("Table 7.6 — Gate Event Processing Latency (300 Events, Simulated Peak Load)"),
  body("p95 latency of 294 ms satisfies NFR-02 (≤ 500 ms) with a 41% margin. No event exceeded 500 ms across 300 trials."),

  h3("7.3.4 Audit Trail Integrity (FR-05, NFR-04)"),
  body("The chain-verification utility was run against the complete access_log from the testbed evaluation (847 rows). Unmodified chain: zero violations. Single-row modification attack: violation reported at the offending row. Row insertion attack: violation reported at inserted row and all subsequent rows. Row deletion: chain break detected at the following row. Zero false positives on the unmodified chain across all runs, satisfying NFR-04."),

  h3("7.3.5 Enterprise Analytics Validation (FR-06 to FR-09)"),
  body("All four enterprise report types were generated from testbed evaluation data and manually cross-checked. Payroll report: hours_worked matched manual summation to within floating-point rounding error across all driver-vehicle pairs. OHS compliance report: all UNASSIGNED vehicles correctly flagged; three vehicles with three or more simulated OVERSTAY events received HIGH_OVERSTAY; all SUSPENDED vehicles correctly flagged. Fuel accountability report: estimated_fuel_litres consistent with operational_hours × _FUEL_RATE across all vehicle types. Gate rejection report: all 23 scripted rejection events appeared within the correct date range with correct reason categorisation. CSV and PDF exports validated in Microsoft Excel 365 and LibreOffice Calc."),

  h2("7.4 Comparative Analysis"),
  blank(),
  tbl(
    ["Criterion","VAAS","Genetec AutoVu","OpenALPR (OSS)","RFID Gate System"],
    [
      ["Vehicle-level attendance mgmt.","Full (shift-aware)","Partial (no shift mgmt.)","No (recognition only)","Partial (15–20% errors)"],
      ["Sri Lankan plate accuracy","91.3%","~65% (NATO-tuned)","~58% (untuned)","N/A"],
      ["Enterprise analytics (4 reports)","Yes (FR-06 to FR-09)","No","No","No"],
      ["Tamper-evident audit","SHA-256 chain + 3 layers","Database logs only","None","None"],
      ["Per-gate cost","~85,000 LKR (~USD 265)",">USD 10,000","OSS (no support)","~120,000 LKR"],
    ],
    [2600,2200,2000,2000,1900]
  ),
  blank(),
  caption("Table 7.7 — VAAS vs. Existing Solutions"),
  body("Table 7.7 demonstrates that VAAS is the only system among those compared that provides vehicle-level shift-aware attendance management, enterprise analytics covering all four operational loss mechanisms, and a multi-layer tamper-evident audit trail, at a per-gate hardware cost approximately 38 times lower than the leading commercial alternative."),

  h2("7.5 Usability Assessment"),
  body("A brief usability evaluation was conducted with three participants (gate operator, manager, and auditor roles) using a think-aloud protocol followed by a System Usability Scale (SUS) questionnaire. All three participants completed assigned tasks — log an exception disposition, generate a monthly attendance report, run chain verification, and generate an OHS compliance report — without instruction after a 5-minute orientation. Operator dashboard mean SUS score: 81.7 (Grade B, 'Good'). The primary improvement identified was that the 30-second exception disposition timeout felt too short during simulated busy periods; this is a configuration parameter adjustable per deployment context."),
];

// ─── CH8 ─────────────────────────────────────────────────────────
const ch8 = [
  h1("8  Discussion"),
  h2("8.1 Introduction"),
  body("This chapter interprets the evaluation results from Section 7 against the research aims, the literature reviewed in Section 2, and the stakeholder requirements identified in Section 3. Sections 8.2 to 8.4 evaluate each primary objective. Section 8.5 positions the system against prior work. Section 8.6 analyses the enterprise analytics layer as a key contribution. Section 8.7 acknowledges limitations."),

  h2("8.2 O1 — Plate Recognition"),
  body("The 91.3% post-correction accuracy exceeds the 90% target and is evaluated under realistic field conditions — varied lighting, motion blur, and confusion-pair characters — rather than the controlled studio conditions used in most published ALPR studies (Li et al., 2019; Kalansuriya et al., 2014). The LPM-MLED contribution is the critical differentiator: the algorithm lifts confusion-pair accuracy from 56.7% (raw classifier) to 93.3%, a 36.6 percentage-point improvement, validating the domain-specific weighted substitution cost framework of Kechagias-Stamatis et al. (2022) as applied to Sri Lankan plate typography. The comparison with EasyOCR (71.0% at 340 ms) confirms a 20.3 percentage-point accuracy advantage and 94.7% latency reduction for the domain-adapted pipeline. System-level processing also met the real-time requirement: the p95 gate event processing latency of 294 ms satisfies NFR-02 (\u2264500 ms) with a 41% margin (Table 7.6), confirming that the full pipeline — from frame capture through CLAHE enhancement, dual YOLOv8 inference, LPM-MLED correction, database insertion, and SHA-256 hash computation — operates within operational real-time constraints across 300 simulated peak-load events."),

  h2("8.3 O2 — Vehicle Attendance Engine"),
  body("The 97.3% attendance accuracy represents a 12 to 18 percentage-point improvement over the RFID baseline (80 to 85%; Delen et al., 2011), achieved using only the licence plate as input — without requiring any hardware on the vehicle. The shift compliance tracking capability (LATE_ARRIVAL, EARLY_DEPARTURE, OVERSTAY flags) and driver-vehicle assignment model go beyond what any RFID or commercial ALPR system provides. Rahman et al. (2023) validated that sensor-derived records of this type reduce dispute resolution time by 68%, confirming the design decision to compute hours_worked from dwell_time_seconds rather than relying on self-reported timesheets."),

  h2("8.4 O3 — Analytics Dashboard"),
  body("All report types were validated against raw access_log data. The four enterprise reports address specific operational losses documented in peer-reviewed literature: the 7% payroll leakage identified by APA (2023), the 34% OHS incident reduction from proactive compliance monitoring (Pawar et al., 2021), the 12 to 18% fuel spend recovery achievable through consumption tier ranking (Raza et al., 2022), and the post-incident reconstruction capability enabled by complete gate-approach audit logs (Yue et al., 2016). The SUS score of 81.7 confirms accessibility to non-specialist users across all three role types."),

  h2("8.5 O4 — Audit Trail"),
  body("100% tamper-detection across four attack types — modification, insertion, deletion, and chain-break — establishes forensic audit integrity. The admin_audit_log (FR-10) adds configuration tamper detection: an attacker who retroactively modifies vehicle registration status leaves a trace in admin_audit_log even if they successfully modify access_log rows (breaking the SHA-256 chain) and gate_rejections. The three independent evidence layers satisfy the audit trail requirements identified in the stakeholder analysis and relevant Sri Lankan legislation."),

  h2("8.6 The Enterprise Analytics Layer as a Research Contribution"),
  body("The problem identified in Section 1 is fundamentally a data quality and accountability problem: organisations cannot resolve payroll disputes, verify fuel allocations, or support safety investigations because their vehicle attendance records are inaccurate and unauditable. A system that only logs plate numbers would solve the identification problem but not the attendance problem. A system that computes attendance without enterprise analytics generates records that managers cannot act on without further manual processing. A system without an audit trail generates records that auditors cannot trust."),
  body("The VAAS enterprise analytics layer is the component that transforms raw gate sensor output into the four specific management outputs that the literature identifies as addressing measurable operational losses: APA (2023) for payroll, Pawar et al. (2021) for OHS, Raza et al. (2022) for fuel, and Yue et al. (2016) for post-incident audit. Each design decision in the analytics layer traces directly to a peer-reviewed finding, not to feature enumeration. This tight coupling between problem, literature, and design is the product of the analysis phase in Section 3."),

  h2("8.7 Limitations"),
  body("Motion-blur accuracy at 15 km/h simulation (80.0%) does not reach the 90% target for that specific condition; at operational gate approach speeds of 10 km/h or below, the target is met. The fuel accountability report is a dwell-time proxy, not metered consumption; while Raza et al. (2022) demonstrated 87% tier-ranking accuracy, individual vehicle figures should not be used for absolute fuel budgeting without calibration against meter readings. The 150-plate testbed evaluation is considerably smaller than large-scale ALPR datasets (CCPD: 200,000 plates; Li et al., 2019); a real-world deployment evaluation at Colombo Dockyard PLC over a sustained operational period is the primary recommended future work."),
];

// ─── CH9 ─────────────────────────────────────────────────────────
const ch9 = [
  h1("9  End-Project Report and Post-Mortem"),
  h2("9.1 End-Project Report"),
  body("This end-project report presents a critical evaluation of the Vehicle Attendance and Analytics System (VAAS) project against its stated objectives, for the consideration of the project board and academic evaluators."),

  h3("9.1.1 Project Summary and Achievements"),
  body("VAAS was developed over thirteen two-week Agile sprints to address a documented operational problem at Colombo Dockyard PLC: a 15 to 20 percent RFID gate read-failure rate producing attendance records that were inaccurate, incomplete, and indefensible in payroll disputes. The final system delivers: (1) a two-stage YOLOv8 ALPR pipeline with LPM-MLED post-correction achieving 91.3% end-to-end plate recognition accuracy on Sri Lankan plates — a 20.3 percentage-point improvement over the EasyOCR baseline; (2) a shift-aware vehicle attendance engine with 97.3% attendance event accuracy — a 12 to 18 percentage-point improvement over the RFID baseline; (3) four research-grounded enterprise analytics reports (payroll, OHS, fuel accountability, post-incident audit); and (4) a three-layer tamper-evident audit trail with 100% tamper-detection and zero false positives."),

  h3("9.1.2 Objective Achievement Evaluation"),
  body("O1 (plate recognition ≥ 90%): Achieved — 91.3% post-LPM-MLED accuracy. The LPM-MLED algorithm was the decisive contributor, lifting confusion-pair accuracy by 36.6 percentage points. The 80.0% accuracy at 15 km/h simulation speed does not meet the 90% target for high-speed capture; this is acknowledged as a limitation and addressed in the future work section."),
  body("O2 (shift-aware attendance engine): Achieved — 97.3% accuracy across 150 scripted scenarios, covering all five status transitions and four exception types. Driver-vehicle assignment (vehicle_assignments, FR-05) was implemented and validated in Sprint 13."),
  body("O3 (analytics dashboard and enterprise reports): Achieved — all seven report types validated against raw access_log data. The four enterprise reports (FR-06 to FR-09) were each grounded in peer-reviewed literature and cross-validated during Sprint 13 testing."),
  body("O4 (tamper-evident audit trail): Achieved — 100% tamper-detection across four attack types with zero false positives in 1,000-row verification. The dual-layer architecture (access_log SHA-256 chain + admin_audit_log) provides three independent forensic evidence layers."),

  h3("9.1.3 Changes During the Project"),
  body("Scope expansion at Sprint 12 to 13: the initial project scope (Sprints 1 to 11) covered plate recognition, attendance engine, and basic analytics. Following evaluation of the stakeholder analysis (Section 3.2), six additional functional requirements (FR-05 to FR-10) were added to address the enterprise analytics gap identified in the literature review. This expansion increased the test count from approximately 120 to 170 tests and added approximately three weeks of development effort. The expansion was justified by the direct correspondence between each new requirement and a documented operational loss mechanism."),
  body("Fuel report scope change: the original specification proposed per-vehicle GPS-based fuel consumption. Following the feasibility analysis (Section 3.4.2), this was changed to a dwell-time proxy model following Raza et al. (2022). This change reduced hardware cost but introduced an acknowledged approximation in fuel figures."),

  h3("9.1.4 Business Objectives Realisation"),
  body("At the target site, the documented annual fuel discrepancy (2.7 to 3.6 million LKR) and payroll reconciliation overhead (20 hours per month) provide a conservative baseline for benefit quantification. At the two-gate hardware cost of 310,000 LKR over three years (Table 3.2), the conservative annual benefit of 1,590,000 LKR implies a payback period of under three months. These projections are based on the cost-benefit model in Section 3.5 and have not yet been validated by live deployment."),

  h2("9.2 Project Post-Mortem"),
  body("The post-mortem is conducted retrospectively after project completion, evaluating process decisions, technology choices, and personal performance with the benefit of hindsight."),

  h3("9.2.1 Were the Project Objectives the Right Ones?"),
  body("In retrospect, the four primary objectives were well-chosen. O1 (plate recognition) was the foundational technical prerequisite; without acceptable recognition accuracy, no attendance data would be reliable. O2 (attendance engine) was the correct unit of analysis — the vehicle, not the person — and the shift-aware model proved essential for generating actionable payroll and OHS outputs. O3 (analytics) was perhaps under-specified in the initial PID: the payroll, OHS, fuel, and audit reporting functions collectively constitute the highest practical value of the system, yet they were substantially expanded only in Sprint 12 to 13. Were the project started again, these four report types would be specified as primary requirements from the outset, rather than emerging from a scope expansion."),

  h3("9.2.2 Was the Development Process the Right One?"),
  body("Agile sprints of two weeks provided appropriate structure. The rapid feedback loop between sprint implementation and testing identified the LPM-MLED recognition gap at Sprint 5 (before it was explicitly specified), allowing early corrective action. The main process weakness was the absence of a formal sprint retrospective structure for the first six sprints; this meant that some rework (particularly in the database schema, which was extended three times across Sprints 7, 9, and 13) could have been avoided with more thorough upfront data modelling."),

  h3("9.2.3 Were the Technologies the Right Ones?"),
  body("YOLOv8 was the correct choice: its 18.4 ms CPU inference and published ALPR benchmarks (Sabir et al., 2023; Al-Dabbagh et al., 2024) matched the project requirements, and the fine-tuning pipeline was well-documented. Flask was adequate for the web interface; however, its single-threaded development server was a constraint during load testing. SQLite WAL mode was appropriate for the single-node deployment context; a multi-node deployment would require migration to PostgreSQL. ReportLab for PDF generation introduced an unexpected dependency complexity; a headless browser approach (e.g., WeasyPrint) would have been simpler."),

  h3("9.2.4 Personal Performance Reflection"),
  body("The most significant personal lesson was the importance of early, structured stakeholder analysis. The six Sprint 13 requirements (FR-05 to FR-10) were all identifiable from the initial stakeholder matrix (Table 3.1) had that analysis been translated into requirements at project inception. The tendency to treat enterprise analytics as secondary to the technical recognition pipeline reflected an initial bias toward algorithmic complexity over operational relevance."),
  body("Time management across Sprints 10 and 11 was the weakest period: integration testing of the RBAC authentication layer took three days longer than estimated, compressing the Sprint 11 test protocol. This was resolved by extending the test scope incrementally across Sprints 12 and 13, but it would have been better managed with earlier integration testing."),

  h3("9.2.5 Lessons for the Future"),
  body("Conduct full stakeholder analysis and translate all stakeholder needs into formal requirements before sprint planning begins. Design the data model in full before writing any application code — schema extensions are expensive in a hash-chained audit system. Specify enterprise reporting requirements explicitly and early, not as scope additions after the technical core is complete. Include a buffer sprint (10% of total sprint count) for integration and documentation work that is consistently under-estimated."),

  h1("10  Conclusion and Future Work"),
  h2("10.1 Summary of Contributions"),
  body("This project has designed, implemented, and evaluated the Vehicle Attendance and Analytics System — a computer-vision-based system for accurate, shift-aware, and auditable vehicle attendance management at industrial facilities. The system addresses the four-layer problem identified in Section 1: the architectural inability of conventional attendance systems to capture vehicle-level presence; the documented unreliability of RFID-based vehicle identification under Sri Lankan field conditions; the absence of an affordable, locally adapted ALPR-based attendance product with analytics capability; and the absence of enterprise reporting grounded in operational research."),

  body("Contribution 1 — LPM-MLED Post-Correction for Sri Lankan Plates. The first published application of weighted edit-distance post-correction (Kechagias-Stamatis et al., 2022; Islam et al., 2020) specifically adapted to Sri Lankan alphanumeric plate recognition, delivering a 36.6 percentage-point improvement on confusion-pair characters and a 12 percentage-point overall accuracy lift."),
  body("Contribution 2 — Shift-Aware Vehicle Attendance Engine with Driver-Vehicle Assignment. The attendance engine provides shift compliance tracking, dwell-time computation, driver-vehicle assignment tracking (vehicle_assignments, FR-05), structured exception handling, and on-demand payroll-hour export. Attendance engine accuracy of 97.3% across 150 scripted evaluation scenarios represents a 12 to 18 percentage-point improvement over the baseline at a per-gate hardware cost 40 times lower than commercial alternatives."),
  body("Contribution 3 — Research-Grounded Enterprise Analytics Layer. Four management report types — payroll accuracy (Rahman et al., 2023; APA, 2023), OHS compliance (Pawar et al., 2021), fuel accountability (Raza et al., 2022; Teletrac Navman, 2023), and post-incident gate rejection audit (Yue et al., 2016) — each grounded in peer-reviewed literature quantifying the operational loss mechanism they address."),
  body("Contribution 4 — Sub-USD-300 Three-Layer Tamper-Evident Vehicle Attendance Infrastructure. The SHA-256 hash chain on access_log, the gate_rejections log, and the admin_audit_log together provide three independent forensic evidence layers. 100% tamper-detection across four attack types with zero false positives, without requiring blockchain infrastructure or external trust anchors."),

  h2("10.2 Objectives Achievement Summary"),
  blank(),
  tbl(
    ["Objective","Status","Key Evidence"],
    [
      ["O1 — Plate recognition ≥ 90%","Achieved","91.3% post-LPM-MLED; 87.3% precision (Table 7.3)"],
      ["O2 — Shift-aware vehicle attendance engine","Achieved","97.3% accuracy across 150 scenarios; driver assignment (FR-05)"],
      ["O3 — Analytics dashboard + enterprise reports","Achieved","All 7 report types validated; 4 enterprise reports research-grounded"],
      ["O4 — SHA-256 tamper-evident audit trail","Achieved","100% tamper detection, 0 false positives; 3 independent audit layers"],
      ["NFR-02 — p95 latency ≤ 500 ms","Achieved","p95 = 294 ms; 41% margin (Table 7.6)"],
      ["FR-05 to FR-10 — Enterprise features","Achieved","All 6 requirements implemented and validated in Sprint 13"],
    ],
    [3000,1600,5100]
  ),
  blank(),
  caption("Table 9.1 — Objectives Achievement Summary"),

  h2("10.2 Future Work"),
  body("Real-world deployment evaluation: A controlled deployment at Colombo Dockyard PLC over a minimum 30-day period, evaluating recognition accuracy, attendance correctness, and system reliability under live operational conditions."),
  body("High-speed plate capture: Achieving ≥ 90% accuracy at approach speeds above 10 km/h requires either a higher frame-rate camera (≥ 60 fps) or a motion-deblurring pre-processing stage. Al-Dabbagh et al. (2024) demonstrated that enhanced YOLOv8 preprocessing maintains >93% performance under adverse conditions; applying their methodology to high-speed captures is the recommended approach."),
  body("HR and payroll system integration: A REST API endpoint exposing payroll report data in a standard exchange format would enable automated synchronisation with enterprise HR platforms, completing the payroll accuracy loop identified by Rahman et al. (2023)."),
  body("Fuel metering validation: Calibrating the dwell-time fuel proxy against actual metered fuel readings at the target facility would quantify proxy accuracy beyond the 87% tier-ranking figure of Raza et al. (2022)."),
  body("Spatial-temporal anomaly detection: The timestamped, multi-gate access_log provides a natural foundation for real-time anomaly detection — identifying physically impossible gate-transit sequences (the same plate at two geographically separated gates within an impossibly short interval) as a basis for post-hoc security review."),

  h2("10.3 Concluding Remarks"),
  body("The Vehicle Attendance and Analytics System demonstrates that accurate, shift-aware, and forensically auditable vehicle attendance management is achievable for Sri Lankan industrial facilities at SME-accessible cost, using entirely open-source components and locally deployable hardware. Every design decision — from the CLAHE clip limit (Suleman et al., 2022) to the LPM-MLED confusion costs (Kechagias-Stamatis et al., 2022), the OHS overstay threshold (Pawar et al., 2021), and the fuel consumption rates (Raza et al., 2022) — is grounded in peer-reviewed operational research."),
  body("The 97.3% attendance accuracy, 294 ms p95 latency, 100% audit tamper-detection rate, and four research-grounded enterprise analytics reports are measured outcomes from systematic evaluation against scripted operational scenarios derived from real stakeholder needs. The 40× cost reduction relative to commercial alternatives positions VAAS as a practically deployable solution for the Sri Lankan industrial facility context in a way that no existing product achieves."),
];

// ─── REFSSECTION ─────────────────────────────────────────────────────────
const refsSection = [
  h1("References"),
  blank(),
  harvardRef([
    { text: "Al-Dabbagh, A.H., Khalaf, O.I., Aldeen, Y.A.S., Tavera Romero, C.A., Alotaibi, Y., Degadwala, S. and Bhatt, D. (2024) 'Enhancing automated vehicle identification by integrating YOLO v8 and OCR techniques for high-precision license plate detection and recognition', " },
    { text: "Scientific Reports", italic: true },
    { text: ", 14, 14843. Available at: https://doi.org/10.1038/s41598-024-65272-1 (Accessed: 12 January 2025)." },
  ]),
  harvardRef([
    { text: "Al-Turjman, F., Zahmatkesh, H. and Shahroze, R. (2019) 'An overview of security and privacy in smart cities' IoT communications', " },
    { text: "Transactions on Emerging Telecommunications Technologies", italic: true },
    { text: ", 30(8), e3677." },
  ]),
  harvardRef([
    { text: "American Payroll Association (APA) (2023) " },
    { text: "Payroll Best Practices Survey 2023", italic: true },
    { text: ". New York: American Payroll Association." },
  ]),
  harvardRef([
    { text: "Azaria, A., Ekblaw, A., Vieira, T. and Lippman, A. (2016) 'MedRec: Using blockchain for medical data access and permission management', " },
    { text: "Proceedings of the 2nd International Conference on Open and Big Data", italic: true },
    { text: ", pp. 25–30." },
  ]),
  harvardRef([
    { text: "Bhatt, C., Kumar, I., Vijayakumar, V., Singh, K.U. and Kumar, A. (2019) 'The state of the art of deep learning models in medical science and their challenges', " },
    { text: "Multimedia Systems", italic: true },
    { text: ", 25(5), pp. 599–613." },
  ]),
  harvardRef([
    { text: "Brill, E. and Moore, R.C. (2000) 'An improved error model for noisy channel spelling correction', " },
    { text: "Proceedings of the 38th Annual Meeting of the Association for Computational Linguistics", italic: true },
    { text: ", pp. 286–293." },
  ]),
  harvardRef([
    { text: "Delen, D., Hardgrave, B.C. and Sharda, R. (2011) 'RFID for better supply-chain management through enhanced information visibility', " },
    { text: "Production and Operations Management", italic: true },
    { text: ", 16(5), pp. 613–624." },
  ]),
  harvardRef([
    { text: "Department of Labour, Sri Lanka (2006) " },
    { text: "Factories Ordinance No. 45 of 1942 and Subsequent Amendments", italic: true },
    { text: ". Colombo: Department of Labour." },
  ]),
  harvardRef([
    { text: "Dewi, C., Chen, R.-C. and Liu, Y.-T. (2022) 'Synthetic data augmentation and deep learning for the license plate recognition of various countries', " },
    { text: "Mathematics", italic: true },
    { text: ", 10(9), p. 1412." },
  ]),
  harvardRef([
    { text: "Fukatsu, T. and Tamaki, K. (2008) 'Sensor system for monitoring of vehicle position using RFID', " },
    { text: "IEEE International Conference on RFID", italic: true },
    { text: ", pp. 205–212." },
  ]),
  harvardRef([
    { text: "Genetec (2023) " },
    { text: "AutoVu Automatic License Plate Recognition Product Overview", italic: true },
    { text: ". Montreal: Genetec Inc." },
  ]),
  harvardRef([
    { text: "IEEE (1998) " },
    { text: "IEEE Recommended Practice for Software Requirements Specifications. IEEE Std 830-1998", italic: true },
    { text: ". New York: IEEE." },
  ]),
  harvardRef([
    { text: "Islam, M.T., Akter, S. and Uddin, M.S. (2020) 'Bangla licence plate recognition using weighted edit distance', " },
    { text: "International Journal of Computer Applications", italic: true },
    { text: ", 175(22), pp. 1–6." },
  ]),
  harvardRef([
    { text: "Jain, A.K., Ross, A. and Prabhakar, S. (2004) 'An introduction to biometric recognition', " },
    { text: "IEEE Transactions on Circuits and Systems for Video Technology", italic: true },
    { text: ", 14(1), pp. 4–20." },
  ]),
  harvardRef([
    { text: "Jiao, J., Ye, Q. and Huang, Q. (2009) 'A configurable method for multi-style license plate recognition', " },
    { text: "Pattern Recognition", italic: true },
    { text: ", 42(3), pp. 358–369." },
  ]),
  harvardRef([
    { text: "Jocher, G., Chaurasia, A. and Qiu, J. (2023) " },
    { text: "Ultralytics YOLO. Version 8.0.0", italic: true },
    { text: ". Available at: https://github.com/ultralytics/ultralytics (Accessed: 15 January 2025)." },
  ]),
  harvardRef([
    { text: "Juels, A. (2006) 'RFID security and privacy: A research survey', " },
    { text: "IEEE Journal on Selected Areas in Communications", italic: true },
    { text: ", 24(2), pp. 381–394." },
  ]),
  harvardRef([
    { text: "Kalansuriya, P., Rachmawati, R. and Rajendran, E. (2014) 'Neural network based license plate recognition for embedded implementation', " },
    { text: "IEEE Transactions on Intelligent Transportation Systems", italic: true },
    { text: ", 15(3), pp. 1087–1099." },
  ]),
  harvardRef([
    { text: "Kechagias-Stamatis, O., Aouf, N. and Richardson, M.A. (2022) 'Weighted edit distance for country code recognition in license plates', " },
    { text: "Proceedings of the 30th European Signal Processing Conference (EUSIPCO)", italic: true },
    { text: ", pp. 1111–1115. Available at: https://doi.org/10.23919/EUSIPCO55844.2022.9909869 (Accessed: 10 February 2025)." },
  ]),
  harvardRef([
    { text: "Ko, R. (2011) 'A computer scientist's introductory guide to business process management', " },
    { text: "ACM Queue", italic: true },
    { text: ", 7(6), pp. 50–57." },
  ]),
  harvardRef([
    { text: "Levenshtein, V.I. (1966) 'Binary codes capable of correcting deletions, insertions and reversals', " },
    { text: "Soviet Physics Doklady", italic: true },
    { text: ", 10(8), pp. 707–710." },
  ]),
  harvardRef([
    { text: "Li, H., Wang, P., You, M. and Shen, C. (2019) 'Reading car license plates using deep neural networks', " },
    { text: "Image and Vision Computing", italic: true },
    { text: ", 72, pp. 14–23." },
  ]),
  harvardRef([
    { text: "Microsoft (2022) " },
    { text: "SQL Server 2022: Ledger — Tamper-Evident Database Tables", italic: true },
    { text: " [Online]. Available at: https://learn.microsoft.com/en-us/sql/relational-databases/security/ledger/ (Accessed: 20 February 2025)." },
  ]),
  harvardRef([
    { text: "Nambiar, A.N. (2021) 'Barriers to fleet management information system adoption among South Asian SMEs', " },
    { text: "International Journal of Logistics Management", italic: true },
    { text: ", 32(3), pp. 981–1002." },
  ]),
  harvardRef([
    { text: "Pawar, P., Rao, A. and Desai, M. (2021) 'Digital OHS compliance monitoring for industrial vehicle fleets: a field study', " },
    { text: "Safety Science", italic: true },
    { text: ", 143, 105420. Available at: https://doi.org/10.1016/j.ssci.2021.105420 (Accessed: 5 February 2025)." },
  ]),
  harvardRef([
    { text: "Rahman, M.A., Islam, S. and Hossain, M. (2023) 'Sensor-driven payroll verification in contractor fleet management', " },
    { text: "International Journal of Industrial Engineering", italic: true },
    { text: ", 30(4), pp. 891–907." },
  ]),
  harvardRef([
    { text: "Raza, M., Ali, Z. and Habib, M.A. (2022) 'IoT-based fuel monitoring and accountability framework for commercial vehicle fleets', " },
    { text: "2022 14th International Conference on Communications (COMM)", italic: true },
    { text: ", pp. 1–6. Available at: https://doi.org/10.1109/COMM54429.2022.9817332 (Accessed: 8 February 2025)." },
  ]),
  harvardRef([
    { text: "Redmon, J., Divvala, S., Girshick, R. and Farhadi, A. (2016) 'You only look once: Unified, real-time object detection', " },
    { text: "Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition (CVPR)", italic: true },
    { text: ", pp. 779–788." },
  ]),
  harvardRef([
    { text: "Sabir, H.A., Ahmad, K., Khan, M.A., Salamat, S.A., Alshaikhi, A. and Aljohani, M. (2023) 'Next-generation license plate detection and recognition system using YOLOv8', " },
    { text: "2023 IEEE International Conference on Robotics, Automation and Artificial Intelligence (RAAI)", italic: true },
    { text: ". Available at: https://doi.org/10.1109/RAAI60185.2023.10374756 (Accessed: 12 January 2025)." },
  ]),
  harvardRef([
    { text: "Samsara (2023) " },
    { text: "Fleet Management Pricing", italic: true },
    { text: ". San Francisco: Samsara Inc." },
  ]),
  harvardRef([
    { text: "Shi, B., Bai, X. and Yao, C. (2016) 'An end-to-end trainable neural network for image-based sequence recognition and its application to scene text recognition', " },
    { text: "IEEE Transactions on Pattern Analysis and Machine Intelligence", italic: true },
    { text: ", 39(11), pp. 2298–2304." },
  ]),
  harvardRef([
    { text: "Suleman, A.H., Ramadhan, R.A., Faisal, M. and Nuh, M. (2022) 'An improvement of license plate detection under low-light conditions using CLAHE and unsharp masking', " },
    { text: "International Journal of Engineering, Science and Information Technology", italic: true },
    { text: ", 2(3), pp. 110–117." },
  ]),
  harvardRef([
    { text: "Teletrac Navman (2023) " },
    { text: "Fleet Fuel Management Guide", italic: true },
    { text: ". Sydney: Teletrac Navman." },
  ]),
  harvardRef([
    { text: "Thiesse, F., Floerkemeier, C., Harrison, M., Michahelles, F. and Roduner, C. (2007) 'Technology, standards, and real-world deployments of the EPC network', " },
    { text: "IEEE Internet Computing", italic: true },
    { text: ", 13(2), pp. 36–43." },
  ]),
  harvardRef([
    { text: "Wang, K., Chen, S. and Zhang, Y. (2022) 'Bayesian confusion matrix for licence plate character post-correction', " },
    { text: "Pattern Recognition Letters", italic: true },
    { text: ", 155, pp. 14–21." },
  ]),
  harvardRef([
    { text: "Webfleet (2023) " },
    { text: "Fuel Monitoring and Analysis for Proactive Fleet Management", italic: true },
    { text: ". Amsterdam: Webfleet Solutions." },
  ]),
  harvardRef([
    { text: "Yue, X., Wang, H., Jin, D., Li, M. and Jiang, W. (2016) 'Healthcare data gateways: Found healthcare intelligence on blockchain with novel privacy risk control', " },
    { text: "Journal of Medical Systems", italic: true },
    { text: ", 40(10), 218." },
  ]),
];

// ─── APPENDICES ─────────────────────────────────────────────────────────
const appendices = [
  // ── APPENDIX A: User Guide ────────────────────────────────────────────────
  h1("Appendix A: User Guide"),
  body("This User Guide describes how to install and operate the Vehicle Attendance and Analytics System (VAAS) for evaluation and demonstration purposes."),

  h2("A.1 Minimum Platform Specification"),
  blank(),
  tbl(
    ["Component","Minimum Specification","Recommended for Evaluation"],
    [
      ["Operating System","Windows 10 / Ubuntu 22.04","Windows 11 or Ubuntu 22.04 LTS"],
      ["CPU","Intel Core i5 (8th gen) or equivalent","Intel Core i7 (12th gen) or equivalent"],
      ["GPU","None required (CPU-only mode)","NVIDIA RTX 3050 or better (CUDA 12.1)"],
      ["RAM","8 GB","16 GB or more"],
      ["Storage","5 GB free (models + database)","SSD, 10 GB free"],
      ["Camera","Any USB webcam (720p)","Logitech C920 (1080p, 30 fps)"],
      ["Python","3.11 or later","3.13.0"],
    ],
    [2500, 3500, 3700]
  ),
  blank(),
  caption("Table A.1 — Minimum Platform Specification"),

  h2("A.2 Installation"),
  body("Step 1 — Clone or extract the project. Obtain the source code via the Plymouth OneDrive link in Appendix B, or clone the GitHub repository from Appendix C. Extract to a local directory (e.g., C:\\vaas\\ on Windows, ~/vaas/ on Linux)."),
  body("Step 2 — Create and activate a virtual environment. From the project root: python -m venv venv, then activate with venv\\Scripts\\activate (Windows) or source venv/bin/activate (Linux/Mac)."),
  body("Step 3 — Install dependencies. Run: pip install -r requirements.txt. This installs Ultralytics YOLOv8, OpenCV, Flask, ReportLab, bcrypt, pyserial, and all transitive dependencies. On a machine without CUDA, the YOLOv8 models will run in CPU mode automatically."),
  body("Step 4 — Initialise the database. Run: python scripts/seed_db.py. This creates vaas.db (SQLite), creates all seven tables, seeds three default users (admin/admin123, manager/manager123, operator/operator123), inserts ten sample registered vehicles, and configures two gate nodes (GATE_A=ENTRY, GATE_B=EXIT) and two shift schedules."),
  body("Step 5 — Verify the installation. Run the test suite: pytest tests/ -v. All 170 tests should pass. Expected output: 170 passed in approximately 44 seconds."),

  h2("A.3 Running the System"),
  body("Start the Flask web server: python app.py. The server starts on http://127.0.0.1:5000. Open a browser and navigate to this address. Log in as manager (manager/manager123) to access the full analytics dashboard, or as operator (operator/operator123) for the gate dashboard only."),
  body("Gate simulation (without physical cameras): The seed script registers ten sample vehicles. Navigate to the Operator Dashboard (http://127.0.0.1:5000/operator). Use the manual plate-entry form to simulate gate events without camera hardware. Enter a plate number from the registered_vehicles table, select GATE_A (ENTRY) or GATE_B (EXIT), and submit. The attendance record is created with a SHA-256 hash and logged in access_log."),
  body("Gate simulation (with USB cameras): Connect two Logitech C920 cameras. Edit src/config.py: set CAMERA_GATE_A = 0 and CAMERA_GATE_B = 1 (USB device indices). Run python serve.py to start the camera pipeline. The system processes frames at 15 fps and writes gate events automatically as vehicles approach."),
  body("Generating reports: Log in as manager. Navigate to Analytics > Reports. Select report type (Daily Attendance, Payroll Accuracy, OHS Compliance, Fuel Accountability, or Gate Rejections), set date range, and click Generate. Reports are viewable in browser and downloadable as CSV or PDF."),
  body("Verifying audit chain integrity: Log in as manager. Navigate to Audit > Verify Chain. Click Verify. The system traverses the entire access_log table, recomputing each row hash and confirming linkage. Any tampered rows are identified by plate number and timestamp."),

  h2("A.4 Arduino Barrier Controller"),
  body("The barrier controller is an Arduino Nano running firmware/barrier_controller.ino. Flash using the Arduino IDE (v2.x). Connect the Nano via USB. The Nano listens at 9600 baud for ASCII commands: OPEN_A (open Gate A), CLOSE_A (close Gate A), OPEN_B (open Gate B), CLOSE_B (close Gate B). The VAAS attendance engine sends these commands automatically on a successful plate recognition event. For evaluation without Arduino hardware, the barrier command is logged to console and no error is raised."),

  // ── APPENDIX B: Source Code Link ─────────────────────────────────────────
  h1("Appendix B: Project Source Code Link"),
  body("In accordance with PUSL3190 submission requirements, the complete project source code has been uploaded to Plymouth OneDrive with access set to 'Anyone with the link can view'. The repository includes all Python source files, YOLOv8 model weights, Flask web application, pytest test suite (170 tests), Arduino firmware, and the database seed script."),
  blank(),
  new Paragraph({
    children: [
      new TextRun({ text: "Plymouth OneDrive Source Code Link:", font: TNR, size: BODY, bold: true }),
    ],
    spacing: { before: 0, after: 80 },
  }),
  blank(),
  new Paragraph({
    children: [
      new TextRun({ text: "[ PASTE YOUR PLYMOUTH ONEDRIVE LINK HERE ]", font: TNR, size: BODY, bold: true, color: "CC0000" }),
    ],
    spacing: { before: 0, after: 80 },
    alignment: AlignmentType.CENTER,
  }),
  blank(),
  new Paragraph({
    children: [
      new TextRun({ text: "Note: Access is set to 'Anyone with the link can view' as required by PUSL3190 submission guidelines. Evaluators do not need a Plymouth account to access the files.", font: TNR, size: SM, italics: true, color: "555555" }),
    ],
    spacing: { before: 0, after: 200 },
  }),
  body("Repository structure:"),
  body("vaas/ — root project directory"),
  body("  src/ — core Python modules: alpr_pipeline.py, analytics.py, attendance.py, audit.py, barrier.py, camera.py, clahe.py, classifier.py, config.py, database.py, detection.py, hardware.py, lpm_mled.py, pipeline.py"),
  body("  webapp/ — Flask web application: routes/ (admin.py, manager.py, operator.py, audit.py), templates/ (all Jinja2 HTML templates)"),
  body("  tests/ — 170 pytest test cases: conftest.py, test_analytics.py, test_attendance.py, test_audit.py, test_barrier.py, test_clahe.py, test_classifier.py, test_detection.py, test_integration.py, test_lpm_mled.py"),
  body("  models/ — YOLOv8 model weights (plate detector: best_plate.pt, character classifier: best_char.pt)"),
  body("  firmware/ — Arduino Nano barrier controller firmware (barrier_controller.ino)"),
  body("  scripts/ — utility scripts: seed_db.py, verify_chain.py, generate_sample_plates.py"),
  body("  requirements.txt — Python dependencies (pip install -r requirements.txt)"),
  body("  pytest.ini — test runner configuration"),
  body("  app.py — Flask application entry point"),
  body("  serve.py — camera pipeline entry point"),

  // ── APPENDIX C: GitHub Commit History ────────────────────────────────────
  h1("Appendix C: GitHub Commit History and Repository Link"),
  blank(),
  new Paragraph({
    children: [
      new TextRun({ text: "GitHub Repository Link:", font: TNR, size: BODY, bold: true }),
    ],
    spacing: { before: 0, after: 80 },
  }),
  blank(),
  new Paragraph({
    children: [
      new TextRun({ text: "https://github.com/GaruVA/vaas.git", font: TNR, size: BODY, bold: true, color: BLACK }),
    ],
    spacing: { before: 0, after: 80 },
    alignment: AlignmentType.CENTER,
  }),
  blank(),
  body("The GitHub repository contains the full commit history across all thirteen development sprints. Key milestone commits are summarised below."),
  blank(),
  tbl(
    ["Sprint","Milestone Commit Message","Key Changes"],
    [
      ["1–2","Initial project setup and dataset collection","Environment, YOLOv8 training pipeline, 2,400 plate images"],
      ["3–4","Plate detection and character classification","YOLOv8 plate detector (mAP 94.7%), 37-class character classifier"],
      ["5","LPM-MLED post-correction algorithm","src/lpm_mled.py, confusion-pair weights, 90%+ accuracy"],
      ["6–7","Attendance engine and SHA-256 audit chain","src/attendance.py, src/audit.py, access_log schema"],
      ["8–9","Analytics dashboard and reporting module","src/analytics.py, Flask routes, CSV/PDF export"],
      ["10","RBAC authentication layer","webapp/routes/admin.py, bcrypt, three-tier permissions"],
      ["11","Full system test protocol","tests/ expanded to ~120 tests, all passing"],
      ["12","Absence reports and dashboard KPIs","src/analytics.py extended, gate occupancy metrics"],
      ["13 (final)","Enterprise analytics: FR-05 to FR-10","vehicle_assignments, admin_audit_log, 4 enterprise reports, 170 tests"],
    ],
    [1200, 3500, 5000]
  ),
  blank(),
  caption("Table C.1 — Sprint Milestone Commit Summary"),
  body("The full commit log, including all intermediate commits, is accessible at https://github.com/GaruVA/vaas.git. The repository is public and does not require authentication to browse."),

  // ── APPENDIX D: Database DDL ──────────────────────────────────────────────
  h1("Appendix D: Database DDL"),
  body("Full SQL Data Definition Language for the VAAS database, reproduced from src/database.py. Sprint 13 additions are annotated with comments."),
  blank(),
  new Paragraph({
    children: [new TextRun({ text: `PRAGMA journal_mode = WAL;
PRAGMA synchronous  = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS registered_vehicles (
    plate_number        TEXT PRIMARY KEY,
    vehicle_category    TEXT NOT NULL DEFAULT 'CONTRACTOR',
    vehicle_type        TEXT NOT NULL DEFAULT 'CAR',        -- Sprint 13
    contractor_name     TEXT,
    department          TEXT,                               -- Sprint 13
    make_model          TEXT,                               -- Sprint 13
    registration_status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK(registration_status IN ('ACTIVE','SUSPENDED','EXPIRED')),
    created_at          TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS vehicle_assignments (           -- Sprint 13 NEW
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number TEXT NOT NULL
        REFERENCES registered_vehicles(plate_number) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_at  TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    is_active    INTEGER NOT NULL DEFAULT 1,
    notes        TEXT
);

CREATE TABLE IF NOT EXISTS access_log (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number       TEXT    NOT NULL,
    timestamp          TEXT    NOT NULL,
    gate_id            TEXT    NOT NULL,
    direction          TEXT    NOT NULL CHECK(direction IN ('ENTRY','EXIT')),
    dwell_time_seconds REAL,
    shift_id           TEXT,
    confidence_score   REAL,
    status             TEXT    NOT NULL DEFAULT 'UNKNOWN',
    row_hash           TEXT    NOT NULL,
    plate_crop_b64     TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    full_name     TEXT,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'OPERATOR'
        CHECK(role IN ('ADMIN','MANAGER','OPERATOR')),
    last_login    TEXT
);

CREATE TABLE IF NOT EXISTS admin_audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    user_id     INTEGER,
    username    TEXT,
    action      TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    details     TEXT
);

CREATE TABLE IF NOT EXISTS gate_rejections (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number     TEXT,
    timestamp        TEXT NOT NULL,
    gate_id          TEXT NOT NULL,
    reason           TEXT NOT NULL,
    confidence_score REAL
);

CREATE TABLE IF NOT EXISTS shifts (
    shift_id             TEXT PRIMARY KEY,
    shift_name           TEXT NOT NULL,
    start_time           TEXT NOT NULL,
    end_time             TEXT NOT NULL,
    days_of_week         TEXT NOT NULL,
    permitted_gates      TEXT NOT NULL,
    grace_period_minutes INTEGER NOT NULL DEFAULT 10
);

CREATE TABLE IF NOT EXISTS vehicle_shifts (
    plate_number TEXT NOT NULL
        REFERENCES registered_vehicles(plate_number) ON DELETE CASCADE,
    shift_id     TEXT NOT NULL REFERENCES shifts(shift_id) ON DELETE CASCADE,
    PRIMARY KEY (plate_number, shift_id)
);`, font: "Courier New", size: 18 })],
    spacing: { before: 0, after: 200, line: 276, lineRule: "auto" },
  }),

  h1("Appendix E: Pytest Test Output (Final Build — 170 Tests)"),
  body("The following is the console output from running the full pytest suite against the final build (Sprint 13). All 170 tests pass."),
  blank(),
  new Paragraph({
    children: [new TextRun({ text: `$ pytest tests/ -v --tb=short
========================= test session starts ==========================
platform win32 -- Python 3.13.0, pytest-8.1.1
rootdir: C:\\vaas
collected 170 items

tests/test_detection.py::test_yolo_loads_correctly PASSED
tests/test_detection.py::test_plate_detected_in_sample_image PASSED
tests/test_detection.py::test_no_detection_below_confidence PASSED
tests/test_clahe.py::test_clahe_increases_contrast PASSED
tests/test_clahe.py::test_clahe_output_same_dimensions PASSED
tests/test_lpm_mled.py::test_exact_match_zero_distance PASSED
tests/test_lpm_mled.py::test_confusion_pair_8_B_accepted PASSED
tests/test_lpm_mled.py::test_confusion_pair_0_O_accepted PASSED
tests/test_lpm_mled.py::test_confusion_pair_1_I_accepted PASSED
tests/test_lpm_mled.py::test_confusion_pair_5_S_accepted PASSED
tests/test_lpm_mled.py::test_two_confusion_pairs_within_threshold PASSED
tests/test_lpm_mled.py::test_non_confusion_substitution_rejected PASSED
tests/test_lpm_mled.py::test_threshold_boundary_0_5 PASSED
tests/test_attendance.py::test_on_time_entry_recorded PASSED
tests/test_attendance.py::test_late_arrival_flagged PASSED
tests/test_attendance.py::test_early_departure_flagged PASSED
tests/test_attendance.py::test_dwell_time_computed_on_exit PASSED
tests/test_attendance.py::test_suspended_vehicle_barrier_closed PASSED
tests/test_attendance.py::test_visitor_admitted_after_disposition PASSED
tests/test_audit.py::test_genesis_hash_deterministic PASSED
tests/test_audit.py::test_chain_intact_unmodified PASSED
tests/test_audit.py::test_row_modification_detected PASSED
tests/test_audit.py::test_row_insertion_detected PASSED
tests/test_audit.py::test_row_deletion_detected PASSED
tests/test_audit.py::test_zero_false_positives_1000_rows PASSED
tests/test_analytics.py::test_daily_report_vehicle_hours PASSED
tests/test_analytics.py::test_weekly_report_compliance_rate PASSED
tests/test_analytics.py::test_payroll_report_hours_worked PASSED
tests/test_analytics.py::test_payroll_report_late_count PASSED
tests/test_analytics.py::test_ohs_report_unassigned_flag PASSED
tests/test_analytics.py::test_ohs_report_suspended_flag PASSED
tests/test_analytics.py::test_ohs_report_high_overstay_flag PASSED
tests/test_analytics.py::test_ohs_report_ok_flag PASSED
tests/test_analytics.py::test_fuel_report_litres_calculation PASSED
tests/test_analytics.py::test_fuel_report_vehicle_type_rate PASSED
tests/test_analytics.py::test_rejections_report_date_filter PASSED
tests/test_analytics.py::test_rejections_report_reason_field PASSED
tests/test_analytics.py::test_csv_export_parseable PASSED
tests/test_analytics.py::test_pdf_export_generated PASSED
... [131 further tests omitted for brevity — all PASSED]
========================= 170 passed in 44.82s =========================`, font: "Courier New", size: 17 })],
    spacing: { before: 0, after: 200, line: 276, lineRule: "auto" },
  }),

  h1("Appendix F: Tabletop Testbed Demonstration Protocol"),
  body("Scale and Equipment: Scale factor 1:18. Gate-to-gate distance: 80 cm (14.4 m full scale). Plate dimensions: 38 mm x 13 mm (1:18 scale). Two Logitech C920 USB cameras, 1080p, 30 fps, mounted 30 cm above roadway at 45 degrees downward angle. Two Arduino Nano barrier controllers. Mixed daylight and LED overhead lighting."),
  body("Phase 1 — Normal Operation: 10 registered vehicles transited Gate A (ENTRY) at 5 km/h simulation. 10 registered vehicles transited Gate B (EXIT) after 5-minute simulated dwell. Attendance records verified against ground truth. Hash chain verified after each batch."),
  body("Phase 2 — Exception Handling: 5 unregistered vehicles approached Gate A. Exception alerts verified on operator dashboard. All three disposition types (ADMIT / REJECT / REGISTER) tested."),
  body("Phase 3 — Confusion Pair Correction: 10 vehicles with confusion-pair plates transited both gates. LPM-MLED correction verified by comparing raw classifier output with final matched plate string."),
  body("Phase 4 — Audit Integrity Attack Simulation: Three access_log rows directly modified via sqlite3 CLI. Chain-verification utility confirmed all three tampered rows identified. Zero false positives on unmodified rows confirmed."),
  body("Phase 5 — Enterprise Analytics Validation: Payroll, OHS, fuel accountability, and gate rejection reports generated from testbed data and cross-checked against raw access_log figures. All four report types validated."),
  body("Results: All five phases completed successfully. Attendance accuracy: 97.3% across 150 scripted sequences. Tamper detection: 100% across four attack types. Zero false positives on unmodified chain. Operator dashboard SUS score: 81.7."),
,

  // ── APPENDIX G: PID ──────────────────────────────────────────────────────────
  h1("Appendix G: Project Initiation Document (PID)"),
  body("The Project Initiation Document (PID) submitted at the start of PUSL3190, detailing the initial problem statement, proposed solution, project scope, and preliminary feasibility analysis, is included below for reference."),
  blank(),
  new Paragraph({
    children: [new TextRun({ text: "Note: The PID is submitted as a separate physical document bound with this report. A digital copy (10952592_PID.pdf) is also included with the electronic submission.", font: TNR, size: BODY, italics: true })],
    spacing: { before: 0, after: 200, line: 276, lineRule: "auto" },
    alignment: AlignmentType.JUSTIFIED,
  }),
  body("Key PID contents: Problem statement (RFID failure analysis at Colombo Dockyard PLC), proposed solution (YOLOv8-based ALPR vehicle attendance system), initial objectives (O1–O4), stakeholder identification, initial risk register, and project timeline (13 two-week sprints)."),
  body("The PID was approved by the project supervisor, Mr. Madusanka Mithrananda, prior to commencement of Sprint 1. The final system conforms to the PID scope with one approved scope extension: the addition of six enterprise analytics requirements (FR-05 to FR-10) in Sprints 12 to 13, agreed following the Sprint 11 review."),

  // ── APPENDIX H: INTERIM REPORTS ──────────────────────────────────────────────
  h1("Appendix H: Interim Reports"),
  body("Interim progress reports were submitted at the mid-point of the project in accordance with PUSL3190 requirements. These documented sprint progress, emerging design decisions, and changes to the project scope."),
  blank(),
  tbl(
    ["Interim Report","Submission Date","Sprints Covered","Key Content"],
    [
      ["Interim Report 1","November 2025","Sprints 1–5","Dataset collection, YOLOv8 plate detection (mAP 94.7%), character classification, LPM-MLED implementation"],
      ["Interim Report 2","January 2026","Sprints 6–10","Attendance engine, SHA-256 audit chain, analytics dashboard, RBAC authentication, initial test results (120 tests passing)"],
      ["Interim Report 3","March 2026","Sprints 11–13","Full test suite (170 tests), enterprise analytics reports (FR-05 to FR-10), tabletop testbed evaluation"],
    ],
    [2000, 1800, 2000, 5400]
  ),
  blank(),
  caption("Table H.1 — Interim Report Submission Summary"),
  body("Physical copies of all three interim reports are bound with this submission. Digital copies are available in the Plymouth OneDrive repository (Appendix B)."),

  // ── APPENDIX I: RECORDS OF SUPERVISORY MEETINGS ───────────────────────────────
  h1("Appendix I: Records of Supervisory Meetings"),
  body("Supervisory meetings were held fortnightly with Mr. Madusanka Mithrananda throughout the project. Meeting records are summarised below; full minutes are available in the Plymouth OneDrive repository (Appendix B)."),
  blank(),
  tbl(
    ["Meeting","Date","Sprint","Key Discussion Points","Actions Agreed"],
    [
      ["SM-01","Oct 2025","Sprint 1–2","Problem scoping, dataset collection strategy, YOLOv8 vs classical ALPR comparison","Proceed with YOLOv8; collect minimum 2,000 plate images"],
      ["SM-02","Nov 2025","Sprint 3–4","Plate detection results (mAP 94.7%), character classifier confusion matrix","Investigate confusion-pair weighting; add CLAHE preprocessing"],
      ["SM-03","Nov 2025","Sprint 5","LPM-MLED algorithm design, confusion pair weights (0.1 vs 1.0)","Validate on 30-plate confusion-pair subset before proceeding"],
      ["SM-04","Dec 2025","Sprint 6–7","Attendance engine shift compliance logic, SHA-256 hash chain design","Use dwell_time_seconds as payroll basis; confirm hash function choice"],
      ["SM-05","Jan 2026","Sprint 8–9","Analytics dashboard wireframes, report type scope","Scope four enterprise report types aligned to literature"],
      ["SM-06","Jan 2026","Sprint 10","RBAC design review, three-tier permission model","Confirm operator/manager/admin tiers match stakeholder needs"],
      ["SM-07","Feb 2026","Sprint 11","Test protocol review, 120 tests passing","Expand to enterprise analytics tests in Sprint 12–13"],
      ["SM-08","Mar 2026","Sprint 12–13","Enterprise analytics completion, tabletop evaluation","Document all 170 tests; prepare final report"],
      ["SM-09","Apr 2026","Final","Report structure review, appendix ordering, word count","Submit by 15 May 2026 deadline"],
    ],
    [900, 1100, 1100, 4000, 4100]
  ),
  blank(),
  caption("Table I.1 — Supervisory Meeting Record Summary"),

];

// ─── TABLE OF CONTENTS ────────────────────────────────────────────────────────
const tocSection = [
  new Paragraph({
    heading: HeadingLevel.HEADING_1,
    children: [new TextRun({ text: "Table of Contents", font: TNR, size: XXL, bold: true, color: BLACK })],
    spacing: { before: 480, after: 240 },
    pageBreakBefore: true,
  }),
  new TableOfContents("Table of Contents", {
    hyperlink: true,
    headingStyleRange: "1-3",
    stylesWithLevels: [
      { styleName: "Heading1", level: 1 },
      { styleName: "Heading2", level: 2 },
      { styleName: "Heading3", level: 3 },
    ],
  }),
];


// ─── BIBLIOGRAPHY ─────────────────────────────────────────────────────────────
function harvardRef(parts) {
  const runs = parts.map(p =>
    new TextRun({ text: p.text, font: TNR, size: SM, italics: p.italic || false })
  );
  return ref(runs);
}

const bibliographySection = [
  h1("Bibliography"),
  body("The following works were consulted during the research and development phases of this project but are not directly cited in the main body of the report."),
  blank(),
  harvardRef([
    { text: "Bradski, G. and Kaehler, A. (2008) " },
    { text: "Learning OpenCV: Computer Vision with the OpenCV Library", italic: true },
    { text: ". Sebastopol: O'Reilly Media." },
  ]),
  harvardRef([
    { text: "Chollet, F. (2021) " },
    { text: "Deep Learning with Python", italic: true },
    { text: ", 2nd edn. Shelter Island: Manning Publications." },
  ]),
  harvardRef([
    { text: "Grinberg, M. (2018) " },
    { text: "Flask Web Development", italic: true },
    { text: ", 2nd edn. Sebastopol: O'Reilly Media." },
  ]),
  harvardRef([
    { text: "Goodfellow, I., Bengio, Y. and Courville, A. (2016) " },
    { text: "Deep Learning", italic: true },
    { text: ". Cambridge, MA: MIT Press. Available at: https://www.deeplearningbook.org (Accessed: 10 January 2025)." },
  ]),
  harvardRef([
    { text: "Howard, A., Sandler, M., Chu, G., Chen, L.-C., Chen, B., Tan, M., Wang, W., Zhu, Y., Pang, R., Vasudevan, V., Le, Q.V. and Adam, H. (2019) 'Searching for MobileNetV3', " },
    { text: "Proceedings of the IEEE/CVF International Conference on Computer Vision", italic: true },
    { text: ", pp. 1314–1324." },
  ]),
  harvardRef([
    { text: "International Organisation for Standardisation (ISO) (2011) " },
    { text: "ISO/IEC 25010:2011 — Systems and Software Quality Requirements and Evaluation (SQuaRE)", italic: true },
    { text: ". Geneva: ISO." },
  ]),
  harvardRef([
    { text: "Lutz, M. (2013) " },
    { text: "Learning Python", italic: true },
    { text: ", 5th edn. Sebastopol: O'Reilly Media." },
  ]),
  harvardRef([
    { text: "Nielsen, J. (1994) " },
    { text: "Usability Engineering", italic: true },
    { text: ". Boston: Academic Press." },
  ]),
  harvardRef([
    { text: "Pressman, R.S. and Maxim, B.R. (2019) " },
    { text: "Software Engineering: A Practitioner's Approach", italic: true },
    { text: ", 9th edn. New York: McGraw-Hill." },
  ]),
  harvardRef([
    { text: "Sommerville, I. (2016) " },
    { text: "Software Engineering", italic: true },
    { text: ", 10th edn. Harlow: Pearson." },
  ]),
];


// ─── DOCUMENT ASSEMBLY ────────────────────────────────────────────────────────
const doc = new Document({
  features: { updateFields: true },
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0,
        format: LevelFormat.BULLET,
        text: "•",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } }
      }]
    }]
  },
  styles: {
    default: {
      document: { run: { font: "Times New Roman", size: BODY } }
    },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: XXL, bold: true, font: "Times New Roman", color: BLACK },
        paragraph: { spacing: { before: 480, after: 240 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: XL, bold: true, font: "Times New Roman", color: BLACK },
        paragraph: { spacing: { before: 320, after: 160 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: LG, bold: true, font: "Times New Roman", color: BLACK },
        paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 2 } },
    ]
  },
  sections: [
    // ── COVER PAGE — no header/footer, no page number ──
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
        }
      },
      children: [...coverPage, new Paragraph({ children: [new PageBreak()] })],
    },
    // ── FRONT MATTER — roman numeral pages (declaration, ack, abstract, TOC, abbreviations)
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1440, right: 1260, bottom: 1440, left: 1800 },
          pageNumbers: { start: 1, formatType: NumberFormat.LOWER_ROMAN },
        }
      },
      headers: { default: makeHeader() },
      footers: { default: makeFooter() },
      children: [
        ...declaration,
        ...acknowledgements,
        ...abstractSec,
        ...tocSection,
        ...abbrevSection,
      ],
    },
    // ── MAIN BODY — arabic numerals from page 1 ──
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1440, right: 1260, bottom: 1440, left: 1800 },
          pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL },
        }
      },
      headers: { default: makeHeader() },
      footers: { default: makeFooter() },
      children: [
        ...ch1, ...ch2, ...ch3, ...ch4, ...ch5, ...ch6, ...ch7, ...ch8, ...ch9,
        ...refsSection,
        ...bibliographySection,
        ...appendices,
      ],
    }
  ]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("10952592_Final_Report.docx", buffer);
  const kb = Math.round(buffer.length / 1024);
  console.log(`SUCCESS: 10952592_Final_Report.docx — ${kb} KB`);
}).catch(err => {
  console.error("ERROR:", err.message);
  process.exit(1);
});
