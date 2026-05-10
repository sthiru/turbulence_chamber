# Calibration Process: Turbulence Chamber Characterization

## Abstract

This document describes the comprehensive calibration procedure for the turbulence chamber system, which consists of two sequential calibration steps:

1. **Fan-to-Windflow Sensor Characterization**: Establishes linear relationships between fan PWM speeds and windflow sensor readings
2. **Hot Plate 4D Calibration**: Establishes 4D lookup tables mapping hot plate temperature × fan speed → chamber temperature/Cn²

These calibrations enable precise control of chamber turbulence by determining the required actuator settings (fan speed, hot plate temperature) to achieve desired Cn² values.

## 1. Purpose

The calibration establishes a mathematical relationship between:
- **Input**: Fan speed (PWM duty cycle, 0-255)
- **Output**: Windflow sensor reading (arbitrary units proportional to air velocity)

This relationship allows us to:
- Predict the windflow for any given fan speed
- Calculate the required fan speed to achieve a target windflow
- Quantify the accuracy of the fan-sensor response

## 2. Physical Setup

**Configuration:**
- One windflow sensor placed at a fixed distance of 40 cm directly downstream from a speed-controlled fan
- The fan speed is controlled via PWM (Pulse Width Modulation) with a range of 0-255
- The windflow sensor outputs a value proportional to air velocity at the sensor location

**Why 40 cm distance:**
- Allows airflow to develop and stabilize after leaving the fan
- Far enough to avoid turbulent wake effects near the fan blades
- Close enough to maintain signal strength and signal-to-noise ratio
- Provides a representative measurement of the fan's generated airflow

**Ambient Conditions:**
During calibration, the following environmental parameters are recorded:
- **Ambient Temperature**: Measured in °C
- **Ambient Pressure**: Measured in hPa (hectopascal) or mbar
- **Relative Humidity**: Measured in %

These parameters are captured at the start of calibration and stored with the polynomial coefficients.

## 3. Mathematical Model

### 3.1 Relationship Between Fan Speed and Windflow

The relationship between fan speed (S) and windflow (Q) is approximately linear over the operating range. We model this relationship using a linear polynomial:

```
Q = a·S + b
```

Where:
- **S** = Fan speed (PWM value, 0 to 255)
- **Q** = Windflow sensor reading (arbitrary units)
- **a, b** = Coefficients determined through calibration (slope and intercept)

**Why linear polynomial:**
- Fan speed to windflow relationship is linear in the operating range
- Provides sufficient accuracy for control purposes
- Enables simple analytical solution for inverse mapping
- Computationally efficient for real-time control
- Reduces overfitting risk with limited data points

### 3.2 Calibration Data Collection

To determine the coefficients a and b, we collect data points (S, Q) at multiple fan speeds:

**Procedure:**
1. Set fan speed to S₀ = 0, 5, 10, 15, ..., 255 (step size of 5 PWM units)
2. At each speed S, measure the windflow Q
3. Record multiple readings at each speed and average to reduce noise
4. This yields N data points: {(S₁, Q₁), (S₂, Q₂), ..., (S_N, Q_N)}

**Why multiple speeds:**
- Provides sufficient data points for regression fitting (at least 2 points for linear)
- Captures the full operating range of the fan
- Validates the linearity assumption across the range

**Why averaging at each speed:**
- Reduces random measurement noise
- Accounts for short-term fluctuations in airflow
- Improves accuracy of the fitted model

### 3.3 Polynomial Fitting (Regression)

Given N data points, we find coefficients a and b that minimize the sum of squared errors:

```
Minimize: Σ (Q_i - (a·S_i + b))²
```

This is a least-squares regression problem, solved analytically using linear algebra.

**Goodness of Fit (R²):**
We quantify how well the model fits the data using the coefficient of determination:

```
R² = 1 - (SS_res / SS_tot)
```

Where:
- SS_res = Σ(Q_i - Q̂_i)² (residual sum of squares)
- SS_tot = Σ(Q_i - Q̄)² (total sum of squares)
- Q̂_i = Predicted windflow from model
- Q̄ = Mean of all measured windflow values

**Interpretation:**
- R² = 1: Perfect fit (model explains all variance)
- R² = 0: Model explains none of the variance
- R² > 0.9: Good fit for most applications
- R² < 0.9: May indicate sensor issues or non-polynomial behavior

### 3.4 Forward Mapping: Fan Speed → Windflow

Once coefficients are determined, we can predict windflow for any fan speed:

```
Q = a·S + b
```

**Use case:** Given a desired fan speed setting, predict the resulting windflow.

**Example:**
If coefficients are a = 0.2, b = 0.1:
- At S = 100: Q = 0.2(100) + 0.1 = 20.1
- At S = 200: Q = 0.2(200) + 0.1 = 40.1

### 3.5 Inverse Mapping: Desired Windflow → Required Fan Speed

To achieve a target windflow Q_target, we need to solve for S:

```
a·S + b = Q_target
S = (Q_target - b) / a
```

This yields a single solution. We ensure the solution:
- Lies within valid PWM range [0, 255]
- Is clamped to boundaries if outside range

**Use case:** Given a desired windflow value, calculate the required fan speed setting.

**Example:**
If coefficients are a = 0.2, b = 0.1:
- For Q_target = 30:
  - S = (30 - 0.1) / 0.2
  - S = 29.9 / 0.2
  - S = 149.5 PWM (round to 150)

## 4. Why This Calibration is Necessary

### 4.1 Linear Response Characterization
While the fan-to-windflow relationship is approximately linear in the operating range, calibration is still necessary to:
- Determine the exact slope and intercept for each fan-sensor pair
- Account for sensor-specific characteristics (sensitivity, offset)
- Validate the linearity assumption across the full operating range
- Quantify the accuracy of the linear model (R²)

Without calibration, assuming ideal linear response would lead to:
- Inaccurate airflow predictions due to sensor offsets
- Poor control precision due to uncharacterized slopes
- Inability to detect sensor degradation or drift

### 4.2 Sensor Variability
Different sensors (even of the same model) may have:
- Different sensitivity (output per unit velocity)
- Different offset (zero reading)

Calibration characterizes each specific sensor-fan pair to account for these variations.

### 4.3 Environmental Factors
The windflow measurement depends on:
- **Air density**: Varies with temperature and pressure (ρ ∝ P/T)
- **Air viscosity**: Affected by temperature and humidity
- Chamber geometry (airflow patterns)

**Why ambient conditions are recorded:**
- Air density directly affects the relationship between fan speed and generated airflow
- Higher temperature → lower air density → reduced windflow for same fan speed
- Higher pressure → higher air density → increased windflow for same fan speed
- Humidity affects air viscosity, influencing flow characteristics
- Recording these parameters enables:
  - Comparison between calibration sessions under different conditions
  - Potential normalization of calibration data to standard conditions
  - Identification of environmental variations affecting measurements
  - Reproducibility of experimental conditions

Calibration under controlled conditions provides a baseline relationship that can be adjusted for environmental factors if needed.

### 4.4 Control Precision
To precisely control chamber turbulence, we need to:
- Set airflow to specific values
- Reproduce experimental conditions
- Maintain stable turbulence levels

The calibrated inverse mapping enables precise control by directly setting the fan speed to achieve the target windflow.

## 5. Calibration Validation

After fitting the polynomial, we validate by:
1. **Check R²**: Should be > 0.9 for good fit
2. **Check monotonicity**: Windflow should increase with fan speed
3. **Check physical plausibility**: Coefficient 'a' should be positive (convex response)
4. **Cross-validation**: Test with a subset of data not used for fitting
5. **Repeatability**: Perform calibration multiple times to ensure consistency

## 6. Calibration Procedure Details

### 6.1 Data Collection Parameters

**Fan Speed Step Size:**
- Default: 5 PWM units
- Range: 0, 5, 10, 15, ..., 255
- Total steps: 52 levels per fan
- Adjustable parameter (can be set to 1-50 for different resolution)

**Sampling:**
- Readings per speed level: 5 samples
- Sampling interval: 0.2 seconds between readings
- Stabilization delay: 2 seconds after speed change
- Average calculation: Mean of 5 readings

**Total Duration:**
- Per fan: ~52 steps × (2s stabilization + 1s sampling) ≈ 156 seconds ≈ 2.6 minutes
- All 4 fans: ~10.4 minutes total

### 6.2 Data Structure

Each calibration session produces the following data structure:

```json
{
  "calibration_id": "windflow_YYYYMMDD_HHMMSS",
  "timestamp": "2026-05-07T22:00:00",
  "sensor_distance_cm": 40.0,
  "ambient_temperature": 25.3,
  "ambient_pressure": 1013.2,
  "ambient_humidity": 45.7,
  "polynomials": [
    {
      "fan_id": 0,
      "windflow_sensor_id": 0,
      "coefficients": [a₀, b₀],
      "degree": 1,
      "r_squared": 0.985,
      "data_points": [[0, Q₀], [5, Q₁], ..., [255, Q₅₁]]
    },
    {
      "fan_id": 1,
      "windflow_sensor_id": 1,
      "coefficients": [a₁, b₁],
      "degree": 1,
      "r_squared": 0.982,
      "data_points": [[0, Q₀], [5, Q₁], ..., [255, Q₅₁]]
    },
    ...
  ]
}
```

**Coefficient Interpretation:**
- `coefficients[0]` = a (slope term)
- `coefficients[1]` = b (intercept term)

### 6.3 File Storage

Calibration results are saved in two locations:
1. **Timestamped**: `calibration_data/windflow_YYYYMMDD_HHMMSS.json`
2. **Latest**: `windflow_polynomials_latest.json` (always contains most recent calibration)

### 6.4 Multi-Fan Calibration

The system supports simultaneous calibration of all 4 fan-windflow pairs:
- Fan 0 → Windflow Sensor 0
- Fan 1 → Windflow Sensor 1
- Fan 2 → Windflow Sensor 2
- Fan 3 → Windflow Sensor 3

Each pair is calibrated independently to account for:
- Individual fan characteristics
- Sensor-to-sensor variability
- Position-dependent airflow patterns

## 7. Summary

**What calibration does:**
- Collects data points (fan speed, windflow) across the operating range
- Records ambient environmental conditions (temperature, pressure, humidity)
- Fits a linear polynomial: Q = a·S + b
- Calculates goodness of fit (R²)
- Saves coefficients and metadata for future use

**Why calibration is done:**
- Fan-speed to windflow relationship is approximately linear but needs characterization
- Sensors have individual characteristics (sensitivity, offset)
- Air density varies with environmental conditions
- Enables accurate prediction and control
- Provides quantitative validation of hardware

**How it's used:**
- **Forward**: Given fan speed → predict windflow
- **Inverse**: Given desired windflow → calculate required fan speed
- **Environmental correction**: Use ambient conditions to normalize or adjust for environmental variations

This mathematical relationship forms the foundation for precise control of airflow and turbulence in the experimental chamber.

---

## 8. Hot Plate 4D Calibration

### 8.1 Purpose

The hot plate 4D calibration establishes a 4D lookup table mapping:
- **Inputs**: Hot plate temperature (80-120°C) × Fan speed (255, 191, 128, 64 PWM)
- **Outputs**: Chamber temperature, Cn² value, individual sensor temperatures

This enables:
- Precise lookup of required actuator settings for target Cn²
- Interpolation for intermediate temperature/fan speed combinations
- Comprehensive characterization of coupled thermal and flow effects
- Foundation for Cn² control system

### 8.2 Physical Setup

**Configuration:**
- Both hot plates set to same temperature
- Fan speeds varied at fixed levels: 255, 191, 128, 64 PWM (100%, 75%, 50%, 25%)
- All DS18B20 sensors recorded
- Cn² calculated from optical measurements (camera-based)

**Nested Loop Structure:**
```
For each fan_speed in [255, 191, 128, 64]:
    For each temp in [80, 82, 84, ..., 120]:
        Set fans to fan_speed
        Set hot plates to temp
        Record data for 15 minutes
```

### 8.3 Lookup Table Structure (Option C: Interpolation-Friendly Array)

The lookup table uses a matrix format optimized for interpolation:

**Structure:**
```json
{
  "hotplate_temps": [80.0, 82.0, 84.0, ..., 120.0],
  "fan_speeds": [255, 191, 128, 64],
  "cn2_matrix": [
    [cn2_80_255, cn2_80_191, cn2_80_128, cn2_80_64],
    [cn2_82_255, cn2_82_191, cn2_82_128, cn2_82_64],
    ...
  ],
  "chamber_temp_matrix": [
    [temp_80_255, temp_80_191, temp_80_128, temp_80_64],
    ...
  ],
  "sensor_temp_matrices": {
    "sensor_1": [[temp_80_255, ...], ...],
    "sensor_3": [[temp_80_255, ...], ...],
    "sensor_5": [[temp_80_255, ...], ...],
    "sensor_7": [[temp_80_255, ...], ...]
  }
}
```

**Advantages:**
- Row-major: temperatures vary by row, fan speeds vary by column
- Easy to interpolate using bilinear interpolation
- Compact storage with predictable access patterns
- Fast lookup for control system

### 8.4 Calibration Procedure

**Parameters:**
- Temperature range: 80-120°C (configurable)
- Temperature step: 2°C (default, configurable)
- Fan speeds: [255, 191, 128, 64] PWM (configurable)
- Recording duration: 900 seconds (15 minutes, configurable)
- Sampling interval: 10 seconds (configurable)

**Procedure:**
1. For each fan speed in [255, 191, 128, 64]:
   a. Set all fans to current fan speed
   b. Wait 2 seconds for fan stabilization
   c. For each target temperature (80, 82, 84, ..., 120°C):
      i. Set hot plates to target temperature
      ii. Wait 60 seconds for initial heating
      iii. Record all sensor temperatures for 15 minutes at 10s intervals
      iv. Calculate chamber temperature average (sensors 1, 3, 5, 7)
      v. Calculate Cn² from optical data
2. Build 4D lookup table from collected data
3. Save lookup table in interpolation-friendly format

**Estimated Duration:**
- Temperature steps: 21 (80-120°C in 2°C steps)
- Fan speeds: 4
- Total data points: 21 × 4 = 84
- Per point: 60s initial + 900s recording = 960s = 16 minutes
- Total: 84 × 16 minutes ≈ 22.4 hours

### 8.5 Data Processing

**Steady-State Selection:**
- Use last 30% of recorded data for each data point
- This captures the stabilized state after saturation
- Reduces transient effects in lookup table values

**Matrix Construction:**
- For each temperature-fan speed combination:
  - Calculate average Cn² from steady-state data
  - Calculate average chamber temperature
  - Calculate average individual sensor temperatures
- Populate matrices with averaged values

### 8.6 Interpolation

For queries with intermediate temperature/fan speed values:

**Nearest Neighbor (Current Implementation):**
- Find nearest temperature index: `temp_idx = searchsorted(temps, target_temp)`
- Find nearest fan speed index: `fan_idx = searchsorted(fans, target_fan)`
- Return value at matrix[temp_idx][fan_idx]

**Future Enhancement: Bilinear Interpolation:**
- Interpolate between 4 nearest points for smoother results
- Use weighted average based on distance to each point
- Provides sub-grid resolution lookup capability

### 8.7 Data Structure

```json
{
  "calibration_id": "hotplate_4d_calib_YYYYMMDD_HHMMSS",
  "timestamp": "2026-05-07T22:00:00",
  "config": {
    "temp_min": 80.0,
    "temp_max": 120.0,
    "temp_step": 2.0,
    "fan_speeds": [255, 191, 128, 64],
    "recording_duration": 900,
    "sampling_interval": 10
  },
  "lookup_table": {
    "hotplate_temps": [80.0, 82.0, ..., 120.0],
    "fan_speeds": [255, 191, 128, 64],
    "cn2_matrix": [[...], ...],
    "chamber_temp_matrix": [[...], ...],
    "sensor_temp_matrices": {
      "sensor_1": [[...], ...],
      "sensor_3": [[...], ...],
      "sensor_5": [[...], ...],
      "sensor_7": [[...], ...]
    },
    "metadata": {
      "calibration_type": "hotplate_4d",
      "interpolation_method": "nearest_neighbor",
      "data_points_count": 5400
    }
  },
  "ambient_temperature": 25.3,
  "ambient_pressure": 1013.2,
  "ambient_humidity": 45.7
}
```

### 8.8 File Storage

- **Timestamped**: `calibration_data/hotplate_4d_calib_YYYYMMDD_HHMMSS/combined_calibration.json`
- **Latest**: `calibration_data/combined_calibration.json`
- **Data CSV**: `combined_calibration_data.csv` with all sensor readings

---

## 9. Calibration Workflow

### 9.1 Recommended Order

Calibrations should be performed in the following order:

1. **Fan-to-Windflow** (Fastest, ~10 minutes)
   - Characterizes basic airflow control
   - Independent of thermal effects
   - Foundation for flow-based control

2. **Hot Plate 4D** (Longest, ~22.4 hours)
   - Characterizes coupled thermal-flow effects
   - Provides complete 4D lookup table
   - Enables Cn²-based control
   - Includes fan speed variations for comprehensive characterization

### 9.2 When to Recalibrate

Recalibration is recommended when:
- Sensors are replaced or moved
- Fans or hot plates are replaced
- Significant environmental changes (different ambient conditions)
- Hardware shows degraded performance
- Control precision degrades
- After maintenance or repairs

### 9.3 Calibration Validation

After each calibration:
1. Check R² values (> 0.9 for good fit)
2. Verify monotonic relationships
3. Check physical plausibility of parameters
4. Perform cross-validation with test data
5. Verify repeatability across multiple runs

---

## 10. API Endpoints

### 10.1 Fan-to-Windflow Calibration

- `POST /api/calibration/windflow/start` - Start calibration
- `GET /api/calibration/windflow-polynomials` - Get polynomials
- `GET /api/calibration/latest-data` - Get latest CSV data
- `GET /api/calibration/latest-metadata` - Get latest metadata

### 10.2 Hot Plate 4D Calibration

- `POST /api/calibration/hotplate/start` - Start hot plate 4D calibration
  - Parameters: temp_min, temp_max, temp_step, fan_speeds (comma-separated), recording_duration, sampling_interval
- `GET /api/calibration/lookup-table` - Get full lookup table
- `GET /api/calibration/lookup-table/interpolate?hotplate_temp=X&fan_speed=Y` - Interpolate values

### 10.3 General Control

- `POST /api/calibration/control` - Pause/Resume/Stop calibration
- `GET /api/calibration/status` - Get current calibration status

---

## 11. Summary

**Two-Step Calibration System:**

1. **Fan-to-Windflow**: Linear model Q = a·S + b
   - Quick characterization (~10 minutes)
   - Independent thermal effects
   - Foundation for flow control

2. **Hot Plate 4D**: 4D lookup table (temperature × fan speed → Cn²)
   - Long duration (~22.4 hours)
   - Complete system characterization
   - Enables Cn² control
   - Replaces separate hot plate and combined calibrations

**Usage:**
- Individual calibrations can be run separately
- Lookup table enables inverse mapping: desired Cn² → required hot plate temp + fan speed
- Interpolation provides sub-grid resolution
- Environmental conditions recorded for normalization

This comprehensive calibration system enables precise, automated control of chamber turbulence for experimental applications.
