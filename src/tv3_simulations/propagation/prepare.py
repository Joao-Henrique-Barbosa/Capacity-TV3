"""Prepare mapas, registre sua integridade e publique os IDs consumidos pelos modelos.

Os caminhos pertencem ao YAML que os declara. Bases geográficas são abertas
somente quando é necessário calcular um mapa; mapas completos podem ser reutilizados.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import sys
import uuid

import yaml

from ..common.config import load_paths, load_towers, load_yaml, number_list, positive_int, relative_path, selected_towers
from ..common.environments import GEOMETRY, register_source, resolve_dataset
from ..common.files import atomic_json


def configure_suriacov(config_path: Path, paths, work: Path):
    # As bases geográficas são necessárias apenas na extração, não no Monte Carlo.
    raw = load_yaml(config_path)
    required = ('radio_zone_grid_shp', 'brazil_terr_limits_shp', 'clutter_ref_tif', 'brazil_geotiff')
    for name in required:
        path = paths.geography.get(name)
        if path is None or not path.is_file():
            raise FileNotFoundError(f'Configure geography.{name} no YAML de caminhos. Arquivo atual: {path}')
    raw['filePaths'] = {
        'ibge': {k: str(paths.geography[k]) for k in required[:2]},
        'ibgp': {'clutter_ref_tif': str(paths.geography['clutter_ref_tif'])},
        'srtm': {'brazil_geotiff': str(paths.geography['brazil_geotiff'])},
        'output_data_folder': str(work / 'suriacov_output'), 'tifs_data_folder': str(work / 'tifs'),
    }
    work.mkdir(parents=True, exist_ok=True)
    effective = work / 'suriacov.yaml'
    effective.write_text(yaml.safe_dump(raw, sort_keys=False), encoding='utf-8')
    os.environ['TV3_SURIACOV_CONFIG'] = str(effective)
    import matplotlib
    matplotlib.use('Agg')
    module_name = 'tv3_simulations.propagation.suriacov_local'
    if module_name in sys.modules:
        importlib.reload(sys.modules[module_name])
    else:
        importlib.import_module(module_name)
    return effective


def prepare(config_path: Path, *, dry_run=False):
    config_path = config_path.resolve()
    config = load_yaml(config_path)
    paths = load_paths(relative_path(config_path, config['paths']))
    towers = selected_towers(config, load_towers(relative_path(config_path, config['tower_catalog'])))
    frequencies = number_list(config['frequencies_ghz'], 'frequencies_ghz', strictly=True)
    # Overrides mudam os parâmetros efetivos; a simulação exige um cadastro compatível.
    overrides = config.get('extraction_overrides', {})
    allowed = {'num_samples', 'rx_height_ov_ground', 'field_th', 'excedance_perc'}
    if set(overrides) - allowed:
        raise ValueError(f'Overrides permitidos: {sorted(allowed)}')
    if 'num_samples' in overrides:
        positive_int(overrides['num_samples'], 'num_samples')
    towers = [dict(t, **overrides) for t in towers]
    for tower in towers:
        if tower['num_samples'] < 10:
            raise ValueError('O extrator legado precisa de num_samples >= 10 para sua vizinhanca central e perfis P.1812.')
    if not isinstance(config.get('reuse_existing', True), bool):
        raise ValueError('reuse_existing deve ser booleano.')
    print(f'Preparacao de grade completa: {len(towers)} torres x {len(frequencies)} frequencias.', flush=True)
    if dry_run:
        return []
    started = datetime.now(timezone.utc).isoformat()
    work = paths.work / 'extraction' / uuid.uuid4().hex
    work.mkdir(parents=True)
    marker = work / 'status.json'
    atomic_json(marker, {'status': 'running', 'started_at': started, 'config': config})
    configured = False
    entries = []
    try:
        # A extração percorre torres e frequências em sequência.
        for tower in towers:
            for frequency in frequencies:
                params = dict(tower, frequency_ghz=frequency)
                matches = []
                catalog_file = paths.environments / 'catalog.json'
                if catalog_file.exists() and config.get('reuse_existing', True):
                    catalog = json.loads(catalog_file.read_text(encoding='utf-8'))
                    matches = [e for e in catalog['datasets'].values() if e['params'] == params and e['geometry'] == GEOMETRY]
                if len(matches) > 1:
                    raise ValueError(f'Multiplos conjuntos para {params["proj_name"]}/{frequency}. Escolha explicitamente um dataset nas simulacoes ou prepare com reuse_existing: false.')
                if matches:
                    # Reutilizar também exige conferir a integridade dos arquivos.
                    _, entry = resolve_dataset(paths.environments, matches[0]['id'], tower, frequency)
                    print(f'Reutilizando {entry["id"]}', flush=True)
                else:
                    if not configured:
                        configure_suriacov(relative_path(config_path, config['suriacov_config']), paths, work)
                        configured = True
                    from .legacy_extraction import run_extraction
                    local = work / f'{tower["proj_name"]}_{frequency:g}GHz'
                    run_extraction(params, str(local))
                    entry = register_source(local / 'data', paths.environments,
                                            provenance={'kind': 'suriacov_full_grid', 'config': config, 'started_at': started})
                    # Imagens de diagnóstico ficam separadas dos mapas verificados por hash.
                    import shutil
                    if (local / 'env_imgs').exists():
                        shutil.copytree(local / 'env_imgs', paths.environments / entry['path'] / 'env_imgs', dirs_exist_ok=True)
                entries.append(entry)
        # Publica os IDs para as simulações somente quando todo o lote termina.
        selection = relative_path(config_path, config['selection_output'])
        selection.parent.mkdir(parents=True, exist_ok=True)
        value = {'datasets': [{'tower': e['params']['proj_name'], 'frequency_ghz': e['params']['frequency_ghz'], 'dataset_id': e['id']} for e in entries]}
        selection.write_text(yaml.safe_dump(value, sort_keys=False), encoding='utf-8')
        atomic_json(marker, {'status': 'complete', 'started_at': started, 'config': config, 'datasets': [e['id'] for e in entries], 'selection': str(selection)})
        print(f'Selecao gravada em {selection}', flush=True)
        return entries
    except BaseException as exc:
        atomic_json(marker, {'status': 'failed', 'started_at': started, 'config': config, 'error': f'{type(exc).__name__}: {exc}'})
        raise


def main(default_config: Path, argv=None):
    parser = argparse.ArgumentParser(description='Prepara dados SuriaCov sem executar modelos Monte Carlo.')
    parser.add_argument('--config', type=Path, default=default_config)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    prepare(args.config, dry_run=args.dry_run)
    return 0
