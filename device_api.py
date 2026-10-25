"""Small, cooperative HTTP API for the ESP32 device."""

import json
import socket


class DeviceApiServer:
    """Serve the two device-management endpoints from the main loop."""

    def __init__(self, host, port, health_callback, wifi_callback, api_key):
        self._health_callback = health_callback
        self._wifi_callback = wifi_callback
        self._api_key = api_key
        self._server = socket.socket()
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((host, port))
        self._server.listen(1)
        self._server.setblocking(False)

    def close(self):
        self._server.close()

    def poll(self):
        """Handle at most one short request; call this from the main loop."""
        try:
            client, _ = self._server.accept()
        except OSError:
            return

        try:
            client.settimeout(0.2)
            request = self._read_request(client)
            if request is None:
                self._respond(client, 400, {"error": "invalid request"})
                return

            method, path, headers, body = request
            if method == "GET" and path == "/health":
                self._respond(client, 200, self._health_callback())
                return

            if method == "POST" and path == "/wifi":
                if headers.get("x-api-key") != self._api_key:
                    self._respond(client, 401, {"error": "unauthorized"})
                    return
                self._handle_wifi(client, body)
                return

            self._respond(client, 404, {"error": "not found"})
        except Exception as error:
            self._respond(client, 500, {"error": str(error)})
        finally:
            client.close()

    @staticmethod
    def _read_request(client):
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 2048:
            try:
                chunk = client.recv(512)
            except OSError:
                return None
            if not chunk:
                break
            data += chunk

        separator = data.find(b"\r\n\r\n")
        if separator < 0:
            return None

        header_bytes = data[:separator].split(b"\r\n")
        try:
            method, path, _ = header_bytes[0].decode().split(" ", 2)
        except ValueError:
            return None

        headers = {}
        for line in header_bytes[1:]:
            if b":" in line:
                key, value = line.split(b":", 1)
                headers[key.decode().lower()] = value.decode().strip()

        body = data[separator + 4:]
        content_length = int(headers.get("content-length", "0"))
        while len(body) < content_length:
            try:
                chunk = client.recv(min(512, content_length - len(body)))
            except OSError:
                return None
            if not chunk:
                return None
            body += chunk

        return method, path, headers, body[:content_length]

    def _handle_wifi(self, client, body):
        try:
            values = json.loads(body.decode())
            ssid = values["ssid"]
            password = values["password"]
            if not isinstance(ssid, str) or not isinstance(password, str):
                raise ValueError("ssid and password must be strings")
            if not ssid or len(ssid) > 64 or len(password) > 128:
                raise ValueError("invalid credential length")
        except (KeyError, TypeError, ValueError, UnicodeError) as error:
            self._respond(client, 400, {"error": str(error)})
            return

        result = self._wifi_callback(ssid, password)
        self._respond(client, 200, result)

    @staticmethod
    def _respond(client, status_code, payload):
        reason = {
            200: "OK",
            400: "Bad Request",
            401: "Unauthorized",
            404: "Not Found",
            500: "Internal Server Error",
        }.get(status_code, "Error")
        body = json.dumps(payload).encode()
        response = (
            "HTTP/1.1 {} {}\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: {}\r\n"
            "Connection: close\r\n\r\n"
        ).format(status_code, reason, len(body)).encode() + body
        client.send(response)
