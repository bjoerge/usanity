def merge(x: dict, y: dict):
    z = x.copy()
    z.update(y)
    return z


_HEX = b"0123456789abcdef"


def encode_uri_component(uri_component: str):
    result = bytearray()
    for b in uri_component.encode():
        if (0x41 <= b <= 0x5A) or (0x61 <= b <= 0x7A) or (0x30 <= b <= 0x39) or b == 0x2D or b == 0x2E:
            result.append(b)
        else:
            result.append(0x25)  # %
            result.append(_HEX[b >> 4])
            result.append(_HEX[b & 0x0F])
    return result.decode()
