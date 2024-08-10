import os
import time

import adafruit_datetime
import analogio
import rtc

# noinspection PyBroadException
try:
    from typing import Any, Optional, Callable, Final
except:
    pass

import adafruit_connection_manager
import adafruit_imageload
import adafruit_ntp
import board
import busio
import displayio
import adafruit_requests
from adafruit_esp32spi import adafruit_esp32spi
from digitalio import DigitalInOut
from adafruit_display_text.label import Label
from adafruit_bitmap_font import bitmap_font
from displayio import Display
import supervisor

supervisor.runtime.autoreload = False

class Wifi:
    def __init__(self):
        self.requests = None
        self.socketpool = None

    def connect(self) -> None:
        esp32_cs = DigitalInOut(board.ESP_CS)
        esp32_ready = DigitalInOut(board.ESP_BUSY)
        esp32_reset = DigitalInOut(board.ESP_RESET)

        spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
        esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)

        self.socketpool = adafruit_connection_manager.get_radio_socketpool(esp)
        self.requests = adafruit_requests.Session(
            self.socketpool,
            adafruit_connection_manager.get_radio_ssl_context(esp)
        )

        if esp.status == adafruit_esp32spi.WL_IDLE_STATUS:
            print("ESP32 found and in idle mode")
        print("Firmware version: " + esp.firmware_version)
        print("MAC address: " + ":".join("%02X" % byte for byte in esp.MAC_address))

        ssid = os.getenv("CIRCUITPY_WIFI_SSID")
        print(f"Connecting to {ssid}...")
        while not esp.connected:
            try:
                esp.connect_AP(ssid, os.getenv("CIRCUITPY_WIFI_PASSWORD"))
                break
            except OSError as e:
                print(f"Got {e} while connecting, retrying")

        print(f"Connected to {esp.ap_info.ssid}, IP {esp.ipv4_address}")

    def sync_rtc(self):
        print("Getting date/time from NTP...")
        ntp = adafruit_ntp.NTP(self.socketpool)
        now = ntp.datetime
        rtc.RTC().datetime = now
        print(f"Synced: {adafruit_datetime.datetime.now()}")

class BabyBuddy:
    LEFT_BREAST = -1
    RIGHT_BREAST = 1
    BOTH_BREASTS = 0

    def __init__(self, wifi: Wifi, url: str, api_key: str):
        self.wifi = wifi
        self.url = url
        self.api_key = api_key

    def get_last_feeding(self) -> tuple[Optional[adafruit_datetime.datetime], Optional[int]]:
        feedings = self.get("feedings/?limit=1")

        if len(feedings["results"]) == 0:
            return None, None

        feeding = feedings["results"][0]
        if feeding["method"] == "left breast":
            which_breast = BabyBuddy.LEFT_BREAST
        elif feeding["method"] == "right breast":
            which_breast = BabyBuddy.RIGHT_BREAST
        elif feeding["method"] == "both breasts":
            which_breast = BabyBuddy.BOTH_BREASTS
        else:
            which_breast = None

        last_feeding_datetime = adafruit_datetime.datetime.fromisoformat(feeding["start"])

        return last_feeding_datetime, which_breast

    def get_last_changes(self) -> tuple[Optional[adafruit_datetime.datetime], Optional[adafruit_datetime.datetime]]:
        changes = self.get("changes/?limit=25")

        if len(changes["results"]) == 0:
            return None, None

        last_pee = None
        last_poop = None

        for change in changes["results"]:
            if change["wet"] and last_pee is None:
                last_pee = adafruit_datetime.datetime.fromisoformat(change["time"])

            if change["solid"] and last_poop is None:
                last_poop = adafruit_datetime.datetime.fromisoformat(change["time"])

            if last_pee is not None and last_poop is not None:
                break

        return last_pee, last_poop

    def get_feeding_timer(self) -> Optional[adafruit_datetime.datetime]:
        timers = self.get("timers/")

        for timer in timers["results"]:
            if timer["name"] is not None and "feeding" in timer["name"].lower():
                return adafruit_datetime.datetime.fromisoformat(timer["start"])

        return None

    def get(self, uri: str):
        full_url = self.url + uri
        print(f"GET {full_url}...", end = "")
        response = self.wifi.requests.get(full_url, headers = {"Authorization": f"Token {self.api_key}"}, timeout = 5)
        if response.status_code < 200 or response.status_code >= 300:
            raise ValueError(f"Got HTTP {response.status_code} instead of expected 2xx")
        print(response.status_code)
        json = response.json()
        response.close()
        return json

class UI:
    fonts = {
        "main": bitmap_font.load_font("SF-Compact-Display-Medium-88.pcf"),
        "last_breast": bitmap_font.load_font("SF-Compact-Display-Medium-40.pcf"),
        "change": bitmap_font.load_font("SF-Compact-Display-Medium-40.pcf"),
    }

    def __init__(self, display: Display, bb: BabyBuddy):
        self.display = display
        self.root = displayio.Group()
        self.bb = bb
        display.root_group = self.root

        self.display.auto_refresh = False

        self.main_label = self.append_label(
            font_name = "main",
            text = "...",
            color = 0xFF0000,
            anchor_point = (0.5, 0.0),
            anchored_position = (display.width // 2, 35)
        )

        self.sub_label = self.append_label(
            font_name = "last_breast",
            text = "",
            color = 0xFF0000,
            anchor_point = (0.5, 0.0),
            anchored_position = (display.width // 2, 150)
        )

        self.append_bitmap("/poop.bmp", (display.width // 2 - 64, display.height - 64 - 5))
        self.append_bitmap("/pee.bmp", (display.width // 2 + 20, display.height - 64 - 5))

        self.poop_label = self.append_label(
            font_name = "change",
            text = "",
            color = 0x883300,
            anchor_point = (1.0, 0.5),
            anchored_position = (display.width // 2 - 64 - 20, display.height - 64 // 2 - 5)
        )

        self.pee_label = self.append_label(
            font_name = "change",
            text = "",
            color = 0x0066FF,
            anchor_point = (0.0, 0.5),
            anchored_position = (display.width // 2 + 40 + 20 + 10, display.height - 64 // 2 - 5)
        )

    def append_label(self,
        font_name: str,
        text: str,
        color: int,
        anchor_point: tuple[float, float],
        anchored_position: tuple[int, int]
    ):
        label = Label(font = UI.fonts[font_name], text = text, color = color)
        label.anchor_point = anchor_point
        label.anchored_position = anchored_position

        self.root.append(label)
        return label

    def append_bitmap(self, filename: str, coords: tuple[int, int]):
        bitmap, palette = adafruit_imageload.load(
            file_or_filename = filename,
            bitmap = displayio.Bitmap,
            palette = displayio.Palette
        )

        x, y = coords
        tile_grid = displayio.TileGrid(bitmap = bitmap, pixel_shader = palette, x = x, y = y)

        self.root.append(tile_grid)
        return tile_grid

    @staticmethod
    def now():
        # noinspection PyUnresolvedReferences
        return adafruit_datetime.datetime.now().replace(tzinfo = adafruit_datetime.timezone.utc)

    def update(self):
        feeding_timer = self.bb.get_feeding_timer()
        if feeding_timer is None:
            self.update_last_feeding()
        else:
            self.update_feeding_timer(feeding_timer)
        self.update_last_changes()
        self.display.refresh()

    def update_last_feeding(self):
        last_feeding_datetime, which_breast = self.bb.get_last_feeding()

        breast_text = ""

        self.main_label.color = 0xFF0000
        self.sub_label.color = 0xFF0000

        if last_feeding_datetime is None:
            self.main_label.text = "No data"
        else:
            now = UI.now()
            then = last_feeding_datetime
            time_ago = now - then

            if which_breast is not None:
                if which_breast == BabyBuddy.RIGHT_BREAST:
                    breast_text = "○●"
                elif which_breast == BabyBuddy.LEFT_BREAST:
                    breast_text = "●○"
                elif which_breast == BabyBuddy.BOTH_BREASTS:
                    breast_text = "●●"

            # noinspection PyUnresolvedReferences
            self.main_label.text = f"{time_ago.seconds // 60 // 60}h {time_ago.seconds // 60 % 60}m"

        self.sub_label.text = breast_text

    def update_feeding_timer(self, timer: adafruit_datetime.datetime):
        self.main_label.color = 0xFFFFFF
        self.sub_label.color = 0xFFFFFF

        now = UI.now()
        elapsed = now - timer

        # noinspection PyUnresolvedReferences
        self.main_label.text = f"{elapsed.seconds // 60}m"

        hour = timer.hour
        meridian = "AM"
        if hour >= 12:
            meridian = "PM"
            if hour > 12:
                hour -= 12
        elif hour == 0:
            hour = 12

        self.sub_label.text = f"Started {hour}:{timer.minute:>02} {meridian}"

    @staticmethod
    def datetime_to_change_label(datetime: Optional[adafruit_datetime.datetime], label: Label):
        if datetime is None:
            label.text = "?"
        else:
            now = UI.now()
            delta = now - datetime
            # noinspection PyUnresolvedReferences
            if delta.seconds < 60 * 60:
                # noinspection PyUnresolvedReferences
                label.text = f"{delta.seconds // 60}m"
            else:
                # noinspection PyUnresolvedReferences
                label.text = f"{delta.seconds // 60 // 60}h"

    def update_last_changes(self):
        last_peed, last_pooped = self.bb.get_last_changes()

        UI.datetime_to_change_label(last_peed, self.pee_label)
        UI.datetime_to_change_label(last_pooped, self.poop_label)

wifi = Wifi()
wifi.connect()

bb = BabyBuddy(wifi, os.getenv("BABYBUDDY_URL"), os.getenv("BABYBUDDY_API_KEY"))

ui = UI(board.DISPLAY, bb)

UPDATE_INTERVAL_SECONDS: Final = 30
DIM_BACKLIGHT_THRESHOLD = 600
NTP_RESYNC_INTERVAL_SECONDS = 60 * 30

light_sensor = analogio.AnalogIn(board.LIGHT)

tick = -1
light_samples = []
while True:
    tick += 1

    if tick % NTP_RESYNC_INTERVAL_SECONDS == 0:
        wifi.sync_rtc()

    if tick % UPDATE_INTERVAL_SECONDS == 0:
        ui.update()

    light_samples.append(light_sensor.value)
    while len(light_samples) > 10:
        light_samples.pop(0)

    if all(value < DIM_BACKLIGHT_THRESHOLD for value in light_samples):
        board.DISPLAY.brightness = 0.3
    else:
        board.DISPLAY.brightness = 1

    time.sleep(1)
