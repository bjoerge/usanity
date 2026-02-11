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


class Comment:
    def __init__(self, text=""):
        self.text = text

    def __eq__(self, other):
        return isinstance(other, Comment) and self.text == other.text

    def __repr__(self):
        return "Comment(text=%r)" % self.text


class Reconnect:
    def __eq__(self, other):
        return isinstance(other, Reconnect)

    def __repr__(self):
        return "Reconnect()"


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
    _include_comments = False
    _include_reconnects = False
    _pending_reconnect = False

    def __init__(self, url, headers=None, last_event_id=None, include_comments=False, include_reconnects=False):
        self._url = url
        self._headers = headers or {}
        self._sock = None
        self._buf = bytearray()
        self._last_event_id = last_event_id
        self._retry_ms = 3000
        self._include_comments = include_comments
        self._include_reconnects = include_reconnects
        self._pending_reconnect = False
        self._connect()

    def _connect(self):
        host, port, path, use_ssl = parse_url(self._url)

        addr = socket.getaddrinfo(host, port)[0][-1]
        self._sock = socket.socket()
        self._sock.connect(addr)

        if use_ssl:
            self._sock = ssl.wrap_socket(self._sock, server_hostname=host)

        # Write HTTP request directly to socket to avoid building full string
        w = self._sock.write
        w(b"GET ")
        w(path.encode())
        w(b" HTTP/1.1\r\nHost: ")
        w(host.encode())
        w(b"\r\nAccept: text/event-stream\r\n")
        if self._last_event_id is not None:
            w(b"Last-Event-ID: ")
            w(str(self._last_event_id).encode())
            w(b"\r\n")
        for key, value in self._headers.items():
            w(key.encode())
            w(b": ")
            w(value.encode())
            w(b"\r\n")
        w(b"\r\n")

        # Skip HTTP status line and response headers
        self._read_until(b"\r\n\r\n")

    def _read_until(self, delimiter):
        while True:
            idx = self._buf.find(delimiter)
            if idx >= 0:
                end = idx + len(delimiter)
                result = bytes(self._buf[:end])
                self._buf = self._buf[end:]
                return result
            chunk = self._sock.readline()
            if not chunk:
                raise OSError("Connection closed")
            self._buf.extend(chunk)

    def _readline(self):
        """Read one line from the socket. Returns bytes (without line ending)."""
        while True:
            idx = self._buf.find(b"\n")
            if idx >= 0:
                end = idx
                if end > 0 and self._buf[end - 1] == 0x0D:
                    end -= 1
                line = bytes(self._buf[:end])
                self._buf = self._buf[idx + 1 :]
                return line
            chunk = self._sock.readline()
            if not chunk:
                raise OSError("Connection closed")
            self._buf.extend(chunk)

    def __iter__(self):
        return self

    def __next__(self):
        # Parse SSE fields inline with bytes to avoid intermediate string allocations
        event_type = None
        data_parts = []
        event_id = None
        retry = None
        has_fields = False

        while True:
            if self._pending_reconnect:
                self._pending_reconnect = False
                return Reconnect()

            try:
                line = self._readline()
            except OSError:
                self._reconnect()
                if self._include_reconnects:
                    self._pending_reconnect = True
                event_type = None
                data_parts = []
                event_id = None
                retry = None
                has_fields = False
                continue

            if not line:
                if not has_fields:
                    continue
                if retry is not None:
                    self._retry_ms = retry
                if data_parts:
                    eid = event_id.decode() if event_id is not None else None
                    event = Event(
                        event=event_type.decode() if event_type is not None else "message",
                        data=b"\n".join(data_parts).decode(),
                        id=eid,
                    )
                    if eid is not None:
                        self._last_event_id = eid
                    return event
                # Had fields but no data — reset
                event_type = None
                data_parts = []
                event_id = None
                retry = None
                has_fields = False
            elif line.startswith(b"data:"):
                data_parts.append(line[5:].lstrip(b" "))
                has_fields = True
            elif line.startswith(b"event:"):
                event_type = line[6:].lstrip(b" ")
                has_fields = True
            elif line.startswith(b"id:"):
                event_id = line[3:].lstrip(b" ")
                has_fields = True
            elif line.startswith(b"retry:"):
                val = line[6:].strip()
                if val.isdigit():
                    retry = int(val)
                has_fields = True
            elif line.startswith(b":"):
                if self._include_comments and not has_fields:
                    return Comment(line[1:].lstrip(b" ").decode())

    def _reconnect(self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self._buf = bytearray()
        while True:
            sleep(self._retry_ms / 1000)
            try:
                self._connect()
                return
            except OSError:
                pass

    def close(self):
        if self._sock:
            self._sock.close()
            self._sock = None
