from mutations import create_if_not_exists, patch, patch_set, insert, set_if_missing
from request import mutate_request
from tests.helpers import expect_equal
from meta import USER_AGENT


def test_query_mutation():
    sensor_document_id = "temperature-xyz"
    sensor_value = 0.6

    mutations = [
        create_if_not_exists({"_id": sensor_document_id, "_type": "sensor"}),
        patch(sensor_document_id, patch_set("value", sensor_value)),
        patch(sensor_document_id, set_if_missing("history", [])),
        patch(
            sensor_document_id,
            insert(
                "history",
                "before",
                0,
                [{"timestamp": 1678407421, "value": sensor_value}],
            ),
        ),
    ]

    url, headers, body = mutate_request(
        mutations,
        project_id="abc",
        dataset="iot",
        api_version="2023-03-10",
        token="abcxyz",
    )

    expect_equal(url, "https://abc.api.sanity.io/v2023-03-10/data/mutate/iot")
    expect_equal(headers, {"User-Agent": USER_AGENT, "Authorization": "Bearer abcxyz"})
    expect_equal(
        body,
        {
            "mutations": [
                {"createIfNotExists": {"_type": "sensor", "_id": "temperature-xyz"}},
                {"patch": {"id": "temperature-xyz", "set": {"value": 0.6}}},
                {"patch": {"setIfMissing": {"history": []}, "id": "temperature-xyz"}},
                {
                    "patch": {
                        "insert": {
                            "before": "history[0]",
                            "items": [{"value": 0.6, "timestamp": 1678407421}],
                        },
                        "id": "temperature-xyz",
                    }
                },
            ]
        },
    )
