"""Prepare as bases incluídas no clone e crie a configuração local.

Usa somente a biblioteca padrão. Confere os hashes antes de extrair e preserva
paths.local.yaml e bases existentes; não baixa dados nem inicia simulações.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def setup(root: Path = PROJECT_ROOT) -> None:
    bundle = root / 'data/geography'
    manifest = json.loads((bundle / 'manifest.json').read_text(encoding='utf-8'))
    destination = (bundle / 'extracted').resolve()
    # A lista do manifesto também impede caminhos fora da pasta de dados.
    for name, info in manifest['files'].items():
        target = (destination / name).resolve()
        if destination not in target.parents:
            raise ValueError(f'Caminho fora da pasta de bases: {name}')
        if target.exists() and sha256(target) != info['sha256']:
            raise ValueError(f'Base existente diferente do manifesto: {target}. '
                             'Mova sua base personalizada antes de executar o setup.')

    if not all((destination / name).is_file() for name in manifest['files']):
        # O ZIP é dividido para respeitar o limite por arquivo do GitHub.
        with tempfile.TemporaryFile() as combined:
            for part in manifest['parts']:
                path = bundle / part['name']
                if sha256(path) != part['sha256']:
                    raise ValueError(f'Parte ausente ou corrompida: {path}')
                with path.open('rb') as stream:
                    shutil.copyfileobj(stream, combined)
            combined.seek(0)
            if hashlib.file_digest(combined, 'sha256').hexdigest() != manifest['sha256']:
                raise ValueError('O ZIP reconstruído diverge do manifesto.')
            combined.seek(0)
            with zipfile.ZipFile(combined) as archive:
                if set(archive.namelist()) != set(manifest['files']):
                    raise ValueError('Conteúdo do ZIP diverge do manifesto.')
                for name, info in manifest['files'].items():
                    target = destination / name
                    if target.exists():
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(name) as source, target.open('wb') as output:
                        shutil.copyfileobj(source, output)
                    if sha256(target) != info['sha256']:
                        raise ValueError(f'Falha na integridade de {target}')

    local = root / 'configs/paths.local.yaml'
    if local.exists():
        print(f'Configuração existente preservada: {local}')
    else:
        shutil.copyfile(root / 'configs/paths.example.yaml', local)
        print(f'Configuração criada: {local}')
    print(f'Bases verificadas: {destination}')
    print('Próximo passo: python scripts/prepare_environments.py --config configs/extraction/exemplo_guia.yaml --dry-run')


if __name__ == '__main__':
    setup()
