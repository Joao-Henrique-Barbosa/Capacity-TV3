"""Shared plot primitives, copied without numerical changes."""
import numpy as np

class Plotter:
    _plt = None
    _sns = None

    @classmethod
    def libraries(cls):
        if cls._plt is None or cls._sns is None:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import seaborn as sns

            cls._plt = plt
            cls._sns = sns
        return cls._plt, cls._sns

    @classmethod
    def setup_style(cls):
        plt, sns = cls.libraries()
        plt.style.use("bmh")
        sns.set_theme(style="whitegrid")

    @classmethod
    def plot_heatmap(cls, data, title, label, output_path, cmap="viridis", vmin=None, vmax=None):
        plt, sns = cls.libraries()
        plt.figure(figsize=(10, 8))
        sns.heatmap(data, cmap=cmap, cbar_kws={"label": label}, vmin=vmin, vmax=vmax)
        plt.title(title, fontsize=15)
        plt.xlabel("Pixels (X)")
        plt.ylabel("Pixels (Y)")
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

    @classmethod
    def plot_los(cls, data, title, output_path):
        plt, sns = cls.libraries()
        plt.figure(figsize=(10, 8))
        cmap = sns.color_palette("RdYlGn", 2)
        sns.heatmap(data, cmap=cmap, cbar_kws={"ticks": [0, 1], "label": "0: Obstruido | 1: Visada"})
        plt.title(f"{title}\nMapa de Visada Direta (LOS)", fontsize=15)
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()

    @classmethod
    def plot_plos_analysis(cls, bin_centers, plos_per_bin, valid, f_interp, min_dist, max_dist, title, output_path):
        plt, _ = cls.libraries()
        plt.figure(figsize=(10, 6))
        plt.scatter(bin_centers[valid], plos_per_bin[valid], color="red", label="Medidas (Bins)", alpha=0.6)
        d_smooth = np.linspace(min_dist, max_dist, 200)
        plt.plot(d_smooth, f_interp(d_smooth), "--", color="blue", label="Interpolacao Linear")
        plt.title(f"{title}\nProbabilidade de Visada Direta (P_LOS) vs Distancia")
        plt.xlabel("Distancia (km)")
        plt.ylabel("Probabilidade (0.0 a 1.0)")
        plt.grid(True, linestyle=":", alpha=0.7)
        plt.legend()
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()
