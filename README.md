# µsanity
[MicroPython](https://micropython.org/) client for [Sanity.io](https://www.sanity.io/)

## Install

If you're connected to the REPL and connected to Wi-Fi, the easiest way to install is by running the following:

```python
import mip
mip.install("github:bjoerge/usanity")
```

More info about the MicroPython package manager and alternative ways to install here: https://docs.micropython.org/en/latest/reference/packages.html#installing-packages-with-mip

## Quick start

```python
from usanity.client import SanityClient

client = SanityClient(
    project_id="your-project-id",
    dataset="production",
    api_version="2026-02-26",
    token="your-token",       # optional for public datasets
    use_cdn=True,             # optional, default False
)

# Query with GROQ
result = client.query(
    "*[_type == 'sensor' && _id == $id]",
    variables={"id": "temperature-xyz"},
)
print(result)
```

## Usage

### Querying

```python
# Fetch documents by GROQ query
result = client.query("*[_type == 'sensor'][0...10]")

# Fetch documents by ID
result = client.doc(["doc-id-1", "doc-id-2"])
```

### Mutating

```python
from usanity.mutations import create, patch, patch_set, set_if_missing

result = client.mutate([
    create({"_type": "sensor", "name": "Temperature"}),
    patch("my-doc", patch_set("some.path", "hello world")),
    patch("my-doc", set_if_missing("maybeUpdate", "maybe hello world")),
], return_ids=True)
```

Available mutation helpers:

| Function | Description |
|---|---|
| `create(doc)` | Create a new document |
| `create_if_not_exists(doc)` | Create only if `_id` doesn't exist |
| `create_or_replace(doc)` | Create or fully replace by `_id` |
| `delete(id)` | Delete a document |
| `patch(id, ...)` | Patch a document (combine with helpers below) |

Available patch helpers:

| Function | Description |
|---|---|
| `patch_set(path, value)` | Set a field value (alias: `set`) |
| `set_if_missing(path, value)` | Set only if the field doesn't exist |
| `unset(path)` | Remove a field |
| `inc(path, by)` | Increment a numeric field |
| `dec(path, by)` | Decrement a numeric field |
| `insert(path, pos, ref, items)` | Insert items into an array |

### Listening for real-time updates

Real-time listening requires the async client:

```python
import asyncio
import json
from usanity.client import AsyncSanityClient

async def main():
    client = AsyncSanityClient(
        project_id="your-project-id",
        dataset="production",
        api_version="2026-02-26",
        token="your-token",
    )

    async for event in client.listen("_type == 'sensor'", include_result=True):
        if event.event == "mutation":
            data = json.loads(event.data)
            print("Document changed:", data["documentId"])
            print("Result:", data.get("result"))

asyncio.run(main())
```

### Custom HTTP backend

Both clients accept a `requester` parameter to inject a custom HTTP backend. The requester must have `get(url, headers=...)` and `post(url, headers=..., json=...)` methods returning a response with a `.json()` method:

```python
client = SanityClient(
    project_id="your-project-id",
    dataset="production",
    api_version="2026-02-26",
    requester=my_custom_http_module,
)
```

### Low-level API

If you prefer full control over HTTP requests, use the request-builder functions directly. They return `(url, headers)` or `(url, headers, body)` tuples that you pass to your HTTP library of choice.

### Query

```python
import urequests
from usanity import query_request

url, headers = query_request(
    "*[_type == 'sensor' && _id == $id]",
    variables={"id": "temperature-xyz"},
    project_id="your-project-id",
    dataset="production",
    api_version="2026-02-26",
    token="your-token",
    use_cdn=True,
)
res = urequests.get(url, headers=headers)
print(res.json()['result'])
```

### Mutate

```python
import urequests
from usanity import mutate_request
from usanity.mutations import (
    create_if_not_exists,
    patch,
    # set is a builtin, so use patch_set instead
    patch_set,
    set_if_missing,
    insert,
)

mutations = [
    create_if_not_exists({
        "_id": "temperature-xyz",
        "_type": "sensor",
    }),
    patch("temperature-xyz", patch_set("value", read_sensor())),
    patch("temperature-xyz", set_if_missing("history", [])),
    patch("temperature-xyz", insert("history", "before", 0, [
        {"timestamp": ntptime.time(), "value": read_sensor()}
    ])),
]

url, headers, body = mutate_request(
    mutations,
    project_id="your-project-id",
    dataset="production",
    api_version="2026-02-26",
    token="your-token",
)
res = urequests.post(url, json=body, headers=headers)
print(res.json())
```

### Listen

```python
import asyncio
import json
from usanity import listen_request
from usanity.http.eventsource import EventSource

url, headers = listen_request(
    "_type == 'sensor' && sensorType == $type",
    variables={"sensorType": "temperature"},
    project_id="your-project-id",
    dataset="production",
    api_version="2026-02-26",
    token="your-token",
    include_result=True,
)

async def main():
    async for event in EventSource(url, headers):
        if event.event == "mutation":
            data = json.loads(event.data)
            print("Document changed:", data["documentId"])
            print("Result:", data.get("result"))

asyncio.run(main())
```

The `EventSource` automatically reconnects on connection drops, sending the `Last-Event-ID` header so the server can resume the stream. To resume from a known position:

```python
from usanity.http.eventsource import EventSource

es = EventSource(url, headers, last_event_id="last-known-event-id")
async for event in es:
    ...
```

## License

MIT
