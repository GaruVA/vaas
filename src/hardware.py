import serial
import time
import logging

class ArduinoController:
    def __init__(self, port='COM3', baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.connection = None
        self.connect()

    def connect(self):
        try:
            self.connection = serial.Serial(self.port, self.baudrate, timeout=1)
            time.sleep(2)  # Wait for Arduino to reset upon connection
            logging.info(f"Successfully connected to Arduino on {self.port}")
        except Exception as e:
            logging.error(f"Failed to connect to Arduino on {self.port}: {e}")

    def grant_access(self):
        """Sends command to Arduino to open the gate/turn on green LED."""
        if self.connection and self.connection.is_open:
            self.connection.write(b'OPEN_GATE\n')
            logging.info("Command sent: OPEN_GATE")
        else:
            logging.warning("Arduino not connected. Gate cannot be opened.")

    def deny_access(self):
        """Sends command to Arduino for unauthorized vehicle (e.g., sound alarm/red LED)."""
        if self.connection and self.connection.is_open:
            self.connection.write(b'DENY_ACCESS\n')
            logging.info("Command sent: DENY_ACCESS")
            
    def close(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
