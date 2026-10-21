"""Import only deterministic data; never move or alter the source project."""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from .config import load_paths
from .environments import register_source
from .files import atomic_json


def import_legacy(source: Path, destination: Path, selection: Path):
    source, destination = source.resolve(), destination.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('Origem e destino da importacao precisam ser separados.')
    directories = sorted(source.glob('*/*/data'))
    if not directories:
        raise ValueError(f'Nenhuma extracao torre/frequencia/data em {source}.')
    entries, rejected = [], []
    for directory in directories:
        try:
            entry = register_source(directory, destination, provenance={'kind': 'legacy_import', 'source_root': source.name})
            entries.append(entry)
            print(f'Importado {entry["params"]["proj_name"]} {entry["params"]["frequency_ghz"]} GHz -> {entry["id"]}', flush=True)
        except (ValueError, OSError, KeyError) as exc:
            rejected.append({'source': str(directory), 'reason': str(exc)})
    grouped = {}
    for entry in entries:
        key = (entry['params']['proj_name'], float(entry['params']['frequency_ghz']))
        grouped.setdefault(key, {})[entry['id']] = entry
    conflicts = [{'tower': key[0], 'frequency_ghz': key[1], 'dataset_ids': list(group)} for key, group in grouped.items() if len(group) != 1]
    report = {'source': str(source), 'scanned': len(directories), 'accepted': len(entries),
              'unique': len({e['id'] for e in entries}), 'rejected': rejected, 'conflicts': conflicts}
    atomic_json(selection.with_suffix('.import.json'), report)
    if rejected or conflicts:
        raise ValueError(f'Importacao requer revisao; consulte {selection.with_suffix(".import.json")}. Nenhuma selecao ambigua foi publicada.')
    references = [{'tower': key[0], 'frequency_ghz': key[1], 'dataset_id': next(iter(group))} for key, group in sorted(grouped.items())]
    selection.parent.mkdir(parents=True, exist_ok=True)
    selection.write_text(yaml.safe_dump({'datasets': references}, sort_keys=False), encoding='utf-8')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description='Importa somente as pastas data dos pipelines completos.')
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--paths', required=True, type=Path)
    parser.add_argument('--selection', required=True, type=Path, help='YAML de datasets para selecionar nas simulacoes.')
    args = parser.parse_args(argv)
    report = import_legacy(args.source, load_paths(args.paths).environments, args.selection)
    print(report)
    return 0
