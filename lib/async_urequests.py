import uasyncio as asyncio

HTTP__version__ = "1.1"


class Response:

    def __init__(self, reader, chunked, charset, h):
        self.raw = reader
        self.chunked = chunked
        self.encoder = charset
        self.h = h
        self.chunk_size = 0
        self._headers_dict = None

    async def read(self, sz=4096):
        parts = []
        # keep reading chunked data
        if self.chunked:
            while True:
                if self.chunk_size == 0:
                    l = await self.raw.readline()  # get Hex size
                    l = l.split(b";", 1)[0]
                    self.chunk_size = int(l, 16)  # convert to int
                    if self.chunk_size == 0:  # end of message
                        sep = await self.raw.read(2)
                        assert sep == b"\r\n"
                        break
                data = await self.raw.read(min(sz, self.chunk_size))
                self.chunk_size -= len(data)
                parts.append(data)
                if self.chunk_size == 0:
                    sep = await self.raw.read(2)
                    assert sep == b"\r\n"
        # non chunked data
        else:
            while True:
                data = await self.raw.read(sz)
                if not data or data == b"":
                    break
                parts.append(data)
        return b"".join(parts)

    @property
    def text(self):
        return str(self.content, self.encoder)

    @property
    def headers(self):
        if self._headers_dict is None:
            result = {}
            for i in self.h:
                h = i.decode(self.encoder).strip().split(":", 1)
                result[h[0]] = h[-1].strip()
            self._headers_dict = result
        return self._headers_dict

    def json(self):
        import ujson
        return ujson.loads(self.content)

    def close(self):
        pass

    def __repr__(self):
        return "<Response [%d]>" % (self.status_code)


async def _request_raw(method, url, headers, data, json):
    try:
        proto, dummy, host, path = url.split("/", 3)
    except ValueError:
        proto, dummy, host = url.split("/", 2)
        path = ""
    try:
        host, port = host.split(":")
        if proto == "https:":
            ssl = True
        elif proto == "http:":
            ssl = False
        else:
            raise ValueError("Unsupported protocol: %s" % (proto))
    except ValueError:
        if proto == "http:":
            port = 80
            ssl = False
        elif proto == "https:":
            port = 443
            ssl = True
        else:
            raise ValueError("Unsupported protocol: %s" % (proto))

    reader, writer = await asyncio.open_connection(host, int(port), ssl=ssl)

    if json is not None:
        assert data is None
        import ujson
        data = ujson.dumps(json)

    parts = [
        method, " /", path, " HTTP/", HTTP__version__,
        "\r\nHost: ", host,
        "\r\nConnection: close\r\n",
        headers,
    ]
    if "User-Agent:" not in headers:
        parts.append("User-Agent: compat\r\n")
    if json is not None and "Content-Type:" not in headers:
        parts.append("Content-Type: application/json\r\n")
    if data and "Content-Length:" not in headers:
        parts.append("Content-Length: %d\r\n" % len(data))
    parts.append("\r\n")

    await writer.awrite("".join(parts).encode())
    if data:
        await writer.awrite(data.encode() if isinstance(data, str) else data)
    return reader


async def _requests(method, url, data=None, headers={}, json=None):
    # headers support
    h_parts = []
    for k in headers:
        h_parts.append(k)
        h_parts.append(": ")
        h_parts.append(headers[k])
        h_parts.append("\r\n")
    h = "".join(h_parts)

    reader = await _request_raw(method=method, url=url, headers=h, data=data, json=json)
    try:
        sline = await reader.readline()
        sline = sline.split(None, 2)
        status_code = int(sline[1])
        if len(sline) > 1:
            reason = sline[2].decode().rstrip()
        chunked = False
        resp_headers = []
        charset = 'utf-8'
        # read headers
        while True:
            line = await reader.readline()
            if not line or line == b"\r\n":
                break
            resp_headers.append(line)
            if line.startswith(b"Transfer-Encoding:"):
                if b"chunked" in line:
                    chunked = True
            elif line.startswith(b"Content-Type:"):
                if b"charset" in line:
                    charset = line.rstrip().decode().split(None, 2)[-1].split("=")[-1]

        resp = Response(reader, chunked, charset, resp_headers)
        resp.content = await resp.read()
        resp.status_code = status_code
        resp.reason = reason
        resp.url = url
        return resp
    finally:
        try:
            await reader.wait_closed()
        except NameError:
            pass


async def get(url, timeout=10, **kwargs):
    return await asyncio.wait_for(_requests("GET", url, **kwargs), timeout=timeout)


async def post(url, timeout=10, **kwargs):
    return await asyncio.wait_for(_requests("POST", url, **kwargs), timeout=timeout)