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
from utils import get_calibration_data_folder
from csv_utils import init_csv_file

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
        
        # Session persistence
        calibration_data_folder = get_calibration_data_folder()
        self.session_file = os.path.join(calibration_data_folder, "current_session.json")
        
        # Try to recover existing session on startup
        self._recover_session()
        self.hotplate_calibration_result: Optional[HotplateCalibrationResult] = None

        # Combined calibrator
        self.combined_calibrator = CombinedCalibrator()
        self.combined_calibration_result: Optional[CombinedCalibrationResult] = None

        # Ensure calibration data folder exists
        os.makedirs(calibration_data_folder, exist_ok=True)
        
        # Store calibration data folder for use in other methods
        self.calibration_data_folder = calibration_data_folder
    
    def _save_session(self):
        """Save current session state to file"""
        if self.current_session:
            try:
                session_data = {
                    "session": self.current_session.dict(),
                    "is_running": self.is_running,
                    "is_paused": self.is_paused,
                    "stop_requested": self.stop_requested,
                    "calibration_type": self._get_calibration_type(),
                    "timestamp": datetime.now().isoformat()
                }
                with open(self.session_file, 'w') as f:
                    json.dump(session_data, f, indent=2, default=str)
                logger.info(f"Session saved to {self.session_file}")
            except Exception as e:
                logger.error(f"Failed to save session: {e}")
    
    def _recover_session(self):
        """Recover session state from file"""
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, 'r') as f:
                    session_data = json.load(f)
                
                # Check if session is still valid (not too old)
                session_time = datetime.fromisoformat(session_data.get("timestamp", ""))
                if (datetime.now() - session_time).total_seconds() > 86400:  # 24 hours
                    logger.info("Session file is too old, ignoring")
                    os.remove(self.session_file)
                    return
                
                # Recover session
                session_dict = session_data.get("session", {})
                if session_dict:
                    self.current_session = CalibrationSession(**session_dict)
                    self.is_running = session_data.get("is_running", False)
                    self.is_paused = session_data.get("is_paused", False)
                    self.stop_requested = session_data.get("stop_requested", False)
                    
                    # If session was running, mark it as paused (server restart)
                    if self.is_running:
                        self.is_running = False
                        self.is_paused = True
                        self.current_session.status = CalibrationStatus.PAUSED
                        self.current_session.error_message = "Server restarted - session paused. Can be resumed."
                        self._save_session()  # Update with paused status
                    
                    logger.info(f"Session recovered: {self.current_session.session_id}")
            else:
                logger.info("No existing session file found")
        except Exception as e:
            logger.error(f"Failed to recover session: {e}")
            # Remove corrupted session file
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
    
    def _get_calibration_type(self) -> str:
        """Determine the type of current calibration"""
        if not self.current_session:
            return "none"
        
        session_id = self.current_session.session_id.lower()
        if "pid" in session_id:
            return "pid"
        elif  "4d" in session_id:
            return "4d"
        elif "windflow" in session_id:
            return "windflow"
        else:
            return "turbulence"
    
    def get_current_session_info(self) -> Optional[Dict]:
        """Get information about the current session"""
        if not self.current_session:
            return None
        
        return {
            "session_id": self.current_session.session_id,
            "status": self.current_session.status.value,
            "calibration_type": self._get_calibration_type(),
            "current_step": self.current_session.current_step,
            "total_steps": self.current_session.total_steps,
            "progress": self.current_session.get_progress(),
            "start_time": self.current_session.start_time.isoformat() if self.current_session.start_time else None,
            "is_running": self.is_running,
            "current_temperature": self.current_session.current_temperature,
            "current_fan_speed": self.current_session.current_fan_speed,
            "phase": self.current_session.phase,
            "phase_details": self.current_session.phase_details,
            "error_message": self.current_session.error_message
        }
    
    def clear_session(self):
        """Clear current session and remove session file"""
        self.current_session = None
        self.is_running = False
        self.is_paused = False
        self.stop_requested = False
        
        try:
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
                logger.info("Session file removed")
        except Exception as e:
            logger.error(f"Failed to remove session file: {e}")
    
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
        
        # Save session state
        self._save_session()
        
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

        # Save session state
        self._save_session()

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
                sensor_data = await self._capture_sensor_data()
                if sensor_data:
                    # Get ambient temperature from BME280 sensor
                    if sensor_data['temperature_bmp'] and len(sensor_data['temperature_bmp']) > 0:
                        ambient_temp = sensor_data['temperature_bmp'][0]
                    # Get pressure from BME280 sensor
                    if sensor_data['pressure'] and len(sensor_data['pressure']) > 0:
                        ambient_pressure = sensor_data['pressure'][0]
                    # Get humidity from DHT22 sensor
                    if sensor_data['humidity'] and len(sensor_data['humidity']) > 0:
                        ambient_humidity = sensor_data['humidity'][0]
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
            
            # Create session folder for metadata
            session_folder = os.path.join(
                self.calibration_data_folder,
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
                
                for sample_idx in range(num_samples):
                    sensor_data = await self._capture_sensor_data()
                    if sensor_data:
                        flow_rates = sensor_data['flow_rates']
                        for sensor_id in range(min(4, len(flow_rates))):
                            all_flow_readings[sensor_id].append(flow_rates[sensor_id])
                
                # Calculate averages for each sensor
                avg_flows = []
                for sensor_id, readings in enumerate(all_flow_readings):
                    avg_flow = np.mean(readings) if readings else 0.0
                    avg_flows.append(avg_flow)
                    fan_data[sensor_id].append((fan_speed, avg_flow))
                
                # Update session with all flow rates
                self.current_session = self.current_session.model_copy(update={
                    "current_flow_rates": avg_flows
                })
                
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
        """Main hot plate calibration loop following proper stages"""
        try:
            if fan_speeds is None:
                fan_speeds = [255, 191, 128, 64]

            # Capture ambient conditions at start
            ambient_temp = None
            ambient_pressure = None
            ambient_humidity = None
            try:
                sensor_data = await self._capture_sensor_data()
                if sensor_data:
                    if sensor_data['temperature_bmp'] and len(sensor_data['temperature_bmp']) > 0:
                        ambient_temp = sensor_data['temperature_bmp'][0]
                    if sensor_data['pressure'] and len(sensor_data['pressure']) > 0:
                        ambient_pressure = sensor_data['pressure'][0]
                    if sensor_data['humidity'] and len(sensor_data['humidity']) > 0:
                        ambient_humidity = sensor_data['humidity'][0]
                    logger.info(f"Ambient conditions: {ambient_temp}°C, {ambient_pressure} hPa, {ambient_humidity}% RH")
            except Exception as e:
                logger.warning(f"Could not capture ambient conditions: {e}")

            # Create session folder
            session_folder = os.path.join(
                self.calibration_data_folder,
                self.current_session.session_id
            )
            os.makedirs(session_folder, exist_ok=True)

            # Save session metadata
            self._save_session_metadata(session_folder)

            # Initialize CSV file for data capture
            csv_filepath = init_csv_file(session_folder, "hotplate")
            if not csv_filepath:
                logger.error("Failed to initialize CSV file, calibration will continue without data logging")

            # Generate temperature steps
            temp_steps = []
            current_temp = temp_min
            while current_temp <= temp_max:
                temp_steps.append(current_temp)
                current_temp += temp_step

            logger.info(f"Testing {len(fan_speeds)} fan speeds × {len(temp_steps)} temperature steps")

            # Calculate total data points
            total_data_points = len(fan_speeds) * len(temp_steps) * (recording_duration // sampling_interval)
            self.current_session.total_data_points = total_data_points
            logger.info(f"Total data points to capture: {total_data_points}")

            # Initialize config
            config = CombinedCalibrationConfig(
                temp_min=temp_min,
                temp_max=temp_max,
                temp_step=temp_step,
                fan_speeds=fan_speeds,
                recording_duration=recording_duration,
                sampling_interval=sampling_interval
            )
            self.current_session.config = config.dict()

            # Collect all data points
            all_data_points = []

            step_count = 0
            for fan_speed in fan_speeds:
                if self.stop_requested:
                    break

                # Stage 0: Stop all fans - set PWM to 0
                logger.info("Stage 0: Stopping all fans...")
                self.current_session.phase = "Stopping Fans"
                self.current_session.phase_details = "Setting all fans to 0 PWM"
                for fan_id in range(4):
                    await self.arduino_comm.set_fan_speed(fan_id, 0)
                await asyncio.sleep(2)

                for target_temp in temp_steps:
                    if self.stop_requested:
                        break

                    step_count += 1
                    self.current_session.current_step = step_count
                    self.current_session.current_speed_step = step_count
                    self.current_session.current_fan_speed = fan_speed
                    self.current_session.current_temperature = target_temp
                    
                    # Notify status callback at step start
                    if self.status_callback:
                        self.status_callback(self.current_session)

                    # Stage 1: Stabilize the hotplate surface temperature
                    logger.info(f"Step {step_count}: Stage 1 - Stabilizing hotplate to {target_temp}°C")
                    self.current_session.phase = "Stabilizing Hotplate"
                    self.current_session.phase_details = f"Setting hot plates to {target_temp}°C"

                    # Set hot plate temperatures
                    for hotplate_id in [0, 1]:
                        await self.arduino_comm.set_temperature(hotplate_id, target_temp)
                        await asyncio.sleep(0.5)
                    
                    # Notify status callback
                    if self.status_callback:
                        self.status_callback(self.current_session)

                    # Wait for stabilization
                    logger.info("Waiting for temperature stabilization (60 seconds)...")
                    await asyncio.sleep(60)

                    # Stage 2: Start the fans at desired value
                    logger.info(f"Stage 2: Starting fans at {fan_speed} PWM")
                    self.current_session.phase = "Starting Fans"
                    self.current_session.phase_details = f"Setting fans to {fan_speed} PWM"
                    for fan_id in range(4):
                        await self.arduino_comm.set_fan_speed(fan_id, fan_speed)
                    await asyncio.sleep(2)  # Wait for fans to stabilize
                    
                    # Notify status callback
                    if self.status_callback:
                        self.status_callback(self.current_session)

                    # Stage 3 & 4: Run background task and capture data
                    start_time = datetime.now()
                    end_time = start_time.timestamp() + recording_duration

                    logger.info(f"Stage 3&4: Recording data for {recording_duration} seconds at {sampling_interval}s intervals")
                    self.current_session.phase = "Recording"
                    self.current_session.phase_details = f"Recording data for {recording_duration}s at {sampling_interval}s intervals"

                    while datetime.now().timestamp() < end_time and not self.stop_requested:
                        sensor_data = await self._capture_sensor_data()

                        if sensor_data:
                            timestamp = datetime.now().timestamp() - start_time.timestamp()

                            # Get sensor temperatures
                            sensor_temps = sensor_data['temperatures']

                            # Update current temperature from first sensor
                            if sensor_temps and len(sensor_temps) > 0:
                                self.current_session.current_temperature = sensor_temps[0]

                            # Save session state periodically (every 30 seconds)
                            if int(timestamp) % 30 == 0:
                                self._save_session()

                            # Calculate chamber temperature average (sensors 1, 3, 5, 7)
                            relevant_sensors = [0, 2, 4, 6]  # 0-indexed for sensors 1, 3, 5, 7
                            chamber_temps = [sensor_temps[i] for i in relevant_sensors if i < len(sensor_temps)]
                            chamber_temp_avg = np.mean(chamber_temps) if chamber_temps else 0.0

                            # Calculate Cn² (placeholder - would use optical data)
                            cn2_value = 0.0

                            # Create data point and add to all_data_points
                            data_point = CombinedDataPoint(
                                timestamp=timestamp,
                                fan_speed=fan_speed,
                                target_temperature=target_temp,
                                chamber_temperature=chamber_temp_avg,
                                cn2_value=cn2_value,
                                sensor_temperatures=sensor_temps,
                                flow_rates=sensor_data.get('flow_rates', [])
                            )
                            all_data_points.append(data_point)

                            # Notify status callback more frequently for smooth progress updates
                            if self.status_callback:
                                self.status_callback(self.current_session)

                        await asyncio.sleep(sampling_interval)

                    logger.info(f"Completed recording for Fan {fan_speed} PWM @ {target_temp}°C")

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

            self._save_session_metadata(session_folder)

        finally:
            self.is_running = False
            await self._reset_hardware()

            if self.status_callback:
                self.status_callback(self.current_session)
    
    def _save_session_metadata(self, session_folder: str):
        """Save session metadata to file"""
        try:
            metadata_file = os.path.join(session_folder, "session_metadata.json")
            with open(metadata_file, 'w') as f:
                json.dump(self.current_session.model_dump(mode='json'), f, indent=2)
            logger.info(f"Session metadata saved to {metadata_file}")
        except Exception as e:
            logger.error(f"Error saving session metadata: {e}")
    
    async def _capture_sensor_data(self) -> Optional[Dict]:
        """Capture sensor data from Arduino"""
        try:
            status = await self.arduino_comm.get_status()
            if status:
                return {
                    'temperatures': status.get('temperatures', []),
                    'flow_rates': status.get('flow_rates', []),
                    'temperature_bmp': status.get('temperature_bmp', []),
                    'pressure': status.get('pressure', []),
                    'humidity': status.get('humidity', [])
                }
        except Exception as e:
            logger.error(f"Error capturing sensor data: {e}")
        return None
    
    def _save_combined_calibration(self, session_folder: str):
        """Save combined calibration result to file"""
        try:
            if self.combined_calibration_result:
                result_file = os.path.join(session_folder, "combined_calibration_result.json")
                with open(result_file, 'w') as f:
                    json.dump(self.combined_calibration_result.model_dump(mode='json'), f, indent=2)
                logger.info(f"Combined calibration result saved to {result_file}")
        except Exception as e:
            logger.error(f"Error saving combined calibration result: {e}")    
        
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
