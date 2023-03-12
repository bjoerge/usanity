from constants import USER_AGENT
from utils import encode_uri_component, merge


def base_url(project_id: str, use_cdn: bool = False, api_host: str = None):
    if api_host:
        return f"https://{api_host}"
    return f'https://{project_id}.{"apicdn" if use_cdn else "api"}.sanity.io'


def versioned_path(version: str):
    return f"/v{version}"


def mutate_endpoint(api_version: str, dataset: str):
    return versioned_path(api_version) + f"/data/mutate/{dataset}"


def query_endpoint(api_version: str, dataset: str):
    return versioned_path(api_version) + f"/data/query/{dataset}"


def doc_endpoint(api_version: str, dataset: str, document_ids: list):
    return versioned_path(api_version) + f"/data/doc/{dataset}/{','.join(document_ids)}"


def variables_to_query_params(variables: dict = None, explain=False):
    params = dict([(f"${name}", value) for (name, value) in variables.items()])
    if explain:
        params["explain"] = "true"
    return params


def base_headers(token: str | None = None):
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def base_params(tag: str | None):
    return {"tag": tag} if tag else {}


def encode_params(params: dict):
    return "&".join(
        [
            f"{key}={encode_uri_component(value)}" if value is not None else key
            for (key, value) in params.items()
        ]
    )


def build_url(base, endpoint, params):
    return base + endpoint + (f"?{encode_params(params)}" if params else "")


def query_request(
    query: str,
    project_id: str,
    dataset: str,
    api_version: str,
    variables: dict = None,
    token: str = None,
    use_cdn: bool = False,
    api_host=None,
    params: dict = None,
):
    qs = merge(
        merge(params or {}, variables_to_query_params(variables or {})),
        {"query": query},
    )
    return (
        build_url(
            base_url(project_id, use_cdn, api_host),
            query_endpoint(api_version, dataset),
            qs,
        ),
        base_headers(token),
    )


def mutate_request(
    mutations: list,
    project_id: str,
    dataset: str,
    api_version: str,
    token: str = None,
    visibility: str = None,  # either "async", "sync" or "deferred". Default "sync" on the backend side
    return_documents: bool = False,
    return_ids: bool = False,
    dry_run: bool = False,
):
    params = {}
    if visibility:
        params["visibility"] = visibility
    if return_documents:
        params["return_documents"] = return_documents
    if return_ids:
        params["return_ids"] = return_ids
    if dry_run:
        params["dry_run"] = dry_run

    return (
        build_url(
            base_url(project_id, False), mutate_endpoint(api_version, dataset), params
        ),
        base_headers(token),
        {"mutations": mutations},
    )


def doc_request(
    project_id: str,
    dataset: str,
    api_version: str,
    document_ids: list,
    token: str = None,
    explain: bool = False,
):
    params = {}
    if explain:
        params["explain"] = explain
    return (
        build_url(
            base_url(project_id, False),
            doc_endpoint(api_version, dataset, document_ids),
            params,
        ),
        base_headers(token),
    )
