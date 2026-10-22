"""Regressões para distância no centro e preservação dos perfis P.1812."""
import ast
import math
from pathlib import Path
import sys
import time
from types import SimpleNamespace, MethodType
import unittest
from unittest.mock import Mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
# Isola os métodos sem carregar bases geográficas durante a importação.
SOURCE = ROOT / 'src/tv3_simulations/propagation/suriacov_local.py'
TREE = ast.parse(SOURCE.read_text(encoding='utf-8'))
COVERAGE = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'Coverage')
HELPER = next(n for n in COVERAGE.body if isinstance(n, ast.FunctionDef) and n.name == '_short_path_coverage')
NAMESPACE = dict(np=np, math=math)
exec(compile(ast.Module(body=[HELPER], type_ignores=[]), str(SOURCE), 'exec'), NAMESPACE)

def short_path_coverage(distance_map, tx_index, rx_index, frequency_ghz, tx_power_kw, antenna_gain_db):
    cov = SimpleNamespace(distance_map=distance_map,
        env=SimpleNamespace(coord_to_index=lambda *args: tx_index),
        tx=SimpleNamespace(tx_coord=(0, 0), freq_ghz=frequency_ghz, tx_power_kw=tx_power_kw))
    return NAMESPACE['_short_path_coverage'](cov, rx_index, antenna_gain_db)


class NearFieldTests(unittest.TestCase):
    def test_distance_frequency_power_and_antenna_gain(self):
        distance = np.array([[1., 2.]])
        first, field = short_path_coverage(distance, (9, 9), (0, 0), .273, 1., 0.)
        second, _ = short_path_coverage(distance, (9, 9), (1, 0), .273, 1., 0.)
        self.assertAlmostEqual(first, 32.44 + 20 * math.log10(273))
        self.assertAlmostEqual(second - first, 20 * math.log10(2))
        other_loss, other_field = short_path_coverage(distance, (9, 9), (0, 0), .273, 10., 3.)
        self.assertEqual(first, other_loss)
        self.assertAlmostEqual(other_field - field, 13.)

    def test_transmitter_uses_closest_receiver_not_artificial_one_meter(self):
        distance = np.array([[.8247666884612934, 1.], [2., .6731288814088542]])
        loss, _ = short_path_coverage(distance, (0, 0), (0, 0), .273, 1., 0.)
        nearest, _ = short_path_coverage(distance, (0, 0), (1, 1), .273, 1., 0.)
        self.assertAlmostEqual(loss, 77.72521743854651)
        self.assertEqual(loss, nearest)

    def test_zero_distance_uses_positive_sample_and_invalid_map_fails(self):
        loss, _ = short_path_coverage(np.array([[0., 1.]]), (0, 0), (0, 0), .273, 1., 0.)
        self.assertAlmostEqual(loss, 32.44 + 20 * math.log10(273))
        with self.assertRaises(ValueError):
            short_path_coverage(np.zeros((2, 2)), (0, 0), (0, 0), .273, 1., 0.)

    def test_actual_coverage_loop_preserves_p1812_border(self):
        # Carrega os métodos reais sem inicializar bases geográficas na importação
        # do SuriaCov. O terreno e P.1812 são controlados para isolar o fallback.
        source = ROOT / 'src/tv3_simulations/propagation/suriacov_local.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Coverage')
        methods = [n for n in cls.body if isinstance(n, ast.FunctionDef)
                   and n.name in ('compute_coverage', 'compute_point_coverage', '_short_path_coverage')]
        p1812 = Mock(return_value=(150., 40.))
        namespace = dict(np=np, math=math, time=time, P1812=SimpleNamespace(bt_loss=p1812),
                         _GLB_ITU_LIMITS_NUM_POINTS=4, short_path_coverage=short_path_coverage)
        exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), 'exec'), namespace)
        rows, cols = np.indices((13, 13))
        distance = np.hypot(rows - 6.4, cols - 6.4)
        env = SimpleNamespace(data_array=np.zeros((13, 13)),
                              coord_to_index=lambda x, y: (6, 6),
                              index_to_coord=lambda x, y: (x, y))
        tx = SimpleNamespace(tx_coord=(6., 6.), tx_ant_pattern={0: 1., 180: 1., 360: 1.},
                             tx_ant_pattern_db={0: 0., 180: 0., 360: 0.},
                             tx_height_ov_ground=80., freq_ghz=.273, tx_power_kw=1., tx_polarization_id=1)

        def profile(receiver):
            x, y = receiver
            n = max(abs(x - 6), abs(y - 6)) + 1
            zeros = np.zeros(n)
            return zeros, np.linspace(0, distance[y, x], n), zeros, [(x, y)] * n, zeros, zeros, n

        cov = SimpleNamespace(env=env, tx=tx, rx_height=10., perc=50., distance_map=distance,
                              _get_path_profiles=profile, dist_los=[], pl_los=[], dist_nlos=[], pl_nlos=[])
        cov._short_path_coverage = MethodType(namespace['_short_path_coverage'], cov)
        namespace['compute_coverage'](cov, 'test')
        central = (abs(rows - 6) <= 3) & (abs(cols - 6) <= 3)
        self.assertEqual(p1812.call_count, 13 * 13 - 49)
        np.testing.assert_array_equal(cov.path_loss_map[~central], 150.)
        np.testing.assert_array_equal(cov.field_intensity_map[~central], 40.)
        self.assertGreater(np.unique(cov.path_loss_map[central]).size, 10)
        self.assertTrue(np.isfinite(cov.path_loss_map).all())
        for receiver in ((6, 6), (3, 3), (2, 6)):
            loss, field = namespace['compute_point_coverage'](cov, receiver)
            x, y = receiver
            self.assertEqual(loss, cov.path_loss_map[y, x])
            self.assertEqual(field, cov.field_intensity_map[y, x])


if __name__ == '__main__':
    unittest.main()
