# User Requirements Specification (URS)
## HelpChoreAI: Biophysical Measurement & Protocol-Variance Auditing Platform

> **Status: draft, validation-ready, not validated.** Written by the developer with AI coding agents. No independent quality unit has reviewed or approved it, and nothing here is signed. It maps requirements to automated tests; it is not a GxP validation record. HelpChoreAI is a research tool: it gives no medical advice and is not meant for clinical decisions or regulatory submissions. Test counts are as recorded on 2026-11-02; run `pytest` for the current suite. Revised 2026-11-04: statistics claims corrected (see `CROSS_DOMAIN_EVIDENCE.md`).

**Document Identifier**: `VAL-URS-2026-001`  
**Revision**: `1.0`  
**GAMP 5 Classification**: `Category 5 — Custom / Bespoke Computational Science Tool`  
**Regulatory Standards**: `GAMP 5 (Second Edition), FDA 21 CFR Part 11, ICH Q9 Quality Risk Management, ALCOA+ Data Integrity Principles`  
**Target Environment**: `HelpChoreAI Python 3.12+ (Windows / Linux / POSIX)`  
**Effective Date**: `2026-11-02`  
**Status**: `Draft, self-assessed (not approved)`  

---

### Executive Approval Sign-Off

| Role | Name & Title | Signature | Date |
|:---|:---|:---|:---|
| **Project Lead & System Owner** | Muhammed Ali Sain | *Not signed (draft)* | 2026-11-02 |

---

## 1. Introduction & Regulatory Purpose

HelpChoreAI is an open-source research tool for auditing biophysical measurements and protocol variance. It is designed to separate biological changes in cells from flow-rate effects and measurement noise in deformability cytometry assays. Specifically, the system processes:
1. Longitudinal red blood cell (RBC) morphometry in rare neurodegenerative disorders (VPS13A chorea-acanthocytosis), tracking the discocyte-to-acanthocyte phenotypic transition.
2. High-throughput Real-Time Deformability Cytometry (RT-DC) of hematopoietic and leukemic cell populations (e.g. HL60 promyelocytic leukemia, peripheral blood leukocytes, and erythrocytes) subjected to actin perturbants (Latrunculin B) and osmotic shock gradients (200–700 mOsm).

HelpChoreAI gives no medical advice and is not intended for clinical decisions, trial design or regulatory submissions. These documents borrow the structure of GAMP 5 and 21 CFR Part 11 so that a lab that later wants to use the tool in a regulated setting has a starting point; that lab's quality unit would own the validation.

---

## 2. GAMP 5 System Classification & Justification

Under the ISPE GAMP 5 (Second Edition, 2022) taxonomy, computerized systems are categorized according to software complexity and risk:
- *Category 1*: Infrastructure Software (operating systems, database engines, standard Python interpreters).
- *Category 3*: Non-configured Off-The-Shelf Software.
- *Category 4*: Configured Software.
- *Category 5*: **Custom / Bespoke Software**.

### Classification Determination: **GAMP 5 Category 5**
**Justification**:  
While HelpChoreAI executes within standard CPython 3.12+ / 3.14+ runtime environments and utilizes scientific open-source libraries (NumPy, SciPy, Statsmodels, Pandas, Cryptography), its core business logic, statistical calibration engine, hydrodynamic standardisation algorithms, cryptographic audit chain, and fail-closed AI claim auditor consist of custom-developed algorithmic routines. Consequently, HelpChoreAI is classified as **Category 5 Bespoke Application Software**, requiring full lifecycle verification under the GAMP V-Model:
$$\text{URS} \longrightarrow \text{FS} \longrightarrow \text{Design} \longrightarrow \text{Coding} \longrightarrow \text{Unit/Integration Tests} \longrightarrow \text{IQ} \longrightarrow \text{OQ} \longrightarrow \text{PQ}$$

---

## 3. Operational Roles and Personas

The system enforces distinct operational roles to ensure segregation of duties and maintain traceability:

| Persona | Role Code | Responsibilities & Access Bounds |
|:---|:---|:---|
| **Cytometrist / Lab Operator** | `ROLE_OPERATOR` | Ingests microfluidic run files, monitors real-time channel stability, flags experimental disturbances, and verifies cell segmentation masks. Cannot sign official regulatory audit reports. |
| **Biostatistician / Methodologist** | `ROLE_STATISTICIAN` | Audits Generalized Linear Model (GLM) convergence, verifies $\Delta\text{AIC}$ confounder selections, validates Reference Change Value (RCV) bounds, and executes sample size power forecasts. |
| **Quality Assurance / Auditor** | `ROLE_AUDITOR` | Verifies cryptographic hash chains, checks Ed25519 digital signatures on clean offline environments, executes the fail-closed claim auditor, and certifies GxP compliance. |
| **System Administrator** | `ROLE_ADMIN` | Manages environment dependencies (`uv.lock`), provisions Ed25519 public key pinning, and ensures directory write permissions and audit trail immutability. |

---

## 4. Quality Risk Management (ICH Q9 FMEA)

In alignment with **ICH Q9 (Quality Risk Management)**, failure modes, effects, and critical mitigations have been formally assessed:

| Risk ID | Hazard / Failure Mode | Severity | Probability | Detectability | Risk Priority (RPN) | Regulatory Mitigation Mechanism |
|:---|:---|:---:|:---:|:---:|:---:|:---|
| **RISK-01** | **False Alarm Inflation**: Normal measurement wobble misidentified as disease progression or treatment response. | High (4) | High (4) | Low (4) | **64 (Critical)** | Implementation of Few-Cluster Student-$t$ RCV calibration with $df = n_A + n_B - 2$. Constrains false-exceed rate to $\le 0.064$ (target: 0.05). |
| **RISK-02** | **Confounder Distortion**: Uncalibrated pump flow rate ($Q$) artificially shifting apparent cell deformation. | High (4) | High (4) | Moderate (3) | **48 (High)** | Step 4b unpenalised GLM standardisation triggering at $\Delta\text{AIC} > 2.0$. Eliminates $>70\%$ overall and $>80\%$ within-treatment variance. |
| **RISK-03** | **Data Tampering / Post-Hoc Alteration**: Retrospective modification of cell counts or visit labels to manufacture therapeutic claims. | Critical (5) | Low (2) | High (1) | **10 (Controlled)** | SHA-256 provenance hash chain connecting fetch manifests, raw tables, and JSON payloads sealed via Ed25519 cryptographic signatures. |
| **RISK-04** | **AI Hallucination / Regulatory Transgression**: LLM generating unvalidated clinical prescriptions or diagnostic statements. | Critical (5) | Moderate (3) | Low (4) | **60 (Critical)** | Dual-layer protection: deterministic template banning numbers in narrative slots, plus fail-closed Claim Auditor API rejecting clinical directives. |
| **RISK-05** | **Synthetic / Fabricated Data Ingestion**: Reliance on unverified mock data producing false assurance of algorithmic reliability. | High (4) | Low (2) | Moderate (3) | **24 (Moderate)** | Mandatory ingestion gate asserting non-synthetic provenance against public DOIs (Figshare, Nature Methods, DCOR) and SHA-256 digests. |

---

## 5. Detailed User Requirements Specifications

### 5.1 URS-DATA: Data Ingestion & Authenticity

| Requirement ID | Requirement Description | Criticality | Verification Method |
|:---|:---|:---:|:---|
| **URS-DATA-01** | **Authentic Multi-Condition Microfluidic Ingestion**: The system SHALL ingest real experimental microfluidic and RT-DC datasets spanning multiple biological cell types (human red blood cells, leukocytes, and HL60 cells) and experimental conditions (flow rates $0.02 - 0.12\,\mu\text{L/s}$, Latrunculin B actin perturbation $0 - 0.10\,\mu\text{M}$, and buffer osmolarities $200 - 700\,\text{mOsm}$). | Mandatory | OQ / PQ: Run-level ingestion assertions (`test_rtdc_dataset_files_present`, `test_rtdc_run_level_experimental_numbers`). |
| **URS-DATA-02** | **Provenance Verification**: Every dataset file SHALL be listed with its source, licence and SHA-256 digest, and derived or example files SHALL be labelled as such. Every ingested dataset SHALL be verifiable against peer-reviewed scientific literature (Reichel et al. 2022, Urbanska et al. 2020) and public repository manifests (Figshare DOI `10.6084/m9.figshare.c.5793482`, `10.6084/m9.figshare.11704119.v2`) with cryptographic SHA-256 digests. | Mandatory | IQ / OQ: Manifest digest validator and provenance checks. |
| **URS-DATA-03** | **Standardized Lab Run Table Schema**: The system SHALL ingest arbitrary laboratory run tables in CSV/TSV format adhering to the standardized schema: `subject`, `visit`, `visit_order`, `run`, `marked`, `rated`, `total`, `disturbance`. The ingestion engine SHALL validate that $0 \le \text{marked} \le \text{rated} \le \text{total}$ and $\text{disturbance} > 0$. | Mandatory | OQ: Parser schema validation in `tools/audit_table.py` (`load`). |
| **URS-DATA-04** | **Single-Cell Event Cytometry Ingestion**: The system SHALL parse unaggregated single-cell event records comprising cross-sectional cell area ($\mu\text{m}^2$), contour deformation ($1 - \text{circularity}$), aspect ratio, and derived Young's elastic modulus ($E$, kPa). | Mandatory | PQ: Verification of single-cell tables (`test_rtdc_single_cell_tables_valid`). |
| **URS-DATA-05** | **Raw Data Immutability**: The system SHALL treat all ingested raw assets in `data/` as write-protected, immutable records. Derived features, normalized fractions, and adjusted metrics SHALL be written exclusively to distinct output directories (`data/tables/`, `data/checker/`). | Mandatory | IQ: File system permission and directory structure validation. |

### 5.2 URS-STAT: Biophysical & Statistical Engine

| Requirement ID | Requirement Description | Criticality | Verification Method |
|:---|:---|:---:|:---|
| **URS-STAT-01** | **Hydrodynamic Confounder Detection**: The system SHALL compute non-parametric Spearman rank correlation ($\rho$) between microfluidic flow rate / hydrodynamic disturbance and cellular deformation / marker fraction, reporting exact asymptotic two-sided $p$-values. | Mandatory | OQ: Assert $\rho > +0.80, p < 10^{-25}$ on multi-flow benchmark datasets (`test_spearman_rank_correlation_significant`). |
| **URS-STAT-02** | **GLM Confounder Standardisation ($\Delta\text{AIC} > 2.0$)**: The system SHALL evaluate an unpenalised Generalized Linear Model (GLM) comparing Model 0 (biological replicate/patient intercepts) against Model 1 (replicate intercepts + $\log(\text{disturbance})$). The system SHALL incorporate the flow confounder into standardisation IF AND ONLY IF $\Delta\text{AIC} = \text{AIC}(M_0) - \text{AIC}(M_1) > 2.0$. | Mandatory | OQ / PQ: Fit GLM across 105 active runs; assert $\Delta\text{AIC} = 141.86 > 2.0$ and positive flow slope (`test_glm_delta_aic_exceeds_threshold`). |
| **URS-STAT-03** | **Log-Scale Flow Standardisation**: The system SHALL project all observed run-level measurements to a standardized reference flow rate ($FR_{\text{ref}} = 0.016\,\mu\text{L/s}$ for RBC assay, $0.08\,\mu\text{L/s}$ for RT-DC). The transformation SHALL operate on the logit scale for cell fractions ($\text{logit}(p_{\text{adj}}) = \text{logit}(p_{\text{obs}}) + \eta_{\text{ref}} - \eta_{\text{run}}$) or linear scale for continuous deformations ($y_{\text{adj}} = y_{\text{obs}} - b \cdot (\log(FR) - \log(FR_{\text{ref}}))$). | Mandatory | OQ: Analytical invariance testing in `src/stats.py` and `src/step4b_model.py`. |
| **URS-STAT-04** | **Variance Reduction Invariant**: The system SHALL achieve greater than $70.0\%$ overall variance reduction across multi-flow experimental runs and greater than $75.0\%$ within-treatment variance reduction across all Latrunculin B concentration groups. | Mandatory | PQ: Quantitative variance reduction analysis (`test_variance_reduction_after_standardisation`). |
| **URS-STAT-05** | **Few-Cluster Student-$t$ RCV Calibration**: To discriminate between normal measurement wobble and authentic biological changes across visits, the system SHALL calculate the 95% Reference Change Value ($\text{RCV}_{95}$) using Student's $t$-distribution critical value with degrees of freedom $df = n_{\text{runs},A} + n_{\text{runs},B} - 2$, strictly rejecting Gaussian normal approximations ($z=1.96$) that inflate false alarms. | Mandatory | OQ / PQ: Regression testing against preregistered decision table (`data/tables/visit_pairs_decisions_v3.csv`). |
| **URS-STAT-06** | **Quality Control (QC) Gating**: The system SHALL automatically flag and categorize visit pairs as `indeterminate_QC` if the unreadable skip rate exceeds $25\%$ ($\text{skip\_rate} > 0.25$) or if total kept cells fall below $500$ ($n_{\text{kept}} < 500$) in either visit. | Mandatory | OQ: Boundary condition testing with corrupted and high-skip tables. |
| **URS-STAT-07** | **Sample Size & Power Forecasting**: The system SHALL calculate the estimated number of runs ($N_{\text{runs}}$) required to achieve a targeted statistical power ($1 - \beta \ge 0.80$) for specified biologically meaningful effect sizes ($\delta$), based on empirical within-visit variance. | Mandatory | OQ: Verification of power forecasting equation in `tools/audit_table.py` (`runs_needed`). |

### 5.3 URS-COMP: FDA 21 CFR Part 11 & Compliance Controls

| Requirement ID | Requirement Description | Criticality | Verification Method |
|:---|:---|:---:|:---|
| **URS-COMP-01** | **Computer-Generated Time-Stamped Audit Trail (§ 11.10(e))**: The system SHALL maintain a secure, append-only, machine-readable audit trail recording the timestamp (UTC ISO 8601), operator/agent identifier, Git commit hash, tool version, and cryptographic hash chain of input and output records. | Mandatory | OQ: Verification of audit logging structures and hash-chain continuity. |
| **URS-COMP-02** | **Cryptographic Digital Signatures (§ 11.50, § 11.70)**: Every generated report SHALL be cryptographically bound to its structured payload and signed using an Ed25519 private key. The signature SHALL link: printed signer role, UTC timestamp, report SHA-256, payload SHA-256, and input table hashes. Tampering with a single byte in the report or payload SHALL invalidate the signature. | Mandatory | OQ: Signature verification and bit-flip tamper detection (`test_checker.py`). |
| **URS-COMP-03** | **Offline Standalone Verification (§ 11.10(a))**: The system SHALL provide a zero-dependency CLI verification command (`python -m src.agent verify <report_id>`) that validates digital signatures, payload consistency, and table hash chains without requiring external cloud tokens, network access, or proprietary runtimes. | Mandatory | IQ / OQ: Execution of clean clone verification in disconnected network state. |
| **URS-COMP-04** | **Anti-Hallucination Numeric Templating**: The report generation engine SHALL template all numerical outputs exclusively from the cryptographically signed payload. Narrative text slots SHALL be programmatically barred from containing any digits, spelled-out number words, or percent words. | Mandatory | OQ: Regex enforcement test in `src/checker.py` (`render_report`). |
| **URS-COMP-05** | **Fail-Closed Clinical Claim Auditor**: The system SHALL route all generated narrative text through an automated compliance gate enforcing clinical claim blocklists (e.g. banning "diagnos", "disease progression", "recommend treatment", "start dasatinib"). If the claim auditor encounters a network failure, malformed response, or clinical directive, it SHALL fail closed to `BLOCK`. | Mandatory | OQ: Claim auditor positive and negative control tests (`test_claim_auditor_literature_sentences_pass`, `test_claim_auditor_negative_control_blocks`). |

### 5.4 URS-QUAL: System Quality & Regression Invariance

| Requirement ID | Requirement Description | Criticality | Verification Method |
|:---|:---|:---:|:---|
| **URS-QUAL-01** | **Baseline Regression Invariance**: All 128 pre-existing unit, integration, and biophysical tests (119 baseline + 9 cross-domain) SHALL continue to pass without a single failure, error, or warning, confirming zero regression across core functionality. | Mandatory | IQ / OQ / PQ: Pytest execution in target project (`pytest -q`). |
| **URS-QUAL-02** | **Independent Validation Architecture**: All computerized system validation (CSV) tests, stress testing scripts, and GAMP documentation SHALL reside in dedicated validation directories (`tests/csv/` or `tests/test_csv_validation.py` and `docs/csv/`), ensuring complete architectural decoupling from application source code in `src/`. | Mandatory | IQ: Codebase layout inspection and file ownership boundary check. |

---

## 6. Regulatory Acceptance Criteria

To achieve formal regulatory sign-off, the HelpChoreAI platform must satisfy the following baselines:
1. **Traceability Completeness**: 100% of User Requirements (URS-DATA, URS-STAT, URS-COMP, URS-QUAL) must trace forward to Functional Specifications and backward from Qualification Protocol test executions.
2. **Defect Tolerance**: Zero critical or high-severity open defects.
3. **Reproducibility**: 100% deterministic reproducibility across repeated executions on identical input datasets (verified via pinned pseudorandom seeds `SEED = 20261026`).
4. **Audit Readiness**: Complete, legible, and tamper-evident documentation suite generated and placed in `docs/csv/`.
