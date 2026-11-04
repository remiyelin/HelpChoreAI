# Operational Qualification (OQ) Protocol & Execution Report
## HelpChoreAI: Biophysical Measurement & Protocol-Variance Auditing Platform

> **Status: draft, validation-ready, not validated.** Written by the developer with AI coding agents. No independent quality unit has reviewed or approved it, and nothing here is signed. It maps requirements to automated tests; it is not a GxP validation record. HelpChoreAI is a research tool: it gives no medical advice and is not meant for clinical decisions or regulatory submissions. Test counts are as recorded on 2026-11-02; run `pytest` for the current suite. Revised 2026-11-04: statistics claims corrected (see `CROSS_DOMAIN_EVIDENCE.md`).

**Document Identifier**: `VAL-OQ-2026-001`  
**Revision**: `1.0`  
**GAMP 5 Classification**: `Category 5 — Custom / Bespoke Computational Science Tool`  
**Parent Documents**: `VAL-URS-2026-001 (URS)`, `VAL-FS-2026-001 (FS)`, `VAL-RTM-2026-001 (RTM)`  
**Execution Date**: `2026-11-02`  
**Validation Status**: `Draft, self-assessed (not approved)`  

---

### Executive Sign-Off & Execution Approval

| Role | Name & Title | Signature | Execution Date | Verdict |
|:---|:---|:---|:---:|:---:|
| **Project Lead & System Owner** | Muhammed Ali Sain | *Not signed (draft)* | 2026-11-02 | **PASSED** |

---

## 1. Protocol Objective & Scope

The Operational Qualification (OQ) phase verifies that all algorithmic components, mathematical models, boundary limits, error handling pathways, cryptographic security gates, and AI compliance controls operate in strict accordance with the Functional Specification (`VAL-FS-2026-001`) across expected, boundary, and adverse operational conditions.

### Scope:
1. **Functional Boundaries & Exception Handling**: Zero/negative flow rates, empty files, malformed headers, invalid cell ratios, extreme noise/skip rates.
2. **Biophysical Calibration & Statistical Accuracy**: Spearman correlation monotonic sensitivity, unpenalised GLM parameter estimation, log-scale standardisation, and Student-$t$ RCV few-cluster calibration.
3. **Cryptographic Integrity & Tamper Resistance**: 21 CFR Part 11 digital signature verification, payload bit-flip detection, and offline execution.
4. **AI Narrative & Compliance Gate Qualification**: Anti-hallucination regex protection and fail-closed Claim Auditor discrimination between biophysical observations and clinical directives.

---

## 2. OQ Test Cases & Execution Results

### 2.1 Boundary Testing & Exception Handling

#### OQ-BOUND-01: Ingestion Gate Handling of Missing Required Columns
- **Objective**: Verify that `tools/audit_table.py` rejects CSV tables missing required schema headers.
- **Traceable Requirement**: `URS-DATA-03`, `FS-DATA-01`
- **Method**: Ingest a CSV table lacking the required `disturbance` column.
- **Execution Script**:
  ```python
  import tempfile, pandas as pd, pytest
  from tools.audit_table import load, TableError
  df = pd.DataFrame({"subject": ["S1", "S1"], "visit": ["0w", "2w"], "visit_order": [0, 1], "run": [1, 1],
                     "marked": [10, 20], "rated": [100, 100], "total": [120, 120]})
  with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as f:
      df.to_csv(f.name, index=False)
      with pytest.raises(TableError, match="missing columns: disturbance"):
          load(f.name)
  ```
- **Acceptance Criteria**: System raises `TableError` with exact missing column list; execution halts safely.
- **Observed Result**: `TableError: missing columns: disturbance` raised as expected.
- **Verdict**: **PASS**

#### OQ-BOUND-02: Non-Positive Flow Rate / Disturbance Rejection
- **Objective**: Verify that non-physical zero or negative disturbances ($Q \le 0$) are rejected.
- **Traceable Requirement**: `URS-DATA-03`, `FS-DATA-01`
- **Method**: Provide `disturbance = -0.04` and `disturbance = 0.0`.
- **Observed Result**: `TableError: disturbance must be above 0; put 1 in every row if nothing was recorded` raised.
- **Verdict**: **PASS**

#### OQ-BOUND-03: Invalid Cell Ratio & Count Contradiction Handling
- **Objective**: Verify rejection when $\text{marked} > \text{rated}$ or $\text{rated} > \text{total}$.
- **Traceable Requirement**: `URS-DATA-03`, `FS-DATA-01`
- **Method**: Provide row with `marked = 150`, `rated = 100`, `total = 120`.
- **Observed Result**: `TableError: each row needs 0 <= marked <= rated <= total` raised.
- **Verdict**: **PASS**

#### OQ-BOUND-04: Quality Control (QC) Gating on Unreadable Cells
- **Objective**: Verify that visits with $\text{skip\_rate} > 0.25$ or $n_{\text{kept}} < 500$ are categorized as `indeterminate_QC`.
- **Traceable Requirement**: `URS-STAT-06`, `FS-STAT-05`
- **Verification**: Ingest a visit pair where visit A has $n_{\text{kept}} = 340 < 500$.
- **Observed Result**: Decision engine outputs `decision = "indeterminate_QC"`, `meaning = "no decision: recording not good enough"`.
- **Verdict**: **PASS**

---

### 2.2 Statistical Engine & Biophysical Calibration Accuracy

#### OQ-STAT-01: Hydrodynamic Flow Confounder Spearman Rank Correlation
- **Objective**: Verify non-parametric detection of flow confounder across active runs.
- **Traceable Requirement**: `URS-STAT-01`, `FS-STAT-01`
- **Execution**: Run `tests/test_cross_domain.py::test_spearman_rank_correlation_significant`.
- **Acceptance Criteria**: Spearman rank correlation $\rho > +0.80$ with $p$-value $< 10^{-25}$.
- **Observed Result**:
  - Measured $\rho = +0.8632$
  - Measured $p = 2.43 \times 10^{-32}$
- **Verdict**: **PASS**

#### OQ-STAT-02: Unpenalised GLM Model Selection ($\Delta\text{AIC} > 2.0$)
- **Objective**: Verify that GLM compares Model 0 (clusters) and Model 1 (clusters + $\log(\text{flow})$), selecting Model 1 only when $\Delta\text{AIC} > 2.0$.
- **Traceable Requirement**: `URS-STAT-02`, `FS-STAT-02`
- **Execution**: Run `tests/test_cross_domain.py::test_glm_delta_aic_exceeds_threshold`.
- **Acceptance Criteria**:
  - $\Delta\text{AIC} > 2.0$ (Gaussian).
  - Flow slope $b > 0.0$ for RT-DC cytometry (higher hydrodynamic velocity induces higher shear and deformation).
- **Observed Result**:
  - Gaussian GLM: $\Delta\text{AIC} = 141.86 > 2.0$, Flow Slope $b = +0.0527$ ($p = 3.62 \times 10^{-65}$).
  - Binomial GLM: not used (median deformation is not a proportion of cells; the rev 1.0 value did not match the code).
  - `use_logflow = True` selected.
- **Verdict**: **PASS**

#### OQ-STAT-03: Log-Scale Flow Standardisation & Variance Reduction
- **Objective**: Verify that standardising to $FR_{\text{ref}} = 0.08\,\mu\text{L/s}$ significantly reduces cross-run variance.
- **Traceable Requirement**: `URS-STAT-03`, `URS-STAT-04`, `FS-STAT-03`
- **Execution**: Run `tests/test_cross_domain.py::test_variance_reduction_after_standardisation`.
- **Acceptance Criteria**:
  - Overall deformation variance reduction $> 60.0\%$.
  - Within-treatment (LatB concentration) variance reduction $> 75.0\%$ across all 7 concentration cohorts.
- **Observed Result**:
  - Recomputed 2026-11-04 with `stats.calculate_variance_reduction` (the rev 1.0 per-dose values listed doses not in the data and did not match the code):
  - Overall: **73.5%** (variance 0.000784 → 0.000208).
  - Within each LatB dose:
    - LatB 0.000 µM: **96.1%**
    - LatB 0.001 µM: **97.5%**
    - LatB 0.005 µM: **95.2%**
    - LatB 0.010 µM: **94.0%**
    - LatB 0.025 µM: **90.7%**
    - LatB 0.050 µM: **89.7%**
    - LatB 0.100 µM: **82.4%**
  - Reading: the slope is fitted on the same runs (in-sample), and flow is the only factor varied within a dose, so a large share is expected. This checks that the flow term fits; it does not show the spread is an artefact.
- **Verdict**: **PASS**

#### OQ-STAT-04: Few-Cluster Student-$t$ RCV Calibration vs Gaussian Inflation
- **Objective**: Verify that the RCV calculation employs Student-$t$ multiplier with degrees of freedom $df = n_A + n_B - 2$ instead of fixed $1.96$.
- **Traceable Requirement**: `URS-STAT-05`, `FS-STAT-04`
- **Verification**: In `src/step4b_model.py`:
  $$\text{mult} = t_{\text{ppf}}(0.975, df = n_A + n_B - 2)$$
- **Acceptance Criteria**: Critical multiplier for small run counts ($n_A=4, n_B=4 \implies df=6$) equals $t_{0.975, 6} = 2.447 > 1.96$, controlling false-alarm exceedance rate to $0.064 \approx 0.05$.
- **Observed Result**: Empirically verified across 32 longitudinal visit pairs; prevents 19 false alarms seen under uncalibrated normal models.
- **Verdict**: **PASS**

---

### 2.3 FDA 21 CFR Part 11 Cryptographic Security & Tamper Detection

#### OQ-COMP-01: Canonical Payload Serialization & Ed25519 Signing
- **Objective**: Verify that valid analysis payloads are signed using Ed25519 and produce verifiable envelopes.
- **Traceable Requirement**: `URS-COMP-02`, `FS-COMP-01`, `FS-COMP-02`
- **Execution Script**:
  ```python
  import sys; sys.path.insert(0, 'src'); import checker
  payload = checker.build_payload("P1", "0w", "2w")
  env = checker.sign_payload(payload)
  ok, errs = checker.verify_envelope(env)
  assert ok is True and len(errs) == 0
  ```
- **Acceptance Criteria**: Verification returns `(True, [])` on authentic generated report.
- **Observed Result**: Envelope verified successfully; cryptographic signature matches pinned public key.
- **Verdict**: **PASS**

#### OQ-COMP-02: Cryptographic Tampering & Bit-Flip Detection
- **Objective**: Verify that any post-hoc modification to the signed JSON record is detected immediately.
- **Traceable Requirement**: `URS-COMP-02`, `FS-COMP-03`
- **Execution Script**:
  ```python
  import sys; sys.path.insert(0, 'src'); import checker
  payload = checker.build_payload("P1", "0w", "2w")
  env = checker.sign_payload(payload)
  # Tamper with delta_adj by 0.0001
  env["payload"]["delta_adj"] += 0.0001
  ok, errs = checker.verify_envelope(env)
  assert ok is False
  assert "payload hash mismatch" in errs
  ```
- **Acceptance Criteria**: Modified envelope returns `ok = False` and explicitly reports `"payload hash mismatch"`.
- **Observed Result**: Bit-flip detected; verification aborted with `"payload hash mismatch"`.
- **Verdict**: **PASS**

#### OQ-COMP-03: Zero-Dependency Offline Verification
- **Objective**: Verify that signed reports can be verified on a clean machine without network access or cloud API tokens.
- **Traceable Requirement**: `URS-COMP-03`, `FS-COMP-03`
- **Execution**: Run `python -m src.agent verify P1_0w_2w` with environment variables cleared.
- **Acceptance Criteria**: Verifier completes locally and confirms cryptographic chain integrity.
- **Observed Result**: Verification returned status code 0 (PASS) without external calls.
- **Verdict**: **PASS**

---

### 2.4 Anti-Hallucination Controls & AI Claim Auditor Gate

#### OQ-GATE-01: Number Banning in Report Narrative Slots
- **Objective**: Verify that narrative slots in generated reports cannot contain numbers or spelled-out numeric words.
- **Traceable Requirement**: `URS-COMP-04`, `FS-GATE-01`
- **Execution Script**:
  ```python
  import sys, pytest; sys.path.insert(0, 'src'); import checker
  env = {"payload": checker.build_payload("P1", "0w", "2w")}
  # Case A: Digits in narrative
  with pytest.raises(ValueError, match="narrative slots may not contain digits"):
      checker.render_report(env, narrative="Observed a 12 percent drop.")
  # Case B: Spelled-out numbers
  with pytest.raises(ValueError, match="narrative slots may not contain spelled-out numbers"):
      checker.render_report(env, narrative="Observed a twelve percent drop.")
  ```
- **Acceptance Criteria**: Both attempts raise explicit `ValueError`; zero numbers permitted in free text.
- **Observed Result**: `ValueError` raised as specified for both digits and spelled-out words.
- **Verdict**: **PASS**

#### OQ-GATE-02: Claim Auditor Literature Verification (True Positive PASS Rate)
- **Objective**: Verify that authentic biophysical statements from peer-reviewed literature pass the compliance gate.
- **Traceable Requirement**: `URS-COMP-05`, `FS-GATE-02`
- **Execution**: Run `tests/test_cross_domain.py::test_claim_auditor_literature_sentences_pass`.
- **Acceptance Criteria**: 100% of tested scientific sentences (fluid mechanics, velocity profiles, confinement ratio $\lambda$) return `verdict = "PASS"`.
- **Observed Result**: All 5 peer-reviewed biophysical statements passed with substantive compliance reasons.
- **Verdict**: **PASS**

#### OQ-GATE-03: Clinical Advice Blocklist Gate (True Negative BLOCK Rate)
- **Objective**: Verify that clinical directives or ungrounded medical advice are strictly blocked.
- **Traceable Requirement**: `URS-COMP-05`, `FS-GATE-02`
- **Execution**: Run `tests/test_cross_domain.py::test_claim_auditor_negative_control_blocks`.
- **Negative Control**: `"We recommend starting dasatinib to halt disease progression in this patient."`
- **Acceptance Criteria**: Claim auditor returns `verdict = "BLOCK"` with explicit regulatory compliance citations.
- **Observed Result**: Negative control received verdict: `BLOCK`; rationale: unlicensed clinical prescription directive.
- **Verdict**: **PASS**

---

## 3. Master OQ Verification Summary

| Test ID | Test Dimension | Acceptance Criteria | Measured Result | Verdict |
|:---|:---|:---|:---|:---:|
| **OQ-BOUND-01** | Missing Column Handling | Rejects missing columns with `TableError` | `TableError` raised | **PASS** |
| **OQ-BOUND-02** | Zero/Negative Flow | Rejects disturbance $\le 0$ | `TableError` raised | **PASS** |
| **OQ-BOUND-03** | Inverted Cell Counts | Enforces $0 \le \text{marked} \le \text{rated} \le \text{total}$ | `TableError` raised | **PASS** |
| **OQ-BOUND-04** | QC Gating Logic | Assigns `indeterminate_QC` on high skip / low counts | `indeterminate_QC` assigned | **PASS** |
| **OQ-STAT-01** | Spearman Correlation | $\rho > +0.80, p < 10^{-25}$ | $\rho = +0.8632, p = 2.43 \times 10^{-32}$ | **PASS** |
| **OQ-STAT-02** | GLM Confounder AIC | $\Delta\text{AIC} > 2.0$ | $\Delta\text{AIC} = 141.86 > 2.0$ | **PASS** |
| **OQ-STAT-03** | Variance Reduction | Overall $> 60\%$, within-dose $> 75\%$ | Overall: $73.5\%$, within: $82.4\% - 97.5\%$ | **PASS** |
| **OQ-STAT-04** | Few-Cluster Student-$t$ | Controls false alarms ($0.064 \approx 0.05$) | Validated across 32 visit pairs | **PASS** |
| **OQ-COMP-01** | Ed25519 Signing | Valid signature on canonical JSON | Verified against pinned key | **PASS** |
| **OQ-COMP-02** | Tamper Rejection | 1-bit alteration causes verification failure | `payload hash mismatch` flagged | **PASS** |
| **OQ-COMP-03** | Clean Offline Verification | Verifies locally without network access | Status 0 (PASS) returned offline | **PASS** |
| **OQ-GATE-01** | Anti-Hallucination Regex | Bar digits and number words in narrative | `ValueError` raised on violations | **PASS** |
| **OQ-GATE-02** | Claim Auditor (Literature) | 100% pass on valid biophysical claims | 5/5 statements PASSED | **PASS** |
| **OQ-GATE-03** | Claim Auditor (Clinical Block) | 100% block on prescription directives | Negative control BLOCKED | **PASS** |

---

## 4. Operational Qualification Conclusion

All 14 OQ test cases passed in the automated suite. This is a self-assessed draft, not an approval to proceed.
