"""
Modelo de canal para analise de desempenho de um sistema TV 3.0
MIMO 2x2 com Layered Division Multiplexing (LDM).

O arquivo segue a mesma arquitetura de SystemModel.py, mas substitui a
capacidade MIMO de camada unica pelas capacidades das camadas UL e LL.
"""

import numpy as np

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, *args, **kwargs):
        return iterable


class MIMOChannelModel:
    """
    Nucleo matematico do modelo de canal MIMO 2x2 com LDM.
    """
    bandwidth_hz = 6e6
    c = 299792458.0
    boltzmann_constant = 1.380649e-23
    temperature_k = 290

    def __init__(self,
                 p_tx: float,
                 injection_ratio_db: float,
                 nmse: float,
                 tx_height_ov_ground: float,
                 rx_height_ov_ground: float,
                 mu_chi_bar_db: float,
                 sigma_chi_bar_db: float,
                 mu_chi_tilde_db: float,
                 sigma_chi_tilde_db: float,
                 delta_tx: float,
                 delta_rx: float,
                 freq_hz: float,
                 bandwidth_hz: float = 6e6,
                 det_epsilon: float = 1e-12) -> None:

        self.p_tx = p_tx
        self.tx_height = tx_height_ov_ground
        self.rx_height = rx_height_ov_ground
        self.mu_chi_bar_db = mu_chi_bar_db
        self.sigma_chi_bar_db = sigma_chi_bar_db
        self.mu_chi_tilde_db = mu_chi_tilde_db
        self.sigma_chi_tilde_db = sigma_chi_tilde_db
        self.var_chi_tilde_db = sigma_chi_tilde_db ** 2
        self.bandwidth_hz = bandwidth_hz

        self.lambda_c = self.c / freq_hz
        self.delta_tx = delta_tx * self.lambda_c
        self.delta_rx = delta_rx * self.lambda_c
        self.p_noise = self.bandwidth_hz * self.boltzmann_constant * self.temperature_k
        self.input_snr = self.p_tx / self.p_noise

        self.injection_ratio_db = injection_ratio_db
        self.injection_ratio = 10 ** (self.injection_ratio_db / 10)
        self.alpha_ul = self.injection_ratio / (1 + self.injection_ratio)
        self.alpha_ll = 1 / (1 + self.injection_ratio)

        self.nmse = self._validate_nonnegative_real(nmse, "nmse")

        self.det_epsilon = det_epsilon

        self.channel_realizations = None
        self.H = None
        self.E = None

    @staticmethod
    def _validate_realization_count(value, name):
        count = int(value)
        if count < 1:
            raise ValueError(f"{name} deve ser maior ou igual a 1.")
        return count

    @staticmethod
    def _validate_nonnegative_real(value, name):
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{name} deve ser um valor real nao negativo.") from None

        if not np.isfinite(number) or number < 0:
            raise ValueError(f"{name} deve ser um valor real nao negativo.")
        return number

    def _compute_P_matrix(self, x_linear):
        """Implementa a matriz de ponderacao de polarizacao P(x)."""
        term1 = np.sqrt(x_linear / (2*(x_linear + 1)))
        term2 = np.sqrt(1 / (2*(x_linear + 1)))

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
        """Calcula a componente LoS base H_bar."""
        H_bar = np.zeros((2, 2), dtype=complex)
        for m in range(2):
            for n in range(2):
                phase = (2 * np.pi / self.lambda_c) * (
                    m * self.delta_rx * np.sin(theta_rx) +
                    n * self.delta_tx * np.sin(theta_tx)
                )
                H_bar[m, n] = np.exp(-1j * phase)
        return H_bar

    def _compute_H_bar_base_batch(self, theta_tx, theta_rx):
        """Calcula a componente LoS base H_bar para um vetor de enlaces."""
        theta_tx = np.asarray(theta_tx, dtype=np.float64)
        theta_rx = np.asarray(theta_rx, dtype=np.float64)
        H_bar = np.zeros(theta_tx.shape + (2, 2), dtype=np.complex128)
        for m in range(2):
            for n in range(2):
                phase = (2 * np.pi / self.lambda_c) * (
                    m * self.delta_rx * np.sin(theta_rx) +
                    n * self.delta_tx * np.sin(theta_tx)
                )
                H_bar[..., m, n] = np.exp(-1j * phase)
        return H_bar

    def _compute_P_matrix_batch(self, x_linear):
        """Implementa P(x) para x com dimensoes (enlaces, realizacoes)."""
        term1 = np.sqrt(x_linear / (2*(x_linear + 1)))
        term2 = np.sqrt(1 / (2*(x_linear + 1)))

        P = np.zeros(x_linear.shape + (2, 2), dtype=np.float64)
        P[..., 0, 0] = term1
        P[..., 0, 1] = term2
        P[..., 1, 0] = term2
        P[..., 1, 1] = term1
        return P

    @staticmethod
    def _plos_weights(plos):
        """Calcula os pesos LoS/NLoS mantendo a formula K usada no legado."""
        plos = np.asarray(plos, dtype=np.float64)
        K_los = np.empty_like(plos)
        K_nlos = np.empty_like(plos)

        los_only = plos == 1.0
        K_los[los_only] = 1.0
        K_nlos[los_only] = 0.0

        mixed = ~los_only
        K = plos[mixed] / (1 - plos[mixed])
        K_los[mixed] = np.sqrt(K / (K + 1))
        K_nlos[mixed] = np.sqrt(1 / (K + 1))
        return K_los, K_nlos

    def _complex_gaussian(self, variance, shape):
        """Gera variaveis complexas gaussianas CN(0, variance)."""
        if variance <= 0:
            return np.zeros(shape, dtype=complex)

        std = np.sqrt(variance / 2)
        real = np.random.normal(0, std, shape)
        imag = np.random.normal(0, std, shape)
        return real + 1j * imag

    def _safe_inverse(self, matrices):
        """Calcula a inversa evitando falha quando alguma matriz fica singular."""
        try:
            return np.linalg.inv(matrices)
        except np.linalg.LinAlgError:
            identity_shape = (1,) * (np.ndim(matrices) - 2) + (2, 2)
            I = np.eye(2, dtype=np.asarray(matrices).dtype).reshape(identity_shape)
            return np.linalg.inv(matrices + self.det_epsilon * I)

    def _rate_from_covariance(self, covariance_matrices):
        """Calcula B log2 det(I + 1/2 R^-1) para varias realizacoes."""
        I = np.eye(2)
        cap_argument = I + 0.5 * self._safe_inverse(covariance_matrices)
        det_values = np.real(np.linalg.det(cap_argument))
        det_values = np.maximum(det_values, 1.0)
        return np.log2(det_values) * (self.bandwidth_hz / 1e6)

    def generate_channel_realizations(self, B_lin, plos, theta_tx, theta_rx, num_channel_realizations):
        """Gera N realizacoes da matriz de canal H e as mantem fixas."""
        num_channel_realizations = self._validate_realization_count(
            num_channel_realizations,
            "num_channel_realizations",
        )

        K = plos / (1 - plos) if plos != 1.0 else None

        H_tilde_real = np.random.normal(0, np.sqrt(0.5), (num_channel_realizations, 2, 2))
        H_tilde_imag = np.random.normal(0, np.sqrt(0.5), (num_channel_realizations, 2, 2))
        H_tilde = H_tilde_real + 1j * H_tilde_imag

        phi_0 = np.random.uniform(-np.pi, np.pi, num_channel_realizations)
        H_bar_base = self._compute_H_bar_base(theta_tx, theta_rx)
        H_bar = H_bar_base[np.newaxis, :, :] * np.exp(-1j * phi_0)[:, np.newaxis, np.newaxis]

        chi_bar_db = np.random.normal(
            self.mu_chi_bar_db,
            self.sigma_chi_bar_db,
            num_channel_realizations,
        )
        chi_bar_linear = 10 ** (chi_bar_db / 10)
        P_chi_bar_broadcast = self._compute_P_matrix(chi_bar_linear)

        chi_tilde_db = np.random.normal(
            self.mu_chi_tilde_db,
            self.sigma_chi_tilde_db,
            num_channel_realizations,
        )
        chi_tilde_linear = 10 ** (chi_tilde_db / 10)
        P_chi_tilde_broadcast = self._compute_P_matrix(chi_tilde_linear)

        B_sqrt = np.sqrt(B_lin)

        K_los = np.sqrt(K / (K + 1)) if plos != 1.0 else 1.0
        K_nlos = np.sqrt(1 / (K + 1)) if plos != 1.0 else 0.0

        term_los = K_los * (H_bar * P_chi_bar_broadcast)
        term_nlos = K_nlos * (H_tilde * P_chi_tilde_broadcast)

        self.channel_realizations = B_sqrt * (term_los + term_nlos)
        self.H = self.channel_realizations
        self.E = None
        return self.channel_realizations

    def _build_channel_batch(
        self,
        B_lin,
        plos,
        theta_tx,
        theta_rx,
        H_tilde_real,
        H_tilde_imag,
        phi_0,
        chi_bar_db,
        chi_tilde_db,
    ):
        H_tilde = H_tilde_real + 1j * H_tilde_imag

        H_bar_base = self._compute_H_bar_base_batch(theta_tx, theta_rx)
        H_bar = H_bar_base[:, np.newaxis, :, :] * np.exp(-1j * phi_0)[..., np.newaxis, np.newaxis]

        chi_bar_linear = 10 ** (chi_bar_db / 10)
        P_chi_bar = self._compute_P_matrix_batch(chi_bar_linear)

        chi_tilde_linear = 10 ** (chi_tilde_db / 10)
        P_chi_tilde = self._compute_P_matrix_batch(chi_tilde_linear)

        K_los, K_nlos = self._plos_weights(plos)
        K_los = K_los[:, np.newaxis, np.newaxis, np.newaxis]
        K_nlos = K_nlos[:, np.newaxis, np.newaxis, np.newaxis]
        B_sqrt = np.sqrt(B_lin)[:, np.newaxis, np.newaxis, np.newaxis]

        term_los = K_los * (H_bar * P_chi_bar)
        term_nlos = K_nlos * (H_tilde * P_chi_tilde)
        return B_sqrt * (term_los + term_nlos)

    def _generate_realizations_batch_legacy_order(
        self,
        B_lin,
        plos,
        theta_tx,
        theta_rx,
        num_channel_realizations,
        num_error_realizations,
    ):
        num_links = B_lin.size
        channel_shape = (num_links, num_channel_realizations, 2, 2)
        error_shape = (num_links, num_channel_realizations, num_error_realizations, 2, 2)
        channels = np.empty(channel_shape, dtype=np.complex128)
        errors = np.empty(error_shape, dtype=np.complex128)

        for link_idx in range(num_links):
            H_tilde_real = np.random.normal(0, np.sqrt(0.5), (num_channel_realizations, 2, 2))
            H_tilde_imag = np.random.normal(0, np.sqrt(0.5), (num_channel_realizations, 2, 2))
            phi_0 = np.random.uniform(-np.pi, np.pi, num_channel_realizations)
            chi_bar_db = np.random.normal(
                self.mu_chi_bar_db,
                self.sigma_chi_bar_db,
                num_channel_realizations,
            )
            chi_tilde_db = np.random.normal(
                self.mu_chi_tilde_db,
                self.sigma_chi_tilde_db,
                num_channel_realizations,
            )
            channels[link_idx] = self._build_channel_batch(
                B_lin[link_idx : link_idx + 1],
                plos[link_idx : link_idx + 1],
                theta_tx[link_idx : link_idx + 1],
                theta_rx[link_idx : link_idx + 1],
                H_tilde_real[np.newaxis, :, :, :],
                H_tilde_imag[np.newaxis, :, :, :],
                phi_0[np.newaxis, :],
                chi_bar_db[np.newaxis, :],
                chi_tilde_db[np.newaxis, :],
            )[0]

            if self.nmse == 0.0:
                errors[link_idx] = 0.0
            else:
                omega_e = self._complex_gaussian(
                    1.0,
                    (num_channel_realizations, num_error_realizations, 2, 2),
                )
                errors[link_idx] = np.sqrt(B_lin[link_idx]) * self.nmse * omega_e

        return channels, errors

    def _generate_realizations_batch_chunked_order(
        self,
        B_lin,
        plos,
        theta_tx,
        theta_rx,
        num_channel_realizations,
        num_error_realizations,
    ):
        num_links = B_lin.size
        shape = (num_links, num_channel_realizations)

        H_tilde_real = np.random.normal(0, np.sqrt(0.5), shape + (2, 2))
        H_tilde_imag = np.random.normal(0, np.sqrt(0.5), shape + (2, 2))
        phi_0 = np.random.uniform(-np.pi, np.pi, shape)
        chi_bar_db = np.random.normal(self.mu_chi_bar_db, self.sigma_chi_bar_db, shape)
        chi_tilde_db = np.random.normal(self.mu_chi_tilde_db, self.sigma_chi_tilde_db, shape)

        channels = self._build_channel_batch(
            B_lin,
            plos,
            theta_tx,
            theta_rx,
            H_tilde_real,
            H_tilde_imag,
            phi_0,
            chi_bar_db,
            chi_tilde_db,
        )

        error_shape = (num_links, num_channel_realizations, num_error_realizations, 2, 2)
        if self.nmse == 0.0:
            errors = np.zeros(error_shape, dtype=np.complex128)
        else:
            omega_e = self._complex_gaussian(1.0, error_shape)
            errors = np.sqrt(B_lin)[:, np.newaxis, np.newaxis, np.newaxis, np.newaxis] * self.nmse * omega_e

        return channels, errors

    def generate_realizations_batch(
        self,
        B_lin,
        plos,
        theta_tx,
        theta_rx,
        num_channel_realizations,
        num_error_realizations=1,
        rng_mode="legacy",
    ):
        """Gera realizacoes para varios enlaces em lote."""
        num_channel_realizations = self._validate_realization_count(
            num_channel_realizations,
            "num_channel_realizations",
        )
        num_error_realizations = self._validate_realization_count(
            num_error_realizations,
            "num_error_realizations",
        )

        B_lin = np.asarray(B_lin, dtype=np.float64).reshape(-1)
        plos = np.asarray(plos, dtype=np.float64).reshape(-1)
        theta_tx = np.asarray(theta_tx, dtype=np.float64).reshape(-1)
        theta_rx = np.asarray(theta_rx, dtype=np.float64).reshape(-1)

        expected_shape = (B_lin.size,)
        for name, value in (
            ("plos", plos),
            ("theta_tx", theta_tx),
            ("theta_rx", theta_rx),
        ):
            if value.shape != expected_shape:
                raise ValueError(f"{name} deve ter o mesmo tamanho de B_lin.")

        if rng_mode == "legacy":
            channels, errors = self._generate_realizations_batch_legacy_order(
                B_lin,
                plos,
                theta_tx,
                theta_rx,
                num_channel_realizations,
                num_error_realizations,
            )
        elif rng_mode in {"chunked", "vectorized"}:
            channels, errors = self._generate_realizations_batch_chunked_order(
                B_lin,
                plos,
                theta_tx,
                theta_rx,
                num_channel_realizations,
                num_error_realizations,
            )
        else:
            raise ValueError("rng_mode deve ser 'legacy', 'chunked' ou 'vectorized'.")

        self.channel_realizations = channels
        self.H = channels[:, :, np.newaxis, :, :]
        self.E = errors
        return self.H, self.E

    def generate_error_realizations(self, B_lin, num_error_realizations):
        """Gera M matrizes de erro para cada canal H ja sorteado."""
        num_error_realizations = self._validate_realization_count(
            num_error_realizations,
            "num_error_realizations",
        )

        if self.channel_realizations is None:
            raise RuntimeError("Gere as realizacoes de canal antes das matrizes de erro.")

        error_shape = (
            self.channel_realizations.shape[0],
            num_error_realizations,
            2,
            2,
        )
        self.H = self.channel_realizations[:, np.newaxis, :, :]
        if self.nmse == 0.0:
            self.E = np.zeros(error_shape, dtype=np.complex128)
            return self.E

        omega_e = self._complex_gaussian(1.0, error_shape)
        self.E = np.sqrt(B_lin) * self.nmse * omega_e
        return self.E

    def generate_realizations(
        self,
        B_lin,
        plos,
        theta_tx,
        theta_rx,
        num_channel_realizations,
        num_error_realizations=1,
    ):
        """Gera N canais e, para cada canal fixo, M matrizes de erro."""
        self.generate_channel_realizations(
            B_lin,
            plos,
            theta_tx,
            theta_rx,
            num_channel_realizations,
        )
        self.generate_error_realizations(B_lin, num_error_realizations)

    def calculate_layer_capacities(self):
        """Calcula as capacidades instantaneas das camadas UL e LL."""
        if self.H is None or self.E is None:
            raise RuntimeError("Gere as realizacoes de canal e erro antes de calcular as capacidades.")

        H_hat = self.H + self.E
        H_hat_inv = self._safe_inverse(H_hat)

        Delta = H_hat_inv @ self.E
        W_H = H_hat_inv @ self.H

        Delta_Delta_H = Delta @ Delta.conj().swapaxes(-1, -2)
        W_H_W_H_H = W_H @ W_H.conj().swapaxes(-1, -2)
        noise_cov = self.p_noise * (H_hat_inv @ H_hat_inv.conj().swapaxes(-1, -2))

        R_w = (
            0.5 * Delta_Delta_H
            + (0.5 / self.injection_ratio) * W_H_W_H_H
            + noise_cov / (self.alpha_ul * self.p_tx)
        )

        R_v = (
            0.5 * (self.injection_ratio + 1) * Delta_Delta_H
            + noise_cov / (self.alpha_ll * self.p_tx)
        )

        cap_ul = self._rate_from_covariance(R_w)
        cap_ll = self._rate_from_covariance(R_v)

        return cap_ul, cap_ll


class SimulationEnvironment:
    """Lida com os dados deterministicos do terreno e do enlace."""
    def __init__(self,
                 B_map=None,
                 plos_map=None,
                 los_map=None,
                 distance_map=None,
                 height_map=None) -> None:
        self.B_map = np.asarray(B_map, dtype=np.float64)
        self.plos_map = np.asarray(plos_map, dtype=np.float64)
        self.los_map = np.asarray(los_map)
        self.distance_map = np.asarray(distance_map, dtype=np.float64)
        self.height_map = np.asarray(height_map, dtype=np.float64)

        self._validate_shapes()
        flat_idx = np.nanargmin(self.distance_map)

        tx_x, tx_y = np.unravel_index(flat_idx, self.distance_map.shape)

        self.tx_height_env = self.height_map[tx_x, tx_y]

    def _validate_shapes(self):
        shape = self.B_map.shape
        for name, value in (
            ("plos_map", self.plos_map),
            ("los_map", self.los_map),
            ("distance_map", self.distance_map),
            ("height_map", self.height_map),
        ):
            if value.shape != shape:
                raise ValueError(f"{name} shape {value.shape} difere de B_map shape {shape}.")

    @property
    def valid_mask(self):
        return ~np.isnan(self.B_map)


class MonteCarloSimulator:
    """Responsavel por orquestrar a simulacao pixel a pixel."""
    def __init__(self,
                 env: SimulationEnvironment,
                 channel_params: dict,
                 num_realizations: int = 1000,
                 num_error_realizations: int = 1,
                 num_channel_realizations=None,
                 chunk_size: int = 128,
                 show_progress: bool = True,
                 rng_mode: str = "legacy") -> None:
        if num_channel_realizations is None:
            num_channel_realizations = num_realizations

        self.num_channel_realizations = MIMOChannelModel._validate_realization_count(
            num_channel_realizations,
            "num_channel_realizations",
        )
        self.num_error_realizations = MIMOChannelModel._validate_realization_count(
            num_error_realizations,
            "num_error_realizations",
        )
        self.num_realizations = self.num_channel_realizations
        self.total_realizations = self.num_channel_realizations * self.num_error_realizations
        self.env = env
        self.channel_params = channel_params
        self.chunk_size = max(1, int(chunk_size))
        self.show_progress = bool(show_progress)
        self.rng_mode = rng_mode
        self.base_channel = MIMOChannelModel(**channel_params)

    def _angles_for_indices(self, indices):
        distance_flat = self.env.distance_map.ravel()
        height_flat = self.env.height_map.ravel()

        tx_height = self.env.tx_height_env + self.channel_params['tx_height_ov_ground']
        rx_height = height_flat[indices] + self.channel_params['rx_height_ov_ground']
        distance = distance_flat[indices]

        height_delta = rx_height - tx_height
        theta_tx = np.empty_like(distance, dtype=np.float64)
        nonzero_delta = height_delta != 0
        theta_tx[nonzero_delta] = np.arctan(distance[nonzero_delta] / height_delta[nonzero_delta])
        theta_tx[~nonzero_delta] = np.pi / 2

        with np.errstate(divide="ignore", invalid="ignore"):
            theta_rx = np.arctan((tx_height - rx_height) / distance)

        return theta_tx, theta_rx

    @staticmethod
    def _mean_capacity(capacity):
        axes = tuple(range(1, capacity.ndim))
        return np.nan_to_num(
            np.mean(capacity, axis=axes),
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        )

    def run_legacy(self):
        """Executa o algoritmo pixel a pixel original para testes de equivalencia."""
        rows, cols = self.env.plos_map.shape
        capacity_ul_map = np.zeros((rows, cols))
        capacity_ll_map = np.zeros((rows, cols))

        tx_height = self.env.tx_height_env + self.channel_params['tx_height_ov_ground']

        row_iterator = range(rows)
        if self.show_progress:
            row_iterator = tqdm(row_iterator, desc="Processando Grade LDM (Pixels)")

        for i in row_iterator:
            for j in range(cols):

                B_lin = self.env.B_map[i, j]

                if np.isnan(B_lin):
                    capacity_ul_map[i, j] = 0
                    capacity_ll_map[i, j] = 0
                    continue

                else:

                    plos = self.env.plos_map[i, j]
                    rx_height = self.env.height_map[i, j] + self.channel_params['rx_height_ov_ground']

                    theta_tx = np.arctan(self.env.distance_map[i, j] / (rx_height - tx_height)) if (rx_height - tx_height) != 0 else np.pi / 2
                    theta_rx = np.arctan((tx_height - rx_height) / self.env.distance_map[i, j])

                    self.base_channel.generate_realizations(
                        B_lin,
                        plos,
                        theta_tx,
                        theta_rx,
                        self.num_channel_realizations,
                        self.num_error_realizations,
                    )

                    cap_ul, cap_ll = self.base_channel.calculate_layer_capacities()

                    capacity_ul_map[i, j] = np.nan_to_num(np.mean(cap_ul), nan=0.0, posinf=0.0, neginf=0.0)
                    capacity_ll_map[i, j] = np.nan_to_num(np.mean(cap_ll), nan=0.0, posinf=0.0, neginf=0.0)

        return capacity_ul_map, capacity_ll_map

    def run(self):
        """Executa a simulacao para toda a grade usando chunks de pixels validos."""
        rows, cols = self.env.plos_map.shape
        flat_size = rows * cols
        capacity_ul_flat = np.zeros(flat_size, dtype=np.float64)
        capacity_ll_flat = np.zeros(flat_size, dtype=np.float64)

        valid_indices = np.flatnonzero(self.env.valid_mask.ravel())
        iterator = range(0, valid_indices.size, self.chunk_size)
        if self.show_progress:
            iterator = tqdm(iterator, desc="Processando Grade LDM (Chunks)")

        B_flat = self.env.B_map.ravel()
        plos_flat = self.env.plos_map.ravel()

        for start in iterator:
            chunk_indices = valid_indices[start : start + self.chunk_size]
            theta_tx, theta_rx = self._angles_for_indices(chunk_indices)

            self.base_channel.generate_realizations_batch(
                B_flat[chunk_indices],
                plos_flat[chunk_indices],
                theta_tx,
                theta_rx,
                self.num_channel_realizations,
                self.num_error_realizations,
                rng_mode=self.rng_mode,
            )
            cap_ul, cap_ll = self.base_channel.calculate_layer_capacities()

            capacity_ul_flat[chunk_indices] = self._mean_capacity(cap_ul)
            capacity_ll_flat[chunk_indices] = self._mean_capacity(cap_ll)

        return capacity_ul_flat.reshape(rows, cols), capacity_ll_flat.reshape(rows, cols)
