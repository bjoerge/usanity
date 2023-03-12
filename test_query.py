from lib import request
from test_helpers import expect_equal


def test_query_use_cdn():
    url, headers = request.query_request(
        "*[_type == 'sensor' && _id == $id]",
        variables={"id": "temperature-xyz"},
        project_id="abc",
        dataset="iot",
        api_version="2023-03-10",
        use_cdn=True,
    )

    expect_equal(
        url,
        "https://abc.apicdn.sanity.io/v2023-03-10/data/query/iot?$id=temperature-xyz&query=%2a%5b%5ftype%20%3d%3d%20%27sensor%27%20%26%26%20%5fid%20%3d%3d%20%24id%5d",
    )

    url, headers = request.query_request(
        "*[_type == 'sensor' && _id == $id]",
        variables={"id": "temperature-xyz"},
        project_id="abc",
        dataset="iot",
        api_version="2023-03-10",
        token="your token",
    )

    expect_equal(
        url,
        "https://abc.api.sanity.io/v2023-03-10/data/query/iot?$id=temperature-xyz&query=%2a%5b%5ftype%20%3d%3d%20%27sensor%27%20%26%26%20%5fid%20%3d%3d%20%24id%5d",
    )


def test_with_token():
    _, headers = request.query_request(
        "*[_type == 'sensor'",
        project_id="abc",
        dataset="iot",
        api_version="2023-03-10",
        token="xyz",
    )
    expect_equal(headers["Authorization"], "Bearer xyz")
