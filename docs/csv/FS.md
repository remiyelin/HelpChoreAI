# Functional Specification (FS)
## HelpChoreAI: Biophysical Measurement & Protocol-Variance Auditing Platform

> **Status: draft, validation-ready, not validated.** Written by the developer with AI coding agents. No independent quality unit has reviewed or approved it, and nothing here is signed. It maps requirements to automated tests; it is not a GxP validation record. HelpChoreAI is a research tool: it gives no medical advice and is not meant for clinical decisions or regulatory submissions. Test counts are as recorded on 2026-11-02; run `pytest` for the current suite. Revised 2026-11-04: statistics claims corrected (see `CROSS_DOMAIN_EVIDENCE.md`).

**Document Identifier**: `VAL-FS-2026-001`  
**Revision**: `1.0`  
**GAMP 5 Classification**: `Category 5 — Custom / Bespoke Computational Science Tool`  
**Traceable URS**: `VAL-URS-2026-001`  
**Target Environment**: `HelpChoreAI Python 3.12+ (Windows / Linux / POSIX)`  
**Effective Date**: `2026-11-02`  
**Status**: `Draft, self-assessed (not approved)`  

---

### Executive Approval Sign-Off

| Role | Name & Title | Signature | Date |
|:---|:---|:---|:---|
| **Project Lead & System Architect** | Muhammed Ali Sain | *Not signed (draft)* | 2026-11-02 |

---

## 1. System Architecture & Functional Decomposition

HelpChoreAI implements a modular, deterministic computational pipeline structured into four primary functional engines:
1. **FS-DATA (Ingestion & Schema Engine)**: Validates input table schemas, enforces data integrity bounds, verifies raw file SHA-256 digests, and generates immutable provenance manifests.
2. **FS-STAT (Biophysical Calibration & Statistical Engine)**: Detects hydrodynamic flow confounders, estimates Generalized Linear Models (GLMs), standardises deformation and cell counts to nominal reference flow rates, calculates Reference Change Value ($\text{RCV}_{95}$) bands using small-sample Student-$t$ multipliers, and forecasts required sample sizes for statistical power.
3. **FS-COMP (Cryptographic Sealing & Regulatory Compliance Engine)**: Constructs canonical JSON payloads, computes immutable hash chains, generates and verifies Ed25519 digital signatures against pinned public keys, and renders strictly templated reports.
4. **FS-GATE (Anti-Hallucination & Claim Auditor Engine)**: Enforces regex-based narrative blocklists preventing numbers or clinical advice in free-text slots, and submits claims to a fail-closed compliance gate.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               HELPCHOREAI ARCHITECTURE                                 │
├────────────────────────────────────────────────────────────────────────────────────────┤
│  [Raw Experimental Ingestion]                                                          │
│    ├── FS-DATA-01: Tabular CSV/TSV Parser & Validator (tools/audit_table.py)           │
│    ├── FS-DATA-02: Single-Cell Event Cytometry Parser (src/stats.py, step2_analysis.py)│
│    └── FS-DATA-03: SHA-256 Manifest Digest Validator (tools/figshare_ingest.py)        │
│                                       │                                                │
│                                       ▼                                                │
│  [Biophysical Calibration & Statistical Decision Engine]                               │
│    ├── FS-STAT-01: Spearman Rank Correlation Evaluator                                 │
│    ├── FS-STAT-02: GLM Confounder Calibration & Information Criterion (ΔAIC > 2.0)     │
│    ├── FS-STAT-03: Flow Standardisation Transform (Continuous Linear & Logit-Scale)   │
│    ├── FS-STAT-04: Few-Cluster Student-t RCV & Bootstrap Variance Estimator           │
│    ├── FS-STAT-05: Quality Control (QC) Gating & Tri-State Decision Logic              │
│    └── FS-STAT-06: Statistical Power & Sample Size Forecasting                         │
│                                       │                                                │
│                                       ▼                                                │
│  [Cryptographic Sealing & Audit Engine]                                                │
│    ├── FS-COMP-01: Canonical JSON Serialization & Hash-Chaining                        │
│    ├── FS-COMP-02: Ed25519 Signature Generator & Public Key Pinner                    │
│    └── FS-COMP-03: Standalone Zero-Dependency Offline Verifier                        │
│                                       │                                                │
│                                       ▼                                                │
│  [Compliance Gate & Anti-Hallucination Layer]                                          │
│    ├── FS-GATE-01: Deterministic Number-Free Narrative Templater                       │
│    └── FS-GATE-02: Fail-Closed LLM Claim Auditor Compliance Client                     │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Mathematical Foundations & Algorithmic Specifications

### 2.1 FS-STAT-01: Spearman Monotonic Rank Correlation
To evaluate whether microfluidic volumetric flow rate ($Q$) acts as a physical confounder of cell deformability, the system computes the non-parametric Spearman rank correlation:
$$\rho = 1 - \frac{6 \sum_{i=1}^n d_i^2}{n(n^2 - 1)}$$
where $d_i = \text{rank}(Q_i) - \text{rank}(D_i)$, and $D_i$ denotes observed cellular deformation ($1 - \text{circularity}$).  
The two-sided asymptotic $p$-value is derived via Student's $t$ transformation:
$$t = \rho \sqrt{\frac{n - 2}{1 - \rho^2}}, \quad p = 2 \cdot \left(1 - F_t(|t|, df = n - 2)\right)$$

### 2.2 FS-STAT-02: Generalized Linear Model (GLM) Confounder Selection ($\Delta\text{AIC}$)
To standardise measurements without assuming homoscedasticity or linear normality, HelpChoreAI specifies two GLM families:

#### Model 0: Biological Replicate Baseline (No Flow Predictor)
$$\eta_0 = \sum_{c \in \text{Clusters}} \beta_c \cdot \mathbb{I}(c_i = c)$$
where $\mathbb{I}$ is the indicator function for biological replicate date or patient identifier.

#### Model 1: Confounder-Augmented Specification
$$\eta_1 = \sum_{c \in \text{Clusters}} \beta_c \cdot \mathbb{I}(c_i = c) + \beta_{\text{flow}} \cdot \log(Q_i)$$

#### Family-Specific Links:
1. **Gaussian GLM (Continuous Deformability)**:
   - Target: Median deformation $MedD \in (0, 1)$.
   - Link: Identity ($\eta = \mu$).
   - Log-likelihood: $\ell(\mu, \sigma^2) = -\frac{n}{2}\log(2\pi\sigma^2) - \frac{1}{2\sigma^2}\sum_{i=1}^n (y_i - \mu_i)^2$.
2. **Binomial GLM (Aggregated Single-Cell Counts)** — not used for RT-DC median deformation, which is not a proportion of cells:
   - Target: Successes $k_i = \text{round}(p_i \cdot N_i)$, trials $N_i$.
   - Link: Logit ($\eta = \log\frac{p}{1 - p}$).
   - Log-likelihood: $\ell(p) = \sum_{i=1}^n \left[ k_i \log(p_i) + (N_i - k_i)\log(1 - p_i) \right]$.

#### Model Selection Criterion:
The system computes the Akaike Information Criterion for both models:
$$\text{AIC} = 2k - 2\ln(\hat{L})$$
$$\Delta\text{AIC} = \text{AIC}(M_0) - \text{AIC}(M_1)$$
The flow confounder is incorporated into standardisation **if and only if**:
$$\Delta\text{AIC} > 2.0$$
If $\Delta\text{AIC} \le 2.0$, the system selects $M_0$ ($\beta_{\text{flow}} \equiv 0$), preventing over-fitting when flow variations do not exert statistically significant mechanical artifacts.

### 2.3 FS-STAT-03: Log-Scale Flow Standardisation Transform
Measurements are projected from their observed flow rate $Q_i$ to the nominal benchmark reference flow rate $Q_{\text{ref}}$ ($0.016\,\mu\text{L/s}$ for RBC assay, $0.08\,\mu\text{L/s}$ for RT-DC assay):

#### Continuous Deformation (Linear Transform):
$$y_{\text{adj}, i} = y_{\text{obs}, i} - \hat{\beta}_{\text{flow}} \cdot \left(\log(Q_i) - \log(Q_{\text{ref}})\right)$$

#### Binary Cell Fraction / Marker Share (Logit Transform):
$$\text{logit}(p_{\text{adj}, i}) = \text{logit}(p_{\text{obs}, i}) + \left(\hat{\eta}(Q_{\text{ref}}, c_i) - \hat{\eta}(Q_i, c_i)\right)$$
$$p_{\text{adj}, i} = \frac{1}{1 + \exp\left(-\text{logit}(p_{\text{adj}, i})\right)}$$
where $p_{\text{obs}, i}$ is clipped to $[\epsilon, 1 - \epsilon]$ ($\epsilon = 10^{-6}$) to prevent singularity.

### 2.4 FS-STAT-04: Few-Cluster Student-$t$ Reference Change Value ($\text{RCV}_{95}$)
To evaluate whether the observed change between two longitudinal visits ($\text{Visit}_A \to \text{Visit}_B$) exceeds measurement noise, the system employs cluster bootstrapping and a Student-$t$ distribution multiplier:

1. **Cluster Bootstrapping**:
   - Resampling unit: Laboratory run (cluster) within visit.
   - Replications: $B = 2,000$, seeded deterministically at $\text{SEED} = 20261026$.
   - Weighting: Within each bootstrap sample $b \in \{1, \dots, B\}$, the mean adjusted fraction is weighted by kept cell count:
     $$\bar{p}_b = \frac{\sum_{j \in \text{sample}} n_{\text{kept}, j} \cdot p_{\text{adj}, j}}{\sum_{j \in \text{sample}} n_{\text{kept}, j}}$$
   - Visit variance is estimated as the sample bootstrap variance:
     $$\hat{\sigma}^2_V = \frac{1}{B - 1}\sum_{b=1}^B (\bar{p}_b - \bar{p}^*)^2$$

2. **Few-Cluster Critical Multiplier**:
   Standard normal approximations ($z_{0.975} = 1.96$) assume infinite degrees of freedom, producing an anti-conservative false-alarm rate of $8.4\%$ when visits contain few runs ($n_{\text{runs}} \in [4, 11]$).  
   HelpChoreAI substitutes the Student-$t$ critical value:
   $$t_{\text{crit}} = t_{0.975, df}, \quad df = \max(n_A + n_B - 2, 1)$$
   $$\text{RCV}_{95} = t_{\text{crit}} \cdot \sqrt{\hat{\sigma}^2_A + \hat{\sigma}^2_B}$$
   This degrees-of-freedom correction restores empirical false-alarm rates to $0.064$, aligning with nominal $\alpha = 0.05$ expectations.

### 2.5 FS-STAT-05: Quality Control Gating & Tri-State Decision Logic
For each consecutive visit pair $(V_A, V_B)$ with observed adjusted difference $\Delta_{\text{adj}} = \bar{p}_{\text{adj}, B} - \bar{p}_{\text{adj}, A}$:
1. **QC Gating**:
   $$\text{If } \left(\text{skip\_rate}_A > 0.25 \text{ or } \text{skip\_rate}_B > 0.25 \text{ or } n_{\text{kept}, A} < 500 \text{ or } n_{\text{kept}, B} < 500\right):$$
   $$\implies \text{Decision} = \texttt{indeterminate\_QC}$$
2. **Biological Exceedance**:
   $$\text{Else if } |\Delta_{\text{adj}}| > \text{RCV}_{95}: \implies \text{Decision} = \texttt{exceeds\_RCV}$$
3. **Measurement Wobble (Within Limits)**:
   $$\text{Else}: \implies \text{Decision} = \texttt{within\_RCV}$$

### 2.6 FS-STAT-06: Sample Size and Statistical Power Forecasting
The system calculates the required run count ($N_{\text{runs}}$) per visit to detect a true underlying biological shift $\delta$ with targeted statistical power $1 - \beta = 0.80$ at $\alpha = 0.05$:
$$N_{\text{needed}} = \left\lceil N_{\text{median}} \cdot \left(\frac{\text{wobble}_{\text{median}}}{\delta_{\text{target}}}\right)^2 \right\rceil$$
where $\text{wobble}_{\text{median}}$ is the median $\text{RCV}_{95}$ across observed visit pairs, and $N_{\text{median}}$ is the median run count per visit.

---

## 3. Data Schema Specifications

### 3.1 FS-DATA-01: Tabular Run Table Schema (CSV/TSV)
All input laboratory run tables processed by `tools/audit_table.py` must strictly adhere to the 8-column schema:

| Column Name | Data Type | Permissible Range | Nullable | Functional Validation Rule |
|:---|:---|:---:|:---:|:---|
| `subject` | String | `[A-Za-z0-9_-]{1,32}` | No | Anonymized identifier. Regex-validated; no patient names permitted. |
| `visit` | String | UTF-8 Text | No | Visit label (e.g. `0w`, `2w`, `8w`). |
| `visit_order` | Integer | $\ge 0$ | No | Monotonically non-decreasing order index. |
| `run` | Integer/String | Alphanumeric | No | Intra-visit run identifier. Unique per `(subject, visit, run)`. |
| `marked` | Integer | $\ge 0$ | No | Count of cells exhibiting target morphometric marker. |
| `rated` | Integer | $\ge 0$ | No | Count of readable cells evaluated by classifier/operator. |
| `total` | Integer | $\ge 1$ | No | Total cellular events recorded by cytometer. |
| `disturbance` | Float | $> 0.0$ | No | Flow rate ($\mu\text{L/s}$), pressure, or elapsed wait time. |

**Invariants Enforced**:
- $0 \le \text{marked} \le \text{rated} \le \text{total}$
- $\text{disturbance} > 0.0$
- At least two distinct visits per subject (`len(visits) >= 2`).

### 3.2 FS-DATA-02: Single-Cell Event Data Schema (RT-DC TSV)
Unaggregated single-cell deformation records (`RTDC_singlecell_strain_300mOsm.tsv`, `RTDC_singlecell_latb_set1.txt`) require:

| Column Name | Physical Quantity | Standard Units | Expected Range |
|:---|:---|:---:|:---:|
| `deform` / `Deformation` | Hydrodynamic deformation | Dimensionless | $[0.0, 0.80]$ |
| `area_um` / `area_cvx` | Cell cross-sectional area | $\mu\text{m}^2$ | $[10.0, 600.0]$ |
| `aspect` | Bounding box aspect ratio | Dimensionless | $[0.8, 3.5]$ |
| `emodulus` | Estimated Young's modulus | $\text{kPa}$ | $[0.1, 10.0]$ |
| `pos_x`, `pos_y` | Lateral channel position | $\mu\text{m}$ | Centerline channel bounds |

### 3.3 FS-COMP-01: Signed JSON Report Envelope Schema
The cryptographic output record generated by `src/checker.py` and `src/agent.py` conforms to the canonical JSON schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "HelpChoreAI Signed Audit Envelope",
  "type": "object",
  "required": ["payload", "signature_hex", "public_key_hex"],
  "properties": {
    "public_key_hex": {
      "type": "string",
      "pattern": "^[0-9a-f]{64}$"
    },
    "signature_hex": {
      "type": "string",
      "pattern": "^[0-9a-f]{128}$"
    },
    "payload": {
      "type": "object",
      "required": [
        "dataset_doi",
        "patient",
        "from_visit",
        "to_visit",
        "treatment",
        "delta_raw",
        "delta_adj",
        "rcv95",
        "decision",
        "ref_flow_ul_s",
        "measurand",
        "disclaimer",
        "chain",
        "payload_sha256",
        "report_sha256"
      ],
      "properties": {
        "dataset_doi": {"type": "string"},
        "patient": {"type": "string"},
        "from_visit": {"type": "string"},
        "to_visit": {"type": "string"},
        "treatment": {"type": "string"},
        "delta_raw": {"type": "number"},
        "delta_adj": {"type": "number"},
        "rcv95": {"type": "number"},
        "decision": {
          "type": "string",
          "enum": ["exceeds_RCV", "within_RCV", "indeterminate_QC"]
        },
        "ref_flow_ul_s": {"type": "number"},
        "measurand": {"type": "string"},
        "disclaimer": {"type": "string"},
        "chain": {
          "type": "object",
          "required": ["raw_manifest_sha256", "tables_sha256", "hashed_files"],
          "properties": {
            "raw_manifest_sha256": {"type": "string"},
            "tables_sha256": {
              "type": "object",
              "additionalProperties": {"type": "string"}
            },
            "hashed_files": {
              "type": "array",
              "items": {"type": "string"}
            }
          }
        },
        "payload_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "report_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}
      }
    }
  }
}
```

---

## 4. Cryptographic Envelope & Integrity Mechanisms

### 4.1 Canonical Serialization
To guarantee deterministic cryptographic digests across different operating systems and JSON serializers, payloads are serialized under RFC 8785 canonical rules:
1. Object keys sorted lexicographically (`sort_keys=True`).
2. Minimal delimiters without whitespace (`separators=(',', ':')`).
3. UTF-8 byte encoding with ASCII escape guarantees (`ensure_ascii=True`).

### 4.2 Ed25519 Digital Signing
- **Algorithm**: PureEdDSA using Curve25519 and SHA-512 (RFC 8032).
- **Private Key Storage**: Restrictively managed in `data/checker/private_key.pem`.
- **Public Key Pinning**: Pinned hex string loaded from `data/checker/public_key.hex`. The signing engine validates that $\text{Public}(\text{PrivateKey}) \equiv \text{PinnedKey}$ before computing signatures.
- **Signing Execution**:
  $$\text{PayloadHash} = \text{SHA256}(\text{Canonical}(\text{Payload}_{\backslash \{\text{sha}\}}))$$
  $$\text{ReportHash} = \text{SHA256}(\text{LF-Normalised}(\text{ReportMarkdown}))$$
  $$\text{Signature} = \text{Ed25519-Sign}(\text{PrivateKey}, \text{Canonical}(\text{Payload}))$$

### 4.3 Provenance Hash-Chaining
Reports link their decision to the upstream raw data via a nested SHA-256 chain:
$$\text{RawManifestHash} = \text{SHA256}\left(\bigoplus_{m \in \text{Manifests}} \text{LF-Norm}(m)\right)$$
$$\text{TableHashes} = \left\{ t: \text{SHA256}(\text{LF-Norm}(t)) \mid t \in \{\text{per\_run}, \text{per\_visit\_adj\_v3}, \text{visit\_pairs\_dec\_v3}\} \right\}$$
$$\text{Chain} = \text{SHA256}(\text{RawManifestHash} \parallel \text{TableHashes})$$

---

## 5. Compliance Gate & Error Handling Pathways

### 5.1 FS-GATE-01: Regex Narrative Protection
To prevent Large Language Models (LLMs) or automated agents from fabricating hallucinated statistics in audit summaries, `render_report` enforces:
1. `\d` regex search: Narrative slot cannot contain any numeric digits.
2. `NUMBER_WORDS` regex search: Narrative slot cannot contain written numeric words (`zero` through `million`, `percent`, `percentage`).
3. `BANNED` clinical phrase match: Narrative cannot contain clinical advice keywords (`diagnos`, `progression of disease`, `recommend treatment`, `start dasatinib`, `stop lithium`).

### 5.2 FS-GATE-02: Fail-Closed Claim Auditor API Gateway
External inference requests (`meta_api.baseten_chat`) submit narrative statements to a specialized compliance evaluation prompt. The response parser enforces:
- Strict JSON structure: `{"verdict": "PASS" | "BLOCK", "reasons": [...]}`.
- Failure Modes: Network timeout, non-200 HTTP code, malformed JSON, missing fields, or Markdown backticks automatically default to `verdict = "BLOCK"`.

### 5.3 Exception Handling Matrix

| Error Scenario | Root Cause | Triggered Exception | System Behavior & Mitigation |
|:---|:---|:---|:---|
| **Empty File** | File size 0 bytes | `TableError` / `FileNotFoundError` | Pipeline halts before execution; logs fatal error. |
| **Missing Schema Columns** | Header missing `disturbance` or `marked` | `TableError("missing columns: ...")` | Rejects file at ingestion gate; zero partial processing. |
| **Non-Positive Disturbance** | Flow rate $\le 0.0\,\mu\text{L/s}$ | `TableError("disturbance must be above 0")` | Rejects non-physical zero/negative flow in lab table. In RT-DC, filters reservoir controls. |
| **Inverted Cell Counts** | $\text{marked} > \text{rated}$ or $\text{rated} > \text{total}$ | `TableError("0 <= marked <= rated <= total")` | Identifies invalid counter logic; terminates ingestion. |
| **Post-Hoc Data Tampering** | Single decimal altered in signed JSON | Verification returns `(False, ["payload hash mismatch"])` | Rejects tampered record; alerts QA compliance. |
| **Missing Pinned Key** | `public_key.hex` deleted | `KeyMismatch("pinned public key missing")` | Blocks signing and verification; fails closed. |
| **Clinical Directive Detected** | AI generates "Start dasatinib 100mg" | `ValueError("narrative contains banned...")` | Blocks report generation; flags regulatory violation. |
