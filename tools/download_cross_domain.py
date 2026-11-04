"""Download and verify genuine MetaDeformability RT-DC dataset."""
import urllib.request
from pathlib import Path
import pandas as pd

DEST = Path(__file__).resolve().parent.parent / "data" / "cross_domain"
DEST.mkdir(parents=True, exist_ok=True)

URLS = {
    "HL60_LatB_3fr_20151019.txt": "https://raw.githubusercontent.com/dicarlo-lab/metadeformability/master/Data_Raw/LatB_FlowRate/20151019_HL60_LatB_3fr.txt",
    "HL60_LatB_3fr_20151128.txt": "https://raw.githubusercontent.com/dicarlo-lab/metadeformability/master/Data_Raw/LatB_FlowRate/20151128_HL60_LatB_3fr.txt",
    "HL60_LatB_3fr_20151130.txt": "https://raw.githubusercontent.com/dicarlo-lab/metadeformability/master/Data_Raw/LatB_FlowRate/20151130_HL60_LatB_3fr.txt",
    "HL60_LatB_3fr_20151206.txt": "https://raw.githubusercontent.com/dicarlo-lab/metadeformability/master/Data_Raw/LatB_FlowRate/20151206_HL60_LatB_3fr.txt",
    "HL60_LatB_3fr_20151213.txt": "https://raw.githubusercontent.com/dicarlo-lab/metadeformability/master/Data_Raw/LatB_FlowRate/20151213_HL60_LatB_3fr.txt",
    "RTDC_singlecell_strain_300mOsm.tsv": "https://raw.githubusercontent.com/dicarlo-lab/metadeformability/master/Data_Raw/Strain/RTDC/20160129_04_300mOsm%20-%20M1.tsv",
    "RTDC_singlecell_latb_set1.txt": "https://raw.githubusercontent.com/dicarlo-lab/metadeformability/master/Data_Raw/LatB/RT-DC/RTDC_LatB_set1_20151019.txt",
    "LatB_RTDC_Medians_Summary.csv": "https://raw.githubusercontent.com/dicarlo-lab/metadeformability/master/Data_Processed/LatB/LatB_RTDC_Medians_Summary.csv",
}

def download_all():
    print(f"Target directory: {DEST}")
    for fname, url in URLS.items():
        p = DEST / fname
        if not p.exists() or p.stat().st_size == 0:
            print(f"Downloading {fname} from {url}...")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read()
                p.write_bytes(content)
            print(f"Saved {fname} ({len(content):,} bytes)")
        else:
            print(f"Already exists: {fname} ({p.stat().st_size:,} bytes)")

def verify_dataset():
    run_files = sorted(list(DEST.glob("HL60_LatB_3fr_*.txt")))
    dfs = []
    for f in run_files:
        df = pd.read_csv(f, sep=r"\s+")
        dfs.append(df)
    all_runs = pd.concat(dfs, ignore_index=True)
    active_runs = all_runs[all_runs["FR"] > 0]
    total_cells = int(active_runs["N"].sum())
    n_active = len(active_runs)
    flow_rates = sorted(list(active_runs["FR"].unique()))
    dates = sorted(list(all_runs["Date"].unique()))

    print("\n=== RT-DC Multi-Flow Verification ===")
    print(f"Run files count: {len(run_files)}")
    print(f"Replicates (dates): {dates}")
    print(f"Total rows in run files: {len(all_runs)}")
    print(f"Active flow runs (FR > 0): {n_active}")
    print(f"Total measured cells across active runs: {total_cells:,}")
    print(f"Flow rates tested (uL/s): {flow_rates}")
    print(f"Mean deformation at 0.04 uL/s: {active_runs[active_runs['FR']==0.04]['MedD'].mean():.4f}")
    print(f"Mean deformation at 0.08 uL/s: {active_runs[active_runs['FR']==0.08]['MedD'].mean():.4f}")
    print(f"Mean deformation at 0.12 uL/s: {active_runs[active_runs['FR']==0.12]['MedD'].mean():.4f}")

    # Single cell tables
    sc1 = DEST / "RTDC_singlecell_strain_300mOsm.tsv"
    if sc1.exists():
        df_sc1 = pd.read_csv(sc1, sep="\t")
        print(f"\nSingle-cell strain table events: {len(df_sc1):,} cells, columns: {list(df_sc1.columns)[:6]}...")
    sc2 = DEST / "RTDC_singlecell_latb_set1.txt"
    if sc2.exists():
        df_sc2 = pd.read_csv(sc2, sep=r"\s+")
        print(f"Single-cell LatB titration table events: {len(df_sc2):,} cells, columns: {list(df_sc2.columns)[:6]}...")

if __name__ == "__main__":
    download_all()
    verify_dataset()
