from lib import endpoints
from test_helpers import expect_equal


def test_query():
    url, headers = endpoints.query_request(
        '*[_type == "sensor" && _id == $id && value < $threshold][0...$limit && isActive=$active]',
        variables={"id": "temperature-xyz", "limit": 100, "isActive": True, "threshold": 0.052},
        project_id="abc",
        dataset="iot",
        api_version="2023-03-10",
        token="your token",
        params={"tag": "test-request"},
    )

    expect_equal(
        url,
        "https://abc.api.sanity.io/v2023-03-10/data/query/iot?tag=test-request&$id=%22temperature-xyz%22&$limit=100&$isActive=true&$threshold=0.052&query=%2a%5b_type%20%3d%3d%20%22sensor%22%20%26%26%20_id%20%3d%3d%20%24id%20%26%26%20value%20%3c%20%24threshold%5d%5b0...%24limit%20%26%26%20isActive%3d%24active%5d",
    )


def test_query_use_cdn():
    url, headers = endpoints.query_request(
        "*[_type == 'sensor' && _id == $id]",
        variables={"id": "temperature-xyz"},
        project_id="abc",
        dataset="iot",
        api_version="2023-03-10",
        use_cdn=True,
    )

    expect_equal(
        url,
        "https://abc.apicdn.sanity.io/v2023-03-10/data/query/iot?$id=%22temperature-xyz%22&query=%2a%5b_type%20%3d%3d%20%27sensor%27%20%26%26%20_id%20%3d%3d%20%24id%5d",
    )


def test_with_token():
    _, headers = endpoints.query_request(
        "*[_type == 'sensor'",
        project_id="abc",
        dataset="iot",
        api_version="2023-03-10",
        token="xyz",
    )
    expect_equal(headers["Authorization"], "Bearer xyz")
