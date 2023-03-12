
def get_version():
    VERSION = 0.3

def get_user_agent():
    import os
    [sysname, _, _, _, machine] = os.uname()
    USER_AGENT = f"usanity v{get_version()} / {sysname} - {machine}"
