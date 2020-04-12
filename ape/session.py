import aiohttp
import logging

from tusclient.client import TusClient
from tusclient.exceptions import TusCommunicationError
from tusclient import uploader

from .exceptions import Exit

log = logging.getLogger(__name__)

UPLOAD_CHUNK_SIZE = 5 * 1024 * 1024


# tusd returns a Location header with "http" instead of the schema used to
# make the call. tuspy uses that URL to make further calls, resulting in
# additional 301s to HTTPS. Hijack the function doing this, and patch it
# up so it returns an HTTPS URL.
def uploader_urljoin(base_url, url):
    return base_url + url.split("/")[-1]


uploader.urljoin = uploader_urljoin


class Session:
    def __init__(self, api_url, tus_url):
        self.session = None
        self.api_url = api_url
        self.tus_url = tus_url

        self._headers = {}

    async def start(self):
        self.session = aiohttp.ClientSession()

    async def stop(self):
        await self.session.close()

    async def _read_response(self, response):
        if response.status in (200, 201, 400, 404):
            data = await response.json()
        else:
            data = None

        return response.status, data

    async def get(self, url):
        response = await self.session.get(f"{self.api_url}{url}", headers=self._headers)
        return await self._read_response(response)

    async def post(self, url, json):
        response = await self.session.post(f"{self.api_url}{url}", json=json, headers=self._headers)
        return await self._read_response(response)

    async def put(self, url, json):
        response = await self.session.put(f"{self.api_url}{url}", json=json, headers=self._headers)
        return await self._read_response(response)

    def tus_upload(self, upload_token, fullpath, filename):
        tus = TusClient(f"{self.tus_url}/new-package/tus/")
        tus.set_headers({"Upload-Token": upload_token})
        tus.set_headers({"Authorization": self._headers["Authorization"]})

        try:
            uploader = tus.uploader(fullpath, chunk_size=UPLOAD_CHUNK_SIZE, metadata={"filename": filename})
            uploader.upload()
        except TusCommunicationError:
            log.exception(f"Failed to upload file '{filename}'")
            raise Exit

    def set_header(self, header, value):
        self._headers[header] = value
