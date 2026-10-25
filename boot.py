# This file is executed on every boot, including wake-boot from deep sleep.
from main import Main
from main_test import run


# Main()
run(test_mode=True, send_data=False)
