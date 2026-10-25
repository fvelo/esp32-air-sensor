# ESP32 Air Quality Sensor

MicroPython application for an ESP32-S3-Pico connected to a PMS5003 and an
SCD41 air-quality sensor.

## Configuration

`config.py` contains the local Wi-Fi and API credentials and is intentionally
ignored by Git. Keep it next to `main.py` on the board. Use
`config.example.py` as the template for a new installation.

## Files

- `boot.py` starts the normal measurement loop.
- `main.py` contains the application and calibration workflow.
- `main_test.py` runs the sensors in test mode without sending API requests.
- `pms5003.py` and `scd4x_sensirion.py` are the sensor drivers.
- `scd4x_helper/` contains the SCD4x bus and CRC helpers.

## Device upload

Upload all Python files and the `scd4x_helper` directory to the board with
Thonny. Upload the local `config.py` too; it is not included in Git commits.
