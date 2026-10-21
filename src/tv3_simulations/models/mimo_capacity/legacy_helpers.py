"""Original variant labels and seeding, preserved for reproducibility."""
import numpy as np

def _variant_name_from_power_freq(p_tx_dbm, frequency_ghz):
    p_tx_w = 10 ** ((p_tx_dbm - 30) / 10)
    freq_mhz = int(frequency_ghz * 1000)
    variant_name = f"{p_tx_w:.2f}w_{freq_mhz}Mhz".replace(".00", "")
    return p_tx_w, freq_mhz, variant_name

def _seed_worker(random_seed, p_tx_dbm, frequency_ghz):
    if random_seed is None:
        return
    seed = np.random.SeedSequence([int(random_seed), int(round(p_tx_dbm * 10)), int(round(frequency_ghz * 1e6))])
    np.random.seed(int(seed.generate_state(1)[0]))
