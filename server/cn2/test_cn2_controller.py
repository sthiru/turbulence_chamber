import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Make the cn2 package importable when this test file is run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cn2.cn2_controller import Cn2Controller


class TestCn2Controller(unittest.TestCase):
    def setUp(self):
        self.lookup_table = [
            {"dt": 0.0, "hotplate_temp": 60.0, "fan_speed": 50},
            {"dt": 1.0, "hotplate_temp": 80.0, "fan_speed": 100},
            {"dt": 10.0, "hotplate_temp": 120.0, "fan_speed": 200},
        ]
        self.controller = Cn2Controller(
            ambient_temp_c=25.0,
            pressure_hpa=1010.0,
            r_m=0.5,
            lookup_table=self.lookup_table,
            hotplate_min_c=60.0,
            hotplate_max_c=250.0,
            fan_min=50,
            fan_max=255,
            safety_margin_c=280.0,
            cn2_min=1e-16,
            cn2_max=1e-7,
        )

    def test_compute_required_dt_matches_formula(self):
        target = 1e-10
        ambient_k = 25.0 + 273.15
        term = (7.9e-5 * (1010.0 / (ambient_k ** 2))) ** 2
        expected = math.sqrt(target * (0.5 ** (2.0 / 3.0)) / term)

        actual = self.controller.compute_required_dt(target)
        self.assertAlmostEqual(actual, expected, places=10)

    def test_compute_required_dt_clamping(self):
        # Below the configured minimum -> clamped to cn2_min
        dt_min = self.controller.compute_required_dt(1e-20)
        self.assertEqual(dt_min, self.controller.compute_required_dt(self.controller.cn2_min))

    def test_interpolation(self):
        # dt = 5.5 is halfway between 1.0 (80) and 10.0 (120)
        hotplate = self.controller._interpolate(5.5, "hotplate_temp")
        self.assertAlmostEqual(hotplate, 100.0, places=6)

        fan = self.controller._interpolate(5.5, "fan_speed")
        self.assertAlmostEqual(fan, 150.0, places=6)

    def test_clamping_low_dt(self):
        result = self.controller.get_hotplate_and_fan(-5.0)
        self.assertEqual(result["hotplate_temp"], 60.0)
        self.assertEqual(result["fan_speed"], 50)

    def test_clamping_high_dt(self):
        result = self.controller.get_hotplate_and_fan(1000.0)
        self.assertEqual(result["hotplate_temp"], 120.0)
        self.assertEqual(result["fan_speed"], 200)

    def test_actuator_bounds(self):
        table = [
            {"dt": 0.0, "hotplate_temp": 300.0, "fan_speed": 500},
            {"dt": 1.0, "hotplate_temp": 300.0, "fan_speed": 500},
        ]
        controller = Cn2Controller(
            lookup_table=table,
            hotplate_min_c=60.0,
            hotplate_max_c=250.0,
            fan_min=50,
            fan_max=255,
            safety_margin_c=280.0,
        )
        result = controller.get_hotplate_and_fan(0.5)
        self.assertEqual(result["hotplate_temp"], 250.0)
        self.assertEqual(result["fan_speed"], 255)

    def test_safety_margin_below_max(self):
        table = [
            {"dt": 0.0, "hotplate_temp": 100.0, "fan_speed": 50},
            {"dt": 1.0, "hotplate_temp": 100.0, "fan_speed": 50},
        ]
        controller = Cn2Controller(
            lookup_table=table,
            hotplate_min_c=60.0,
            hotplate_max_c=300.0,
            safety_margin_c=100.0,
            fan_min=50,
            fan_max=255,
        )
        result = controller.get_hotplate_and_fan(0.5)
        self.assertEqual(result["hotplate_temp"], 100.0)

    def test_invalid_lookup_table(self):
        with self.assertRaises(ValueError):
            Cn2Controller(lookup_table=[{"dt": 0.0}])

    def test_lookup_table_file_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lookup.json"
            path.write_text(json.dumps(self.lookup_table))
            controller = Cn2Controller(
                lookup_table_path=str(path),
                ambient_temp_c=25.0,
                pressure_hpa=1010.0,
                r_m=0.5,
            )
            self.assertEqual(len(controller.lookup_table), 3)
            self.assertEqual(controller.lookup_table[0]["hotplate_temp"], 60.0)

    def test_get_actuators_for_cn2(self):
        result = self.controller.get_actuators_for_cn2(1e-10)
        self.assertIn("target_cn2", result)
        self.assertIn("required_dt", result)
        self.assertIn("hotplate_temp", result)
        self.assertIn("fan_speed", result)
        self.assertGreater(result["required_dt"], 0.0)


if __name__ == "__main__":
    unittest.main()
