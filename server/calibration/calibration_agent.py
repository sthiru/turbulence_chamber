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
import time
from datetime import datetime
from typing import Optional, List, Dict, Callable, Tuple
import numpy as np

from .config import CalibrationConfig, DEFAULT_CONFIG
from .models import (
    CalibrationSession, CalibrationStep, CalibrationDataPoint,
    CalibrationStatus, CalibrationStepType, CalibrationRequest,
    WindflowCalibrationResult
)
from .windflow_calibration import WindflowCalibrator

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
        
        # Windflow calibrator (polynomial degree 2 for quadratic fit)
        self.windflow_calibrator = WindflowCalibrator(polynomial_degree=2)
        self.windflow_calibration_result: Optional[WindflowCalibrationResult] = None
        
        # Ensure calibration data folder exists
        os.makedirs(self.config.calibration_data_folder, exist_ok=True)
    
    def set_status_callback(self, callback: Callable):
        """Set callback for status updates"""
        self.status_callback = callback
    
    def set_progress_callback(self, callback: Callable):
        """Set callback for progress updates"""
        self.progress_callback = callback
    
    async def start_windflow_calibration(self, fan_speed_step: int = 5) -> CalibrationSession:
        """
        Start fan-to-windflow sensor calibration
        
        Args:
            fan_speed_step: Step size for fan speed variation (default: 5 PWM units)
            
        Returns:
            CalibrationSession object
        """
        if self.is_running:
            raise RuntimeError("Calibration already in progress")
        
        # Create session
        session_id = f"windflow_calib_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        session = CalibrationSession(
            session_id=session_id,
            start_time=datetime.now(),
            status=CalibrationStatus.RUNNING,
            total_steps=4,  # 4 fans to calibrate
            config={"fan_speed_step": fan_speed_step},
            notes=f"Fan-to-Windflow calibration with {fan_speed_step} PWM step"
        )
        
        self.current_session = session
        self.is_running = True
        self.is_paused = False
        self.stop_requested = False
        
        logger.info(f"Starting windflow calibration session {session_id}")
        
        # Start calibration in background
        asyncio.create_task(self._run_windflow_calibration(fan_speed_step))
        
        return session
    
    def _update_config_from_request(self, request: CalibrationRequest) -> CalibrationConfig:
        """Update configuration from request parameters"""
        config = CalibrationConfig()
        
        if request.calibrate_fans is not None:
            config.calibrate_fans = request.calibrate_fans
        if request.calibrate_hotplates is not None:
            config.calibrate_hotplates = request.calibrate_hotplates
        if request.calibrate_combined is not None:
            config.calibrate_combined = request.calibrate_combined
        if request.run_pre_calibration is not None:
            config.run_pre_calibration = request.run_pre_calibration
        
        if request.fan_speed_min is not None:
            config.fan_speed_min = request.fan_speed_min
        if request.fan_speed_max is not None:
            config.fan_speed_max = request.fan_speed_max
        if request.fan_speed_step is not None:
            config.fan_speed_step = request.fan_speed_step
        
        if request.hotplate_temp_min is not None:
            config.hotplate_temp_min = request.hotplate_temp_min
        if request.hotplate_temp_max is not None:
            config.hotplate_temp_max = request.hotplate_temp_max
        if request.hotplate_temp_step is not None:
            config.hotplate_temp_step = request.hotplate_temp_step
        
        if request.stabilization_time is not None:
            config.stabilization_time = request.stabilization_time
        if request.measurement_duration is not None:
            config.measurement_duration = request.measurement_duration
        
        return config
    
    async def _run_windflow_calibration(self, fan_speed_step: int = 5):
        """Main windflow calibration loop"""
        try:
            calibration_data: List[Tuple[int, List[Tuple[int, float]]]] = []
            
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
            
            # Calibrate each fan
            for fan_id in range(4):
                if self.stop_requested:
                    break
                
                logger.info(f"Calibrating Fan {fan_id}...")
                self.current_session.current_step = fan_id + 1
                
                fan_data = await self._calibrate_single_fan(fan_id, fan_speed_step)
                calibration_data.append((fan_id, fan_data))
                
                # Update progress
                if self.progress_callback:
                    self.progress_callback((fan_id + 1) / 4 * 100)
            
            if not self.stop_requested:
                # Fit polynomials
                logger.info("Fitting polynomial curves for all fans...")
                self.windflow_calibration_result = self.windflow_calibrator.calibrate_all_fans(
                    calibration_data,
                    ambient_temperature=ambient_temp,
                    ambient_pressure=ambient_pressure,
                    ambient_humidity=ambient_humidity
                )
                
                # Save results
                self._save_windflow_calibration()
                
                self.current_session.status = CalibrationStatus.COMPLETED
                self.current_session.end_time = datetime.now()
                logger.info("Windflow calibration completed successfully")
            else:
                self.current_session.status = CalibrationStatus.FAILED
                self.current_session.error_message = "Stopped by user"
                self.current_session.end_time = datetime.now()
        
        except Exception as e:
            logger.error(f"Calibration error: {e}")
            self.current_session.status = CalibrationStatus.FAILED
            self.current_session.error_message = str(e)
            self.current_session.end_time = datetime.now()
        
        finally:
            self.is_running = False
            await self._reset_hardware()
            
            if self.status_callback:
                self.status_callback(self.current_session)
    
    async def _calibrate_single_fan(self, fan_id: int, fan_speed_step: int) -> List[Tuple[int, float]]:
        """
        Calibrate a single fan-to-windflow sensor pair
        
        Args:
            fan_id: Fan identifier (0-3)
            fan_speed_step: Step size for fan speed variation
            
        Returns:
            List of (fan_speed, flow_rate) tuples
        """
        fan_data = []
        
        # Generate fan speed steps (0, step, 2*step, ..., 255)
        fan_speeds = list(range(0, 256, fan_speed_step))
        if fan_speeds[-1] != 255:
            fan_speeds.append(255)
        
        logger.info(f"Fan {fan_id}: Testing {len(fan_speeds)} speed levels")
        
        for fan_speed in fan_speeds:
            if self.stop_requested:
                break
            
            # Set fan speed
            await self.arduino_comm.set_fan_speed(fan_id, fan_speed)
            
            # Wait for stabilization (2 seconds for windflow)
            await asyncio.sleep(2)
            
            # Record multiple readings for averaging
            flow_readings = []
            for _ in range(5):
                response = await self.arduino_comm.get_status()
                if response.status == "ok" and response.data:
                    flow_rates = response.data.flow_rates
                    if fan_id < len(flow_rates):
                        flow_readings.append(flow_rates[fan_id])
                await asyncio.sleep(0.2)
            
            # Calculate average flow rate
            if flow_readings:
                avg_flow = np.mean(flow_readings)
                fan_data.append((fan_speed, avg_flow))
                logger.debug(f"Fan {fan_id} @ {fan_speed} PWM → Flow: {avg_flow:.3f}")
        
        return fan_data
    
    def _save_windflow_calibration(self):
        """Save windflow calibration results to file"""
        if not self.windflow_calibration_result:
            return
        
        try:
            # Create timestamped filename
            calib_id = self.windflow_calibration_result.calibration_id
            
            # Save to calibration data folder
            filepath = os.path.join(
                self.config.calibration_data_folder,
                f"{calib_id}.json"
            )
            self.windflow_calibrator.export_polynomials(filepath)
            
            # Also save to root as latest
            latest_filepath = os.path.join(
                os.path.dirname(self.config.calibration_data_folder),
                "windflow_polynomials_latest.json"
            )
            self.windflow_calibrator.export_polynomials(latest_filepath)
            
            logger.info(f"Windflow calibration saved to {filepath}")
            
        except Exception as e:
            logger.error(f"Error saving windflow calibration: {e}")
    
    def _generate_calibration_steps(self, config: CalibrationConfig) -> List[CalibrationStep]:
        """Generate calibration steps based on configuration"""
        steps = []
        step_number = 0
        
        if config.calibrate_combined:
            # Combined calibration: vary both fans and hotplates
            fan_steps = config.get_fan_speed_steps()
            temp_steps = config.get_hotplate_temp_steps()
            
            for fan_speed in fan_steps:
                for temp in temp_steps:
                    for hotplate_id in range(2):  # 2 hot plates
                        step_number += 1
                        step = CalibrationStep(
                            step_type=CalibrationStepType.COMBINED_CALIBRATION,
                            step_number=step_number,
                            fan_speed=fan_speed,
                            hotplate_id=hotplate_id,
                            target_temperature=temp,
                            hotplate_state=True
                        )
                        steps.append(step)
        
        else:
            # Separate calibration
            if config.calibrate_fans:
                fan_steps = config.get_fan_speed_steps()
                for fan_speed in fan_steps:
                    step_number += 1
                    step = CalibrationStep(
                        step_type=CalibrationStepType.FAN_CALIBRATION,
                        step_number=step_number,
                        fan_speed=fan_speed,
                        hotplate_state=False
                    )
                    steps.append(step)
            
            if config.calibrate_hotplates:
                temp_steps = config.get_hotplate_temp_steps()
                for temp in temp_steps:
                    for hotplate_id in range(2):  # 2 hot plates
                        step_number += 1
                        step = CalibrationStep(
                            step_type=CalibrationStepType.HOTPLATE_CALIBRATION,
                            step_number=step_number,
                            hotplate_id=hotplate_id,
                            target_temperature=temp,
                            hotplate_state=True
                        )
                        steps.append(step)
        
        return steps
    
    async def _run_windflow_pre_calibration(self):
        """Run pre-calibration to establish fan-to-windflow polynomial relationships"""
        try:
            # Prepare calibration data for all 4 fan-windflow pairs
            calibration_data = []
            
            for fan_id in range(4):
                fan_data = []
                
                # Generate fan speed steps
                fan_steps = np.linspace(
                    self.config.fan_speed_min, 
                    self.config.fan_speed_max, 
                    self.config.pre_calibration_fan_steps
                ).astype(int)
                
                logger.info(f"Pre-calibrating Fan {fan_id} with {len(fan_steps)} speed steps...")
                
                for fan_speed in fan_steps:
                    if self.stop_requested:
                        break
                    
                    # Set fan speed
                    await self.arduino_comm.set_fan_speed(fan_id, fan_speed)
                    
                    # Wait for stabilization (shorter for windflow)
                    await asyncio.sleep(2)
                    
                    # Record multiple readings for accuracy
                    flow_readings = []
                    for _ in range(5):
                        response = await self.arduino_comm.get_status()
                        if response.status == "ok" and response.data:
                            flow_rates = response.data.flow_rates
                            if fan_id < len(flow_rates):
                                flow_readings.append(flow_rates[fan_id])
                        await asyncio.sleep(0.5)
                    
                    # Calculate average flow rate
                    if flow_readings:
                        avg_flow = np.mean(flow_readings)
                        fan_data.append((fan_speed, avg_flow))
                        logger.debug(f"Fan {fan_id} @ {fan_speed} PWM → Flow: {avg_flow:.2f}")
                
                calibration_data.append((fan_id, fan_data))
            
            if self.stop_requested:
                logger.warning("Pre-calibration stopped by user")
                return
            
            # Fit polynomials
            logger.info("Fitting polynomial curves...")
            self.windflow_calibration_result = self.windflow_calibrator.calibrate_all_fans(calibration_data)
            
            # Save polynomial coefficients
            self._save_windflow_polynomials()
            
            logger.info("Fan-to-windflow pre-calibration completed")
            
        except Exception as e:
            logger.error(f"Pre-calibration error: {e}")
            raise
    
    def _save_windflow_polynomials(self):
        """Save windflow polynomial coefficients to file"""
        if not self.windflow_calibration_result:
            return
        
        try:
            # Save to calibration data folder
            filepath = os.path.join(
                self.config.calibration_data_folder,
                f"windflow_polynomials_{self.windflow_calibration_result.calibration_id}.json"
            )
            self.windflow_calibrator.export_polynomials(filepath)
            
            # Also save to root as latest
            latest_filepath = os.path.join(
                os.path.dirname(self.config.calibration_data_folder),
                "windflow_polynomials.json"
            )
            self.windflow_calibrator.export_polynomials(latest_filepath)
            
            logger.info(f"Windflow polynomials saved to {filepath}")
            
        except Exception as e:
            logger.error(f"Error saving windflow polynomials: {e}")
    
    async def _run_calibration(self):
        """Main calibration loop"""
        try:
            # Run pre-calibration for fan-to-windflow polynomial fitting
            if self.config.run_pre_calibration:
                logger.info("Starting fan-to-windflow pre-calibration...")
                await self._run_windflow_pre_calibration()
            
            for step in self.current_session.steps:
                if self.stop_requested:
                    logger.info("Calibration stopped by user request")
                    self.current_session.status = CalibrationStatus.FAILED
                    self.current_session.error_message = "Stopped by user"
                    break
                
                while self.is_paused:
                    await asyncio.sleep(1)
                    if self.stop_requested:
                        break
                
                if self.stop_requested:
                    break
                
                # Execute step
                await self._execute_calibration_step(step)
                
                # Update progress
                self.current_session.current_step = step.step_number
                if self.progress_callback:
                    self.progress_callback(self.current_session.get_progress())
            
            # Generate lookup table if completed successfully
            if not self.stop_requested and not self.current_session.error_message:
                self.current_session.lookup_table = self._generate_lookup_table()
                self.current_session.status = CalibrationStatus.COMPLETED
                self.current_session.end_time = datetime.now()
                logger.info(f"Calibration completed successfully: {self.current_session.session_id}")
            else:
                self.current_session.status = CalibrationStatus.FAILED
                self.current_session.end_time = datetime.now()
            
            # Save session data
            self._save_calibration_data(self.current_session)
            
        except Exception as e:
            logger.error(f"Calibration error: {e}")
            self.current_session.status = CalibrationStatus.FAILED
            self.current_session.error_message = str(e)
            self.current_session.end_time = datetime.now()
        
        finally:
            self.is_running = False
            # Reset hardware to safe state
            await self._reset_hardware()
            
            if self.status_callback:
                self.status_callback(self.current_session)
    
    async def _execute_calibration_step(self, step: CalibrationStep):
        """Execute a single calibration step"""
        logger.info(f"Executing step {step.step_number}: {step.step_type}")
        step.status = CalibrationStatus.RUNNING
        step.start_time = datetime.now()
        
        try:
            # Set hardware state
            await self._set_hardware_state(step)
            
            # Wait for stabilization
            logger.info(f"Waiting {self.config.stabilization_time}s for stabilization...")
            await asyncio.sleep(self.config.stabilization_time)
            
            # Record stabilization time
            step.stabilization_time = self.config.stabilization_time
            
            # Record data points
            logger.info(f"Recording data for {self.config.measurement_duration}s...")
            await self._record_data_points(step)
            
            # Calculate statistics
            self._calculate_step_statistics(step)
            
            step.status = CalibrationStatus.COMPLETED
            step.end_time = datetime.now()
            
            logger.info(f"Step {step.step_number} completed")
            
        except Exception as e:
            logger.error(f"Step {step.step_number} failed: {e}")
            step.status = CalibrationStatus.FAILED
            step.error_message = str(e)
            step.end_time = datetime.now()
    
    async def _set_hardware_state(self, step: CalibrationStep):
        """Set hardware state for calibration step"""
        # Set fan speeds
        if step.fan_speed is not None:
            for fan_id in range(4):  # 4 fans
                await self.arduino_comm.set_fan_speed(fan_id, step.fan_speed)
                logger.debug(f"Set fan {fan_id} to speed {step.fan_speed}")
        
        # Set hot plate state and temperature
        if step.hotplate_id is not None and step.target_temperature is not None:
            # Set target temperature
            await self.arduino_comm.set_temperature(step.hotplate_id, step.target_temperature)
            
            # Toggle hot plate
            if step.hotplate_state:
                await self.arduino_comm.toggle_hot_plate(step.hotplate_id, True)
                logger.debug(f"Enabled hot plate {step.hotplate_id} at {step.target_temperature}°C")
            else:
                await self.arduino_comm.toggle_hot_plate(step.hotplate_id, False)
                logger.debug(f"Disabled hot plate {step.hotplate_id}")
    
    async def _record_data_points(self, step: CalibrationStep):
        """Record data points during measurement duration"""
        start_time = time.time()
        end_time = start_time + self.config.measurement_duration
        
        while time.time() < end_time and not self.stop_requested:
            try:
                # Get current status from Arduino
                response = await self.arduino_comm.get_status()
                
                if response.status == "ok" and response.data:
                    data = response.data.dict()
                    
                    # Create data point
                    data_point = CalibrationDataPoint(
                        timestamp=datetime.now(),
                        fan_speeds=data.get("fan_speeds", []),
                        hot_plate_states=data.get("hot_plate_states", []),
                        target_temperatures=data.get("target_temperatures", []),
                        temperatures=data.get("temperatures", []),
                        temperature_bmp=data.get("temperature_bmp", []),
                        pressure=data.get("pressure", []),
                        temperature_dht=data.get("temperature_dht", []),
                        humidity=data.get("humidity", []),
                        flow_rates=data.get("flow_rates", []),
                        cn2=None  # CN2 calculated separately if needed
                    )
                    
                    step.data_points.append(data_point)
                    
            except Exception as e:
                logger.warning(f"Error recording data point: {e}")
            
            # Wait for next sample
            await asyncio.sleep(self.config.sampling_interval)
    
    def _calculate_step_statistics(self, step: CalibrationStep):
        """Calculate statistics for calibration step"""
        if not step.data_points:
            return
        
        # Extract temperatures for each sensor
        temp_data = [[] for _ in range(12)]  # 12 DS18B20 sensors
        flow_data = [[] for _ in range(4)]  # 4 flow sensors
        cn2_data = []
        
        for dp in step.data_points:
            for i, temp in enumerate(dp.temperatures):
                if i < len(temp_data):
                    temp_data[i].append(temp)
            for i, flow in enumerate(dp.flow_rates):
                if i < len(flow_data):
                    flow_data[i].append(flow)
            if dp.cn2 is not None:
                cn2_data.append(dp.cn2)
        
        # Calculate averages and standard deviations
        step.avg_temperatures = [np.mean(temps) if temps else 0.0 for temps in temp_data]
        step.temperature_std = [np.std(temps) if temps else 0.0 for temps in temp_data]
        step.avg_flow_rates = [np.mean(flows) if flows else 0.0 for flows in flow_data]
        step.avg_cn2 = np.mean(cn2_data) if cn2_data else None
    
    def _generate_lookup_table(self) -> Dict:
        """Generate lookup table from calibration data"""
        lookup_table = {
            "fan_speed_to_chamber_temp": {},
            "hotplate_temp_to_surface_temp": {},
            "combined_settings_to_cn2": {}
        }
        
        for step in self.current_session.steps:
            if step.status != CalibrationStatus.COMPLETED:
                continue
            
            if step.step_type == CalibrationStepType.FAN_CALIBRATION:
                # Map fan speed to chamber temperature
                if step.fan_speed is not None and step.avg_temperatures:
                    # Use average of all sensors as chamber temperature
                    chamber_temp = np.mean(step.avg_temperatures)
                    lookup_table["fan_speed_to_chamber_temp"][step.fan_speed] = chamber_temp
            
            elif step.step_type == CalibrationStepType.HOTPLATE_CALIBRATION:
                # Map hot plate target temperature to surface temperature
                if step.hotplate_id is not None and step.target_temperature is not None:
                    # Use the sensor closest to the hot plate (simplified)
                    surface_temp = step.avg_temperatures[step.hotplate_id] if step.hotplate_id < len(step.avg_temperatures) else 0.0
                    key = f"hotplate_{step.hotplate_id}"
                    if key not in lookup_table["hotplate_temp_to_surface_temp"]:
                        lookup_table["hotplate_temp_to_surface_temp"][key] = {}
                    lookup_table["hotplate_temp_to_surface_temp"][key][step.target_temperature] = surface_temp
            
            elif step.step_type == CalibrationStepType.COMBINED_CALIBRATION:
                # Map combined settings to CN2
                if step.fan_speed is not None and step.target_temperature is not None and step.avg_cn2 is not None:
                    key = f"{step.fan_speed}_{step.target_temperature}"
                    lookup_table["combined_settings_to_cn2"][key] = step.avg_cn2
        
        return lookup_table
    
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
    
    def _save_calibration_data(self, session: CalibrationSession):
        """Save calibration data to file"""
        try:
            # Create session folder
            session_folder = os.path.join(
                self.config.calibration_data_folder,
                session.session_id
            )
            os.makedirs(session_folder, exist_ok=True)
            
            # Save session metadata
            metadata_file = os.path.join(session_folder, "session_metadata.json")
            with open(metadata_file, 'w') as f:
                json.dump(session.dict(), f, indent=2, default=str)
            
            # Save lookup table
            if session.lookup_table:
                lookup_file = os.path.join(session_folder, "lookup_table.json")
                with open(lookup_file, 'w') as f:
                    json.dump(session.lookup_table, f, indent=2)
            
            # Save detailed data to CSV
            csv_file = os.path.join(session_folder, "calibration_data.csv")
            with open(csv_file, 'w', newline='') as f:
                writer = csv.writer(f)
                
                # Write header
                header = [
                    "step_number", "step_type", "fan_speed", "hotplate_id",
                    "target_temperature", "hotplate_state", "timestamp",
                    "temperatures", "flow_rates", "cn2"
                ]
                writer.writerow(header)
                
                # Write data for each step
                for step in session.steps:
                    for dp in step.data_points:
                        row = [
                            step.step_number,
                            step.step_type.value,
                            step.fan_speed,
                            step.hotplate_id,
                            step.target_temperature,
                            step.hotplate_state,
                            dp.timestamp.isoformat(),
                            ",".join(map(str, dp.temperatures)),
                            ",".join(map(str, dp.flow_rates)),
                            dp.cn2
                        ]
                        writer.writerow(row)
            
            logger.info(f"Calibration data saved to {session_folder}")
            
        except Exception as e:
            logger.error(f"Error saving calibration data: {e}")
    
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
