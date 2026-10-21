"""MIMO-specific calculation and exports; no dependencies on other models."""
from pathlib import Path

import numpy as np
import pandas as pd

from .model import MonteCarloSimulator, SimulationEnvironment
from .legacy_helpers import _variant_name_from_power_freq
from ...common.environments import read_maps
from ...common.plotting import Plotter


def run(dataset: Path, tower: dict, scenario: dict, config: dict, output: Path) -> dict:
    maps = read_maps(dataset, reader='pandas')
    env = SimulationEnvironment(**maps)
    power, frequency, label = _variant_name_from_power_freq(scenario['p_tx_dbm'], tower['frequency_ghz'])
    # O núcleo recebe a potência em watts e a frequência em hertz.
    channel = {**config['channel'], 'p_tx': power, 'freq_hz': tower['frequency_ghz'] * 1e9,
               'tx_height_ov_ground': tower['tx_height_ov_ground'], 'rx_height_ov_ground': tower['rx_height_ov_ground']}
    simulator = MonteCarloSimulator(env, channel, num_realizations=config['num_realizations'])
    capacity = simulator.run()
    data = output / 'data_simulation'
    data.mkdir()
    pd.DataFrame(capacity).to_csv(data / 'capacity_map.csv', index=False, header=False)
    if config['write_plots']:
        from .analysis import plot_capacity_analysis
        plots = output / 'simulation'
        plots.mkdir()
        Plotter.setup_style()
        Plotter.plot_heatmap(capacity, f"{tower['proj_name']} {label}\nCapacidade", 'Mbps', plots / 'capacity_map.png')
        plot_capacity_analysis(capacity, maps['los_map'], str(output / 'analysis'), label)
    valid = capacity[capacity > 0]
    return dict(variant=label, p_tx_dbm=scenario['p_tx_dbm'], p_tx_w=power,
                frequency_mhz=frequency, mean_capacity=float(np.nanmean(valid)) if valid.size else 0.0,
                max_capacity=float(np.nanmax(capacity)) if capacity.size else 0.0)
