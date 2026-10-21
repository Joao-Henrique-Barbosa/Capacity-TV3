import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns


def calculate_pdf_cdf(data):
    """
    Calcula o Histograma (PDF) e a CDF de um conjunto de dados.
    """
    # Remove NaNs e valores zero (opcional, dependendo da análise)
    clean_data = data[~np.isnan(data)]
    clean_data = clean_data[clean_data > 0]

    if len(clean_data) == 0:
        return None, None, None

    # Ordenar dados para CDF
    sorted_data = np.sort(clean_data)
    y_cdf = np.arange(1, len(sorted_data) + 1) / len(sorted_data)

    return clean_data, sorted_data, y_cdf


def plot_capacity_analysis(capacity_map, los_map, output_dir, proj_name=""):
    """
    Gera gráficos de Histograma e CDF para o mapa de capacidades,
    separando por condição de visada (LoS vs NLoS).
    Gera versões combinadas e individuais.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 1. Preparação dos dados
    cap_total = capacity_map.flatten()
    cap_los = capacity_map[los_map == 1].flatten()
    cap_nlos = capacity_map[los_map == 0].flatten()

    # Cálculo de estatísticas
    stats = {
        'total': calculate_pdf_cdf(cap_total),
        'los': calculate_pdf_cdf(cap_los),
        'nlos': calculate_pdf_cdf(cap_nlos)
    }

    # Configuração do estilo
    plt.style.use('bmh')
    sns.set_theme(style="whitegrid")

    # --- FUNÇÃO AUXILIAR PARA PLOTAGEM ---
    def save_plot(plot_type, mode, data_dict, filename):
        plt.figure(figsize=(10, 6))

        if plot_type == 'pdf':
            if mode in ['total', 'all'] and data_dict['total'][0] is not None:
                sns.histplot(data_dict['total'][0], kde=True, color='gray', label='Total', alpha=0.3, stat="density")
            if mode in ['los', 'all'] and data_dict['los'][0] is not None:
                sns.histplot(data_dict['los'][0], kde=True, color='green', label='LoS (Visada)', alpha=0.5, stat="density")
            if mode in ['nlos', 'all'] and data_dict['nlos'][0] is not None:
                sns.histplot(data_dict['nlos'][0], kde=True, color='red', label='NLoS (Obstruído)', alpha=0.5, stat="density")
            plt.ylabel("Densidade")
            title_suffix = "PDF"
        else:
            if mode in ['total', 'all'] and data_dict['total'][1] is not None:
                plt.plot(data_dict['total'][1], data_dict['total'][2], color='black', linestyle='--', label='Total', linewidth=2)
            if mode in ['los', 'all'] and data_dict['los'][1] is not None:
                plt.plot(data_dict['los'][1], data_dict['los'][2], color='green', label='LoS (Visada)', linewidth=2.5)
            if mode in ['nlos', 'all'] and data_dict['nlos'][1] is not None:
                plt.plot(data_dict['nlos'][1], data_dict['nlos'][2], color='red', label='NLoS (Obstruído)', linewidth=2.5)
            plt.ylabel("Probabilidade Cumulativa")
            plt.ylim(0, 1.05)
            title_suffix = "CDF"

        title_main = f"Capacidade {title_suffix}"
        if mode != 'all': title_main += f" ({mode.upper()})"

        plt.title(f"{title_main} - {proj_name}", fontsize=15)
        plt.xlabel("Capacidade (Mbps)")
        plt.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, filename), dpi=300)
        plt.close()

    # --- GERAR TODOS OS PLOTS ---
    # PDFs
    save_plot('pdf', 'all', stats, "capacity_pdf_combined.png")
    save_plot('pdf', 'total', stats, "capacity_pdf_total.png")
    save_plot('pdf', 'los', stats, "capacity_pdf_los.png")
    save_plot('pdf', 'nlos', stats, "capacity_pdf_nlos.png")

    # CDFs
    save_plot('cdf', 'all', stats, "capacity_cdf_combined.png")
    save_plot('cdf', 'total', stats, "capacity_cdf_total.png")
    save_plot('cdf', 'los', stats, "capacity_cdf_los.png")
    save_plot('cdf', 'nlos', stats, "capacity_cdf_nlos.png")

    print(f"Estatísticas PDF/CDF (Combinadas e Individuais) salvas em: {output_dir}")


def run_analysis_from_files(proj_output_path):
    """
    Função utilitária para carregar os arquivos e rodar a análise.
    Assume a estrutura:
    proj_output_path/
        csv_data/
        analysis/
    """
    try:
        csv_path = os.path.join(proj_output_path, "csv_data")
        analysis_path = os.path.join(proj_output_path, "analysis")

        if not os.path.exists(analysis_path):
            os.makedirs(analysis_path)

        cap_path = os.path.join(csv_path, "capacity_map.csv")
        los_path = os.path.join(csv_path, "los_map.csv")

        capacity_map = pd.read_csv(cap_path, header=None).values
        los_map = pd.read_csv(los_path, header=None).values

        proj_name = os.path.basename(proj_output_path)
        plot_capacity_analysis(capacity_map, los_map, analysis_path, proj_name)

    except Exception as e:
        print(f"Erro ao processar arquivos de análise: {e}")


if __name__ == "__main__":
    # Exemplo de uso manual indicando a pasta do projeto
    # Ajuste o caminho abaixo conforme necessário
    example_proj = "Torre_TV_Digital_BSB_Integrated"
    base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", example_proj)

    if os.path.exists(base_path):
        run_analysis_from_files(base_path)
    else:
        print(f"Pasta de projeto não encontrada para análise: {base_path}")
