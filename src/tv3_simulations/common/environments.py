"""Immutable full-grid datasets, content checksums and shared input readers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

from .files import atomic_json, frequency_label, sha256, token

MAP_FILES = ('distance_map.csv', 'height_map.csv', 'los_map.csv', 'pathloss_map.csv', 'plos_estimated.csv')
REQUIRED_FILES = (*MAP_FILES, 'plos_bins_summary.csv', 'extraction_metadata.json')
GEOMETRY = 'legacy_full_grid_v1'


def write_numeric_csv(path, values):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savetxt(path, np.asarray(values), delimiter=',')


def read_maps(directory: Path, *, reader: str = 'numpy') -> dict:
    # The MIMO pipeline originally used pandas; preserve its float parser too.
    def read(name):
        path = directory / name
        if reader == 'pandas':
            return pd.read_csv(path, header=None).values
        return np.loadtxt(path, delimiter=',', ndmin=2)
    return dict(B_map=10 ** (-read('pathloss_map.csv') / 10),
                plos_map=read('plos_estimated.csv'), los_map=read('los_map.csv'),
                distance_map=read('distance_map.csv'), height_map=read('height_map.csv'))


def validate_source(directory: Path) -> dict:
    for filename in REQUIRED_FILES:
        if not (directory / filename).is_file():
            raise ValueError(f'Extracao incompleta: falta {directory / filename}')
    meta = json.loads((directory / 'extraction_metadata.json').read_text(encoding='utf-8'))
    if meta.get('status', 'complete') != 'complete' or meta.get('extraction_version'):
        raise ValueError(f'Extracao incompleta ou nao legada: {directory}')
    params = meta.get('params', {})
    token(params.get('proj_name'))
    frequency = params.get('frequency_ghz')
    if not isinstance(frequency, (int, float)) or not np.isfinite(frequency) or frequency <= 0:
        raise ValueError(f'Frequencia invalida: {directory}')
    arrays = {n: np.loadtxt(directory / n, delimiter=',', ndmin=2) for n in MAP_FILES}
    shape = arrays['height_map.csv'].shape
    if shape != (params.get('num_samples'), params.get('num_samples')) or any(a.shape != shape for a in arrays.values()):
        raise ValueError(f'Dimensoes inconsistentes nos mapas: {directory}')
    for name in ('distance_map.csv', 'height_map.csv', 'los_map.csv', 'plos_estimated.csv'):
        if not np.all(np.isfinite(arrays[name])):
            raise ValueError(f'Valores nao finitos em {directory / name}')
    if np.any(arrays['distance_map.csv'] < 0) or not np.isin(arrays['los_map.csv'], [0, 1]).all():
        raise ValueError(f'Distancia/LoS invalido: {directory}')
    plos = arrays['plos_estimated.csv']
    loss = arrays['pathloss_map.csv']
    if np.any((plos < 0) | (plos > 1)) or np.any(np.isinf(loss)) or not np.any(np.isfinite(loss)):
        raise ValueError(f'PLOS/perda invalida: {directory}')
    # pandas' original exporter writes empty fields for bins without receivers.
    # Those are valid NaN probabilities, not an incomplete extraction.
    bins = np.genfromtxt(directory / 'plos_bins_summary.csv', delimiter=',', skip_header=1, ndmin=2)
    if bins.shape != (50, 2) or not np.all(np.isfinite(bins[:, 0])) or np.any(np.isinf(bins[:, 1])):
        raise ValueError(f'Resumo PLOS invalido: {directory}')
    finite_prob = bins[:, 1][np.isfinite(bins[:, 1])]
    if np.any((finite_prob < 0) | (finite_prob > 1)):
        raise ValueError(f'Probabilidades dos bins invalidas: {directory}')
    expected = np.unravel_index(np.argmin(arrays['distance_map.csv']), shape)
    bs = meta.get('bs_index', {})
    if (bs.get('row'), bs.get('col')) != expected:
        raise ValueError(f'Indice da torre nao corresponde ao extrator legado: {directory}')
    return {'metadata': meta, 'shape': list(shape), 'checksums': {n: sha256(directory / n) for n in REQUIRED_FILES}}


def dataset_id(checksums: dict) -> str:
    # Só arquivos idênticos, com a mesma convenção de geometria, compartilham o ID.
    payload = json.dumps({'geometry': GEOMETRY, 'files': checksums}, sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()[:20]


def register_source(source: Path, root: Path, *, provenance: dict | None = None) -> dict:
    info = validate_source(source)
    params = info['metadata']['params']
    identifier = dataset_id(info['checksums'])
    relative = Path(token(params['proj_name'])) / frequency_label(params['frequency_ghz']) / identifier
    destination = root / relative
    catalog_path = root / 'catalog.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8')) if catalog_path.exists() else {'schema_version': 1, 'datasets': {}}
    if destination.exists():
        actual = validate_source(destination)
        if actual['checksums'] != info['checksums']:
            raise ValueError(f'Conflito de integridade no destino: {destination}')
    else:
        destination.mkdir(parents=True)
        for filename in REQUIRED_FILES:
            shutil.copy2(source / filename, destination / filename)
        if validate_source(destination)['checksums'] != info['checksums']:
            raise ValueError(f'Falha na verificacao da copia: {destination}')
    entry = catalog['datasets'].get(identifier, {
        'id': identifier, 'path': relative.as_posix(), 'geometry': GEOMETRY,
        'params': params, 'shape': info['shape'], 'checksums': info['checksums'], 'origins': [],
    })
    origin = {'path': str(source.resolve()), **(provenance or {})}
    if origin not in entry['origins']:
        entry['origins'].append(origin)
    atomic_json(destination / 'dataset.json', {**entry, 'status': 'complete'})
    catalog['datasets'][identifier] = entry
    atomic_json(catalog_path, catalog)
    return entry


def resolve_dataset(root: Path, identifier: str, tower: dict, frequency: float) -> tuple[Path, dict]:
    token(identifier)
    catalog_path = root / 'catalog.json'
    if not catalog_path.is_file():
        raise FileNotFoundError(f'Catalogo ausente: {catalog_path}. Execute prepare_environments.py ou importe os dados legados.')
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    if identifier not in catalog['datasets']:
        raise ValueError(f'Conjunto {identifier} nao preparado. Execute prepare_environments.py.')
    entry = catalog['datasets'][identifier]
    directory = (root / entry['path']).resolve()
    if root.resolve() not in directory.parents:
        raise ValueError('Conjunto fora da raiz de dados.')
    # Altura, coordenadas e grade precisam corresponder à extração selecionada.
    expected = {**tower, 'frequency_ghz': float(frequency)}
    if entry['params'] != expected or entry['geometry'] != GEOMETRY:
        raise ValueError(f'Conjunto {identifier} incompativel com torre/frequencia/parametros. Prepare ou selecione outro conjunto.')
    marker = json.loads((directory / 'dataset.json').read_text(encoding='utf-8'))
    if marker.get('status') != 'complete':
        raise ValueError(f'Conjunto incompleto: {identifier}')
    if validate_source(directory)['checksums'] != entry['checksums']:
        raise ValueError(f'Integridade do conjunto {identifier} diverge do catalogo.')
    return directory, entry
