"""Localize src a partir do script e limite threads dentro de cada processo."""
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'src'))
# Evita que cada processo do pool abra outra equipe de threads numéricas.
for variable in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ.setdefault(variable, '1')
os.environ.setdefault('MPLBACKEND', 'Agg')
