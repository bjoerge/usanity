import os

VERSION = "1.0.1"

[sysname, _, _, _, machine] = os.uname()

USER_AGENT = f"usanity v{VERSION} / {sysname} - {machine}"
