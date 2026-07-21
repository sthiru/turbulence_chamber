import json
import logging
import math
from bisect import bisect_left
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

DEFAULTS: Dict[str, Any] = {
    "coefficient": 7.9e-5,
    "r_m": 0.5,
    "ambient_temp_c": 25.0,
    "pressure_hpa": 1010.0,
    "hotplate_min_c": 60.0,
    "hotplate_max_c": 250.0,
    "fan_min": 50,
    "fan_max": 255,
    "safety_margin_c": 280.0,
    "cn2_min": 1e-16,
    "cn2_max": 1e-7,
    "lookup_table_path": "cn2_lookup_table.json",
}


class Cn2Controller:
    """Compute the temperature difference and actuator setpoints required to achieve a target Cn^2."""

    def __init__(self, config_path: Optional[Union[str, Path]] = None, **kwargs):
        self._base_dir = Path(__file__).parent
        config = dict(DEFAULTS)

        if config_path is not None:
            config.update(self._load_json(config_path))
        elif (self._base_dir / "cn2_controller_config.json").is_file():
            config.update(self._load_json(self._base_dir / "cn2_controller_config.json"))

        # Explicit keyword arguments override the configuration file
        config.update(kwargs)

        for key, value in config.items():
            setattr(self, key, value)

        if "lookup_table" in config and config["lookup_table"] is not None:
            self.lookup_table = self._normalize_lookup_table(config["lookup_table"])
        else:
            lookup_path = Path(self.lookup_table_path)
            if not lookup_path.is_absolute():
                lookup_path = self._base_dir / lookup_path
            raw_table = self._load_json(lookup_path)
            self.lookup_table = self._normalize_lookup_table(raw_table)

    @staticmethod
    def _load_json(path: Union[str, Path]) -> Any:
        with open(path, "r") as f:
            return json.load(f)

    @staticmethod
    def _normalize_lookup_table(table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not isinstance(table, list) or not table:
            raise ValueError("lookup_table must be a non-empty list")

        required_keys = ("dt", "hotplate_temp", "fan_speed")
        for row in table:
            if not all(k in row for k in required_keys):
                raise ValueError(f"lookup table row missing one of {required_keys}: {row}")

        table = sorted(table, key=lambda row: float(row["dt"]))
        for i in range(1, len(table)):
            if float(table[i]["dt"]) <= float(table[i - 1]["dt"]):
                raise ValueError("lookup table dt values must be strictly increasing")
        return table

    @staticmethod
    def _to_kelvin(celsius: float) -> float:
        return celsius + 273.15

    def compute_required_dt(self, target_cn2: float) -> float:
        """Solve the thermal Cn^2 formula for dt at r = 0.5 m."""
        if target_cn2 <= 0:
            raise ValueError("target_cn2 must be positive")

        clamped_cn2 = max(self.cn2_min, min(self.cn2_max, target_cn2))
        if clamped_cn2 != target_cn2:
            logger.warning(
                "target_cn2 %s clamped to [%s, %s]",
                target_cn2, self.cn2_min, self.cn2_max,
            )

        ambient_temp_k = self._to_kelvin(self.ambient_temp_c)
        term = (self.coefficient * (self.pressure_hpa / (ambient_temp_k ** 2))) ** 2
        if term == 0.0:
            raise ValueError("Cn^2 coefficient term is zero; check constants")

        dt = math.sqrt(clamped_cn2 * (self.r_m ** (2.0 / 3.0)) / term)
        return dt

    def _interpolate(self, dt: float, key: str) -> float:
        """Linearly interpolate a value from the lookup table keyed by dt."""
        dts = [float(row["dt"]) for row in self.lookup_table]

        if dt <= dts[0]:
            return float(self.lookup_table[0][key])
        if dt >= dts[-1]:
            return float(self.lookup_table[-1][key])

        idx = bisect_left(dts, dt)
        if idx == 0:
            return float(self.lookup_table[0][key])

        p0 = self.lookup_table[idx - 1]
        p1 = self.lookup_table[idx]
        t = (dt - dts[idx - 1]) / (dts[idx] - dts[idx - 1])
        return float(p0[key]) + t * (float(p1[key]) - float(p0[key]))

    def get_hotplate_and_fan(self, dt: float) -> Dict[str, Union[float, int]]:
        """Map a required dt to hotplate temperature and fan speed using the lookup table."""
        raw_hot = self._interpolate(dt, "hotplate_temp")
        raw_fan = self._interpolate(dt, "fan_speed")

        effective_max_temp = min(self.hotplate_max_c, self.safety_margin_c)
        hotplate_temp = max(self.hotplate_min_c, min(effective_max_temp, raw_hot))
        fan_speed = int(round(max(self.fan_min, min(self.fan_max, raw_fan))))

        return {
            "dt": dt,
            "hotplate_temp": hotplate_temp,
            "fan_speed": fan_speed,
        }

    def get_actuators_for_cn2(self, target_cn2: float) -> Dict[str, Union[float, int]]:
        """Return the hotplate temperature and fan speed required to achieve a target Cn^2."""
        required_dt = self.compute_required_dt(target_cn2)
        result = self.get_hotplate_and_fan(required_dt)
        result["target_cn2"] = target_cn2
        result["required_dt"] = required_dt
        return result
