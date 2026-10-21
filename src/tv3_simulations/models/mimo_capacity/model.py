"""
Modelo de canal para análise de desempenho de um sistemas de TV 3.0 (MIMO 2x2)

Authors:        João Henrique Venancio Galvão Barbosa (joaobarbosa.ene@gmail.com)
                Higo Thaian Pereira da Silva (higo.silva@redes.unb.br)


Created:
"""

import numpy as np
from tqdm import tqdm


class MIMOChannelModel:
    """
    Núcleo matemático do modelo de canal MIMO 2x2.
    """
    bandwidth_hz = 6e6
    c = 299792458.0
    boltzmann_constant = 1.380649e-23
    temperature_k = 290

    def __init__(self,
                 p_tx: float,
                 tx_height_ov_ground: float,
                 rx_height_ov_ground: float,
                 mu_chi_bar_db: float,
                 sigma_chi_bar_db: float,
                 mu_chi_tilde_db: float,
                 sigma_chi_tilde_db: float,
                 delta_tx: float,
                 delta_rx: float,
                 freq_hz: float) -> None:

        self.p_tx = p_tx
        self.tx_height = tx_height_ov_ground
        self.rx_height = rx_height_ov_ground
        self.mu_chi_bar_db = mu_chi_bar_db
        self.sigma_chi_bar_db = sigma_chi_bar_db
        self.mu_chi_tilde_db = mu_chi_tilde_db
        self.sigma_chi_tilde_db = sigma_chi_tilde_db
        self.var_chi_tilde_db = sigma_chi_tilde_db ** 2

        self.lambda_c = self.c / freq_hz
        self.delta_tx = delta_tx * self.lambda_c
        self.delta_rx = delta_rx * self.lambda_c
        self.p_noise = self.bandwidth_hz * self.boltzmann_constant * self.temperature_k
        self.input_snr = self.p_tx / self.p_noise

        self.H_tilde = None
        self.phi_0 = None
        self.H_bar = None
        self.H = None

    def _compute_P_matrix(self, x_linear):
        """Implementa a Equação 5 da matriz P(x) do artigo."""
        term1 = np.sqrt(x_linear / 2*(x_linear + 1))
        term2 = np.sqrt(1 / 2*(x_linear + 1))

        if isinstance(x_linear, np.ndarray):
            N = len(x_linear)
            P = np.zeros((N, 2, 2))
            P[:, 0, 0] = term1
            P[:, 0, 1] = term2
            P[:, 1, 0] = term2
            P[:, 1, 1] = term1
            return P

        return np.array([[term1, term2], [term2, term1]])

    def _compute_H_bar_base(self, theta_tx, theta_rx):
        """Calcula a componente LoS base H_bar (Equação 3)."""
        H_bar = np.zeros((2, 2), dtype=complex)
        for m in range(2):
            for n in range(2):
                phase = (2 * np.pi / self.lambda_c) * (
                    m * self.delta_rx * np.sin(theta_rx) +
                    n * self.delta_tx * np.sin(theta_tx)
                )
                H_bar[m, n] = np.exp(-1j * phase)
        return H_bar

    def generate_realizations(self, B_lin, plos, theta_tx, theta_rx, num_realizations):
        """Gera as realizações da matriz de canal H (Equação 2) vetorizada."""

        K = plos / (1 - plos) if plos != 1.0 else None

        H_tilde_real = np.random.normal(0, np.sqrt(0.5), (num_realizations, 2, 2))
        H_tilde_imag = np.random.normal(0, np.sqrt(0.5), (num_realizations, 2, 2))
        self.H_tilde = H_tilde_real + 1j * H_tilde_imag

        phi_0 = np.random.uniform(-np.pi, np.pi, num_realizations)
        H_bar_base = self._compute_H_bar_base(theta_tx, theta_rx)
        self.H_bar = H_bar_base[np.newaxis, :, :] * np.exp(-1j * phi_0)[:, np.newaxis, np.newaxis]

        chi_bar_db = np.random.normal(self.mu_chi_bar_db, self.sigma_chi_bar_db, num_realizations)
        chi_bar_linear = 10 ** (chi_bar_db / 10)
        P_chi_bar_broadcast = self._compute_P_matrix(chi_bar_linear)

        chi_tilde_db = np.random.normal(self.mu_chi_tilde_db, self.sigma_chi_tilde_db, num_realizations)
        chi_tilde_linear = 10 ** (chi_tilde_db / 10)
        P_chi_tilde_broadcast = self._compute_P_matrix(chi_tilde_linear)

        B_sqrt = np.sqrt(B_lin)

        K_los = np.sqrt(K / (K + 1)) if plos != 1.0 else 1.0
        K_nlos = np.sqrt(1 / (K + 1)) if plos != 1.0 else 0.0    

        term_los = K_los * (self.H_bar * P_chi_bar_broadcast)
        term_nlos = K_nlos * (self.H_tilde * P_chi_tilde_broadcast)

        self.H = B_sqrt * (term_los + term_nlos)

        return self.H


class SimulationEnvironment:
    """Lida com os dados determinísticos do terreno e do enlace."""
    def __init__(self,
                 B_map=None,
                 plos_map=None,
                 los_map=None,
                 distance_map=None,
                 height_map=None) -> None:
        self.B_map = B_map
        self.plos_map = plos_map
        self.los_map = los_map
        self.distance_map = distance_map
        self.height_map = height_map

        flat_idx = np.argmin(self.distance_map)

        tx_x, tx_y = np.unravel_index(flat_idx, self.distance_map.shape)

        self.tx_height_env = self.height_map[tx_x, tx_y]

    # def get_B_matrix(self, beta_h, beta_v):
    #    return np.array([[beta_h, 0], [0, beta_v]])


class MonteCarloSimulator:
    """Responsável por orquestrar a simulação pixel a pixel."""
    def __init__(self,
                 env: SimulationEnvironment,
                 channel_params: dict,
                 num_realizations: int = 1000) -> None:
        self.num_realizations = num_realizations
        self.env = env
        self.channel_params = channel_params
        self.base_channel = MIMOChannelModel(**channel_params)

    def run(self):

        """Executa a simulação para toda a grade pixel a pixel."""
        rows, cols = self.env.plos_map.shape
        capacity_map = np.zeros((rows, cols))

        tx_height = self.env.tx_height_env + self.channel_params['tx_height_ov_ground']

        for i in tqdm(range(rows), desc="Processando Grade (Pixels)"):
            for j in range(cols):

                B_lin = self.env.B_map[i, j]

                if np.isnan(B_lin):
                    capacity_map[i, j] = 0
                    continue

                else:

                    plos = self.env.plos_map[i, j]
                    rx_height = self.env.height_map[i, j] + self.channel_params['rx_height_ov_ground']

                    theta_tx = np.arctan(self.env.distance_map[i, j] / (rx_height - tx_height)) if (rx_height - tx_height) != 0 else np.pi / 2
                    theta_rx = np.arctan((tx_height - rx_height) / self.env.distance_map[i, j])

                    H_matrices = self.base_channel.generate_realizations(B_lin, plos, theta_tx, theta_rx, self.num_realizations)

                    HH_H = H_matrices @ H_matrices.conj().transpose(0, 2, 1)
                    SNR_term = (self.base_channel.input_snr / 2)
                    I = np.eye(2)[np.newaxis, :, :]

                    cap_realizations = np.log2(np.real(np.linalg.det(I + SNR_term * HH_H)))

                    capacity_map[i, j] = np.mean(cap_realizations) * (self.base_channel.bandwidth_hz / 1e6)

        return capacity_map
