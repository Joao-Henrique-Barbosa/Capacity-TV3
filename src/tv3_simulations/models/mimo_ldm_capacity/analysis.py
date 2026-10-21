import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


def calculate_pdf_cdf(data):
    """
    Calcula os dados usados nos graficos de PDF e CDF.
    """
    clean_data = np.asarray(data).ravel()
    clean_data = clean_data[np.isfinite(clean_data)]
    clean_data = clean_data[clean_data > 0]

    if len(clean_data) == 0:
        return None, None, None

    sorted_data = np.sort(clean_data)
    y_cdf = np.arange(1, len(sorted_data) + 1) / len(sorted_data)
    return clean_data, sorted_data, y_cdf


def _capacity_stats_by_condition(capacity_map, los_map):
    los_mask = los_map == 1
    nlos_mask = los_map == 0
    return {
        "total": calculate_pdf_cdf(capacity_map),
        "los": calculate_pdf_cdf(capacity_map[los_mask]),
        "nlos": calculate_pdf_cdf(capacity_map[nlos_mask]),
    }


def _selected_conditions(mode):
    if mode == "all":
        return ("total", "los", "nlos")
    return (mode,)


def _plot_pdf(ax, data, color, linestyle, label):
    if data is None:
        return

    sns.histplot(
        data,
        stat="density",
        element="step",
        fill=False,
        common_norm=False,
        color=color,
        linestyle=linestyle,
        linewidth=2.3,
        label=label,
        ax=ax,
    )


def _plot_cdf(ax, sorted_data, y_cdf, color, linestyle, label):
    if sorted_data is None or y_cdf is None:
        return

    ax.plot(
        sorted_data,
        y_cdf,
        color=color,
        linestyle=linestyle,
        linewidth=2.5,
        label=label,
    )


def plot_capacity_analysis_ldm(capacity_ul_map, capacity_ll_map, los_map, output_dir, proj_name=""):
    """
    Gera graficos PDF/CDF comparando as camadas UL e LL na mesma imagem.

    As figuras seguem a mesma organizacao de capacity_analysis.py:
    total, LoS, NLoS e combinado. A diferenca e que cada grafico mostra
    simultaneamente uma curva para UL e outra para LL.
    """
    os.makedirs(output_dir, exist_ok=True)

    capacity_ul_map = np.asarray(capacity_ul_map)
    capacity_ll_map = np.asarray(capacity_ll_map)
    los_map = np.asarray(los_map)

    stats = {
        "ul": _capacity_stats_by_condition(capacity_ul_map, los_map),
        "ll": _capacity_stats_by_condition(capacity_ll_map, los_map),
    }

    plt.style.use("bmh")
    sns.set_theme(style="whitegrid")

    layer_specs = {
        "ul": ("UL", "tab:blue"),
        "ll": ("LL", "tab:orange"),
    }
    condition_specs = {
        "total": ("Total", "-"),
        "los": ("LoS", "--"),
        "nlos": ("NLoS", ":"),
    }

    def save_plot(plot_type, mode, filename):
        fig, ax = plt.subplots(figsize=(10, 6))
        has_data = False

        for condition in _selected_conditions(mode):
            condition_label, linestyle = condition_specs[condition]
            for layer, (layer_label, color) in layer_specs.items():
                clean_data, sorted_data, y_cdf = stats[layer][condition]
                label = layer_label if mode != "all" else f"{layer_label} {condition_label}"

                if plot_type == "pdf":
                    _plot_pdf(ax, clean_data, color, linestyle, label)
                    has_data = has_data or clean_data is not None
                else:
                    _plot_cdf(ax, sorted_data, y_cdf, color, linestyle, label)
                    has_data = has_data or sorted_data is not None

        suffix = "PDF" if plot_type == "pdf" else "CDF"
        title_main = f"Capacidade {suffix}"
        if mode != "all":
            title_main += f" ({condition_specs[mode][0]})"

        ax.set_title(f"{title_main} - {proj_name}", fontsize=15)
        ax.set_xlabel("Capacidade (Mbps)")
        ax.set_ylabel("Densidade" if plot_type == "pdf" else "Probabilidade Cumulativa")
        if plot_type == "cdf":
            ax.set_ylim(0, 1.05)

        if has_data:
            ax.legend(loc="upper right")
        else:
            ax.text(0.5, 0.5, "Sem dados validos", ha="center", va="center", transform=ax.transAxes)

        fig.tight_layout()
        fig.savefig(os.path.join(output_dir, filename), dpi=300)
        plt.close(fig)

    save_plot("pdf", "all", "capacity_pdf_combined.png")
    save_plot("pdf", "total", "capacity_pdf_total.png")
    save_plot("pdf", "los", "capacity_pdf_los.png")
    save_plot("pdf", "nlos", "capacity_pdf_nlos.png")

    save_plot("cdf", "all", "capacity_cdf_combined.png")
    save_plot("cdf", "total", "capacity_cdf_total.png")
    save_plot("cdf", "los", "capacity_cdf_los.png")
    save_plot("cdf", "nlos", "capacity_cdf_nlos.png")

    print(f"Estatisticas PDF/CDF LDM salvas em: {output_dir}")


def _first_existing_path(paths):
    for path in paths:
        if os.path.exists(path):
            return path
    return None


def run_analysis_from_files(proj_output_path):
    """
    Carrega os CSVs de uma variante LDM e gera a analise UL/LL combinada.
    """
    try:
        data_sim_path = os.path.join(proj_output_path, "data_simulation")
        analysis_path = os.path.join(proj_output_path, "analysis")

        ul_path = os.path.join(data_sim_path, "capacity_ul_map.csv")
        ll_path = os.path.join(data_sim_path, "capacity_ll_map.csv")
        los_path = _first_existing_path(
            [
                os.path.join(proj_output_path, "data", "los_map.csv"),
                os.path.join(os.path.dirname(proj_output_path), "data", "los_map.csv"),
                os.path.join(proj_output_path, "los_map.csv"),
            ]
        )

        if los_path is None:
            raise FileNotFoundError("los_map.csv nao encontrado.")

        capacity_ul_map = pd.read_csv(ul_path, header=None).values
        capacity_ll_map = pd.read_csv(ll_path, header=None).values
        los_map = pd.read_csv(los_path, header=None).values

        proj_name = os.path.basename(proj_output_path)
        plot_capacity_analysis_ldm(capacity_ul_map, capacity_ll_map, los_map, analysis_path, proj_name)
    except Exception as exc:
        print(f"Erro ao processar arquivos de analise LDM: {exc}")


if __name__ == "__main__":
    example_proj = "Torre_TV_Digital_BSB_LDM"
    base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output_LDM", example_proj)

    if os.path.exists(base_path):
        run_analysis_from_files(base_path)
    else:
        print(f"Pasta de projeto nao encontrada para analise: {base_path}")
