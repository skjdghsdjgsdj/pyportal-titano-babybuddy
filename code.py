import os
import time

import adafruit_connection_manager
import adafruit_imageload
import board
import busio
import displayio
import supervisor
import adafruit_requests
from adafruit_esp32spi import adafruit_esp32spi
from digitalio import DigitalInOut
from adafruit_display_text import label
from adafruit_bitmap_font import bitmap_font
from adafruit_display_shapes.line import Line
import analogio

#supervisor.runtime.autoreload = False

def connect_to_wifi():
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

#connect_to_wifi()

fonts = {
    "main": bitmap_font.load_font("SF-Compact-Display-Medium-96.pcf"),
    "last_breast": bitmap_font.load_font("SF-Compact-Display-Medium-40.pcf"),
    "change": bitmap_font.load_font("SF-Compact-Display-Medium-40.pcf"),
}

display = board.DISPLAY
group = displayio.Group()

main_label = label.Label(fonts["main"], text = "1h 15m", color = 0xFF0000)
main_label.anchor_point = (0.5, 0.0)
main_label.anchored_position = (display.width // 2, 40)
group.append(main_label)

last_breast_label = label.Label(fonts["last_breast"], text = "○●", color = 0xFF0000)
last_breast_label.anchor_point = (0.5, 0.0)
last_breast_label.anchored_position = (display.width // 2, 150)
group.append(last_breast_label)

poop_bitmap, poop_palette = adafruit_imageload.load(
    "/poop.bmp",
    bitmap = displayio.Bitmap,
    palette = displayio.Palette)

poop = displayio.TileGrid(
    poop_bitmap,
    pixel_shader = poop_palette,
    x = display.width // 2 - 64 - 20,
    y = display.height - 64 - 5
)

group.append(poop)

poop_label = label.Label(fonts["change"], text = "10h", color = 0x883300)
poop_label.anchor_point = (1.0, 0.5)
poop_label.anchored_position = (display.width // 2 - 64 - 20 - 10, display.height - 64 / 2 - 5)
group.append(poop_label)

pee_label = label.Label(fonts["change"], text = "47m", color = 0x0066FF)
pee_label.anchor_point = (0.0, 0.5)
pee_label.anchored_position = (display.width // 2 + 40 + 20 + 10, display.height - 64 / 2 - 5)
group.append(pee_label)

pee_bitmap, pee_palette = adafruit_imageload.load(
    "/pee.bmp",
    bitmap = displayio.Bitmap,
    palette = displayio.Palette)

pee = displayio.TileGrid(
    pee_bitmap,
    pixel_shader = poop_palette,
    x = display.width // 2 + 20,
    y = display.height - 64 - 5
)

group.append(pee)

display.root_group = group

light_sensor = analogio.AnalogIn(board.LIGHT)

MIN_LIGHT_VALUE = 800
MAX_LIGHT_VALUE = 1500

while True:
    light_value = light_sensor.value
    if light_value < MIN_LIGHT_VALUE:
        backlight = 0
    elif light_value > MAX_LIGHT_VALUE:
        backlight = 1
    else:
        backlight = (light_value - MIN_LIGHT_VALUE) / (MAX_LIGHT_VALUE - MIN_LIGHT_VALUE)

    if backlight <= 0.01:
        backlight = 0.01

    board.DISPLAY.brightness = backlight

    time.sleep(0.1)