from lib import request
from test_helpers import expect_equal


def test_listen():
    url, headers = request.listen_request(
        '*[_type == "sensor" && _id == $id]',
        variables={"id": "temperature-xyz"},
        project_id="abc",
        dataset="iot",
        api_version="2023-03-10",
        token="your token",
    )

    expect_equal(
        url,
        "https://abc.api.sanity.io/v2023-03-10/data/listen/iot?$id=%22temperature-xyz%22&query=%2a%5b%5ftype%20%3d%3d%20%22sensor%22%20%26%26%20%5fid%20%3d%3d%20%24id%5d",
    )
    expect_equal(headers["Authorization"], "Bearer your token")


def test_listen_with_options():
    url, headers = request.listen_request(
        '*[_type == "post"]',
        project_id="abc",
        dataset="production",
        api_version="2023-03-10",
        include_result=True,
        include_previous_revision=True,
        visibility="sync",
        effect_format="mendoza",
        tag="my-listener",
    )

    expect_equal(
        url,
        "https://abc.api.sanity.io/v2023-03-10/data/listen/production?query=%2a%5b%5ftype%20%3d%3d%20%22post%22%5d&includeResult=true&includePreviousRevision=true&visibility=sync&effectFormat=mendoza&tag=my-listener",
    )
