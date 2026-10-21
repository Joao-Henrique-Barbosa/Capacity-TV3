"""Execute MIMO-LDM usando os mesmos mapas determinísticos do modelo MIMO."""
import multiprocessing as mp
from _bootstrap import PROJECT_ROOT
from tv3_simulations.common.execution import main

# Use --config para escolher a campanha sem editar este arquivo.
DEFAULT_CONFIG = PROJECT_ROOT / 'configs/simulations/mimo_ldm_capacity/exemplo_guia.yaml'

if __name__ == '__main__':
    mp.freeze_support()
    raise SystemExit(main('mimo_ldm_capacity', DEFAULT_CONFIG))
