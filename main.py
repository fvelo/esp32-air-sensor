"""Main application for the ESP32 air-quality sensor."""

import json
import os
import time
from machine import I2C, Pin, UART

import urequests

import config
from connect_to_wifi import WlanClient
from device_api import DeviceApiServer
from pms5003 import PMS5003
from scd4x_helper.bus_service import I2cAdapter
from scd4x_sensirion import SCD4xSensirion


def load_wifi_credentials():
    """Load persisted Wi-Fi values, falling back to config.py."""
    credentials = {"ssid": config.WIFI_SSID, "password": config.WIFI_PASSWORD}
    try:
        with open(config.WIFI_CONFIG_FILE, "r") as file:
            saved = json.load(file)
        if isinstance(saved.get("ssid"), str) and isinstance(saved.get("password"), str):
            credentials.update(saved)
    except (OSError, ValueError, AttributeError):
        pass
    return credentials


def save_wifi_credentials(ssid, password):
    """Persist Wi-Fi values without changing the active measurement loop."""
    temporary_file = config.WIFI_CONFIG_FILE + ".tmp"
    with open(temporary_file, "w") as file:
        json.dump({"ssid": ssid, "password": password}, file)
    try:
        os.remove(config.WIFI_CONFIG_FILE)
    except OSError:
        pass
    os.rename(temporary_file, config.WIFI_CONFIG_FILE)


def create_scd41():
    i2c = I2C(config.SCD_I2C_ID, scl=Pin(config.SCD_SCL_PIN),
              sda=Pin(config.SCD_SDA_PIN), freq=config.SCD_I2C_FREQUENCY_HZ)
    return SCD4xSensirion(adapter=I2cAdapter(i2c), this_is_scd41=True, check_crc=True)


def create_pms5003():
    uart = UART(config.PMS_UART_ID, tx=Pin(config.PMS_TX_PIN),
                rx=Pin(config.PMS_RX_PIN), baudrate=config.PMS_BAUDRATE)
    return PMS5003(uart=uart, pin_enable=Pin(config.PMS_ENABLE_PIN),
                   pin_reset=Pin(config.PMS_RESET_PIN), mode="active")


def configure_scd41(scd41):
    scd41.start_measurement(start=False, single_shot=False)
    scd41.set_altitude(config.SCD_ALTITUDE_METERS)
    scd41.set_auto_calibration(config.SCD_AUTOMATIC_CALIBRATION)
    print("SCD4x: running self-test...")
    if not scd41.exec_self_test():
        raise RuntimeError("SCD4x self-test failed; check the wiring")
    print("SCD4x self-test passed.")
    scd41.start_measurement(start=True)
    print("SCD4x continuous measurement started.")


def connect_wifi(credentials):
    client = WlanClient()
    print("Connecting to Wi-Fi...")
    while not client.connect_to_wifi(credentials["ssid"], credentials["password"],
                                     timeout=config.WIFI_CONNECT_TIMEOUT_SECONDS):
        print("Wi-Fi connection failed; retrying...")
        time.sleep(config.WIFI_RETRY_DELAY_SECONDS)
    print("Wi-Fi connected:", client.get_connection_data())
    return client


def post_json(url, payload):
    response = None
    try:
        response = urequests.post(url, data=json.dumps(payload),
                                  headers={"Content-Type": "application/json"})
        print("HTTP status:", response.status_code)
        print("HTTP response:", response.text)
        return response.status_code < 400
    except OSError as error:
        print("HTTP request failed:", error)
        return False
    finally:
        if response is not None:
            response.close()


def read_air_quality(pms5003, scd41):
    pms_data = pms5003.read()
    print("PMS5003 ->")
    print(pms_data)
    pm1 = pms_data.pm_ug_per_m3(1.0, atmospheric_environment=True)
    pm2_5 = pms_data.pm_ug_per_m3(2.5, atmospheric_environment=True)
    pm10 = pms_data.pm_ug_per_m3(10, atmospheric_environment=True)
    if not scd41.get_data_status():
        print("SCD4x data not ready.")
        return None

    co2, temperature, humidity = scd41.get_measurement_value()
    print("SCD4x -> CO2: {} ppm, Temperature: {:.2f} C, Humidity: {:.2f} %".format(
        co2, temperature, humidity))
    return {"temperature": temperature, "humidity": humidity, "pm1": pm1,
            "pm2_5": pm2_5, "pm10": pm10, "co2": co2, "voc": 0,
            "apiPassword": config.API_PASSWORD}


def run(test_mode=None, send_data=True):
    if test_mode is None:
        test_mode = config.TEST_MODE

    scd41 = create_scd41()
    pms5003 = create_pms5003()
    configure_scd41(scd41)
    interval = (config.TEST_INTERVAL_SECONDS if test_mode
                else config.NORMAL_INTERVAL_SECONDS)
    state = {"started": time.time(), "last_measurement": None,
             "pms5003_ok": False, "scd41_ok": False, "last_api_ok": None}
    credentials = load_wifi_credentials()
    wifi = connect_wifi(credentials)
    if test_mode:
        print("TEST MODE - API uploads disabled")
        print("ESP32 IP address:", wifi.get_connection_data()[0])

    def health():
        now = time.time()
        last = state["last_measurement"]
        recent = last is not None and now - last <= max(interval * 2, 60)
        return {"status": "ok" if recent and state["pms5003_ok"] and state["scd41_ok"]
                else "starting", "measurement_active": True,
                "last_measurement": last, "pms5003": state["pms5003_ok"],
                "scd41": state["scd41_ok"],
                "wifi": wifi is not None and wifi.is_connected(timeout=0),
                "api_last_request_ok": state["last_api_ok"]}

    def update_wifi(ssid, password):
        save_wifi_credentials(ssid, password)
        return {"saved": True, "requires_reboot": True}

    api = DeviceApiServer(config.DEVICE_API_HOST, config.DEVICE_API_PORT,
                          health, update_wifi, config.API_PASSWORD)
    print("Device API listening on port {}".format(config.DEVICE_API_PORT))

    try:
        while True:
            api.poll()
            try:
                payload = read_air_quality(pms5003, scd41)
                state["pms5003_ok"] = True
                state["scd41_ok"] = payload is not None
                if payload is not None:
                    state["last_measurement"] = time.time()
                    if send_data:
                        state["last_api_ok"] = post_json(config.AIR_DATA_ENDPOINT, payload)
            except Exception as error:
                print("Measurement error:", error)

            remaining = interval if state["last_measurement"] is not None else config.SCD_DATA_NOT_READY_DELAY_SECONDS
            while remaining > 0:
                api.poll()
                time.sleep_ms(100)
                remaining -= 0.1
    except KeyboardInterrupt:
        print("Stopping measurements.")
    finally:
        api.close()
        scd41.start_measurement(start=False, single_shot=False)
        print("SCD4x measurements stopped.")


def calibrateSensor():
    scd41 = create_scd41()
    scd41.set_auto_calibration(config.SCD_AUTOMATIC_CALIBRATION)
    scd41.start_measurement(start=True)
    try:
        time.sleep(config.CALIBRATION_STARTUP_DELAY_SECONDS)
        scd41.get_measurement_value()
        print("Waiting for the calibration measurement period...")
        time.sleep(config.CALIBRATION_MEASUREMENT_SECONDS)
        scd41.start_measurement(start=False, single_shot=False)
        result = scd41.force_recalibration(config.CALIBRATION_REFERENCE_CO2_PPM)
        print("Calibration result:", result)
        post_json(config.CALIBRATION_ENDPOINT, {"isSuccess": result})
    finally:
        scd41.start_measurement(start=False, single_shot=False)


Main = run
