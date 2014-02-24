#!/usr/bin/env python

###########################################################################
# Pi_OBD_LCD_Logger.py
#
# For use with Adafruit LCD Plate for Raspberry Pi
#
# This file is part of Pi_OBD_Logger.
# https://github.com/alex3yoyo/Pi_OBDII_Logger
#
# Pi_OBD_Logger is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# Pi_OBD_Logger is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Pi_OBD_Logger; if not, visit http://www.gnu.org/licenses/gpl.html
#
# Code adapted from PiMyRide by Alan Kehoe, David O'Regan (www.pimyride.com)
###########################################################################

from datetime import datetime
from time import sleep
import sys
import os
import thread
import ConfigParser

from CharLCDPlate import CharLCDPlate
from obd_utils import scanSerial
import obd_io
import obd_sensors


class PiMyRide_Logger():
    """THE class"""
    def __init__(self, path, log_sensors):
        self.lcd = CharLCDPlate()
        self.lcd.begin(16, 1)
        self.port = None
        self.sensor_list = []
        destination_file = path + (
            datetime.now().strftime('%d%b-%H_%M_%S')) + ".csv"
        self.log_csv = open(destination_file, "w", 128)
        self.log_csv.write("Time,RPM,MPH,Throttle-Position,Calculated-Load,"
                           "Coolant-Temp,Air-Temp,Intake-Manifold-Pressure,"
                           "Air-Flow-Rate,Engine-Time,MPG\n")
        for sensor in log_sensors:
            self.add_log_sensor(sensor)

        self.config_path = "/home/pi/PiMyRide/config.ini"
        self.Config = ConfigParser.ConfigParser()
        if not os.path.isfile(self.config_path):
            open(self.config_path, "w")
            self.Config.add_section("Settings")
            self.Config.set("Settings", "logging_enabled", True)
            self.Config.set("Settings", "mpg_enabled", True)
            self.Config.set("Settings", "current_screen", 0)
            self.Config.write(self.config_path)
            self.config_path.close()
        self.Config.read(self.config_path)
        self.logging_enabled = self.Config.getboolean("Settings",
                                                      "logging_enabled")
        self.mpg_enabled = self.Config.getboolean("Settings", "mpg_enabled")
        self.current_screen = self.Config.get("Settings", "current_screen")
        self.display_enabled = True
        self.display_in_use = False

    def exit(self, shutdown):
        self.Config.set("Settings", "current_screen", self.current_screen)
        self.Config.set("Settings", "logging_enabled", self.logging_enabled)
        self.Config.set("Settings", "mpg_enabled", self.mpg_enabled)
        self.Config.write(self.config_path)
        print("Configuration saved.")
        self.lcd.clear()
        self.lcd.noDisplay()
        if shutdown:
            os.command("sudo shutdown now")
            sys.exit()
        elif not shutdown:
            sys.exit()

    def display_alert(self, message, alert_duration):
        """Take control of the LCD screen for displaying an alert"""
        self.display_in_use = True
        self.lcd.clear()
        self.lcd.home()
        self.lcd.message(message)
        sleep(alert_duration)
        self.display_in_use = False

    def lcd_update(self, message, is_alert):
        """
            Update the LCD screen. Allows for rapid updating of the screen,
            while not stopping the program if an alert needs to be
            displayed. Sensor data will not be shown while an alert is
            being displayed
        """
        if self.display_enabled and not self.display_in_use:
            if not is_alert:
                # Rapidly update sensor data readout
                self.lcd.clear()
                self.lcd.home()
                self.lcd.message(message)
            elif is_alert:
                # Display alert using a new thread as to not
                # intturpt the sensor logging.
                alert_duration = 1.5
                thread.start_new_thread(self.display_alert, (
                                        message, alert_duration))

    def connection_error(self, reason):
        print("Connection error, disconnecting")
        if not self.display_enabled:
            self.lcd.display()
        self.lcd_update("Connection error\n" + reason, False)
        sleep(2)
        while 1:
            self.lcd_update("OK to reconnect\nDOWN to shutdown", False)
            if self.lcd.buttonPressed(self.lcd.SELECT):
                print("Select buttpn pressed, \
                      attempting to recconect...")
                self.lcd_update("Reconnecting...", False)
                self.start()
            elif self.lcd.buttonPressed(self.lcd.DOWN):
                print("Down buttpn pressed, shutting down...")
                self.lcd_update("Shutting Down...", False)
                sleep(1)
                self.lcd.noDisplay()
                self.exit(True)
            elif self.lcd.buttonPressed(self.lcd.DOWN):
                print("Up buttpn pressed, exiting...")
                self.lcd_update("Exiting\nProgram...", False)
                sleep(1)
                self.lcd.clear()
                self.lcd.noDisplay()
                self.exit(False)
            sleep(0.10)

    def connect(self):
        """
            Check all serial ports, print availible ports,
            close on no open ports.
        """
        port_names = scanSerial()
        print(port_names)
        for port in port_names:
            self.port = obd_io.OBDPort(port, None, 2, 2)
            if self.port.State == 0:
                self.port.close()
                self.port = None  # No open ports close
            else:
                break  # Break with connection

        if self.port:
            print("Connected")
            self.lcd_update("Connected", False)
        else:
            print("Not Connected")
            self.connection_error("Not connected")

    def is_connected(self):
        return self.port

    def add_log_sensor(self, sensor):
        """
            Add the sensors to read from from the list.
            These sensors are in obd_sensors.py.
        """
        for index, e in enumerate(obd_sensors.SENSORS):
            if sensor == e.shortname:
                self.sensor_list.append(index)
                print("Logging Sensor: " + e.name)
                break

    def get_mpg(self, MPH, MAF):
        """Calculate MPG for petrol enignes, not for diesel"""
        Instant_MPG = (14.7 * 7.273744 * 4.54 * MPH) / (3600 * MAF / 100)
        return Instant_MPG

    def record_data(self):
        """Actually start recording the data and doing stuff with it"""
        if self.port is None:
            return None
        data_screens = [
            ["rpm", "speed"],
            ["throttle_pos", "load"],
            ["temp", "intake_air_temp"],
            ["manifold_pressure", "maf"],
            ["engine_time", "timing_advance"],
        ]
        sensor_names = {
            "rpm": "RPM",
            "speed": "Speed",
            "throttle_pos": "Throttle",
            "load": "Load",
            "temp": "Temp",
            "intake_air_temp": "Intake Temp",
            "manifold_pressure": "Pressure",
            "maf": "MAF",
            "engine_time": "Time",
            "timing_advance": "Timing Advance",
            "fuel_status": "Fuel Status",
            "fuel_rate": "Fuel Rate",
            "fuel_pressure": "Fuel Pressure"
        }
        print("Logging started")
        self.lcd_update("Logging started", True)

        while 1:
            if self.display_enabled:
                if self.lcd.buttonPressed(self.lcd.RIGHT):
                    # Go to next screen; setting is persistent
                    total_screens = len(self.data_screens) - 1
                    if self.current_screen < total_screens:
                        self.current_screen = self.current_screen + 1
                    elif self.current_screen == total_screens:
                        self.current_screen = 0
                    assert self.current_screen <= total_screens
                if self.lcd.buttonPressed(self.lcd.LEFT):
                    # Go to previous screen; setting is persistent
                    total_screens = len(self.data_screens) - 1
                    if self.current_screen > 0:
                        self.current_screen = self.current_screen - 1
                    elif self.current_screen == 0:
                        self.current_screen = total_screens
            if self.lcd.buttonPressed(self.lcd.UP):
                # Enable/disable calculating MPG; persistent
                if self.mpg_enabled:
                    self.mpg_enabled = False
                    print("MPG disabled")
                    self.lcd_update("MPG disabled", True)
                elif not self.mpg_enabled:
                    self.mpg_enabled = True
                    print("MPG enabled")
                    self.lcd_update("MPG enabled", True)
            if self.lcd.buttonPressed(self.lcd.DOWN):
                # Enable/disable logging; persistent
                if self.logging_enabled:
                    self.logging_enabled = False
                    print("Logging disabled")
                    self.lcd_update("Logging disabled", True)
                elif not self.logging_enabled:
                    self.logging_enabled = True
                    print("Logging enabled")
                    self.lcd_update("Logging enabled", True)
            if self.lcd.buttonPressed(self.lcd.SELECT):
                # Turn off/on LCD; not persistent
                if self.display_enabled:
                    self.display_enabled = False
                    self.lcd.clear()
                    self.lcd.home()
                    self.lcd.noDisplay()
                    print("Display disabled")
                elif not self.display_enabled:
                    self.display_enabled = True
                    self.lcd.display()
                    print("Display enabled")
                    self.lcd_update("Display enabled", True)

            log_time = datetime.now().strftime('%d%b-%H:%M:%S.%f')
            log_data = log_time  # Start of the logging string
            result_set = {}
            # Log all of sensor data from sensor_list
            for index in self.sensor_list:
                (name, value, unit) = self.port.sensor(index)
                # print(self.port.sensor(index))  # Print the data
                log_data = log_data + "," + str(value)
                result_set[obd_sensors.SENSORS[index].shortname] = value
            # Exit the program on "NODATA"/dropped connection
            if (result_set["rpm"] == "NODATA") or (
                    result_set["speed"] == "NODATA") or (
                    result_set["temp"] == "NODATA"):
                self.connection_error("NODATA")
                break
            if self.mpg_enabled:
                Instant_MPG = self.get_mpg(result_set["speed"],
                                           result_set["maf"])
                # Add mpg to log string
                log_data = log_data + "," + str(Instant_MPG)
            if self.logging_enabled:
                self.log_csv.write(log_data + "\n")
            if self.display_enabled:
                # Show data on lcd
                msg_line_1 = sensor_names[data_screens[self.current_screen][0]] +\
                    " " + str(round(result_set[data_screens[self.current_screen][0]], 2))
                msg_line_2 = sensor_names[data_screens[self.current_screen][1]] +\
                    " " + str(round(result_set[data_screens[self.current_screen][1]], 2))
                lcd_message = str(msg_line_1) + "\n" + str(msg_line_2)
                self.lcd_update(lcd_message, False)

    def start(self):
        self.connect()
        if not self.is_connected():
            self.connection_error("Not connected")
        self.record_data()


def ensure_dir(f):
    """New directory for each day to make managing the logs easier"""
    d = os.path.dirname(f)
    if not os.path.exists(d):
        os.makedirs(d)

path = datetime.now().strftime('%d-%b-%Y')
ensure_dir("/home/pi/PiMyRide/logs/" + path + "/")
log_sensors = ["rpm", "speed", "throttle_pos", "load", "temp",
               "intake_air_temp", "manifold_pressure", "maf", "engine_time"]
logger = PiMyRide_Logger("/home/pi/PiMyRide/logs/" + path + "/", log_sensors)
logger.start()
