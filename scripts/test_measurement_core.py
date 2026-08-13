from __future__ import annotations

import sys
from pathlib import Path
import unittest

import numpy as np
import polars as pl


sys.path.insert(0, str(Path(__file__).resolve().parent))
from measurement_core import add_measurement_states, bootstrap_mean_ci  # noqa: E402


class MeasurementCoreTests(unittest.TestCase):
    def test_frozen_boundaries(self) -> None:
        frame = pl.DataFrame(
            {
                "arterial_map": [64.0, 65.0, 64.0, 64.0, 75.0, 64.0],
                "cuff_map": [74.0, 55.0, 73.0, 60.0, 65.0, 75.0],
            }
        )
        result = add_measurement_states(frame)
        self.assertEqual(
            result["threshold_discordant"].to_list(),
            [True, True, True, False, False, True],
        )
        self.assertEqual(
            result["large_discordance_10"].to_list(),
            [True, True, False, False, True, True],
        )
        self.assertEqual(
            result["ccd"].to_list(),
            [True, True, False, False, False, True],
        )

    def test_difference_orientation(self) -> None:
        result = add_measurement_states(
            pl.DataFrame({"arterial_map": [70.0], "cuff_map": [65.0]})
        )
        self.assertEqual(result["delta_cuff_minus_arterial"][0], -5.0)

    def test_bootstrap_reproducibility(self) -> None:
        values = np.linspace(0, 1, 31)
        first = bootstrap_mean_ci(values, replicates=200, seed=20260812)
        second = bootstrap_mean_ci(values, replicates=200, seed=20260812)
        self.assertEqual(first, second)
        self.assertAlmostEqual(first[0], 0.5)


if __name__ == "__main__":
    unittest.main()
