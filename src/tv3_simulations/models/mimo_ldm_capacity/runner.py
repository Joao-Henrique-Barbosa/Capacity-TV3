"""MIMO-LDM-specific calculation and exports, preserving the original formulas."""
from pathlib import Path

import numpy as np

from .model import MonteCarloSimulator, SimulationEnvironment
from .legacy_helpers import _variant_name_from_ldm_params
from ...common.environments import read_maps, write_numeric_csv
from ...common.plotting import Plotter

_CACHE = {}


def run(dataset: Path, tower: dict, scenario: dict, config: dict, output: Path) -> dict:
    # Datasets are immutable and identified by content, so process-local reuse is safe.
    key = str(dataset.resolve())
    if _CACHE.get('key') != key:
        maps = read_maps(dataset)
        _CACHE.clear()
        _CACHE.update(key=key, env=SimulationEnvironment(**maps), los=maps['los_map'])
    power, frequency, label = _variant_name_from_ldm_params(
        scenario['p_tx_dbm'], tower['frequency_ghz'], scenario['injection_ratio_db'], scenario['nmse'])
    # O campo legado nmse representa epsilon; o NMSE correspondente é epsilon².
    channel = {**config['channel'], 'p_tx': power, 'freq_hz': tower['frequency_ghz'] * 1e9,
               'tx_height_ov_ground': tower['tx_height_ov_ground'], 'rx_height_ov_ground': tower['rx_height_ov_ground'],
               'injection_ratio_db': scenario['injection_ratio_db'], 'nmse': scenario['nmse']}
    simulator = MonteCarloSimulator(
        _CACHE['env'], channel, num_realizations=config['num_realizations'],
        num_error_realizations=config['num_error_realizations'], chunk_size=config['chunk_size'],
        show_progress=config['show_progress'], rng_mode=config['rng_mode'])
    ul, ll = simulator.run()
    summary = dict(variant=label, p_tx_dbm=scenario['p_tx_dbm'], p_tx_w=power,
                   frequency_mhz=frequency, injection_ratio_db=scenario['injection_ratio_db'], nmse=scenario['nmse'],
                   num_channel_realizations=config['num_realizations'], num_error_realizations=config['num_error_realizations'],
                   total_realizations=config['num_realizations'] * config['num_error_realizations'])
    for layer, values in [('ul', ul), ('ll', ll)]:
        write_numeric_csv(output / 'data_simulation' / f'capacity_{layer}_map.csv', values)
        valid = values[values > 0]
        summary[f'mean_capacity_{layer}'] = float(np.nanmean(valid)) if valid.size else 0.0
        summary[f'max_capacity_{layer}'] = float(np.nanmax(values)) if values.size else 0.0
    if config['write_plots']:
        from .analysis import plot_capacity_analysis_ldm
        plots = output / 'simulation'
        plots.mkdir()
        Plotter.setup_style()
        for layer, values in [('ul', ul), ('ll', ll)]:
            Plotter.plot_heatmap(values, f"{tower['proj_name']} {label}\nCapacidade {layer.upper()}", 'Mbps', plots / f'capacity_{layer}_map.png')
        plot_capacity_analysis_ldm(ul, ll, _CACHE['los'], str(output / 'analysis'), label)
    return summary
