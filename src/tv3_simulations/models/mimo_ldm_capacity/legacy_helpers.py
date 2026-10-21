"""Original variant labels and seeding, preserved for reproducibility."""
import numpy as np

def _variant_name_from_power_freq(p_tx_dbm, frequency_ghz):
    p_tx_w = 10 ** ((p_tx_dbm - 30) / 10)
    freq_mhz = int(frequency_ghz * 1000)
    variant_name = f"{p_tx_w:.2f}w_{freq_mhz}Mhz".replace(".00", "")
    return p_tx_w, freq_mhz, variant_name

def _seed_worker(random_seed, p_tx_dbm, frequency_ghz, injection_ratio_db=0.0, nmse=0.0):
    if random_seed is None:
        return
    seed = np.random.SeedSequence(
        [
            int(random_seed),
            int(round(p_tx_dbm * 10)),
            int(round(frequency_ghz * 1e6)),
            int(round(float(injection_ratio_db) * 10)),
            int(round(float(nmse) * 1e6)),
        ]
    )
    np.random.seed(int(seed.generate_state(1)[0]))

def _format_param_token(value):
    value = float(value)
    if value.is_integer():
        return str(int(value))
    return f"{value:g}".replace("-", "m").replace(".", "p")

def _variant_name_from_ldm_params(p_tx_dbm, frequency_ghz, injection_ratio_db, nmse):
    p_tx_w, freq_mhz, base_name = _variant_name_from_power_freq(p_tx_dbm, frequency_ghz)
    ir_token = _format_param_token(injection_ratio_db)
    nmse_token = _format_param_token(nmse)
    variant_name = f"{base_name}_ir{ir_token}db_nmse{nmse_token}"
    return p_tx_w, freq_mhz, variant_name

def _validate_nonnegative_real(value, name):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} deve ser um valor real nao negativo.") from None

    if not np.isfinite(number) or number < 0:
        raise ValueError(f"{name} deve ser um valor real nao negativo.")
    return number
