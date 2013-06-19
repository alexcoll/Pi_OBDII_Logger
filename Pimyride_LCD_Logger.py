#!/usr/bin/env python

###########################################################################
# PiMyRide_LCD_Logger.py
#
# For use with Adafruit LCD Plate for Raspberry Pi
#
# Copyright 2013 Alan Kehoe, David O'Regan (www.pimyride.com)
#
# This file is part of PiMyRide.
#
# PiMyRide is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# PiMyRide is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PiMyRide; if not, visit http://www.gnu.org/licenses/gpl.html
###########################################################################

from datetime import datetime
from time import sleep
import sys
import os

from CharLCDPlate import CharLCDPlate
from obd_utils import scanSerial
import obd_io
import obd_sensors


class PiMyRide_Logger():
    def __init__(self, path, log_sensors):
        self.port = None
        self.lcd = CharLCDPlate()
        self.lcd.begin(16, 1)
        self.sensor_list = []
        destination_file = path + (datetime.now().strftime('%d%b-%H:%M:%S')) + ".csv"
        self.log_csv = open(destination_file, "w", 128)
        self.log_csv.write(
            "Time,RPM,MPH,Throttle-Position,Calculated-Load,"
            "Coolant-Temp,Air-Temp,Intake-Manifold-Pressure,Air-Flow-Rate,MPG\n")

        for sensor in log_sensors:
            self.add_log_sensor(sensor)

    def connect(self):  # Check all serial ports.
        port_names = scanSerial()  # print available ports
        print port_names
        for port in port_names:
            self.port = obd_io.OBDPort(port, None, 2, 2)
            if self.port.State == 0:
                self.port.close()
                self.port = None  # no open ports close

            else:
                break  # break with connection

        if self.port:
            self.lcd.clear()
            self.lcd.message("Connected")
            print "Connected"

    def is_connected(self):  # check if connected
        return self.port

    # add the sensors to read from from the list below. this sensors are in obd_sensors.py
    def add_log_sensor(self, sensor):
        for index, e in enumerate(obd_sensors.SENSORS):
            if sensor == e.shortname:
                self.sensor_list.append(index)
                print "Logging Sensor: " + e.name  # logging this sensor
                break

    def get_mpg(self, MPH, MAF):
        #  Instant_MPG = (14.7 * 8.637571 * 4.54 * MPH) / (3600 * (MAF * 7.5599) / 100)  #Diesel Inaccurate formula
        Instant_MPG = (14.7 * 7.273744 * 4.54 * MPH) / (3600 * MAF / 100)  # Petrol Should accurate
        return Instant_MPG

    def record_data(self):
        if self.port is None:
            return None

        self.lcd.clear()
        self.lcd.message("Logging started")
        print "Logging started"

        while 1:
            log_time = datetime.now().strftime('%d%b-%H:%M:%S.%f')  # today's date and time
            log_data = log_time  # start of the logging string
            result_set = {}
            for index in self.sensor_list:  # log all of our sensors data from sensor_list
                (name, value, unit) = self.port.sensor(index)
                print self.port.sensor(index)  # print the data provides feedback to user
                log_data = log_data + "," + str(value)  # add to log string
                result_set[obd_sensors.SENSORS[index].shortname] = value
                # we don't want to log "NODATA" if the car drops the OBDII connection rather exit the program
            if (result_set["rpm"] == "NODATA") or (result_set["speed"] == "NODATA") or (
                    result_set["throttle_pos"] == "NODATA") or (result_set["load"] == "NODATA") or (
                    result_set["temp"] == "NODATA") or (result_set["intake_air_temp"] == "NODATA") or (
                    result_set["manifold_pressure"] == "NODATA") or (result_set["maf"] == "NODATA"):
                self.lcd.clear()
                self.lcd.message("Connection Error\n Disconnecting")
                sleep(3)  # show the message
                self.lcd.message("  Disconnected")
                sys.exit()  # exit the program
            Instant_MPG = self.get_mpg(result_set["speed"], result_set["maf"])  # calculate mpg
            self.lcd.clear()
            self.lcd.message('MPG ' + '%.2f' % Instant_MPG + '\n')
            self.lcd.message('RPM ' + str(result_set["rpm"]))
            log_data = log_data + "," + str(Instant_MPG)  # add mpg to result string
            self.log_csv.write(log_data + "\n")  # write to csv


def ensure_dir(f):  # Make a new directory for each day will make managing the logs easier
    d = os.path.dirname(f)
    if not os.path.exists(d):  # check if directory exists if it does not create it
        os.makedirs(d)


dir_date = datetime.now()
path = datetime.now().strftime('%d-%b-%Y')

ensure_dir("/home/pi/logs/" + path + "/")  # ensure the dir is available

log_sensors = ["rpm", "speed", "throttle_pos", "load", "temp", "intake_air_temp", "manifold_pressure", "maf"]
logger = PiMyRide_Logger("/home/pi/logs/" + path + "/", log_sensors)
logger.connect()
if not logger.is_connected():
    error = CharLCDPlate()
    error.begin(16, 1)
    error.message(" Not connected")
logger.record_data()




