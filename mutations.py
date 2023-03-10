# Mutation helpers
# --- Mutations ---
def create_or_replace(document: dict):
    return {"createIfNotExists": document}


def create_if_not_exists(document: dict):
    return {"createIfNotExists": document}


def create(document: dict):
    return {"create": document}


def delete(id: str, purge=False):
    return {"delete": {"id": id, "purge": purge}}


def patch(id: str, patch: dict):
    patch_copy = patch.copy()
    patch_copy["id"] = id
    return {"patch": patch_copy}


# --- Patches ---
def set(path: str, value: any):
    return {"set": {path: value}}


# Alias
patch_set = set


def set_if_missing(path: str, value: any):
    return {"setIfMissing": {path: value}}


def unset(path: str):
    return {"unset": [path]}


def inc(path: str, by: any):
    return {"inc": {path: by}}


def dec(path: str, by: any):
    return {"dec": {path: by}}


def format_array_selector(item_selector: str | int):
    return (
        f'[_key=="{item_selector}"]'
        if isinstance(item_selector, str)
        else f"[{item_selector}]"
    )


# e.g. insert("path.to.array", "before", -1, ["a", "b"])
def insert(
    path: str,
    position: "before" | "after" | "replace",
    reference_selector: str | int,
    items: list,
):
    return {
        "insert": {
            position: path + format_array_selector(reference_selector),
            "items": items,
        }
    }
