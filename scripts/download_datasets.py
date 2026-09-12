#!/usr/bin/env python
"""Download and stage AegisFlow raw datasets into data/raw/."""
from __future__ import annotations
 
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import urlretrieve
 
RAW = Path(__file__).resolve().parents[1] / 'data' / 'raw'
 
KAGGLE_SETS = {
    'paysim':   'ealaxi/paysim1',
    'ieee-cis': 'ieee-fraud-detection',
}
 
DIRECT = {
    'ofac/sdn.csv': 'https://www.treasury.gov/ofac/downloads/sdn.csv',
}
 
 
def have_kaggle() -> bool:
    return bool(os.getenv('KAGGLE_USERNAME') and os.getenv('KAGGLE_KEY'))
 
 
def fetch_kaggle(name: str, ref: str) -> None:
    target = RAW / name
    if target.exists() and any(target.iterdir()):
        print(f'[skip] {name} already present')
        return
    target.mkdir(parents=True, exist_ok=True)
    cmd = ['kaggle', 'datasets', 'download', '-d', ref, '-p', str(target)]
    if '/' not in ref:
        cmd = ['kaggle', 'competitions', 'download', '-c', ref, '-p', str(target)]
    print(f'[get ] {name} <- {ref}')
    subprocess.run(cmd, check=True)
    for z in target.glob('*.zip'):
        with zipfile.ZipFile(z) as zf:
            zf.extractall(target)
        z.unlink()
        
def fetch_direct(rel: str, url: str) -> None:
    target = RAW / rel
    if target.exists():
        print(f'[skip] {rel} already present')
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f'[get ] {rel} <- {url}')
    urlretrieve(url, target)
 
 
def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    if have_kaggle():
        for name, ref in KAGGLE_SETS.items():
            fetch_kaggle(name, ref)
    else:
        print('[warn] KAGGLE_USERNAME/KAGGLE_KEY not set — skipping Kaggle datasets.')
        print('       Place the CSVs manually under data/raw/<name>/ and re-run.')
    for rel, url in DIRECT.items():
        try:
            fetch_direct(rel, url)
        except Exception as exc:  # network restricted environments
            print(f'[warn] {rel} failed: {exc}')
    print('done. Next: dvc add data/raw && dvc push')
    return 0
 
 
if __name__ == '__main__':
    sys.exit(main())
