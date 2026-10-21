"""Small filesystem operations with explicit ownership boundaries."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil


def token(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', value) or value in ('.', '..'):
        raise ValueError(f'Identificador de pasta invalido: {value!r}')
    return value


def frequency_label(ghz: float) -> str:
    return f'{float(ghz) * 1000:.12g}MHz'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    # Publica o JSON inteiro de uma vez, evitando leituras de conteúdo parcial.
    temporary.replace(path)


def owned_directory(path: Path, parent: Path, *, clear: bool = False) -> Path:
    if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
        raise ValueError(f'Nao substituo um diretorio redirecionado: {path}')
    path, parent = path.resolve(), parent.resolve()
    if path.parent != parent or path == parent or path.is_symlink():
        raise ValueError(f'Diretorio fora do pai autorizado: {path}')
    if clear and path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def assert_separate_roots(inputs: Path, outputs: Path) -> None:
    a, b = inputs.resolve(), outputs.resolve()
    if a == b or a in b.parents or b in a.parents:
        raise ValueError('Dados deterministicos e saidas precisam de raizes separadas, sem sobreposicao.')
