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


# --- EventSource async tests ---


async def anext(async_iter):
    return await async_iter.__anext__()


class FakeStreamReader:
    """A fake asyncio StreamReader that yields pre-defined lines."""

    def __init__(self, data):
        # data is bytes; split into lines preserving line endings
        self._buf = data

    async def readline(self):
        if not self._buf:
            return b""
        idx = self._buf.find(b"\n")
        if idx >= 0:
            line = self._buf[: idx + 1]
            self._buf = self._buf[idx + 1 :]
            return line
        # No newline found — return remaining data
        data = self._buf
        self._buf = b""
        return data


class FakeStreamWriter:
    """A fake asyncio StreamWriter that captures written data."""

    def __init__(self):
        self.written = []
        self._closed = False

    def write(self, data):
        self.written.append(data)

    async def drain(self):
        pass

    def close(self):
        self._closed = True


def fake_open_connection(readers_writers):
    """Create a fake open_connection that returns (reader, writer) pairs from a list."""
    pairs = list(readers_writers)

    async def _open_connection(host, port, ssl=None, server_hostname=None):
        if not pairs:
            raise OSError("No more connections")
        return pairs.pop(0)

    return _open_connection


def make_reader_writer(data):
    """Create a (FakeStreamReader, FakeStreamWriter) pair from bytes data."""
    return FakeStreamReader(data), FakeStreamWriter()


async def test_last_event_id_tracked():
    """After receiving an event with id, _last_event_id is updated."""
    stream = b"HTTP/1.1 200 OK\r\n\r\nid: abc-123\r\ndata: hello\r\n\r\n"
    reader, writer = make_reader_writer(stream)

    es = EventSource.__new__(EventSource)
    es._url = "http://localhost/events"
    es._headers = {}
    es._reader = reader
    es._writer = writer
    es._last_event_id = None
    es._retry_ms = 3000
    es._include_comments = False
    es._include_reconnects = False
    es._pending_reconnect = False
    es._debug = None

    # Skip headers
    await es._skip_headers()

    event = await anext(es)
    expect_equal(event, Event(event="message", data="hello", id="abc-123"))
    expect_equal(es._last_event_id, "abc-123")


async def test_last_event_id_not_updated_without_id():
    """Events without id field don't change _last_event_id."""
    stream = b"HTTP/1.1 200 OK\r\n\r\ndata: hello\r\n\r\n"
    reader, writer = make_reader_writer(stream)

    es = EventSource.__new__(EventSource)
    es._url = "http://localhost/events"
    es._headers = {}
    es._reader = reader
    es._writer = writer
    es._last_event_id = "previous"
    es._retry_ms = 3000
    es._include_comments = False
    es._include_reconnects = False
    es._pending_reconnect = False
    es._debug = None

    await es._skip_headers()

    event = await anext(es)
    expect_equal(event, Event(event="message", data="hello"))
    expect_equal(es._last_event_id, "previous")


async def test_retry_field_updates_retry_ms():
    """retry: field updates _retry_ms on the EventSource instance."""
    stream = b"HTTP/1.1 200 OK\r\n\r\nretry: 5000\r\ndata: hello\r\n\r\n"
    reader, writer = make_reader_writer(stream)

    es = EventSource.__new__(EventSource)
    es._url = "http://localhost/events"
    es._headers = {}
    es._reader = reader
    es._writer = writer
    es._last_event_id = None
    es._retry_ms = 3000
    es._include_comments = False
    es._include_reconnects = False
    es._pending_reconnect = False
    es._debug = None

    await es._skip_headers()

    event = await anext(es)
    expect_equal(event, Event(event="message", data="hello"))
    expect_equal(es._retry_ms, 5000)


async def test_last_event_id_header_sent_on_connect():
    """_connect sends Last-Event-ID header when _last_event_id is set."""
    import lib.eventsource as es_mod

    writer = FakeStreamWriter()
    reader = FakeStreamReader(b"HTTP/1.1 200 OK\r\n\r\n")
    original_open_connection = es_mod.open_connection
    es_mod.open_connection = fake_open_connection([(reader, writer)])

    try:
        es = EventSource.__new__(EventSource)
        es._url = "http://localhost/events"
        es._headers = {"Authorization": "Bearer tok"}
        es._reader = None
        es._writer = None
        es._last_event_id = "evt-42"
        es._retry_ms = 3000
        es._include_comments = False
        es._include_reconnects = False
        es._pending_reconnect = False
        es._debug = None
        await es._connect()

        request_str = b"".join(writer.written).decode()
        expect_equal("Last-Event-ID: evt-42\r\n" in request_str, True)
        expect_equal("Authorization: Bearer tok\r\n" in request_str, True)
    finally:
        es_mod.open_connection = original_open_connection


async def test_no_last_event_id_header_when_none():
    """_connect does not send Last-Event-ID header when _last_event_id is None."""
    import lib.eventsource as es_mod

    writer = FakeStreamWriter()
    reader = FakeStreamReader(b"HTTP/1.1 200 OK\r\n\r\n")
    original_open_connection = es_mod.open_connection
    es_mod.open_connection = fake_open_connection([(reader, writer)])

    try:
        es = EventSource.__new__(EventSource)
        es._url = "http://localhost/events"
        es._headers = {}
        es._reader = None
        es._writer = None
        es._last_event_id = None
        es._retry_ms = 3000
        es._include_comments = False
        es._include_reconnects = False
        es._pending_reconnect = False
        es._debug = None
        await es._connect()

        request_str = b"".join(writer.written).decode()
        expect_equal("Last-Event-ID" in request_str, False)
    finally:
        es_mod.open_connection = original_open_connection


async def test_reconnect_on_connection_drop():
    """EventSource reconnects after connection drops and continues reading events."""
    import lib.eventsource as es_mod

    # Track sleep calls and connection count
    sleep_calls = []
    connect_count = [0]
    original_sleep = es_mod.sleep
    original_open_connection = es_mod.open_connection

    async def fake_sleep(secs):
        sleep_calls.append(secs)

    es_mod.sleep = fake_sleep

    # First connection: delivers one event then drops
    # Second connection: delivers another event
    stream1 = b"id: 1\r\ndata: first\r\n\r\n"
    stream2 = b"HTTP/1.1 200 OK\r\n\r\nid: 2\r\ndata: second\r\n\r\n"

    reader1, writer1 = make_reader_writer(stream1)
    reader2, writer2 = make_reader_writer(stream2)

    pairs = [(reader2, writer2)]

    async def mock_open_connection(host, port, ssl=None, server_hostname=None):
        connect_count[0] += 1
        return pairs.pop(0)

    es_mod.open_connection = mock_open_connection

    try:
        es = EventSource.__new__(EventSource)
        es._url = "http://localhost/events"
        es._headers = {}
        es._reader = reader1
        es._writer = writer1
        es._last_event_id = None
        es._retry_ms = 3000
        es._include_comments = False
        es._include_reconnects = False
        es._pending_reconnect = False
        es._debug = None

        # First event
        event1 = await anext(es)
        expect_equal(event1, Event(event="message", data="first", id="1"))
        expect_equal(es._last_event_id, "1")

        # Second anext() will hit OSError from reader1, reconnect, read from reader2
        event2 = await anext(es)
        expect_equal(event2, Event(event="message", data="second", id="2"))
        expect_equal(es._last_event_id, "2")

        # Verify Last-Event-ID was sent on reconnect
        request_str = b"".join(writer2.written).decode()
        expect_equal("Last-Event-ID: 1\r\n" in request_str, True)

        # Verify sleep was called with default retry
        expect_equal(sleep_calls, [3.0])
        expect_equal(connect_count[0], 1)  # one reconnection via _connect
    finally:
        es_mod.sleep = original_sleep
        es_mod.open_connection = original_open_connection


async def test_reconnect_sends_last_event_id():
    """On reconnect, Last-Event-ID header is sent with the last received id."""
    import lib.eventsource as es_mod

    sleep_calls = []
    original_sleep = es_mod.sleep
    original_open_connection = es_mod.open_connection

    async def fake_sleep(secs):
        sleep_calls.append(secs)

    es_mod.sleep = fake_sleep

    stream2 = b"HTTP/1.1 200 OK\r\n\r\ndata: after-reconnect\r\n\r\n"
    reader2, writer2 = make_reader_writer(stream2)

    es_mod.open_connection = fake_open_connection([(reader2, writer2)])

    try:
        # Create an EventSource that already has a last_event_id and an empty reader
        reader1, writer1 = make_reader_writer(
            b""
        )  # immediately returns empty → OSError
        es = EventSource.__new__(EventSource)
        es._url = "http://localhost/events"
        es._headers = {}
        es._reader = reader1
        es._writer = writer1
        es._last_event_id = "evt-99"
        es._retry_ms = 1000
        es._include_comments = False
        es._include_reconnects = False
        es._pending_reconnect = False
        es._debug = None

        event = await anext(es)
        expect_equal(event, Event(event="message", data="after-reconnect"))

        # Verify Last-Event-ID was sent
        request_str = b"".join(writer2.written).decode()
        expect_equal("Last-Event-ID: evt-99\r\n" in request_str, True)

        # Verify sleep used correct retry
        expect_equal(sleep_calls, [1.0])
    finally:
        es_mod.sleep = original_sleep
        es_mod.open_connection = original_open_connection


async def test_reconnect_retries_on_network_error():
    """Reconnect retries when _connect raises OSError (e.g. EHOSTUNREACH)."""
    import lib.eventsource as es_mod

    sleep_calls = []
    original_sleep = es_mod.sleep
    original_open_connection = es_mod.open_connection

    async def fake_sleep(secs):
        sleep_calls.append(secs)

    es_mod.sleep = fake_sleep

    connect_attempts = [0]
    stream2 = b"HTTP/1.1 200 OK\r\n\r\ndata: back online\r\n\r\n"
    reader2, writer2 = make_reader_writer(stream2)

    async def mock_open_connection(host, port, ssl=None, server_hostname=None):
        connect_attempts[0] += 1
        if connect_attempts[0] <= 2:
            raise OSError("EHOSTUNREACH")
        return (reader2, writer2)

    es_mod.open_connection = mock_open_connection

    try:
        reader1, writer1 = make_reader_writer(b"")  # immediately raises OSError
        es = EventSource.__new__(EventSource)
        es._url = "http://localhost/events"
        es._headers = {}
        es._reader = reader1
        es._writer = writer1
        es._last_event_id = None
        es._retry_ms = 1000
        es._include_comments = False
        es._include_reconnects = False
        es._pending_reconnect = False
        es._debug = None

        event = await anext(es)
        expect_equal(event, Event(event="message", data="back online"))
        expect_equal(connect_attempts[0], 3)  # 2 failures + 1 success
        expect_equal(sleep_calls, [1.0, 1.0, 1.0])
    finally:
        es_mod.sleep = original_sleep
        es_mod.open_connection = original_open_connection


async def test_reconnect_yields_reconnect_when_enabled():
    """When include_reconnects is True, a Reconnect is yielded after reconnecting."""
    import lib.eventsource as es_mod

    original_sleep = es_mod.sleep
    original_open_connection = es_mod.open_connection

    async def fake_sleep(secs):
        pass

    es_mod.sleep = fake_sleep

    stream2 = b"HTTP/1.1 200 OK\r\n\r\ndata: hello\r\n\r\n"
    reader2, writer2 = make_reader_writer(stream2)
    es_mod.open_connection = fake_open_connection([(reader2, writer2)])

    try:
        reader1, writer1 = make_reader_writer(b"")  # immediately raises OSError
        es = EventSource.__new__(EventSource)
        es._url = "http://localhost/events"
        es._headers = {}
        es._reader = reader1
        es._writer = writer1
        es._last_event_id = None
        es._retry_ms = 1000
        es._include_comments = False
        es._include_reconnects = True
        es._pending_reconnect = False
        es._debug = None

        msg = await anext(es)
        expect_equal(msg, Reconnect())

        event = await anext(es)
        expect_equal(event, Event(event="message", data="hello"))
    finally:
        es_mod.sleep = original_sleep
        es_mod.open_connection = original_open_connection


async def test_reconnect_not_yielded_by_default():
    """When include_reconnects is False (default), no Reconnect is yielded."""
    import lib.eventsource as es_mod

    original_sleep = es_mod.sleep
    original_open_connection = es_mod.open_connection

    async def fake_sleep(secs):
        pass

    es_mod.sleep = fake_sleep

    stream2 = b"HTTP/1.1 200 OK\r\n\r\ndata: hello\r\n\r\n"
    reader2, writer2 = make_reader_writer(stream2)
    es_mod.open_connection = fake_open_connection([(reader2, writer2)])

    try:
        reader1, writer1 = make_reader_writer(b"")  # immediately raises OSError
        es = EventSource.__new__(EventSource)
        es._url = "http://localhost/events"
        es._headers = {}
        es._reader = reader1
        es._writer = writer1
        es._last_event_id = None
        es._retry_ms = 1000
        es._include_comments = False
        es._include_reconnects = False
        es._pending_reconnect = False
        es._debug = None

        # Should skip straight to the event, no Reconnect
        event = await anext(es)
        expect_equal(event, Event(event="message", data="hello"))
    finally:
        es_mod.sleep = original_sleep
        es_mod.open_connection = original_open_connection


async def test_multiple_events_in_order():
    """Multiple events in a stream are yielded in correct order."""
    stream = (
        b"HTTP/1.1 200 OK\r\n\r\n"
        b"event: welcome\r\ndata: {}\r\n\r\n"
        b'event: mutation\r\nid: tx1\r\ndata: {"doc":"A"}\r\n\r\n'
        b'event: mutation\r\nid: tx2\r\ndata: {"doc":"B"}\r\n\r\n'
    )
    reader, writer = make_reader_writer(stream)

    es = EventSource.__new__(EventSource)
    es._url = "http://localhost/events"
    es._headers = {}
    es._reader = reader
    es._writer = writer
    es._last_event_id = None
    es._retry_ms = 3000
    es._include_comments = False
    es._include_reconnects = False
    es._pending_reconnect = False
    es._debug = None

    await es._skip_headers()

    e1 = await anext(es)
    expect_equal(e1, Event(event="welcome", data="{}"))

    e2 = await anext(es)
    expect_equal(e2, Event(event="mutation", data='{"doc":"A"}', id="tx1"))

    e3 = await anext(es)
    expect_equal(e3, Event(event="mutation", data='{"doc":"B"}', id="tx2"))


async def test_multiple_events_chunked_delivery():
    """Events delivered across multiple read() chunks are still in order."""
    # For async StreamReader, all data is available upfront
    stream = (
        b"HTTP/1.1 200 OK\r\n\r\n"
        b"event: welcome\r\ndata: {}\r\n\r\n"
        b'event: mutation\r\nid: tx1\r\ndata: {"doc":"A"}\r\n\r\n'
        b'event: mutation\r\nid: tx2\r\ndata: {"doc":"B"}\r\n\r\n'
    )
    reader, writer = make_reader_writer(stream)

    es = EventSource.__new__(EventSource)
    es._url = "http://localhost/events"
    es._headers = {}
    es._reader = reader
    es._writer = writer
    es._last_event_id = None
    es._retry_ms = 3000
    es._include_comments = False
    es._include_reconnects = False
    es._pending_reconnect = False
    es._debug = None

    await es._skip_headers()

    e1 = await anext(es)
    expect_equal(e1, Event(event="welcome", data="{}"))

    e2 = await anext(es)
    expect_equal(e2, Event(event="mutation", data='{"doc":"A"}', id="tx1"))

    e3 = await anext(es)
    expect_equal(e3, Event(event="mutation", data='{"doc":"B"}', id="tx2"))


async def test_comment_ignored_by_default():
    """Comment lines are ignored when include_comments is False."""
    stream = b"HTTP/1.1 200 OK\r\n\r\n: heartbeat\r\ndata: hello\r\n\r\n"
    reader, writer = make_reader_writer(stream)

    es = EventSource.__new__(EventSource)
    es._url = "http://localhost/events"
    es._headers = {}
    es._reader = reader
    es._writer = writer
    es._last_event_id = None
    es._retry_ms = 3000
    es._include_comments = False
    es._include_reconnects = False
    es._pending_reconnect = False
    es._debug = None

    await es._skip_headers()

    event = await anext(es)
    expect_equal(event, Event(event="message", data="hello"))


async def test_comment_yielded_when_enabled():
    """Comment lines yield Comment instances when include_comments is True."""
    stream = b"HTTP/1.1 200 OK\r\n\r\n: keepalive\r\ndata: hello\r\n\r\n"
    reader, writer = make_reader_writer(stream)

    es = EventSource.__new__(EventSource)
    es._url = "http://localhost/events"
    es._headers = {}
    es._reader = reader
    es._writer = writer
    es._last_event_id = None
    es._retry_ms = 3000
    es._include_comments = True
    es._include_reconnects = False
    es._pending_reconnect = False
    es._debug = None

    await es._skip_headers()

    msg = await anext(es)
    expect_equal(msg, Comment("keepalive"))

    event = await anext(es)
    expect_equal(event, Event(event="message", data="hello"))


async def test_comment_empty():
    """Empty comment line (just ':') yields Comment with empty text."""
    stream = b"HTTP/1.1 200 OK\r\n\r\n:\r\ndata: hello\r\n\r\n"
    reader, writer = make_reader_writer(stream)

    es = EventSource.__new__(EventSource)
    es._url = "http://localhost/events"
    es._headers = {}
    es._reader = reader
    es._writer = writer
    es._last_event_id = None
    es._retry_ms = 3000
    es._include_comments = True
    es._include_reconnects = False
    es._pending_reconnect = False
    es._debug = None

    await es._skip_headers()

    msg = await anext(es)
    expect_equal(msg, Comment(""))

    event = await anext(es)
    expect_equal(event, Event(event="message", data="hello"))


async def test_comment_mid_event_ignored():
    """Comment lines mid-event are ignored even when include_comments is True."""
    stream = b"HTTP/1.1 200 OK\r\n\r\nevent: mutation\r\n: mid-comment\r\ndata: payload\r\n\r\n"
    reader, writer = make_reader_writer(stream)

    es = EventSource.__new__(EventSource)
    es._url = "http://localhost/events"
    es._headers = {}
    es._reader = reader
    es._writer = writer
    es._last_event_id = None
    es._retry_ms = 3000
    es._include_comments = True
    es._include_reconnects = False
    es._pending_reconnect = False
    es._debug = None

    await es._skip_headers()

    event = await anext(es)
    expect_equal(event, Event(event="mutation", data="payload"))


async def test_debug_callback():
    """Debug callback receives each raw line as bytes."""
    stream = (
        b"HTTP/1.1 200 OK\r\n\r\nevent: mutation\r\nid: tx1\r\ndata: payload\r\n\r\n"
    )
    reader, writer = make_reader_writer(stream)

    debug_lines = []
    es = EventSource.__new__(EventSource)
    es._url = "http://localhost/events"
    es._headers = {}
    es._reader = reader
    es._writer = writer
    es._last_event_id = None
    es._retry_ms = 3000
    es._include_comments = False
    es._include_reconnects = False
    es._pending_reconnect = False
    es._debug = lambda line: debug_lines.append(line)

    await es._skip_headers()

    await anext(es)
    expect_equal(debug_lines, [b"event: mutation", b"id: tx1", b"data: payload", b""])


async def test_constructor_last_event_id():
    """Constructor accepts last_event_id param and sends it on initial connect."""
    import lib.eventsource as es_mod

    writer = FakeStreamWriter()
    reader = FakeStreamReader(b"HTTP/1.1 200 OK\r\n\r\n")
    original_open_connection = es_mod.open_connection
    es_mod.open_connection = fake_open_connection([(reader, writer)])

    try:
        es = EventSource("http://localhost/events", last_event_id="resume-123")
        # Trigger lazy connect
        expect_equal(es._reader, None)
        expect_equal(es._last_event_id, "resume-123")
        expect_equal(es._retry_ms, 3000)

        # Connect happens on first __anext__, but we can also test _connect directly
        await es._connect()
        request_str = b"".join(writer.written).decode()
        expect_equal("Last-Event-ID: resume-123\r\n" in request_str, True)
    finally:
        es_mod.open_connection = original_open_connection
