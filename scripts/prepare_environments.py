"""Prepare mapas de uma estação de exemplo ou de um lote escolhido com --config."""
from _bootstrap import PROJECT_ROOT
from tv3_simulations.propagation.prepare import main

# Use --config para escolher o lote de torres sem editar este arquivo.
DEFAULT_CONFIG = PROJECT_ROOT / 'configs/extraction/exemplo_guia.yaml'

if __name__ == '__main__':
    raise SystemExit(main(DEFAULT_CONFIG))
