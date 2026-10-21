"""Execute MIMO após a extração dos mapas; --dry-run valida sem simular."""
import multiprocessing as mp
from _bootstrap import PROJECT_ROOT
from tv3_simulations.common.execution import main

# Use --config para selecionar uma campanha; o padrão é o exemplo de uma torre.
DEFAULT_CONFIG = PROJECT_ROOT / 'configs/simulations/mimo_capacity/exemplo_guia.yaml'

if __name__ == '__main__':
    mp.freeze_support()
    raise SystemExit(main('mimo_capacity', DEFAULT_CONFIG))
