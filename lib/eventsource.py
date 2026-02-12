try:
    from uasyncio import sleep, open_connection
except ImportError:
    from asyncio import sleep, open_connection


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
    _debug = None

    def __init__(self, url, headers=None, last_event_id=None, include_comments=False, include_reconnects=False, debug=None):
        self._url = url
        self._headers = headers or {}
        self._reader = None
        self._writer = None
        self._last_event_id = last_event_id
        self._retry_ms = 3000
        self._include_comments = include_comments
        self._include_reconnects = include_reconnects
        self._pending_reconnect = False
        self._debug = debug

    async def _connect(self):
        host, port, path, use_ssl = parse_url(self._url)

        self._reader, self._writer = await open_connection(
            host, port, ssl=use_ssl, server_hostname=host if use_ssl else None
        )

        # Write HTTP request
        w = self._writer
        w.write(b"GET ")
        w.write(path.encode())
        w.write(b" HTTP/1.1\r\nHost: ")
        w.write(host.encode())
        w.write(b"\r\nAccept: text/event-stream\r\n")
        if self._last_event_id is not None:
            w.write(b"Last-Event-ID: ")
            w.write(str(self._last_event_id).encode())
            w.write(b"\r\n")
        for key, value in self._headers.items():
            w.write(key.encode())
            w.write(b": ")
            w.write(value.encode())
            w.write(b"\r\n")
        w.write(b"\r\n")
        await w.drain()

        # Skip HTTP status line and response headers
        await self._skip_headers()

    async def _skip_headers(self):
        while True:
            line = await self._reader.readline()
            if not line:
                raise OSError("Connection closed")
            if line == b"\r\n" or line == b"\n":
                return

    async def _readline(self):
        """Read one line from the stream. Returns bytes (without line ending)."""
        line = await self._reader.readline()
        if not line:
            raise OSError("Connection closed")
        # Strip \r\n or \n
        if line.endswith(b"\r\n"):
            return line[:-2]
        if line.endswith(b"\n"):
            return line[:-1]
        return line

    def __aiter__(self):
        return self

    async def __anext__(self):
        # Lazy connect on first iteration
        if self._reader is None:
            await self._connect()

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
                line = await self._readline()
                if self._debug:
                    self._debug(line)
            except OSError:
                await self._reconnect()
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

    async def _reconnect(self):
        if self._writer:
            try:
                self._writer.close()
            except Exception:
                pass
            self._writer = None
        self._reader = None
        while True:
            await sleep(self._retry_ms / 1000)
            try:
                await self._connect()
                return
            except OSError:
                pass

    def close(self):
        if self._writer:
            self._writer.close()
            self._writer = None
        self._reader = None
