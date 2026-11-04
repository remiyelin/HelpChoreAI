# ALCOA+ Data Integrity Assessment
## HelpChoreAI: Biophysical Measurement & Protocol-Variance Auditing Platform

> **Status: draft, validation-ready, not validated.** Written by the developer with AI coding agents. No independent quality unit has reviewed or approved it, and nothing here is signed. It maps requirements to automated tests; it is not a GxP validation record. HelpChoreAI is a research tool: it gives no medical advice and is not meant for clinical decisions or regulatory submissions. Test counts are as recorded on 2026-11-02; run `pytest` for the current suite. Revised 2026-11-04: statistics claims corrected (see `CROSS_DOMAIN_EVIDENCE.md`).

**Document Identifier**: `VAL-ALCOA-2026-001`  
**Revision**: `1.0`  
**Regulatory Standards**: `FDA Guidance on Data Integrity and Compliance with Drug CGMP (2018), EMA Guideline on Computerised Systems and Electronic Data (2023), WHO Guidance on Good Data and Record Management Practices (TRS 996)`  
**GAMP 5 Classification**: `Category 5 — Custom / Bespoke Computational Science Tool`  
**Target Environment**: `HelpChoreAI Python 3.12+ (Windows / Linux / POSIX)`  
**Effective Date**: `2026-11-02`  
**Status**: `Draft, self-assessed (not approved)`  

---

### Executive Sign-Off & Data Integrity Certification

| Role | Name & Title | Signature | Execution Date | Verdict |
|:---|:---|:---|:---:|:---:|
| **Project Lead & System Owner** | Muhammed Ali Sain | *Not signed (draft)* | 2026-11-02 | **Met (self-assessed)** |

---

## 1. Executive Summary & Regulatory Purpose

Data integrity matters for any research measurement. The **ALCOA+** framework used by FDA, EMA and WHO guidance is applied here as a checklist:
- **A** — Attributable
- **L** — Legible
- **C** — Contemporaneous
- **O** — Original
- **A** — Accurate
- **+ Complete**
- **+ Consistent**
- **+ Enduring**
- **+ Available**

Microfluidic deformability cytometry (e.g. RT-DC, constricted channel morphometry) generates high-velocity single-cell optical and hydrodynamic data that are exceptionally vulnerable to physical confounders (flow rate drift, carrier buffer thermal viscosity loss, osmotic swelling, channel fouling). Without rigorous data integrity controls, these physical artifacts masquerade as biological shifts or therapeutic efficacy.

This assessment formally evaluates the architecture, statistical algorithms, cryptographic controls, and audit trails of HelpChoreAI against each of the nine ALCOA+ principles.

---

## 2. Microfluidic Domain Vulnerabilities & Mitigation Engineering

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        MICROFLUIDIC DATA INTEGRITY CHALLENGES                          │
├───────────────────────────────┬────────────────────────────────────────────────────────┤
│ Biophysical Confounder        │ HelpChoreAI Engineering Mitigation                     │
├───────────────────────────────┼────────────────────────────────────────────────────────┤
│ 1. Parabolic Flow Shear       │ Step 4b Unpenalised GLM standardisation to             │
│    Shear stress τ ∝ Q/w³      │ constant reference flow (FR_ref = 0.08 or 0.016 μL/s); │
│    artificially distorts cell │ Selection rule: ΔAIC > 2.0; explains >70% variance.   │
│    deformation.               │                                                        │
├───────────────────────────────┼────────────────────────────────────────────────────────┤
│ 2. Buffer Viscosity Drift     │ Viscosity disturbances tracked in manifest;            │
│    Temperature drops η(T),    │ GLM logit standardisation projects runs to reference   │
│    falsely making cells       │ disturbance level; excludes uncalibrated runs.         │
│    appear stiffer.            │                                                        │
├───────────────────────────────┼────────────────────────────────────────────────────────┤
│ 3. Osmotic Cell Swelling      │ Hypo-/Hyper-tonic runs tracked by condition flags;     │
│    Non-isotonic buffer        │ Gating rules detect abnormal cross-sectional area      │
│    alters spherical tension.  │ shifts and isolate biological osmolarity gradients.    │
├───────────────────────────────┼────────────────────────────────────────────────────────┤
│ 4. Optical Debris / Clumping  │ Contour circularity and convexity gating filters;     │
│    Dust or cell doublets      │ QC Gating automatically flags runs with skip rate      │
│    corrupt marker counts.     │ > 25% or kept cells < 500 as `indeterminate_QC`.       │
├───────────────────────────────┼────────────────────────────────────────────────────────┤
│ 5. Post-Hoc Data Manipulation │ Immutable SHA-256 hash chains connecting manifests     │
│    Manual modification of     │ to raw data; Ed25519 digital signatures linking        │
│    cell counts or visits.     │ payload, report text, and pinned public keys.          │
└───────────────────────────────┴────────────────────────────────────────────────────────┘
```

---

## 3. Comprehensive ALCOA+ Principles Compliance Matrix

### 3.1 Attributable (A)
- **GxP Definition**: Every data point, modification, analysis step, or signature must be unequivocally traceable to the person, system, or instrument generating it.
- **Microfluidic Risk**: Inability to differentiate whether an observed change in cell deformation was caused by a patient's biological response, an unrecorded pump flow adjustment, or an analytical model modification.
- **HelpChoreAI Implementation**:
  - Every run record in `data/tables/per_run.csv` captures explicit metadata: `patient` / `subject`, `visit`, `run_id`, `flow_ul_s`, `date`, `treatment`, and `n_kept`.
  - Machine-readable audit trails embed the execution timestamp, operator/agent identifier (`agent_id`), Git commit hash, and host platform identifier.
  - Final signed reports explicitly record the signer role and digital signature public key (`public_key_hex`).
- **Audit Verification Artifact**:
  - `data/checker/example_report_P1_0w_2w.json` (`payload.patient`, `payload.chain`, `public_key_hex`).
  - `tools/audit_table.py` (`load` enforces non-null, valid alphanumeric subject identifiers).
- **Compliance Status**: **Met (self-assessed)**

### 3.2 Legible (L)
- **GxP Definition**: Data and audit records must be readily readable and understandable by human operators, reviewers, and regulatory inspectors throughout their lifecycle.
- **Microfluidic Risk**: Storing critical analysis outputs in proprietary binary formats (e.g. proprietary cytometer files, serialized binary pickles) that become unreadable upon software obsolescence.
- **HelpChoreAI Implementation**:
  - All primary analysis artifacts are stored in plain-text open formats: JSON schemas, UTF-8 CSV/TSV tables, and standardized GitHub-flavored Markdown.
  - Dual-report generation: Each analysis run produces a machine-readable JSON envelope (`report.json`) and an accompanying human-readable audit report (`report.md`) rendered using plain typography without proprietary styling.
- **Audit Verification Artifact**:
  - `src/checker.py` (`render_report` generates human-readable markdown summaries).
  - Open CSV tables in `data/tables/` (`per_run.csv`, `per_visit_adjusted_v3.csv`, `visit_pairs_decisions_v3.csv`).
- **Compliance Status**: **Met (self-assessed)**

### 3.3 Contemporaneous (C)
- **GxP Definition**: Data and audit records must be recorded at the exact time the physical event or analytical computation occurs.
- **Microfluidic Risk**: Retrospective entry of pump flow rates, back-dated visit labels, or post-hoc alteration of statistical parameters after viewing unblinded outcomes.
- **HelpChoreAI Implementation**:
  - Timestamps are generated using monotonic, synchronized system clocks recorded in UTC ISO 8601 format (`YYYY-MM-DDTHH:MM:SSZ`) at execution time.
  - Cryptographic signatures freeze the exact state of upstream manifest logs and canonical tables; back-dating a report is cryptographically impossible because the hash chain binds the commit and manifest hashes at signature generation.
- **Audit Verification Artifact**:
  - Audit trail timestamps in `data/checker/*.json`.
  - Timestamp verification in `tests/test_checker.py`.
- **Compliance Status**: **Met (self-assessed)**

### 3.4 Original (O)
- **GxP Definition**: The primary, first-recording source data (raw records) must be preserved in an unaltered, unmanipulated state.
- **Microfluidic Risk**: Overwriting raw cytometer output files during filtering, debris gating, or flow standardisation.
- **HelpChoreAI Implementation**:
  - Primary raw experimental files (`HL60_LatB_3fr_*.txt`, `RTDC_singlecell_*.tsv`) in `data/cross_domain/` and `data/dev/` are maintained as write-protected, immutable source records.
  - All transformations, standardisations, and feature extractions are written strictly to downstream derivative directories (`data/tables/`, `data/checker/`).
  - Source data files are indexed with SHA-256 digests in `data/fetch_manifest/`. Changing a single raw data byte invalidates the upstream manifest hash.
- **Audit Verification Artifact**:
  - `src/checker.py` (`chain_hashes()` asserts `raw_manifest_sha256` matching upstream fetch logs).
  - Immutability assertions in `IQ_PROTOCOL_REPORT.md` (IQ-04).
- **Compliance Status**: **Met (self-assessed)**

### 3.5 Accurate (A)
- **GxP Definition**: Data must be truthful, free from mathematical errors, and representative of physical reality.
- **Microfluidic Risk**: Hydrodynamic shear stress artificially distorting cell deformation, causing uncalibrated models to report 19 false alarms in 32 visit pairs.
- **HelpChoreAI Implementation**:
  - Step 4b unpenalised GLM standardisation mathematically projects measurements to a constant reference flow ($FR_{\text{ref}}$), explaining $73.5\%$ of overall and up to $97.5\%$ of within-treatment variance in-sample, in a dataset where flow was varied by design.
  - Few-Cluster Student-$t$ calibration ($df = n_A + n_B - 2$) prevents false alarms caused by small run counts, constraining empirical false-exceed rates to $0.064$ (target: 0.05).
  - Automated Quality Control gating blocks corrupted recordings ($\text{skip\_rate} > 0.25$ or $n_{\text{kept}} < 500$) from generating false biological findings.
- **Audit Verification Artifact**:
  - `tests/test_cross_domain.py` (`test_variance_reduction_after_standardisation`, `test_glm_delta_aic_exceeds_threshold`).
  - Empirical variance reduction table in `PQ_PROTOCOL_REPORT.md`.
- **Compliance Status**: **Met (self-assessed)**

### 3.6 Complete (+ Complete)
- **GxP Definition**: All data, including repeat runs, control samples, and excluded events, must be retained with full context and metadata.
- **Microfluidic Risk**: Cherry-picking runs that confirm a hypothesis while discarding runs with erratic flow or unexpected cell stiffness.
- **HelpChoreAI Implementation**:
  - All 140 experimental runs (105 active flow runs + 35 reservoir control runs comprising 237,813 cells) and all 37 longitudinal patient visits are fully preserved and accounted for in tabular manifests.
  - Runs failing quality criteria are not deleted; they are explicitly categorized as `indeterminate_QC` with recorded unreadable/skip fractions.
- **Audit Verification Artifact**:
  - `stats.load_rtdc_runs` row count assertions ($N=140$, active $N=105$).
  - `per_visit_adjusted_v3.csv` and `visit_pairs_decisions_v3.csv` retain all visit pairs.
- **Compliance Status**: **Met (self-assessed)**

### 3.7 Consistent (+ Consistent)
- **GxP Definition**: The sequence of analytical steps and computational outputs must be repeatable and reproducible without arbitrary variation.
- **Microfluidic Risk**: Stochastic variation in bootstrap resampling, floating-point nondeterminism across operating systems, or package version drift causing discordant results.
- **HelpChoreAI Implementation**:
  - Deterministic execution: Cluster bootstrapping uses a fixed pseudorandom seed ($\text{SEED} = 20261026$) and fixed iteration count ($B = 2,000$).
  - Dependency pinning: Runtime packages are frozen via `uv.lock`.
  - Checksum invariance: 10 consecutive executions produce bitwise identical output tables and checksums.
- **Audit Verification Artifact**:
  - Deterministic seed constants in `src/step4b_model.py` (`SEED = 20261026`, `B = 2000`).
  - Multi-run reproducibility test in `PQ_PROTOCOL_REPORT.md` (PQ-REP-01).
- **Compliance Status**: **Met (self-assessed)**

### 3.8 Enduring (+ Enduring)
- **GxP Definition**: Data and documentation must remain readable, accessible, and intact on durable media throughout the statutory retention period (e.g. 10–25 years for clinical trials).
- **Microfluidic Risk**: Storage on media subject to bit rot, reliance on deprecated third-party software, or closed cloud platforms that terminate service.
- **HelpChoreAI Implementation**:
  - All application code, test suites, and documentation are version-controlled in standard Git repositories.
  - Outputs are stored in human-readable open standards (CSV, JSON, Markdown).
  - Zero cloud dependency for core verification: Signed records can be verified completely offline using open-source cryptography libraries (`python -m src.agent verify`).
- **Audit Verification Artifact**:
  - Standalone verification capability validated in `OQ_PROTOCOL_REPORT.md` (OQ-COMP-03).
  - Open data formats compliant with FAIR (Findable, Accessible, Interoperable, Reusable) data principles.
- **Compliance Status**: **Met (self-assessed)**

### 3.9 Available (+ Available)
- **GxP Definition**: Data must be readily accessible for review, audit, or inspection by authorized personnel and regulatory authorities when requested.
- **Microfluidic Risk**: Analysis locked behind proprietary license servers, inaccessible cloud tokens, or complex multi-server infrastructure.
- **HelpChoreAI Implementation**:
  - Self-contained portable execution: HelpChoreAI runs locally on standard workstations with Python 3.12+ and `uv`.
  - Instantaneous report retrieval: Every audit report and signed envelope is indexed by patient code and visit pair (e.g. `data/checker/example_report_P1_0w_2w.json`).
  - Open inspection API: Local REST/HTTP server (`src/server.py`) exposes endpoints for report retrieval and signature inspection.
- **Audit Verification Artifact**:
  - `src/server.py` inspection endpoints.
  - Command-line audit verification (`python -m src.agent verify <report_id>`).
- **Compliance Status**: **Met (self-assessed)**

---

## 4. Forensic Auditor Readiness Checklist

| Inspection Item | Audit Criterion | Verification Command / Location | Regulatory Status |
|:---|:---|:---|:---:|
| **1. Traceability** | URS $\to$ FS $\to$ Test matrix exists | `docs/csv/TRACEABILITY_MATRIX.md` | **READY** |
| **2. Data Provenance** | Sources, licences and checksums listed (`data/csv/DATASETS_PROVENANCE.md`) | `data/cross_domain/`, DOI: `10.6084/m9.figshare.11704119.v2` | **READY** |
| **3. Confounder Control** | GLM standardisation $\Delta\text{AIC} > 2.0$ | `src/stats.py`, `src/step4b_model.py` | **READY** |
| **4. False-Alarm Control** | Student-$t$ RCV few-cluster calibration | `src/step4b_model.py`, `data/tables/visit_pairs_decisions_v3.csv` | **READY** |
| **5. Tamper Resistance** | Ed25519 signatures detect 1-bit tampering | `src/checker.py`, `data/checker/public_key.hex` | **READY** |
| **6. AI Guardrails** | Numbers barred in narrative; claim gate | `src/checker.py` (`render_report`), `meta_api.baseten_chat` | **READY** |
| **7. Test Invariance** | 128 baseline tests passing | `pytest -q` in project root (128 passed in 18.37s) | **READY** |

---

## 5. Conclusion (self-assessment)

HelpChoreAI was self-assessed against the nine ALCOA+ principles. No independent audit has been done, and this is not a certification.
