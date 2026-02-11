from lib.eventsource import Comment, Event, EventSource, Reconnect, parse_sse_lines, parse_url
from test_helpers import expect_equal


def test_parse_url_https():
    host, port, path, use_ssl = parse_url(
        "https://abc.api.sanity.io/v2023-03-10/data/listen/production?query=*"
    )
    expect_equal(host, "abc.api.sanity.io")
    expect_equal(port, 443)
    expect_equal(path, "/v2023-03-10/data/listen/production?query=*")
    expect_equal(use_ssl, True)


def test_parse_url_http():
    host, port, path, use_ssl = parse_url("http://localhost:3000/events")
    expect_equal(host, "localhost")
    expect_equal(port, 3000)
    expect_equal(path, "/events")
    expect_equal(use_ssl, False)


def test_parse_url_no_path():
    host, port, path, use_ssl = parse_url("https://example.com")
    expect_equal(host, "example.com")
    expect_equal(port, 443)
    expect_equal(path, "/")
    expect_equal(use_ssl, True)


def test_parse_simple_data():
    lines = ["data: hello"]
    event, retry = parse_sse_lines(lines)
    expect_equal(event, Event(event="message", data="hello"))
    expect_equal(retry, None)


def test_parse_multiline_data():
    lines = ["data: line1", "data: line2", "data: line3"]
    event, retry = parse_sse_lines(lines)
    expect_equal(event, Event(event="message", data="line1\nline2\nline3"))
    expect_equal(retry, None)


def test_parse_event_type():
    lines = ["event: mutation", 'data: {"documentId": "abc"}']
    event, retry = parse_sse_lines(lines)
    expect_equal(event, Event(event="mutation", data='{"documentId": "abc"}'))


def test_parse_event_id():
    lines = ["id: 42", "data: something"]
    event, retry = parse_sse_lines(lines)
    expect_equal(event, Event(event="message", data="something", id="42"))


def test_parse_all_fields():
    lines = ["event: update", "id: evt-1", "data: payload"]
    event, retry = parse_sse_lines(lines)
    expect_equal(event, Event(event="update", data="payload", id="evt-1"))


def test_parse_comment_ignored():
    lines = [": this is a comment", "data: actual"]
    event, retry = parse_sse_lines(lines)
    expect_equal(event, Event(event="message", data="actual"))


def test_parse_no_data_returns_none():
    lines = ["event: ping"]
    event, retry = parse_sse_lines(lines)
    expect_equal(event, None)


def test_parse_empty_data():
    lines = ["data:"]
    event, retry = parse_sse_lines(lines)
    expect_equal(event, Event(event="message", data=""))


def test_parse_data_no_space_after_colon():
    lines = ["data:nospace"]
    event, retry = parse_sse_lines(lines)
    expect_equal(event, Event(event="message", data="nospace"))


def test_event_repr():
    e = Event(event="mutation", data="test", id="1")
    expect_equal(repr(e), "Event(event='mutation', data='test', id='1')")


def test_event_equality():
    a = Event(event="message", data="hello", id="1")
    b = Event(event="message", data="hello", id="1")
    expect_equal(a, b)
    expect_equal(a == "not an event", False)


# --- retry: field parsing ---


def test_parse_retry_field():
    lines = ["retry: 5000", "data: hello"]
    event, retry = parse_sse_lines(lines)
    expect_equal(event, Event(event="message", data="hello"))
    expect_equal(retry, 5000)


def test_parse_retry_without_data():
    lines = ["retry: 2000"]
    event, retry = parse_sse_lines(lines)
    expect_equal(event, None)
    expect_equal(retry, 2000)


def test_parse_retry_non_numeric_ignored():
    lines = ["retry: abc", "data: hello"]
    event, retry = parse_sse_lines(lines)
    expect_equal(event, Event(event="message", data="hello"))
    expect_equal(retry, None)


# --- EventSource reconnection ---

class FakeSocket:
    """A fake socket that yields pre-defined chunks and then raises OSError."""
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self._closed = False
        self.written = []
        self._rbuf = b""

    def read(self, n):
        if not self._chunks:
            raise OSError("Connection closed")
        return self._chunks.pop(0)

    def readline(self):
        while b"\n" not in self._rbuf:
            if not self._chunks:
                if self._rbuf:
                    data = self._rbuf
                    self._rbuf = b""
                    return data
                raise OSError("Connection closed")
            self._rbuf += self._chunks.pop(0)
        idx = self._rbuf.index(b"\n")
        line = self._rbuf[:idx + 1]
        self._rbuf = self._rbuf[idx + 1:]
        return line

    def write(self, data):
        self.written.append(data)

    def close(self):
        self._closed = True

    def connect(self, addr):
        pass


def fake_socket_module(make_socket):
    """Create a fake socket module that returns sockets from the given factory."""
    class Module:
        @staticmethod
        def getaddrinfo(host, port):
            return [("", "", "", "", ("127.0.0.1", port))]
        socket = staticmethod(make_socket)
    return Module


def test_last_event_id_tracked():
    """After receiving an event with id, _last_event_id is updated."""
    # Build a stream: HTTP headers + SSE event with id
    stream = b"HTTP/1.1 200 OK\r\n\r\nid: abc-123\r\ndata: hello\r\n\r\n"
    sock = FakeSocket([stream])

    es = EventSource.__new__(EventSource)
    es._url = "http://localhost/events"
    es._headers = {}
    es._sock = sock
    es._buf = bytearray()
    es._last_event_id = None
    es._retry_ms = 3000

    # Skip connect — manually read headers
    es._read_until(b"\r\n\r\n")

    event = next(es)
    expect_equal(event, Event(event="message", data="hello", id="abc-123"))
    expect_equal(es._last_event_id, "abc-123")


def test_last_event_id_not_updated_without_id():
    """Events without id field don't change _last_event_id."""
    stream = b"HTTP/1.1 200 OK\r\n\r\ndata: hello\r\n\r\n"
    sock = FakeSocket([stream])

    es = EventSource.__new__(EventSource)
    es._url = "http://localhost/events"
    es._headers = {}
    es._sock = sock
    es._buf = bytearray()
    es._last_event_id = "previous"
    es._retry_ms = 3000

    es._read_until(b"\r\n\r\n")

    event = next(es)
    expect_equal(event, Event(event="message", data="hello"))
    expect_equal(es._last_event_id, "previous")


def test_retry_field_updates_retry_ms():
    """retry: field updates _retry_ms on the EventSource instance."""
    stream = b"HTTP/1.1 200 OK\r\n\r\nretry: 5000\r\ndata: hello\r\n\r\n"
    sock = FakeSocket([stream])

    es = EventSource.__new__(EventSource)
    es._url = "http://localhost/events"
    es._headers = {}
    es._sock = sock
    es._buf = bytearray()
    es._last_event_id = None
    es._retry_ms = 3000

    es._read_until(b"\r\n\r\n")

    event = next(es)
    expect_equal(event, Event(event="message", data="hello"))
    expect_equal(es._retry_ms, 5000)


def test_last_event_id_header_sent_on_connect():
    """_connect sends Last-Event-ID header when _last_event_id is set."""
    import lib.eventsource as es_mod

    sock = FakeSocket([b"HTTP/1.1 200 OK\r\n\r\n"])
    original_socket = es_mod.socket
    es_mod.socket = fake_socket_module(lambda: sock)

    try:
        es = EventSource.__new__(EventSource)
        es._url = "http://localhost/events"
        es._headers = {"Authorization": "Bearer tok"}
        es._sock = None
        es._buf = bytearray()
        es._last_event_id = "evt-42"
        es._retry_ms = 3000
        es._connect()

        request_str = b"".join(sock.written).decode()
        expect_equal("Last-Event-ID: evt-42\r\n" in request_str, True)
        expect_equal("Authorization: Bearer tok\r\n" in request_str, True)
    finally:
        es_mod.socket = original_socket


def test_no_last_event_id_header_when_none():
    """_connect does not send Last-Event-ID header when _last_event_id is None."""
    import lib.eventsource as es_mod

    sock = FakeSocket([b"HTTP/1.1 200 OK\r\n\r\n"])
    original_socket = es_mod.socket
    es_mod.socket = fake_socket_module(lambda: sock)

    try:
        es = EventSource.__new__(EventSource)
        es._url = "http://localhost/events"
        es._headers = {}
        es._sock = None
        es._buf = bytearray()
        es._last_event_id = None
        es._retry_ms = 3000
        es._connect()

        request_str = b"".join(sock.written).decode()
        expect_equal("Last-Event-ID" in request_str, False)
    finally:
        es_mod.socket = original_socket


def test_reconnect_on_connection_drop():
    """EventSource reconnects after connection drops and continues reading events."""
    import lib.eventsource as es_mod

    # Track sleep calls and connection count
    sleep_calls = []
    connect_count = [0]
    original_sleep = es_mod.sleep

    def fake_sleep(secs):
        sleep_calls.append(secs)

    es_mod.sleep = fake_sleep

    # First connection: delivers one event then drops
    # Second connection: delivers another event
    stream1 = b"id: 1\r\ndata: first\r\n\r\n"
    stream2_headers = b"HTTP/1.1 200 OK\r\n\r\n"
    stream2 = b"id: 2\r\ndata: second\r\n\r\n"

    sock1 = FakeSocket([stream1])  # will OSError after stream1 is consumed
    sock2 = FakeSocket([stream2_headers, stream2])

    sockets = [sock2]  # sock1 is already in use; sock2 for reconnect

    original_socket = es_mod.socket

    def make_socket():
        connect_count[0] += 1
        return sockets.pop(0)

    es_mod.socket = fake_socket_module(make_socket)

    try:
        es = EventSource.__new__(EventSource)
        es._url = "http://localhost/events"
        es._headers = {}
        es._sock = sock1
        es._buf = bytearray()
        es._last_event_id = None
        es._retry_ms = 3000

        # First event
        event1 = next(es)
        expect_equal(event1, Event(event="message", data="first", id="1"))
        expect_equal(es._last_event_id, "1")

        # Second next() will hit OSError from sock1, reconnect, read from sock2
        event2 = next(es)
        expect_equal(event2, Event(event="message", data="second", id="2"))
        expect_equal(es._last_event_id, "2")

        # Verify sleep was called with default retry
        expect_equal(sleep_calls, [3.0])
        expect_equal(connect_count[0], 1)  # one reconnection via _connect
    finally:
        es_mod.sleep = original_sleep
        es_mod.socket = original_socket


def test_reconnect_sends_last_event_id():
    """On reconnect, Last-Event-ID header is sent with the last received id."""
    import lib.eventsource as es_mod

    sleep_calls = []
    original_sleep = es_mod.sleep

    def fake_sleep(secs):
        sleep_calls.append(secs)

    es_mod.sleep = fake_sleep

    stream2_headers = b"HTTP/1.1 200 OK\r\n\r\n"
    stream2 = b"data: after-reconnect\r\n\r\n"

    reconnect_sock = FakeSocket([stream2_headers, stream2])
    original_socket = es_mod.socket
    es_mod.socket = fake_socket_module(lambda: reconnect_sock)

    try:
        # Create an EventSource that already has a last_event_id and an empty socket
        sock1 = FakeSocket([])  # immediately raises OSError
        es = EventSource.__new__(EventSource)
        es._url = "http://localhost/events"
        es._headers = {}
        es._sock = sock1
        es._buf = bytearray()
        es._last_event_id = "evt-99"
        es._retry_ms = 1000

        event = next(es)
        expect_equal(event, Event(event="message", data="after-reconnect"))

        # Verify Last-Event-ID was sent
        request_str = b"".join(reconnect_sock.written).decode()
        expect_equal("Last-Event-ID: evt-99\r\n" in request_str, True)

        # Verify sleep used correct retry
        expect_equal(sleep_calls, [1.0])
    finally:
        es_mod.sleep = original_sleep
        es_mod.socket = original_socket


def test_reconnect_retries_on_network_error():
    """Reconnect retries when _connect raises OSError (e.g. EHOSTUNREACH)."""
    import lib.eventsource as es_mod

    sleep_calls = []
    original_sleep = es_mod.sleep
    es_mod.sleep = lambda secs: sleep_calls.append(secs)

    connect_attempts = [0]
    good_sock = FakeSocket([b"HTTP/1.1 200 OK\r\n\r\n", b"data: back online\r\n\r\n"])

    def make_socket():
        connect_attempts[0] += 1
        if connect_attempts[0] <= 2:
            raise OSError("EHOSTUNREACH")
        return good_sock

    original_socket = es_mod.socket
    es_mod.socket = fake_socket_module(make_socket)

    try:
        sock1 = FakeSocket([])  # immediately raises OSError
        es = EventSource.__new__(EventSource)
        es._url = "http://localhost/events"
        es._headers = {}
        es._sock = sock1
        es._buf = bytearray()
        es._last_event_id = None
        es._retry_ms = 1000
        es._include_comments = False

        event = next(es)
        expect_equal(event, Event(event="message", data="back online"))
        expect_equal(connect_attempts[0], 3)  # 2 failures + 1 success
        expect_equal(sleep_calls, [1.0, 1.0, 1.0])
    finally:
        es_mod.sleep = original_sleep
        es_mod.socket = original_socket


def test_reconnect_yields_reconnect_when_enabled():
    """When include_reconnects is True, a Reconnect is yielded after reconnecting."""
    import lib.eventsource as es_mod

    original_sleep = es_mod.sleep
    es_mod.sleep = lambda secs: None

    reconnect_sock = FakeSocket([b"HTTP/1.1 200 OK\r\n\r\n", b"data: hello\r\n\r\n"])
    original_socket = es_mod.socket
    es_mod.socket = fake_socket_module(lambda: reconnect_sock)

    try:
        sock1 = FakeSocket([])  # immediately raises OSError
        es = EventSource.__new__(EventSource)
        es._url = "http://localhost/events"
        es._headers = {}
        es._sock = sock1
        es._buf = bytearray()
        es._last_event_id = None
        es._retry_ms = 1000
        es._include_comments = False
        es._include_reconnects = True
        es._pending_reconnect = False

        msg = next(es)
        expect_equal(msg, Reconnect())
        expect_equal(msg.is_reconnect, True)
        expect_equal(msg.is_comment, False)

        event = next(es)
        expect_equal(event, Event(event="message", data="hello"))
        expect_equal(event.is_reconnect, False)
    finally:
        es_mod.sleep = original_sleep
        es_mod.socket = original_socket


def test_reconnect_not_yielded_by_default():
    """When include_reconnects is False (default), no Reconnect is yielded."""
    import lib.eventsource as es_mod

    original_sleep = es_mod.sleep
    es_mod.sleep = lambda secs: None

    reconnect_sock = FakeSocket([b"HTTP/1.1 200 OK\r\n\r\n", b"data: hello\r\n\r\n"])
    original_socket = es_mod.socket
    es_mod.socket = fake_socket_module(lambda: reconnect_sock)

    try:
        sock1 = FakeSocket([])  # immediately raises OSError
        es = EventSource.__new__(EventSource)
        es._url = "http://localhost/events"
        es._headers = {}
        es._sock = sock1
        es._buf = bytearray()
        es._last_event_id = None
        es._retry_ms = 1000
        es._include_comments = False
        es._include_reconnects = False
        es._pending_reconnect = False

        # Should skip straight to the event, no Reconnect
        event = next(es)
        expect_equal(event, Event(event="message", data="hello"))
    finally:
        es_mod.sleep = original_sleep
        es_mod.socket = original_socket


def test_multiple_events_in_order():
    """Multiple events in a stream are yielded in correct order."""
    stream = (
        b"HTTP/1.1 200 OK\r\n\r\n"
        b"event: welcome\r\ndata: {}\r\n\r\n"
        b'event: mutation\r\nid: tx1\r\ndata: {"doc":"A"}\r\n\r\n'
        b'event: mutation\r\nid: tx2\r\ndata: {"doc":"B"}\r\n\r\n'
    )
    sock = FakeSocket([stream])

    es = EventSource.__new__(EventSource)
    es._url = "http://localhost/events"
    es._headers = {}
    es._sock = sock
    es._buf = bytearray()
    es._last_event_id = None
    es._retry_ms = 3000

    es._read_until(b"\r\n\r\n")

    e1 = next(es)
    expect_equal(e1, Event(event="welcome", data="{}"))

    e2 = next(es)
    expect_equal(e2, Event(event="mutation", data='{"doc":"A"}', id="tx1"))

    e3 = next(es)
    expect_equal(e3, Event(event="mutation", data='{"doc":"B"}', id="tx2"))


def test_multiple_events_chunked_delivery():
    """Events delivered across multiple read() chunks are still in order."""
    # Simulate event terminator arriving with next event's data
    chunks = [
        b"HTTP/1.1 200 OK\r\n\r\nevent: welcome\r\ndata: {}\r\n",
        b"\r\nevent: mutation\r\nid: tx1\r\ndata: {\"doc\":\"A\"}\r\n",
        b"\r\nevent: mutation\r\nid: tx2\r\ndata: {\"doc\":\"B\"}\r\n\r\n",
    ]
    sock = FakeSocket(chunks)

    es = EventSource.__new__(EventSource)
    es._url = "http://localhost/events"
    es._headers = {}
    es._sock = sock
    es._buf = bytearray()
    es._last_event_id = None
    es._retry_ms = 3000

    es._read_until(b"\r\n\r\n")

    e1 = next(es)
    expect_equal(e1, Event(event="welcome", data="{}"))

    e2 = next(es)
    expect_equal(e2, Event(event="mutation", data='{"doc":"A"}', id="tx1"))

    e3 = next(es)
    expect_equal(e3, Event(event="mutation", data='{"doc":"B"}', id="tx2"))


def test_comment_ignored_by_default():
    """Comment lines are ignored when include_comments is False."""
    stream = b"HTTP/1.1 200 OK\r\n\r\n: heartbeat\r\ndata: hello\r\n\r\n"
    sock = FakeSocket([stream])

    es = EventSource.__new__(EventSource)
    es._url = "http://localhost/events"
    es._headers = {}
    es._sock = sock
    es._buf = bytearray()
    es._last_event_id = None
    es._retry_ms = 3000
    es._include_comments = False

    es._read_until(b"\r\n\r\n")

    event = next(es)
    expect_equal(event, Event(event="message", data="hello"))


def test_comment_yielded_when_enabled():
    """Comment lines yield Comment instances when include_comments is True."""
    stream = b"HTTP/1.1 200 OK\r\n\r\n: keepalive\r\ndata: hello\r\n\r\n"
    sock = FakeSocket([stream])

    es = EventSource.__new__(EventSource)
    es._url = "http://localhost/events"
    es._headers = {}
    es._sock = sock
    es._buf = bytearray()
    es._last_event_id = None
    es._retry_ms = 3000
    es._include_comments = True

    es._read_until(b"\r\n\r\n")

    msg = next(es)
    expect_equal(msg, Comment("keepalive"))
    expect_equal(msg.is_comment, True)

    event = next(es)
    expect_equal(event, Event(event="message", data="hello"))
    expect_equal(event.is_comment, False)


def test_comment_empty():
    """Empty comment line (just ':') yields Comment with empty text."""
    stream = b"HTTP/1.1 200 OK\r\n\r\n:\r\ndata: hello\r\n\r\n"
    sock = FakeSocket([stream])

    es = EventSource.__new__(EventSource)
    es._url = "http://localhost/events"
    es._headers = {}
    es._sock = sock
    es._buf = bytearray()
    es._last_event_id = None
    es._retry_ms = 3000
    es._include_comments = True

    es._read_until(b"\r\n\r\n")

    msg = next(es)
    expect_equal(msg, Comment(""))

    event = next(es)
    expect_equal(event, Event(event="message", data="hello"))


def test_comment_mid_event_ignored():
    """Comment lines mid-event are ignored even when include_comments is True."""
    stream = b"HTTP/1.1 200 OK\r\n\r\nevent: mutation\r\n: mid-comment\r\ndata: payload\r\n\r\n"
    sock = FakeSocket([stream])

    es = EventSource.__new__(EventSource)
    es._url = "http://localhost/events"
    es._headers = {}
    es._sock = sock
    es._buf = bytearray()
    es._last_event_id = None
    es._retry_ms = 3000
    es._include_comments = True

    es._read_until(b"\r\n\r\n")

    event = next(es)
    expect_equal(event, Event(event="mutation", data="payload"))


def test_constructor_last_event_id():
    """Constructor accepts last_event_id param and sends it on initial connect."""
    import lib.eventsource as es_mod

    sock = FakeSocket([b"HTTP/1.1 200 OK\r\n\r\n"])
    original_socket = es_mod.socket
    es_mod.socket = fake_socket_module(lambda: sock)

    try:
        es = EventSource("http://localhost/events", last_event_id="resume-123")
        request_str = b"".join(sock.written).decode()
        expect_equal("Last-Event-ID: resume-123\r\n" in request_str, True)
        expect_equal(es._last_event_id, "resume-123")
        expect_equal(es._retry_ms, 3000)
    finally:
        es_mod.socket = original_socket
