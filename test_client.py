from lib.client import SanityClient, AsyncSanityClient
from lib.http.eventsource import EventSource
from test_helpers import expect_equal


class MockResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class MockRequester:
    """Records calls and returns a configurable response."""
    def __init__(self, response_data=None):
        self.calls = []
        self.response_data = response_data or {}

    def get(self, url, headers=None):
        self.calls.append(("get", url, headers))
        return MockResponse(self.response_data)

    def post(self, url, headers=None, json=None):
        self.calls.append(("post", url, headers, json))
        return MockResponse(self.response_data)


class AsyncMockRequester:
    """Async version of MockRequester."""
    def __init__(self, response_data=None):
        self.calls = []
        self.response_data = response_data or {}

    async def get(self, url, headers=None):
        self.calls.append(("get", url, headers))
        return MockResponse(self.response_data)

    async def post(self, url, headers=None, json=None):
        self.calls.append(("post", url, headers, json))
        return MockResponse(self.response_data)


CONFIG = dict(
    project_id="abc123",
    dataset="production",
    api_version="2024-01-01",
    token="sk-test",
)


# --- SanityClient (sync) tests ---


def test_sync_query():
    mock = MockRequester({"result": [{"_id": "1"}]})
    client = SanityClient(**CONFIG, requester=mock)
    result = client.query("*[_type == 'post']", variables={"limit": 10})

    expect_equal(result, {"result": [{"_id": "1"}]})
    expect_equal(len(mock.calls), 1)
    method, url, headers = mock.calls[0]
    expect_equal(method, "get")
    assert "abc123.api.sanity.io" in url
    assert "v2024-01-01/data/query/production" in url
    assert "query=" in url
    assert "$limit=10" in url
    expect_equal(headers["Authorization"], "Bearer sk-test")


def test_sync_query_use_cdn():
    mock = MockRequester()
    client = SanityClient(**CONFIG, use_cdn=True, requester=mock)
    client.query("*[_type == 'post']")

    _, url, _ = mock.calls[0]
    assert "abc123.apicdn.sanity.io" in url


def test_sync_query_no_token():
    mock = MockRequester()
    client = SanityClient(
        project_id="abc123",
        dataset="production",
        api_version="2024-01-01",
        requester=mock,
    )
    client.query("*")

    _, _, headers = mock.calls[0]
    assert "Authorization" not in headers


def test_sync_mutate():
    mock = MockRequester({"results": [{"id": "new-id"}]})
    client = SanityClient(**CONFIG, requester=mock)
    mutations = [{"create": {"_type": "post", "title": "Hello"}}]
    result = client.mutate(mutations, return_ids=True)

    expect_equal(result, {"results": [{"id": "new-id"}]})
    expect_equal(len(mock.calls), 1)
    method, url, headers, body = mock.calls[0]
    expect_equal(method, "post")
    assert "v2024-01-01/data/mutate/production" in url
    expect_equal(body, {"mutations": mutations})
    expect_equal(headers["Authorization"], "Bearer sk-test")


def test_sync_doc():
    mock = MockRequester({"documents": [{"_id": "doc1"}]})
    client = SanityClient(**CONFIG, requester=mock)
    result = client.doc(["doc1", "doc2"])

    expect_equal(result, {"documents": [{"_id": "doc1"}]})
    _, url, headers = mock.calls[0]
    assert "v2024-01-01/data/doc/production/doc1,doc2" in url


def test_sync_api_host_override():
    mock = MockRequester()
    client = SanityClient(**CONFIG, api_host="custom.api.sanity.io", requester=mock)
    client.query("*")

    _, url, _ = mock.calls[0]
    assert "custom.api.sanity.io" in url


# --- AsyncSanityClient tests ---


async def test_async_query():
    mock = AsyncMockRequester({"result": [{"_id": "1"}]})
    client = AsyncSanityClient(**CONFIG, requester=mock)
    result = await client.query("*[_type == 'post']", variables={"limit": 10})

    expect_equal(result, {"result": [{"_id": "1"}]})
    method, url, headers = mock.calls[0]
    expect_equal(method, "get")
    assert "abc123.api.sanity.io" in url
    assert "query=" in url
    expect_equal(headers["Authorization"], "Bearer sk-test")


async def test_async_mutate():
    mock = AsyncMockRequester({"results": []})
    client = AsyncSanityClient(**CONFIG, requester=mock)
    mutations = [{"create": {"_type": "post", "title": "Hi"}}]
    result = await client.mutate(mutations)

    expect_equal(result, {"results": []})
    method, url, headers, body = mock.calls[0]
    expect_equal(method, "post")
    expect_equal(body, {"mutations": mutations})


async def test_async_doc():
    mock = AsyncMockRequester({"documents": []})
    client = AsyncSanityClient(**CONFIG, requester=mock)
    result = await client.doc(["doc1"])

    expect_equal(result, {"documents": []})
    _, url, _ = mock.calls[0]
    assert "data/doc/production/doc1" in url


def test_async_listen_returns_eventsource():
    client = AsyncSanityClient(**CONFIG)
    es = client.listen("_type == 'post'", include_result=True)

    assert isinstance(es, EventSource)
    assert "abc123.api.sanity.io" in es._url
    assert "data/listen/production" in es._url
    assert "includeResult=true" in es._url
    expect_equal(es._headers["Authorization"], "Bearer sk-test")
