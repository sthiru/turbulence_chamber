# -*- coding: utf-8 -*-
"""
Calibration Agent for Turbulence Chamber
Implements automated fan-to-windflow sensor calibration
"""

import asyncio
import logging
import os
import json
import csv
from datetime import datetime
from typing import Optional, Dict, Callable, List
import numpy as np

from .config import CalibrationConfig, DEFAULT_CONFIG
from .models import (
    CalibrationSession,
    CalibrationStatus,
    WindflowCalibrationResult,
    CalibrationStepType
)
from .windflow_calibration import WindflowCalibrator
from .hotplate_calibration import HotplateCalibrator, HotplateCalibrationConfig
from .combined_calibration import CombinedCalibrator, CombinedCalibrationConfig, CombinedDataPoint

logger = logging.getLogger(__name__)

class CalibrationAgent:
    """Agent for fan-to-windflow sensor calibration"""
    
    def __init__(self, arduino_comm, config: Optional[CalibrationConfig] = None):
        """
        Initialize calibration agent
        
        Args:
            arduino_comm: Arduino communicator instance
            config: Calibration configuration (uses DEFAULT_CONFIG if None)
        """
        self.arduino_comm = arduino_comm
        self.config = config or DEFAULT_CONFIG
        
        # Session state
        self.current_session: Optional[CalibrationSession] = None
        self.is_running = False
        self.is_paused = False
        self.stop_requested = False
        
        # Callbacks for status updates
        self.status_callback: Optional[Callable] = None
        self.progress_callback: Optional[Callable] = None
        
        # Windflow calibrator (polynomial degree 1 for linear fit)
        self.windflow_calibrator = WindflowCalibrator(polynomial_degree=1)
        self.windflow_calibration_result: Optional[WindflowCalibrationResult] = None

        # Hotplate calibrator
        self.hotplate_calibrator = HotplateCalibrator()
        self.hotplate_calibration_result: Optional = None

        # Combined calibrator
        self.combined_calibrator = CombinedCalibrator()
        self.combined_calibration_result: Optional = None

        # Ensure calibration data folder exists
        os.makedirs(self.config.calibration_data_folder, exist_ok=True)
    
    def set_status_callback(self, callback: Callable):
        """Set callback for status updates"""
        self.status_callback = callback
    
    def set_progress_callback(self, callback: Callable):
        """Set callback for progress updates"""
        self.progress_callback = callback
    
    async def start_windflow_calibration(self, fan_speed_step: int = 5, settling_time_ms: int = 1000, num_samples: int = 3) -> CalibrationSession:
        """
        Start fan-to-windflow sensor calibration
        
        Args:
            fan_speed_step: Step size for fan speed variation (default: 5 PWM units)
            settling_time_ms: Settling time in milliseconds after changing fan speed (default: 1000ms)
            num_samples: Number of samples to average per data point (default: 3)
            
        Returns:
            CalibrationSession object
        """
        if self.is_running:
            raise RuntimeError("Calibration already in progress")
        
        # Calculate number of speed steps per fan (starting from 15)
        num_speed_steps = len(range(15, 256, fan_speed_step)) + (1 if 255 % fan_speed_step != 0 else 0)
        
        # Create session
        session_id = f"windflow_calib_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        session = CalibrationSession(
            session_id=session_id,
            start_time=datetime.now(),
            status=CalibrationStatus.RUNNING,
            total_steps=num_speed_steps,  # Number of speed steps per fan
            total_speed_steps=num_speed_steps * 4,  # Total speed levels across all fans
            config={"fan_speed_step": fan_speed_step, "settling_time_ms": settling_time_ms, "num_samples": num_samples},
            notes=f"Fan-to-Windflow calibration with {fan_speed_step} PWM step (parallel execution)"
        )
        
        self.current_session = session
        self.is_running = True
        self.is_paused = False
        self.stop_requested = False
        
        logger.info(f"Starting windflow calibration session {session_id}")
        logger.info(f"Speed steps per fan: {num_speed_steps}, Total speed steps: {num_speed_steps * 4}")
        logger.info(f"Settling time: {settling_time_ms}ms, Samples per point: {num_samples}")
        
        # Start calibration in background
        asyncio.create_task(self._run_windflow_calibration(fan_speed_step, settling_time_ms, num_samples))
        
        return session

    async def start_hotplate_calibration(self,
                                        temp_min: float = 80.0,
                                        temp_max: float = 120.0,
                                        temp_step: float = 2.0,
                                        fan_speeds: List[int] = None,
                                        recording_duration: int = 900,
                                        sampling_interval: int = 10) -> CalibrationSession:
        """
        Start hot plate 4D calibration (temperature × fan speed)

        Args:
            temp_min: Minimum temperature in °C (default: 80.0)
            temp_max: Maximum temperature in °C (default: 120.0)
            temp_step: Temperature step in °C (default: 2.0)
            fan_speeds: List of fan speeds to test (default: [255, 191, 128, 64])
            recording_duration: Recording duration in seconds (default: 900)
            sampling_interval: Sampling interval in seconds (default: 10)

        Returns:
            CalibrationSession object
        """
        if self.is_running:
            raise RuntimeError("Calibration already in progress")

        if fan_speeds is None:
            fan_speeds = [255, 191, 128, 64]

        # Calculate total steps
        num_temp_steps = int((temp_max - temp_min) / temp_step) + 1
        total_steps = num_temp_steps * len(fan_speeds)

        # Create session
        session_id = f"hotplate_4d_calib_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        session = CalibrationSession(
            session_id=session_id,
            start_time=datetime.now(),
            status=CalibrationStatus.RUNNING,
            total_steps=total_steps,
            total_speed_steps=total_steps,
            config={
                "temp_min": temp_min,
                "temp_max": temp_max,
                "temp_step": temp_step,
                "fan_speeds": fan_speeds,
                "recording_duration": recording_duration,
                "sampling_interval": sampling_interval
            },
            notes=f"4D calibration: {len(fan_speeds)} fan speeds × {num_temp_steps} temperature steps"
        )

        self.current_session = session
        self.is_running = True
        self.is_paused = False
        self.stop_requested = False

        logger.info(f"Starting hot plate 4D calibration session {session_id}")
        logger.info(f"Total steps: {total_steps} ({len(fan_speeds)} fan speeds × {num_temp_steps} temperatures)")

        # Start calibration in background
        asyncio.create_task(self._run_hotplate_calibration(
            temp_min, temp_max, temp_step, fan_speeds, recording_duration, sampling_interval
        ))

        return session

    async def start_combined_calibration(self,
                                        temp_min: float = 80.0,
                                        temp_max: float = 120.0,
                                        temp_step: float = 2.0,
                                        fan_speeds: List[int] = None,
                                        recording_duration: int = 900,
                                        sampling_interval: int = 10) -> CalibrationSession:
        """
        Start combined hot plate and fan calibration

        Args:
            temp_min: Minimum temperature in °C (default: 80.0)
            temp_max: Maximum temperature in °C (default: 120.0)
            temp_step: Temperature step in °C (default: 2.0)
            fan_speeds: List of fan speeds to test (default: [255, 191, 128, 64])
            recording_duration: Recording duration in seconds (default: 900)
            sampling_interval: Sampling interval in seconds (default: 10)

        Returns:
            CalibrationSession object
        """
        if self.is_running:
            raise RuntimeError("Calibration already in progress")

        if fan_speeds is None:
            fan_speeds = [255, 191, 128, 64]

        # Calculate total steps
        num_temp_steps = int((temp_max - temp_min) / temp_step) + 1
        total_steps = num_temp_steps * len(fan_speeds)

        # Create session
        session_id = f"combined_calib_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        session = CalibrationSession(
            session_id=session_id,
            start_time=datetime.now(),
            status=CalibrationStatus.RUNNING,
            total_steps=total_steps,
            total_speed_steps=total_steps,
            config={
                "temp_min": temp_min,
                "temp_max": temp_max,
                "temp_step": temp_step,
                "fan_speeds": fan_speeds,
                "recording_duration": recording_duration,
                "sampling_interval": sampling_interval
            },
            notes=f"Combined calibration: {len(fan_speeds)} fan speeds × {num_temp_steps} temperature steps"
        )

        self.current_session = session
        self.is_running = True
        self.is_paused = False
        self.stop_requested = False

        logger.info(f"Starting combined calibration session {session_id}")
        logger.info(f"Total steps: {total_steps} ({len(fan_speeds)} fan speeds × {num_temp_steps} temperatures)")

        # Start calibration in background
        asyncio.create_task(self._run_combined_calibration(
            temp_min, temp_max, temp_step, fan_speeds, recording_duration, sampling_interval
        ))

        return session
    
        
    async def _run_windflow_calibration(self, fan_speed_step: int = 5, settling_time_ms: int = 1000, num_samples: int = 3):
        """Main windflow calibration loop - sets all fans to same speed and reads all sensors"""
        try:
            # Capture ambient conditions at start
            ambient_temp = None
            ambient_pressure = None
            ambient_humidity = None
            try:
                response = await self.arduino_comm.get_status()
                if response.status == "ok" and response.data:
                    # Get ambient temperature from BME280 sensor
                    if response.data.temperature_bmp and len(response.data.temperature_bmp) > 0:
                        ambient_temp = response.data.temperature_bmp[0]
                    # Get pressure from BME280 sensor
                    if response.data.pressure and len(response.data.pressure) > 0:
                        ambient_pressure = response.data.pressure[0]
                    # Get humidity from DHT22 sensor
                    if response.data.humidity and len(response.data.humidity) > 0:
                        ambient_humidity = response.data.humidity[0]
                    logger.info(f"Ambient conditions: {ambient_temp}°C, {ambient_pressure} hPa, {ambient_humidity}% RH")
            except Exception as e:
                logger.warning(f"Could not capture ambient conditions: {e}")
            
            # Calibrate all fans together - set same speed for all, read all sensors
            logger.info("Starting parallel calibration - setting all fans to same speed levels...")
            
            # Generate fan speed steps (15, 15+step, 15+2*step, ..., 255)
            fan_speeds = list(range(15, 256, fan_speed_step))
            if fan_speeds[-1] != 255:
                fan_speeds.append(255)
            
            logger.info(f"Testing {len(fan_speeds)} speed levels for all 4 fans simultaneously")
            
            # Initialize data storage for all fans
            fan_data = [[] for _ in range(4)]
            
            # Convert settling time to seconds
            settling_time_sec = settling_time_ms / 1000.0
            
            # Create session folder for incremental saving
            session_folder = os.path.join(
                self.config.calibration_data_folder,
                self.current_session.session_id
            )
            os.makedirs(session_folder, exist_ok=True)
            
            # Save session metadata
            self._save_session_metadata(session_folder)
            
            for idx, fan_speed in enumerate(fan_speeds):
                if self.stop_requested:
                    break
                
                # Update progress
                self.current_session.current_speed_step = idx + 1
                self.current_session.current_step = idx + 1
                self.current_session.current_fan_speed = fan_speed
                
                # Set all fans to the same speed
                for fan_id in range(4):
                    await self.arduino_comm.set_fan_speed(fan_id, fan_speed)
                
                # Wait for stabilization
                await asyncio.sleep(settling_time_sec)
                
                # Record multiple readings for all sensors
                all_flow_readings = [[] for _ in range(4)]  # Store readings for each sensor
                for _ in range(num_samples):
                    response = await self.arduino_comm.get_status()
                    if response.status == "ok" and response.data:
                        flow_rates = response.data.flow_rates
                        for sensor_id in range(min(4, len(flow_rates))):
                            all_flow_readings[sensor_id].append(flow_rates[sensor_id])
                    #await asyncio.sleep(0.2)
                
                # Calculate averages for each sensor
                avg_flows = []
                for sensor_id, readings in enumerate(all_flow_readings):
                    avg_flow = np.mean(readings) if readings else 0.0
                    avg_flows.append(avg_flow)
                    fan_data[sensor_id].append((fan_speed, avg_flow))
                    logger.debug(f"Sensor {sensor_id} @ {fan_speed} PWM → Flow: {avg_flow:.3f}")
                
                # Update session with all flow rates
                self.current_session = self.current_session.model_copy(update={
                    "current_flow_rates": avg_flows
                })
                
                # Save incremental data after each step
                self._save_incremental_data(session_folder, fan_speed, avg_flows, all_flow_readings)
                
                # Call status callback
                if self.status_callback:
                    self.status_callback(self.current_session)
            
            # Update current step to indicate all steps completed
            self.current_session.current_step = self.current_session.total_steps
            
            if not self.stop_requested:
                # Fit polynomials
                logger.info("Fitting polynomial curves for all fans...")
                calibration_data = [(fan_id, data) for fan_id, data in enumerate(fan_data)]
                self.windflow_calibration_result = self.windflow_calibrator.calibrate_all_fans(
                    calibration_data,
                    ambient_temperature=ambient_temp,
                    ambient_pressure=ambient_pressure,
                    ambient_humidity=ambient_humidity
                )
                
                # Save results to session folder
                self._save_windflow_calibration(session_folder)
                
                self.current_session.status = CalibrationStatus.COMPLETED
                self.current_session.end_time = datetime.now()
                logger.info("Windflow calibration completed successfully")
                
                # Save final session status
                self._save_session_metadata(session_folder)
            else:
                self.current_session.status = CalibrationStatus.FAILED
                self.current_session.error_message = "Calibration stopped"
                self.current_session.end_time = datetime.now()
                
                # Save final session status even if stopped
                self._save_session_metadata(session_folder)
        
        except Exception as e:
            logger.error(f"Calibration error: {e}")
            self.current_session.status = CalibrationStatus.FAILED
            self.current_session.error_message = str(e)
            self.current_session.end_time = datetime.now()
            
            # Save final session status on error
            if 'session_folder' in locals():
                self._save_session_metadata(session_folder)
        
        finally:
            self.is_running = False
            await self._reset_hardware()
            
            # Final status update
            if self.status_callback:
                self.status_callback(self.current_session)

    async def _run_hotplate_calibration(self,
                                       temp_min: float = 80.0,
                                       temp_max: float = 120.0,
                                       temp_step: float = 2.0,
                                       fan_speeds: List[int] = None,
                                       recording_duration: int = 900,
                                       sampling_interval: int = 10):
        """Main hot plate 4D calibration loop - nested loops: fan speeds × temperatures"""
        try:
            if fan_speeds is None:
                fan_speeds = [255, 191, 128, 64]

            # Capture ambient conditions at start
            ambient_temp = None
            ambient_pressure = None
            ambient_humidity = None
            try:
                response = await self.arduino_comm.get_status()
                if response.status == "ok" and response.data:
                    if response.data.temperature_bmp and len(response.data.temperature_bmp) > 0:
                        ambient_temp = response.data.temperature_bmp[0]
                    if response.data.pressure and len(response.data.pressure) > 0:
                        ambient_pressure = response.data.pressure[0]
                    if response.data.humidity and len(response.data.humidity) > 0:
                        ambient_humidity = response.data.humidity[0]
                    logger.info(f"Ambient conditions: {ambient_temp}°C, {ambient_pressure} hPa, {ambient_humidity}% RH")
            except Exception as e:
                logger.warning(f"Could not capture ambient conditions: {e}")

            # Create session folder
            session_folder = os.path.join(
                self.config.calibration_data_folder,
                self.current_session.session_id
            )
            os.makedirs(session_folder, exist_ok=True)

            # Save session metadata
            self._save_session_metadata(session_folder)

            # Generate temperature steps
            temp_steps = []
            current_temp = temp_min
            while current_temp <= temp_max:
                temp_steps.append(current_temp)
                current_temp += temp_step

            logger.info(f"Testing {len(fan_speeds)} fan speeds × {len(temp_steps)} temperature steps")

            # Initialize config
            config = CombinedCalibrationConfig(
                temp_min=temp_min,
                temp_max=temp_max,
                temp_step=temp_step,
                fan_speeds=fan_speeds,
                recording_duration=recording_duration,
                sampling_interval=sampling_interval
            )

            # Collect all data points
            all_data_points = []

            step_count = 0
            for fan_speed in fan_speeds:
                if self.stop_requested:
                    break

                logger.info(f"Setting all fans to {fan_speed} PWM")
                for fan_id in range(4):
                    await self.arduino_comm.set_fan_speed(fan_id, fan_speed)
                await asyncio.sleep(2)  # Wait for fans to stabilize

                for target_temp in temp_steps:
                    if self.stop_requested:
                        break

                    step_count += 1
                    self.current_session.current_step = step_count
                    self.current_session.current_speed_step = step_count

                    logger.info(f"Step {step_count}: Fan {fan_speed} PWM, Hot plates to {target_temp}°C")

                    # Set hot plate temperatures
                    for hotplate_id in [0, 1]:
                        await self.arduino_comm.set_temperature(hotplate_id, target_temp)
                        await asyncio.sleep(0.5)

                    # Wait for heating
                    logger.info("Waiting for temperature stabilization...")
                    await asyncio.sleep(60)

                    # Record data
                    start_time = datetime.now()
                    end_time = start_time.timestamp() + recording_duration

                    logger.info(f"Recording data for {recording_duration} seconds at {sampling_interval}s intervals")

                    while datetime.now().timestamp() < end_time and not self.stop_requested:
                        response = await self.arduino_comm.get_status()

                        if response.status == "ok" and response.data:
                            timestamp = datetime.now().timestamp() - start_time.timestamp()

                            # Get sensor temperatures
                            sensor_temps = response.data.temperatures if response.data.temperatures else []

                            # Calculate chamber temperature average (sensors 1, 3, 5, 7)
                            relevant_sensors = [0, 2, 4, 6]  # 0-indexed for sensors 1, 3, 5, 7
                            chamber_temps = [sensor_temps[i] for i in relevant_sensors if i < len(sensor_temps)]
                            chamber_temp_avg = np.mean(chamber_temps) if chamber_temps else 0.0

                            # Calculate Cn² (placeholder - would use optical data)
                            cn2_value = 0.0

                            # Create data point
                            data_point = CombinedDataPoint(
                                hotplate_temp=target_temp,
                                fan_speed=fan_speed,
                                chamber_temp_avg=float(chamber_temp_avg),
                                cn2_value=cn2_value,
                                sensor_temps={
                                    'sensor_1': float(sensor_temps[0]) if 0 < len(sensor_temps) else 0.0,
                                    'sensor_3': float(sensor_temps[2]) if 2 < len(sensor_temps) else 0.0,
                                    'sensor_5': float(sensor_temps[4]) if 4 < len(sensor_temps) else 0.0,
                                    'sensor_7': float(sensor_temps[6]) if 6 < len(sensor_temps) else 0.0,
                                },
                                timestamp=timestamp
                            )
                            all_data_points.append(data_point)

                        await asyncio.sleep(sampling_interval)

                    logger.info(f"Completed recording for Fan {fan_speed} PWM @ {target_temp}°C")

                    # Save incremental data
                    self._save_combined_incremental_data(session_folder, all_data_points)

            if not self.stop_requested:
                # Build lookup table
                logger.info("Building 4D lookup table...")
                lookup_table = self.combined_calibrator.build_lookup_table(all_data_points, config)

                # Create calibration result
                from .combined_calibration import CombinedCalibrationResult
                self.combined_calibration_result = CombinedCalibrationResult(
                    calibration_id=self.current_session.session_id,
                    timestamp=datetime.now(),
                    config=config,
                    lookup_table=lookup_table,
                    ambient_temperature=ambient_temp,
                    ambient_pressure=ambient_pressure,
                    ambient_humidity=ambient_humidity
                )

                # Save results
                self._save_combined_calibration(session_folder)

                self.current_session.status = CalibrationStatus.COMPLETED
                self.current_session.end_time = datetime.now()
                logger.info("Hot plate 4D calibration completed successfully")

                self._save_session_metadata(session_folder)
            else:
                self.current_session.status = CalibrationStatus.FAILED
                self.current_session.error_message = "Calibration stopped"
                self.current_session.end_time = datetime.now()
                self._save_session_metadata(session_folder)

        except Exception as e:
            logger.error(f"Hot plate 4D calibration error: {e}")
            self.current_session.status = CalibrationStatus.FAILED
            self.current_session.error_message = str(e)
            self.current_session.end_time = datetime.now()

            if 'session_folder' in locals():
                self._save_session_metadata(session_folder)

        finally:
            self.is_running = False
            await self._reset_hardware()

            if self.status_callback:
                self.status_callback(self.current_session)

    def _save_hotplate_incremental_data(self, session_folder: str, target_temp: float, hotplate_data: dict):
        """Save incremental hot plate calibration data to CSV"""
        try:
            csv_file = os.path.join(session_folder, "hotplate_calibration_data.csv")
            file_exists = os.path.exists(csv_file)

            with open(csv_file, 'a', newline='') as f:
                writer = csv.writer(f)

                if not file_exists:
                    header = ["timestamp", "target_temp", "hotplate_id", "hotplate_temp"]
                    for i in range(12):  # 12 DS18B20 sensors
                        header.append(f"sensor_{i}")
                    writer.writerow(header)

                for hotplate_id, data_points in hotplate_data.items():
                    for timestamp, hotplate_temp, sensor_temps in data_points:
                        row = [timestamp, target_temp, hotplate_id, hotplate_temp]
                        row.extend(sensor_temps[:12])  # Limit to 12 sensors
                        writer.writerow(row)

            logger.debug(f"Saved incremental data for {target_temp}°C")
        except Exception as e:
            logger.error(f"Error saving incremental data: {e}")

    def _save_hotplate_calibration(self, session_folder: str):
        """Save hot plate calibration results"""
        if not self.hotplate_calibration_result:
            return

        try:
            # Save to session folder
            filepath = os.path.join(session_folder, "hotplate_calibration.json")
            self.hotplate_calibrator.export_calibration(filepath)
            logger.info(f"Hot plate calibration saved to session: {filepath}")

            # Also save to calibration_data folder root
            calib_folder_abs = os.path.abspath(self.config.calibration_data_folder)
            latest_filepath = os.path.join(calib_folder_abs, "hotplate_calibration.json")
            self.hotplate_calibrator.export_calibration(latest_filepath)
            logger.info(f"Hot plate calibration saved to calibration_data root: {latest_filepath}")

        except Exception as e:
            logger.error(f"Error saving hot plate calibration: {e}")

    async def _run_combined_calibration(self,
                                       temp_min: float = 80.0,
                                       temp_max: float = 120.0,
                                       temp_step: float = 2.0,
                                       fan_speeds: List[int] = None,
                                       recording_duration: int = 900,
                                       sampling_interval: int = 10):
        """Main combined calibration loop - nested loops: fan speeds × hot plate temps"""
        try:
            if fan_speeds is None:
                fan_speeds = [255, 191, 128, 64]

            # Capture ambient conditions at start
            ambient_temp = None
            ambient_pressure = None
            ambient_humidity = None
            try:
                response = await self.arduino_comm.get_status()
                if response.status == "ok" and response.data:
                    if response.data.temperature_bmp and len(response.data.temperature_bmp) > 0:
                        ambient_temp = response.data.temperature_bmp[0]
                    if response.data.pressure and len(response.data.pressure) > 0:
                        ambient_pressure = response.data.pressure[0]
                    if response.data.humidity and len(response.data.humidity) > 0:
                        ambient_humidity = response.data.humidity[0]
                    logger.info(f"Ambient conditions: {ambient_temp}°C, {ambient_pressure} hPa, {ambient_humidity}% RH")
            except Exception as e:
                logger.warning(f"Could not capture ambient conditions: {e}")

            # Create session folder
            session_folder = os.path.join(
                self.config.calibration_data_folder,
                self.current_session.session_id
            )
            os.makedirs(session_folder, exist_ok=True)

            # Save session metadata
            self._save_session_metadata(session_folder)

            # Generate temperature steps
            temp_steps = []
            current_temp = temp_min
            while current_temp <= temp_max:
                temp_steps.append(current_temp)
                current_temp += temp_step

            logger.info(f"Testing {len(fan_speeds)} fan speeds × {len(temp_steps)} temperature steps")

            # Initialize config
            config = CombinedCalibrationConfig(
                temp_min=temp_min,
                temp_max=temp_max,
                temp_step=temp_step,
                fan_speeds=fan_speeds,
                recording_duration=recording_duration,
                sampling_interval=sampling_interval
            )

            # Collect all data points
            all_data_points = []

            step_count = 0
            for fan_speed in fan_speeds:
                if self.stop_requested:
                    break

                logger.info(f"Setting all fans to {fan_speed} PWM")
                for fan_id in range(4):
                    await self.arduino_comm.set_fan_speed(fan_id, fan_speed)
                await asyncio.sleep(2)  # Wait for fans to stabilize

                for target_temp in temp_steps:
                    if self.stop_requested:
                        break

                    step_count += 1
                    self.current_session.current_step = step_count
                    self.current_session.current_speed_step = step_count

                    logger.info(f"Step {step_count}: Fan {fan_speed} PWM, Hot plates to {target_temp}°C")

                    # Set hot plate temperatures
                    for hotplate_id in [0, 1]:
                        await self.arduino_comm.set_temperature(hotplate_id, target_temp)
                        await asyncio.sleep(0.5)

                    # Wait for heating
                    logger.info("Waiting for temperature stabilization...")
                    await asyncio.sleep(60)

                    # Record data
                    start_time = datetime.now()
                    end_time = start_time.timestamp() + recording_duration

                    logger.info(f"Recording data for {recording_duration} seconds at {sampling_interval}s intervals")

                    while datetime.now().timestamp() < end_time and not self.stop_requested:
                        response = await self.arduino_comm.get_status()

                        if response.status == "ok" and response.data:
                            timestamp = datetime.now().timestamp() - start_time.timestamp()

                            # Get sensor temperatures
                            sensor_temps = response.data.temperatures if response.data.temperatures else []

                            # Calculate chamber temperature average (sensors 1, 3, 5, 7)
                            relevant_sensors = [0, 2, 4, 6]  # 0-indexed for sensors 1, 3, 5, 7
                            chamber_temps = [sensor_temps[i] for i in relevant_sensors if i < len(sensor_temps)]
                            chamber_temp_avg = np.mean(chamber_temps) if chamber_temps else 0.0

                            # Calculate Cn² (simplified - use thermal formula)
                            # This would normally use the optical CN² calculation
                            cn2_value = 0.0  # Placeholder - would be calculated from optical data

                            # Create data point
                            data_point = CombinedDataPoint(
                                hotplate_temp=target_temp,
                                fan_speed=fan_speed,
                                chamber_temp_avg=float(chamber_temp_avg),
                                cn2_value=cn2_value,
                                sensor_temps={
                                    'sensor_1': float(sensor_temps[0]) if 0 < len(sensor_temps) else 0.0,
                                    'sensor_3': float(sensor_temps[2]) if 2 < len(sensor_temps) else 0.0,
                                    'sensor_5': float(sensor_temps[4]) if 4 < len(sensor_temps) else 0.0,
                                    'sensor_7': float(sensor_temps[6]) if 6 < len(sensor_temps) else 0.0,
                                },
                                timestamp=timestamp
                            )
                            all_data_points.append(data_point)

                        await asyncio.sleep(sampling_interval)

                    logger.info(f"Completed recording for Fan {fan_speed} PWM @ {target_temp}°C")

                    # Save incremental data
                    self._save_combined_incremental_data(session_folder, all_data_points)

            if not self.stop_requested:
                # Build lookup table
                logger.info("Building 4D lookup table...")
                lookup_table = self.combined_calibrator.build_lookup_table(all_data_points, config)

                # Create calibration result
                from .combined_calibration import CombinedCalibrationResult
                self.combined_calibration_result = CombinedCalibrationResult(
                    calibration_id=self.current_session.session_id,
                    timestamp=datetime.now(),
                    config=config,
                    lookup_table=lookup_table,
                    ambient_temperature=ambient_temp,
                    ambient_pressure=ambient_pressure,
                    ambient_humidity=ambient_humidity
                )

                # Save results
                self._save_combined_calibration(session_folder)

                self.current_session.status = CalibrationStatus.COMPLETED
                self.current_session.end_time = datetime.now()
                logger.info("Combined calibration completed successfully")

                self._save_session_metadata(session_folder)
            else:
                self.current_session.status = CalibrationStatus.FAILED
                self.current_session.error_message = "Calibration stopped"
                self.current_session.end_time = datetime.now()
                self._save_session_metadata(session_folder)

        except Exception as e:
            logger.error(f"Combined calibration error: {e}")
            self.current_session.status = CalibrationStatus.FAILED
            self.current_session.error_message = str(e)
            self.current_session.end_time = datetime.now()

            if 'session_folder' in locals():
                self._save_session_metadata(session_folder)

        finally:
            self.is_running = False
            await self._reset_hardware()

            if self.status_callback:
                self.status_callback(self.current_session)

    def _save_combined_incremental_data(self, session_folder: str, data_points: List):
        """Save incremental combined calibration data to CSV"""
        try:
            csv_file = os.path.join(session_folder, "combined_calibration_data.csv")
            file_exists = os.path.exists(csv_file)

            with open(csv_file, 'a', newline='') as f:
                writer = csv.writer(f)

                if not file_exists:
                    header = ["timestamp", "hotplate_temp", "fan_speed", "chamber_temp_avg", "cn2_value"]
                    for sensor in ['sensor_1', 'sensor_3', 'sensor_5', 'sensor_7']:
                        header.append(sensor)
                    writer.writerow(header)

                for dp in data_points:
                    row = [dp.timestamp, dp.hotplate_temp, dp.fan_speed, dp.chamber_temp_avg, dp.cn2_value]
                    row.extend([dp.sensor_temps[sensor] for sensor in ['sensor_1', 'sensor_3', 'sensor_5', 'sensor_7']])
                    writer.writerow(row)

            logger.debug(f"Saved incremental combined calibration data")
        except Exception as e:
            logger.error(f"Error saving incremental combined data: {e}")

    def _save_combined_calibration(self, session_folder: str):
        """Save combined calibration results"""
        if not self.combined_calibration_result:
            return

        try:
            # Save to session folder
            filepath = os.path.join(session_folder, "combined_calibration.json")
            self.combined_calibrator.export_calibration(filepath)
            logger.info(f"Combined calibration saved to session: {filepath}")

            # Also save to calibration_data folder root
            calib_folder_abs = os.path.abspath(self.config.calibration_data_folder)
            latest_filepath = os.path.join(calib_folder_abs, "combined_calibration.json")
            self.combined_calibrator.export_calibration(latest_filepath)
            logger.info(f"Combined calibration saved to calibration_data root: {latest_filepath}")

        except Exception as e:
            logger.error(f"Error saving combined calibration: {e}")
    
    def _save_session_metadata(self, session_folder: str):
        """Save session metadata to file"""
        try:
            metadata_file = os.path.join(session_folder, "session_metadata.json")
            with open(metadata_file, 'w') as f:
                json.dump(self.current_session.model_dump(mode='json'), f, indent=2)
            logger.info(f"Session metadata saved to {metadata_file}")
        except Exception as e:
            logger.error(f"Error saving session metadata: {e}")
    
    def _save_incremental_data(self, session_folder: str, fan_speed: int, avg_flows: List[float], all_readings: List[List[float]]):
        """Save incremental data for a single speed step"""
        try:
            step_data = {
                "fan_speed": fan_speed,
                "timestamp": datetime.now().isoformat(),
                "avg_flow_rates": avg_flows,
                "raw_readings": all_readings
            }
            
            # Append to CSV file
            csv_file = os.path.join(session_folder, "calibration_data.csv")
            file_exists = os.path.exists(csv_file)
            
            with open(csv_file, 'a', newline='') as f:
                writer = csv.writer(f)
                
                # Write header if file doesn't exist
                if not file_exists:
                    header = ["timestamp", "fan_speed", "sensor_0_avg", "sensor_1_avg", "sensor_2_avg", "sensor_3_avg"]
                    writer.writerow(header)
                
                # Write data row
                row = [datetime.now().isoformat(), fan_speed] + avg_flows
                writer.writerow(row)
            
            logger.debug(f"Saved incremental data for fan_speed={fan_speed}")
            
        except Exception as e:
            logger.error(f"Error saving incremental data: {e}")
    
    def _save_windflow_calibration(self, session_folder: str):
        """Save windflow calibration results to session-specific folder"""
        if not self.windflow_calibration_result:
            return

        try:
            # Save to session folder
            filepath = os.path.join(session_folder, "windflow_polynomials.json")
            self.windflow_calibrator.export_polynomials(filepath)
            logger.info(f"Windflow calibration saved to session: {filepath}")

            # Also save to calibration_data folder root (latest)
            calib_folder_abs = os.path.abspath(self.config.calibration_data_folder)
            latest_filepath = os.path.join(calib_folder_abs, "windflow_polynomials.json")
            self.windflow_calibrator.export_polynomials(latest_filepath)
            logger.info(f"Windflow calibration saved to calibration_data root: {latest_filepath}")

            # Copy session metadata to root
            session_metadata_src = os.path.join(session_folder, "session_metadata.json")
            session_metadata_dst = os.path.join(calib_folder_abs, "session_metadata.json")
            if os.path.exists(session_metadata_src):
                import shutil
                shutil.copy2(session_metadata_src, session_metadata_dst)
                logger.info(f"Session metadata copied to calibration_data root: {session_metadata_dst}")

            # Copy calibration CSV to root
            csv_src = os.path.join(session_folder, "calibration_data.csv")
            csv_dst = os.path.join(calib_folder_abs, "calibration_data.csv")
            if os.path.exists(csv_src):
                import shutil
                shutil.copy2(csv_src, csv_dst)
                logger.info(f"Calibration CSV copied to calibration_data root: {csv_dst}")

        except Exception as e:
            logger.error(f"Error saving windflow calibration: {e}")
     
        
    async def _reset_hardware(self):
        """Reset hardware to safe state"""
        try:
            # Turn off hot plates
            await self.arduino_comm.toggle_hot_plate(0, False)
            await self.arduino_comm.toggle_hot_plate(1, False)
            
            # Set fans to maximum
            for fan_id in range(4):
                await self.arduino_comm.set_fan_speed(fan_id, 255)
            
            logger.info("Hardware reset to safe state")
        except Exception as e:
            logger.error(f"Error resetting hardware: {e}")
    
        
    def pause_calibration(self):
        """Pause current calibration"""
        if self.is_running:
            self.is_paused = True
            self.current_session.status = CalibrationStatus.PAUSED
            logger.info("Calibration paused")
    
    def resume_calibration(self):
        """Resume paused calibration"""
        if self.is_running and self.is_paused:
            self.is_paused = False
            self.current_session.status = CalibrationStatus.RUNNING
            logger.info("Calibration resumed")
    
    def stop_calibration(self):
        """Stop current calibration"""
        if self.is_running:
            self.stop_requested = True
            logger.info("Calibration stop requested")
    
    def get_session_status(self) -> Optional[CalibrationSession]:
        """Get current calibration session status"""
        return self.current_session
    
    def get_latest_lookup_table(self) -> Optional[Dict]:
        """Get the latest lookup table from completed calibration"""
        if self.current_session and self.current_session.lookup_table:
            return self.current_session.lookup_table
        return None
    
    def get_windflow_calibration_result(self) -> Optional[WindflowCalibrationResult]:
        """Get the latest windflow polynomial calibration result"""
        return self.windflow_calibration_result
