# µsanity
[MicroPython](https://micropython.org/) client for [Sanity.io](https://www.sanity.io/)

## Install

## Use mip to install
If you're connected to the REPL and connected to Wi-Fi, the easiest way to install is by running the following:
```python
import mip
mip.install("github:bjoerge/usanity")
```

More info about the MicroPython package manager and alternative ways to install here: https://docs.micropython.org/en/latest/reference/packages.html#installing-packages-with-mip

## Usage examples

### Fetch a groq query
```python
import urequests
from usanity import query_request

sensor_id = "temperature-xyz"

# Fetch the sensor from the dataset using groq (https://groq.dev/)
url, headers = query_request(
    "*[_type == 'sensor' && _id == $id]",
     variables={"id": sensor_id},
     # Get your own project and dataset at https://www.sanity.io/get-started/create-project
     project_id="<your project id>",
     dataset="<your dataset>",
     # API version to use - see https://www.sanity.io/docs/api-versioning for more info
     api_version="2023-03-10",
     # A token with read access (optional for public datasets)
     token="<token>",
     # use the API CDN (https://www.sanity.io/docs/api-cdn)
     use_cdn=True
 )
# Use urequests to perform the actual http request for us
res = urequests.get(url, headers=headers)
sensors = res.json['result']

print(sensors)

```

### Mutate a document
```python
import urequests
from usanity import mutate_request
from usanity.mutations import (
    create_if_not_exists,
    patch,
    patch_set,
    set_if_missing,
    unset,
    insert,
)

sensor_document_id = 'temperature-xyz'

# Get the sensor value (e.g. read from PIN)
sensor_value = read_sensor()
 
mutations = [
    create_if_not_exists({
        "_id": sensor_document_id,
        "_type": "sensor"
    }),
    # set the current value
    patch(sensor_document_id, patch_set("value", sensor_value)),
    # make sure we have a history array
    patch(sensor_document_id, set_if_missing("history", [])),
    # prepend the sensor value to the history array
    patch(sensor_document_id, insert("history", "before", 0, [
        {"timestamp": ntptime.time(), "value": sensor_value}
    ])),
]

url, headers, body = mutate_request(
    mutations,
     # Get your own project and dataset at https://www.sanity.io/get-started/create-project
     project_id="<your project id>",
     dataset="<your dataset>",
     # API version to use - see https://www.sanity.io/docs/api-versioning for more info
     api_version="2023-03-10",
     # Required for writes - create your own write-token at https://www.sanity.io/manage/project/<your-projectid>/api
     token="<token>",
)

# Use urequests to perform the actual http request for us
res = urequests.post(url, json=body, headers=headers)

# Print the response
print(res.json)

```
