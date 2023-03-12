import os

[sysname, _, _, _, machine] = os.uname()

VERSION = 0.2
USER_AGENT = f"usanity v{VERSION} / {sysname} - {machine}"
