import network
import time

class WlanClient:
    def __init__(self):
        # Crea l'interfaccia di rete in modalità station
        self.wlan = network.WLAN(network.STA_IF)
        # Attivala
        self.wlan.active(True)
        self._ssid = None
        self._password = None

    def connect_to_wifi(self, ssid: str, password: str, timeout: int = 15) -> bool:
        """Prova a connettersi alla rete SSID con password.
        Ritorna True se va a buon fine entro timeout secondi."""
        self._ssid = ssid
        self._password = password
        if self.wlan.isconnected():
            return True
        self.wlan.disconnect()
        self.wlan.connect(ssid, password)
        start = time.time()
        while not self.wlan.isconnected():
            if time.time() - start > timeout:
                return False
            time.sleep_ms(100)
        return True

    def is_connected(self, timeout: int = 5) -> bool:
        """Controlla se siamo connessi (aspetta fino a timeout secondi)."""
        start = time.time()
        while not self.wlan.isconnected():
            if time.time() - start > timeout:
                return False
            time.sleep_ms(100)
        return True

    def scan_for_ssid(self):
        """Ritorna la lista di SSID disponibili."""
        nets = self.wlan.scan()
        return [net[0].decode('utf-8', 'ignore') for net in nets]

    def get_connection_data(self):
        """Ritorna (ip, subnet, gateway, DNS) se connesso, altrimenti None."""
        if self.wlan.isconnected():
            return self.wlan.ifconfig()
        return None
    
    def disconnect(self):
        """Disconnects from Wi-Fi and deactivates STA interface."""
        if self.wlan.isconnected():
            self.wlan.disconnect()
        self.wlan.active(False)
