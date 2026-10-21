"""Full-grid extraction from the completed pipelines; formulas unchanged."""
import os
import json
import numpy as np
import pandas as pd
from ..common.plotting import Plotter

def run_extraction(params, project_root_path):
    """Executa a extracao de dados do terreno e perdas via SuriaCov."""
    from . import suriacov_local as sc
    from scipy.interpolate import interp1d

    data_path = os.path.join(project_root_path, "data")
    env_img_path = os.path.join(project_root_path, "env_imgs")

    os.makedirs(data_path, exist_ok=True)
    os.makedirs(env_img_path, exist_ok=True)

    tx, env, cov = sc.compute_coverage(
        proj_name=params["proj_name"],
        tx_latitude=params["tx_latitude"],
        tx_longitude=params["tx_longitude"],
        # Referência da extração; a potência simulada é definida na campanha.
        tx_power_kw=1.0,
        tx_height_ov_ground=params["tx_height_ov_ground"],
        tx_ant_patt=params.get("tx_ant_patt", {}),
        tx_polarization_id=params["tx_polarization_id"],
        frequency_ghz=params["frequency_ghz"],
        rx_height_ov_ground=params["rx_height_ov_ground"],
        field_th=params["field_th"],
        excedance_perc=params["excedance_perc"],
        num_samples=params["num_samples"],
    )

    dist_flat = cov.distance_map.flatten()
    los_flat = cov.los_map.flatten()
    min_dist, max_dist = np.min(dist_flat), np.max(dist_flat)
    bin_edges = np.linspace(min_dist, max_dist, 51)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    # Estima a probabilidade de LoS pela proporção de pixels visíveis em cada faixa de distância.
    plos_per_bin = []
    for i in range(50):
        mask = (dist_flat >= bin_edges[i]) & (dist_flat < bin_edges[i + 1])
        pixels = los_flat[mask]
        plos_per_bin.append(np.mean(pixels) if len(pixels) > 0 else np.nan)

    plos_per_bin = np.array(plos_per_bin)
    valid = ~np.isnan(plos_per_bin)
    f_interp = interp1d(
        bin_centers[valid],
        plos_per_bin[valid],
        kind="linear",
        bounds_error=False,
        fill_value=(1.0, 0.0),
    )

    plos_estimated_matrix = f_interp(cov.distance_map)
    plos_estimated_matrix[cov.los_map == 0] = 0.0
    plos_estimated_matrix = np.clip(plos_estimated_matrix, 0.0, 1.0)

    flat_idx = np.argmin(cov.distance_map)
    bs_row, bs_col = np.unravel_index(flat_idx, cov.distance_map.shape)

    pd.DataFrame(cov.los_map.astype(int)).to_csv(os.path.join(data_path, "los_map.csv"), index=False, header=False)
    pd.DataFrame(cov.distance_map).to_csv(os.path.join(data_path, "distance_map.csv"), index=False, header=False)
    pd.DataFrame(cov.path_loss_map).to_csv(os.path.join(data_path, "pathloss_map.csv"), index=False, header=False)
    pd.DataFrame(env.data_array).to_csv(os.path.join(data_path, "height_map.csv"), index=False, header=False)
    pd.DataFrame(plos_estimated_matrix).to_csv(os.path.join(data_path, "plos_estimated.csv"), index=False, header=False)
    pd.DataFrame({"dist_km": bin_centers, "p_los": plos_per_bin}).to_csv(
        os.path.join(data_path, "plos_bins_summary.csv"),
        index=False,
    )

    metadata = {
        "params": params,
        "bs_index": {"row": int(bs_row), "col": int(bs_col)},
        "env_stats": {
            "min_height": float(np.min(env.data_array)),
            "max_height": float(np.max(env.data_array)),
            "min_dist": float(min_dist),
            "max_dist": float(max_dist),
        },
    }
    with open(os.path.join(data_path, "extraction_metadata.json"), "w") as f:
        json.dump(metadata, f, indent=4)

    Plotter.setup_style()
    Plotter.plot_los(cov.los_map, params["proj_name"], os.path.join(env_img_path, "los_map.png"))
    Plotter.plot_heatmap(
        cov.distance_map,
        f"{params['proj_name']}\nDistancia",
        "km",
        os.path.join(env_img_path, "distance_map.png"),
    )
    Plotter.plot_heatmap(
        env.data_array,
        f"{params['proj_name']}\nTerreno",
        "m",
        os.path.join(env_img_path, "height_map.png"),
        cmap="terrain",
    )
    Plotter.plot_heatmap(
        cov.path_loss_map,
        f"{params['proj_name']}\nPath Loss (dB)",
        "dB",
        os.path.join(env_img_path, "pathloss_map.png"),
        cmap="inferno",
    )
    Plotter.plot_plos_analysis(
        bin_centers,
        plos_per_bin,
        valid,
        f_interp,
        min_dist,
        max_dist,
        params["proj_name"],
        os.path.join(env_img_path, "plos_analysis.png"),
    )
