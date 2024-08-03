import os

import adafruit_connection_manager
import board
import busio
import supervisor
import adafruit_requests
from adafruit_esp32spi import adafruit_esp32spi
from digitalio import DigitalInOut

supervisor.runtime.autoreload = False

esp32_cs = DigitalInOut(board.ESP_CS)
esp32_ready = DigitalInOut(board.ESP_BUSY)
esp32_reset = DigitalInOut(board.ESP_RESET)

spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)

if esp.status == adafruit_esp32spi.WL_IDLE_STATUS:
    print("ESP32 found and in idle mode")
print("Firmware vers.", esp.firmware_version)
print("MAC addr:", ":".join("%02X" % byte for byte in esp.MAC_address))

# noinspection PyTypeChecker
requests = adafruit_requests.Session(
    adafruit_connection_manager.get_radio_socketpool(esp),
    adafruit_connection_manager.get_radio_ssl_context(esp)
)

esp.connect_AP(os.getenv("CIRCUITPY_WIFI_SSID"), os.getenv("CIRCUITPY_WIFI_PASSWORD"))

print("Connected to", esp.ap_info.ssid, "\tRSSI:", esp.ap_info.rssi)
print("IP address: ", esp.ipv4_address)