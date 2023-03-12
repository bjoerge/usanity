
def get_version():
    return 0.3

def get_user_agent():
    import os
    [sysname, _, _, _, machine] = os.uname()
    return f"usanity v{get_version()} / {sysname} - {machine}"
