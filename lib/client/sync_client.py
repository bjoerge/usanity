from lib.endpoints import query_request, mutate_request, doc_request


class SanityClient:
    def __init__(
        self,
        project_id,
        dataset,
        api_version,
        token=None,
        use_cdn=False,
        api_host=None,
        requester=None,
    ):
        self.project_id = project_id
        self.dataset = dataset
        self.api_version = api_version
        self.token = token
        self.use_cdn = use_cdn
        self.api_host = api_host
        self._requester = requester

    @property
    def requester(self):
        if self._requester is None:
            import urequests

            self._requester = urequests
        return self._requester

    def query(self, groq, variables=None, return_query=False, params=None):
        url, headers = query_request(
            groq,
            project_id=self.project_id,
            dataset=self.dataset,
            api_version=self.api_version,
            variables=variables,
            token=self.token,
            use_cdn=self.use_cdn,
            return_query=return_query,
            api_host=self.api_host,
            params=params,
        )
        response = self.requester.get(url, headers=headers)
        return response.json()

    def mutate(
        self,
        mutations,
        visibility=None,
        return_documents=False,
        return_ids=False,
        dry_run=False,
    ):
        url, headers, body = mutate_request(
            mutations,
            project_id=self.project_id,
            dataset=self.dataset,
            api_version=self.api_version,
            token=self.token,
            visibility=visibility,
            return_documents=return_documents,
            return_ids=return_ids,
            dry_run=dry_run,
        )
        response = self.requester.post(url, headers=headers, json=body)
        return response.json()

    def doc(self, document_ids):
        url, headers = doc_request(
            project_id=self.project_id,
            dataset=self.dataset,
            api_version=self.api_version,
            document_ids=document_ids,
            token=self.token,
        )
        response = self.requester.get(url, headers=headers)
        return response.json()
