import os

VERSION = 0.4

[sysname, _, _, _, machine] = os.uname()

USER_AGENT = f"usanity v{VERSION} / {sysname} - {machine}"
