try:
    import usocket as socket
except ImportError:
    import socket

try:
    import ussl as ssl
except ImportError:
    import ssl

try:
    from utime import sleep
except ImportError:
    from time import sleep


class Event:
    def __init__(self, event="message", data="", id=None):
        self.event = event
        self.data = data
        self.id = id

    def __eq__(self, other):
        return (
            isinstance(other, Event)
            and self.event == other.event
            and self.data == other.data
            and self.id == other.id
        )

    def __repr__(self):
        return "Event(event=%r, data=%r, id=%r)" % (self.event, self.data, self.id)


def parse_url(url):
    proto, rest = url.split("://", 1)
    use_ssl = proto == "https"
    port = 443 if use_ssl else 80
    if "/" in rest:
        host_part, path = rest.split("/", 1)
        path = "/" + path
    else:
        host_part = rest
        path = "/"
    if ":" in host_part:
        host, port_str = host_part.split(":", 1)
        port = int(port_str)
    else:
        host = host_part
    return host, port, path, use_ssl


def parse_sse_lines(lines):
    """Parse accumulated SSE lines into an (event_or_none, retry_or_none) tuple."""
    event_type = "message"
    data_parts = []
    event_id = None
    retry = None

    for line in lines:
        if line.startswith("data:"):
            data_parts.append(line[5:].lstrip(" "))
        elif line.startswith("event:"):
            event_type = line[6:].lstrip(" ")
        elif line.startswith("id:"):
            event_id = line[3:].lstrip(" ")
        elif line.startswith("retry:"):
            val = line[6:].strip()
            if val.isdigit():
                retry = int(val)
        elif line.startswith(":"):
            continue

    if not data_parts:
        return None, retry

    return Event(event=event_type, data="\n".join(data_parts), id=event_id), retry


class EventSource:
    def __init__(self, url, headers=None, last_event_id=None):
        self._url = url
        self._headers = headers or {}
        self._sock = None
        self._buf = b""
        self._last_event_id = last_event_id
        self._retry_ms = 3000
        self._connect()

    def _connect(self):
        host, port, path, use_ssl = parse_url(self._url)

        addr = socket.getaddrinfo(host, port)[0][-1]
        self._sock = socket.socket()
        self._sock.connect(addr)

        if use_ssl:
            self._sock = ssl.wrap_socket(self._sock, server_hostname=host)

        # Build HTTP request
        request = f"GET {path} HTTP/1.1\r\n"
        request += f"Host: {host}\r\n"
        request += "Accept: text/event-stream\r\n"
        if self._last_event_id is not None:
            request += f"Last-Event-ID: {self._last_event_id}\r\n"
        for key, value in self._headers.items():
            request += f"{key}: {value}\r\n"
        request += "\r\n"

        self._sock.write(request.encode())

        # Skip HTTP status line and response headers
        self._read_until(b"\r\n\r\n")

    def _read_until(self, delimiter):
        while delimiter not in self._buf:
            chunk = self._sock.read(512)
            if not chunk:
                raise OSError("Connection closed")
            self._buf += chunk
        idx = self._buf.index(delimiter) + len(delimiter)
        result = self._buf[:idx]
        self._buf = self._buf[idx:]
        return result

    def _readline(self):
        while b"\n" not in self._buf:
            chunk = self._sock.read(512)
            if not chunk:
                raise OSError("Connection closed")
            self._buf += chunk
        idx = self._buf.index(b"\n") + 1
        line = self._buf[:idx]
        self._buf = self._buf[idx:]
        return line.rstrip(b"\r\n").decode()

    def __iter__(self):
        return self

    def __next__(self):
        lines = []
        while True:
            try:
                line = self._readline()
            except OSError:
                self._reconnect()
                lines = []
                continue
            if line == "":
                event, retry = parse_sse_lines(lines)
                if retry is not None:
                    self._retry_ms = retry
                if event is not None:
                    if event.id is not None:
                        self._last_event_id = event.id
                    return event
                lines = []
            else:
                lines.append(line)

    def _reconnect(self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self._buf = b""
        sleep(self._retry_ms / 1000)
        self._connect()

    def close(self):
        if self._sock:
            self._sock.close()
            self._sock = None
