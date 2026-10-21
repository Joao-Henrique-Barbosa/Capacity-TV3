"""Valide mapas preparados e execute cenários MIMO ou MIMO-LDM.

O dry-run confere a integridade dos dados sem simular. Uma execução real substitui
os cenários selecionados; use outro nome de campanha para preservar resultados.
"""
from __future__ import annotations

import argparse
import hashlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import importlib
from importlib import metadata as packages
from itertools import product
import json
import multiprocessing as mp
import os
from pathlib import Path
import platform
import secrets
import sys
import time

import matplotlib
matplotlib.use('Agg')
import numpy as np
import pandas as pd

from .config import load_yaml, load_paths, load_towers, number_list, positive_int, relative_path, selected_towers, real
from .environments import resolve_dataset
from .files import atomic_json, frequency_label, owned_directory, sha256, token
from .. import __version__

MODELS = ('mimo_capacity', 'mimo_ldm_capacity')


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def dependency_versions():
    return {name: packages.version(name) for name in ('numpy', 'pandas', 'scipy', 'matplotlib', 'seaborn', 'PyYAML', 'tqdm')}


def source_fingerprint():
    package = Path(__file__).resolve().parents[1]
    values = {p.relative_to(package).as_posix(): sha256(p) for p in sorted(package.rglob('*.py'))}
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def derived_seed(model, base, scenario, frequency):
    # Cada cenário recebe uma semente própria, independente da ordem de conclusão.
    entropy = [int(base), int(round(scenario['p_tx_dbm'] * 10)), int(round(frequency * 1e6))]
    if model == 'mimo_ldm_capacity':
        entropy += [int(round(scenario['injection_ratio_db'] * 10)), int(round(scenario['nmse'] * 1e6))]
    return int(np.random.SeedSequence(entropy).generate_state(1)[0])


def scenario_name(scenario):
    # repr preserves distinct float parameters; the old rounded watt labels stay in summaries.
    def part(value):
        return str(float(value)).replace('-', 'm').replace('.', 'p')
    result = 'pt' + part(scenario['p_tx_dbm']) + 'dbm'
    if 'injection_ratio_db' in scenario:
        result += '_ir' + part(scenario['injection_ratio_db']) + 'db_eps' + part(scenario['nmse'])
    return token(result)


def validate_config(path: Path, model: str):
    config = load_yaml(path)
    if model not in MODELS or config.get('model') != model:
        raise ValueError(f'O YAML deve declarar model: {model}.')
    token(config.get('campaign'))
    positive_int(config.get('num_realizations'), 'num_realizations')
    if config.get('max_workers') is not None:
        positive_int(config['max_workers'], 'max_workers')
    seed = config.get('random_seed')
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int) or seed < 0):
        raise ValueError('random_seed deve ser inteiro nao negativo ou null.')
    for field in ('write_plots',):
        if not isinstance(config.get(field), bool):
            raise ValueError(f'{field} deve ser booleano.')
    config['p_tx_variations_dbm'] = number_list(config.get('p_tx_variations_dbm'), 'p_tx_variations_dbm')
    config['frequencies_ghz'] = number_list(config.get('frequencies_ghz'), 'frequencies_ghz', strictly=True)
    channel = config.get('channel', {})
    required = {'mu_chi_bar_db', 'sigma_chi_bar_db', 'mu_chi_tilde_db', 'sigma_chi_tilde_db', 'delta_tx', 'delta_rx'}
    allowed = required | ({'bandwidth_hz', 'det_epsilon'} if model == 'mimo_ldm_capacity' else set())
    if not required.issubset(channel) or set(channel) - allowed:
        raise ValueError(f'Parametros de channel incorretos; campos permitidos: {sorted(allowed)}')
    for name, value in channel.items():
        real(value, name, minimum=-float('inf') if name.startswith('mu_') else 0,
             strictly=name in ('bandwidth_hz', 'det_epsilon'))
    if model == 'mimo_ldm_capacity':
        for name in ('num_error_realizations', 'chunk_size'):
            positive_int(config.get(name), name)
        if config.get('rng_mode') not in ('legacy', 'chunked', 'vectorized'):
            raise ValueError('rng_mode invalido.')
        if not isinstance(config.get('show_progress'), bool):
            raise ValueError('show_progress deve ser booleano.')
        for name in ('injection_ratio_db_values', 'nmse_values'):
            config[name] = number_list(config.get(name), name)
    paths = load_paths(relative_path(path, config['paths']))
    towers = selected_towers(config, load_towers(relative_path(path, config['tower_catalog'])))
    references = load_yaml(relative_path(path, config['datasets'])).get('datasets')
    if not isinstance(references, list):
        raise ValueError('O arquivo de selecao precisa conter datasets: [...].')
    prepared = []
    for tower, frequency in product(towers, config['frequencies_ghz']):
        matches = [r for r in references if r['tower'] == tower['proj_name'] and float(r['frequency_ghz']) == frequency]
        if len(matches) != 1:
            raise ValueError(f'Selecione exatamente um dataset_id para {tower["proj_name"]} / {frequency} GHz.')
        directory, entry = resolve_dataset(paths.environments, matches[0]['dataset_id'], tower, frequency)
        prepared.append((dict(tower, frequency_ghz=frequency), directory, entry))
    return config, paths, prepared


def execute_job(job):
    output = Path(job['output'])
    marker = output / 'metadata.json'
    metadata = dict(job['metadata'], status='running', started_at=utc_now())
    atomic_json(marker, metadata)
    started = time.perf_counter()
    try:
        np.random.seed(metadata['effective_seed'])
        runner = importlib.import_module(f'tv3_simulations.models.{job["model"]}.runner')
        summary = runner.run(Path(job['dataset']), job['tower'], job['scenario'], job['config'], output)
        summary.update(proj_name=job['tower']['proj_name'], id_estacao=job['tower'].get('id_estacao'),
                       dataset_id=metadata['dataset_id'], scenario=scenario_name(job['scenario']),
                       effective_seed=metadata['effective_seed'], elapsed_s=time.perf_counter() - started)
        files = {str(p.relative_to(output)).replace('\\', '/'): sha256(p) for p in output.rglob('*') if p.is_file() and p.name != 'metadata.json'}
        # Marca como concluído somente depois de gravar e conferir todas as saídas.
        metadata.update(status='complete', finished_at=utc_now(), summary=summary, files=files)
        atomic_json(marker, metadata)
        return summary
    except BaseException as exc:
        metadata.update(status='failed', finished_at=utc_now(), error=f'{type(exc).__name__}: {exc}')
        atomic_json(marker, metadata)
        raise


def refresh_summary(campaign: Path, model: str, *, exclude=()):
    excluded = {Path(path).resolve() for path in exclude}
    rows = []
    for path in sorted(campaign.glob('*/*/*/metadata.json')):
        if path.parent.resolve() in excluded:
            continue
        value = json.loads(path.read_text(encoding='utf-8'))
        if value.get('status') == 'complete':
            rows.append(value['summary'])
    filename = 'ldm_sweep_summary.csv' if model == 'mimo_ldm_capacity' else 'mimo_sweep_summary.csv'
    target = campaign / filename
    campaign.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.csv.tmp')
    pd.DataFrame(rows).to_csv(temporary, index=False)
    temporary.replace(target)
    return rows


def run_campaign(config_path: Path, model: str, *, dry_run=False):
    config_path = config_path.resolve()
    config, paths, prepared = validate_config(config_path, model)
    keys = ['p_tx_dbm'] if model == 'mimo_capacity' else ['p_tx_dbm', 'injection_ratio_db', 'nmse']
    values = [config['p_tx_variations_dbm']]
    if model == 'mimo_ldm_capacity':
        values += [config['injection_ratio_db_values'], config['nmse_values']]
    scenarios = [dict(zip(keys, combination)) for combination in product(*values)]
    count = len(scenarios) * len(prepared)
    workers = config.get('max_workers') or max(1, (os.cpu_count() or 2) - 1)
    workers = min(workers, len(scenarios), 61 if os.name == 'nt' else workers)
    print(f'{model}: {len(prepared)} ambientes, {len(scenarios)} cenarios/ambiente, {count} tarefas; {workers} processos.', flush=True)
    if dry_run:
        return []
    base_seed = config.get('random_seed')
    if base_seed is None:
        base_seed = secrets.randbits(64)
    campaign = paths.results / model / config['campaign']
    versions = dependency_versions()
    code_hash = source_fingerprint()
    model_file = Path(__file__).resolve().parents[1] / 'models' / model / 'model.py'
    jobs = []
    for tower, directory, entry in prepared:
        for scenario in scenarios:
            output = campaign / tower['proj_name'] / frequency_label(tower['frequency_ghz']) / scenario_name(scenario)
            metadata = dict(model=model, campaign=config['campaign'], dataset_id=entry['id'],
                            dataset_checksums=entry['checksums'], tower=tower, scenario=scenario,
                            configuration=config, base_seed=base_seed,
                            effective_seed=derived_seed(model, base_seed, scenario, tower['frequency_ghz']),
                            python=sys.version, platform=platform.platform(), dependencies=versions,
                            package_version=__version__, package_source_sha256=code_hash,
                            model_sha256=sha256(model_file), configured_workers=config.get('max_workers'), actual_workers=workers)
            jobs.append(dict(model=model, output=str(output), dataset=str(directory), tower=tower,
                             scenario=scenario, config=config, metadata=metadata))
    atomic_json(campaign / 'last_execution.json', dict(status='running', started_at=utc_now(),
                configuration=config, base_seed=base_seed, selected_outputs=[str(Path(j['output']).relative_to(campaign)) for j in jobs]))
    # Remove selected old rows before touching their directories. An interruption
    # during invalidation cannot leave stale selected results in the summary.
    refresh_summary(campaign, model, exclude=[j['output'] for j in jobs])
    # Invalidate every selected old result before computing or publishing any new result.
    for job in jobs:
        output = Path(job['output'])
        if campaign.resolve() not in output.resolve().parents:
            raise ValueError('Saida fora da campanha.')
        owned_directory(output, output.parent, clear=True)
        atomic_json(output / 'metadata.json', dict(job['metadata'], status='pending', scheduled_at=utc_now()))
    refresh_summary(campaign, model)
    completed = []
    try:
        # Keep the original granularity: environments in sequence, variants in parallel.
        for offset in range(0, len(jobs), len(scenarios)):
            batch = jobs[offset:offset + len(scenarios)]
            print(f'Ambiente {batch[0]["tower"]["proj_name"]} / {batch[0]["tower"]["frequency_ghz"]} GHz', flush=True)
            if workers == 1:
                iterator = (execute_job(job) for job in batch)
                for result in iterator:
                    completed.append(result)
                    refresh_summary(campaign, model)
                    print(f'Concluido {len(completed)}/{count}: {result["scenario"]}', flush=True)
            else:
                with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context('spawn')) as pool:
                    futures = [pool.submit(execute_job, job) for job in batch]
                    for future in as_completed(futures):
                        completed.append(future.result())
                        refresh_summary(campaign, model)
                        print(f'Concluido {len(completed)}/{count}', flush=True)
    finally:
        refresh_summary(campaign, model)
        atomic_json(campaign / 'last_execution.json', dict(status='complete' if len(completed) == count else 'incomplete',
                    finished_at=utc_now(), configuration=config, base_seed=base_seed, completed=len(completed), total=count,
                    selected_outputs=[str(Path(j['output']).relative_to(campaign)) for j in jobs]))
    return completed


def main(model: str, default_config: Path, argv=None):
    parser = argparse.ArgumentParser(description=f'Executa {model} com dados previamente preparados.')
    parser.add_argument('--config', type=Path, default=default_config)
    parser.add_argument('--dry-run', action='store_true', help='Valida configuracao/dados e conta tarefas, sem gravar ou simular.')
    args = parser.parse_args(argv)
    run_campaign(args.config, model, dry_run=args.dry_run)
    return 0
