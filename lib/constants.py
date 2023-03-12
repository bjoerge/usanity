import os

VERSION = 0.3

[sysname, _, _, _, machine] = os.uname()

USER_AGENT = f"usanity v{VERSION} / {sysname} - {machine}"
