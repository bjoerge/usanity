def merge(x: dict, y: dict):
    z = x.copy()
    z.update(y)
    return z


def encode_uri_component(uri_component: str):
    return "".join(
        [
            character
            if character.isalpha() or character == "-" or character == "."
            else "%" + hex(ord(character))[2:]
            for character in uri_component
        ]
    )


def encode_params(params: dict):
    return "&".join(
        [
            f"{key}={encode_uri_component(value)}" if value is not None else key
            for (key, value) in params.items()
        ]
    )
