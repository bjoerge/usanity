from lib.endpoints import query_request, mutate_request, doc_request, listen_request
from lib.http.eventsource import EventSource


class AsyncSanityClient:
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
            from lib.http import async_urequests

            self._requester = async_urequests
        return self._requester

    async def query(self, groq, variables=None, return_query=False, params=None):
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
        response = await self.requester.get(url, headers=headers)
        return response.json()

    async def mutate(
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
        response = await self.requester.post(url, headers=headers, json=body)
        return response.json()

    async def doc(self, document_ids):
        url, headers = doc_request(
            project_id=self.project_id,
            dataset=self.dataset,
            api_version=self.api_version,
            document_ids=document_ids,
            token=self.token,
        )
        response = await self.requester.get(url, headers=headers)
        return response.json()

    def listen(
        self,
        groq_filter,
        variables=None,
        include_result=False,
        include_previous_revision=False,
        visibility=None,
        effect_format=None,
        tag=None,
    ):
        url, headers = listen_request(
            groq_filter,
            project_id=self.project_id,
            dataset=self.dataset,
            api_version=self.api_version,
            variables=variables,
            token=self.token,
            api_host=self.api_host,
            include_result=include_result,
            include_previous_revision=include_previous_revision,
            visibility=visibility,
            effect_format=effect_format,
            tag=tag,
        )
        return EventSource(url, headers=headers)
