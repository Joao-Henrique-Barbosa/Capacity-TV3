"""Carregue YAMLs: cada caminho relativo parte da pasta do arquivo que o declara."""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

import yaml

from .files import assert_separate_roots, token


def load_yaml(path: Path | str) -> dict:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f'Configuracao nao encontrada: {path}')
    value = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'O YAML precisa conter um mapeamento: {path}')
    return value


def relative_path(config_file: Path, value: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'Caminho ausente em {config_file}')
    # O caminho pertence ao YAML, mesmo quando o comando parte de outra pasta.
    return (config_file.resolve().parent / Path(value)).resolve()


def positive_int(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f'{name} precisa ser inteiro positivo.')
    return value


def real(value, name: str, *, minimum: float = 0, strictly: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} precisa ser numero finito.')
    if value < minimum or (strictly and value == minimum):
        raise ValueError(f'{name} fora do intervalo permitido.')
    return float(value)


def number_list(value, name: str, *, strictly=False) -> list[float]:
    if not isinstance(value, list) or not value:
        raise ValueError(f'{name} precisa ser lista nao vazia.')
    result = [real(v, name, strictly=strictly) for v in value]
    if len(set(result)) != len(result):
        raise ValueError(f'{name} contem valores repetidos.')
    return result


@dataclass(frozen=True)
class Paths:
    environments: Path
    results: Path
    work: Path
    geography: dict[str, Path | None]


def load_paths(path: Path) -> Paths:
    raw = load_yaml(path)
    roots = [relative_path(path, raw[k]) for k in ('environments_root', 'results_root', 'work_root')]
    for i, root in enumerate(roots):
        for other in roots[i+1:]:
            assert_separate_roots(root, other)
    geography = {k: relative_path(path, v) if v is not None else None for k, v in raw.get('geography', {}).items()}
    return Paths(*roots, geography)


def load_towers(path: Path) -> dict[str, dict]:
    towers = load_yaml(path).get('towers')
    if not isinstance(towers, dict) or not towers:
        raise ValueError('O catalogo precisa conter towers: {identificador: parametros}.')
    for name, params in towers.items():
        token(name)
        if params.get('proj_name') != name:
            raise ValueError(f'proj_name deve coincidir com o identificador {name}.')
        for key in ('tx_latitude', 'tx_longitude', 'tx_height_ov_ground', 'rx_height_ov_ground', 'tx_polarization_id', 'field_th', 'excedance_perc', 'num_samples'):
            if key not in params:
                raise ValueError(f'Torre {name}: falta {key}.')
        positive_int(params['num_samples'], 'num_samples')
    return towers


def selected_towers(config: dict, catalog: dict) -> list[dict]:
    names = config.get('towers')
    if not isinstance(names, list) or not names or len(names) != len(set(names)):
        raise ValueError('towers precisa listar identificadores unicos do catalogo.')
    for name in names:
        if name not in catalog:
            raise ValueError(f'Torre nao cadastrada: {name}')
    return [dict(catalog[name]) for name in names]
