import machine
import time
from machine import I2C, Pin, UART

# comunication with server imports
from connect_to_wifi import WlanClient
import urequests
import json

# Sensors imports
from pms5003 import PMS5003
from scd4x_sensirion import SCD4xSensirion
from scd4x_helper.bus_service import I2cAdapter

def Main():
    # Pin configuration for SCD4x (I2C1)
    SCD_I2C_ID = 1
    SCD_SCL_PIN = 40
    SCD_SDA_PIN = 39
    SCD_I2C_FREQ = 100_000  # 100 kHz

    # PMS5003 UART pins
    PMS_UART_ID = 1
    PMS_TX_PIN = 9
    PMS_RX_PIN = 10
    PMS_BAUDRATE = 9600
    PMS_ENABLE_PIN = 3
    PMS_RESET_PIN = 2

    # Measurement intervals (seconds)
    TEST_INTERVAL = 10        # for testing: every 10 seconds
    NORMAL_INTERVAL = 10 * 60  # production: every 10 minutes

    # Mode flag: True = testing, False = production
    TEST_MODE = False

    # Initialize PMS5003 sensor
    drv_uart = UART(PMS_UART_ID, tx=Pin(PMS_TX_PIN), rx=Pin(PMS_RX_PIN), baudrate=PMS_BAUDRATE)
    pms5003 = PMS5003(uart=drv_uart,
                      pin_enable=Pin(PMS_ENABLE_PIN),
                      pin_reset=Pin(PMS_RESET_PIN),
                      mode="active")

    # Initialize SCD4x sensor
    # Uses a separate I2C bus instance
    i2c_scd = I2C(SCD_I2C_ID, scl=Pin(SCD_SCL_PIN), sda=Pin(SCD_SDA_PIN), freq=SCD_I2C_FREQ)
    i2c_adapter = I2cAdapter(i2c_scd)
    scd41 = SCD4xSensirion(adapter=i2c_adapter, this_is_scd41=True, check_crc=True)

    #force sensor in IDLE mode
    scd41.start_measurement(start=False, single_shot=False)

    scd41.set_altitude(155) # in metri
    scd41.set_auto_calibration(value=False) # Perché quando è indor non va bene che si auto alineai

    # Perform self-test on SCD4x
    isScd41Working = False
    print("SCD4x: running self-test...")
    if scd41.exec_self_test():
        isScd41Working = True
        print("SCD4x self-test passed.")
    else:
        print("SCD4x self-test failed. Check wiring.")

    # Start continuous measurement for SCD4x
    scd41.start_measurement(start=True)
    print("SCD4x: continuous measurement started.")

    # Select interval based on mode
    interval = TEST_INTERVAL if TEST_MODE else NORMAL_INTERVAL
    print(f"Measurement interval: {interval} seconds.")

    # connection to wifi
    print('Connection to wifi...')
    wcl = WlanClient()
    connectionResult = False
    while not connectionResult:
        connectionResult = wcl.connect_to_wifi('famiglia-velo-piano-1-2.4ghz','g27h54Etfq4')
        print('La connessione è stata stabilita: ', connectionResult)
    print('Connection succeded.')

    # helper function

    def sendDataToServer(payload):
        url = "http://192.168.1.32:40004/api/v0/insert-air-data"
        #url = "http://localhost:3000/api/v0/insert-air-data"

        # headers: tell the server we’re sending JSON
        headers = {
            "Content-Type": "application/json"
        }
        
        response = urequests.post(url, data=json.dumps(payload), headers=headers)
        print("Status:", response.status_code)
        print("Response:", response.text)
        response.close()   # free up sockets

    try:
        while True:
            # Read PMS5003
            pms_data = pms5003.read()
            pms_data_list = pms_data.to_list()
            print(f"PMS5003 format -> {pms_data}")
            print(f"PMS5003 -> {pms_data_list}")
            PM1 = pms_data_list[3]
            PM2_5 = pms_data_list[4]
            PM10 = pms_data_list[5]


            # Read SCD4x when data is ready
            if not scd41.get_data_status():
                print("SCD4x data not ready.")
                time.sleep(5)
                continue
                    
            co2, scd_temp, scd_rh = scd41.get_measurement_value()
            print(f"SCD4x -> CO2: {co2} ppm, Temperature: {scd_temp:.2f} °C, Humidity: {scd_rh:.2f} %")
            
            # preparing payload
            payload = {
                "temperature": scd_temp,
                "humidity": scd_rh,
                "pm1": PM1,
                "pm2_5": PM2_5,
                "pm10": PM10,
                "co2": co2,
                "voc": 0, # for now
                "apiPassword": '&ng%yAYbXNTBn8D#45r43!TXNwtzZhHkFV9^UE2bS^Vhd&Ksz2LdVhtwv&uNYxAyBk&MoC'
            }
            
            # send data to server
            sendDataToServer(payload)
            
            # Wait for next cycle
            time.sleep(interval)

    except KeyboardInterrupt:
        # Stop SCD4x measurements on exit
        scd41.start_measurement(start=False, single_shot=False)
        print("Stopped SCD4x measurements. Exiting.")
    
def calibrateSensor():
    # Pin configuration for SCD4x (I2C1)
    SCD_I2C_ID = 1
    SCD_SCL_PIN = 40
    SCD_SDA_PIN = 39
    SCD_I2C_FREQ = 100_000  # 100 kHz
        
    i2c_scd = I2C(SCD_I2C_ID, scl=Pin(SCD_SCL_PIN), sda=Pin(SCD_SDA_PIN), freq=SCD_I2C_FREQ)
    i2c_adapter = I2cAdapter(i2c_scd)
    scd41 = SCD4xSensirion(adapter=i2c_adapter, this_is_scd41=True, check_crc=True)

    scd41.set_auto_calibration(value=False) # Perché quando è indor non va bene che si auto alineai
    scd41.start_measurement(start=True)
    time.sleep(15)
    co2, scd_temp, scd_rh = scd41.get_measurement_value()

    #set interval for 5 minutes because 3 min of mesureing is necessary to make the calibration succesful
    print('ora attendo 5 min')
    time.sleep(3 * 60 + 30)
    
    scd41.start_measurement(start=False, single_shot=False)

    x = scd41.force_recalibration(400) #normally concentration in the ourside air is 400ppm
    time.sleep(1)
    print('Successo:', x)

        
    body = {
        "isSuccess": x    
    }
        
    url = "http://192.168.1.32:40004/api/v0/is-calibrated"

    # headers: tell the server we’re sending JSON
    headers = {
        "Content-Type": "application/json"
    }
        
    response = urequests.post(url, data=json.dumps(body), headers=headers)
    print("Status:", response.status_code)
    print("Response:", response.text)
    response.close()   # free up sockets
        
        

        
        