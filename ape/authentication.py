import asyncio
import click
import logging
import os

from aiohttp import web
from aiohttp.web_log import AccessLogger

from .exceptions import Exit

log = logging.getLogger(__name__)


class NoAccessLogger(AccessLogger):
    def log(self, request, response, time):
        pass


class Authenticate:
    event = asyncio.Event()
    routes = web.RouteTableDef()
    code = None
    state = None

    @staticmethod
    @routes.get("/")
    async def callback(request):
        Authenticate.event.set()

        return web.Response(text="Authentication succeeded. You can now close your browser.")

    @staticmethod
    async def wait_for_code():
        # Create a very small webserver
        webapp = web.Application()
        webapp.add_routes(Authenticate.routes)

        # Start the webapp, and wait for the code to be send back
        task = asyncio.create_task(
            web._run_app(webapp, host="127.0.0.1", port=3977, print=None, access_log_class=NoAccessLogger)
        )
        await Authenticate.event.wait()
        task.cancel()


async def authenticate(session):
    ape_folder = click.get_app_dir("ape")
    os.makedirs(ape_folder, exist_ok=True)
    ape_token_filename = ape_folder + "/token"

    if os.path.exists(ape_token_filename):
        with open(ape_token_filename, "r") as f:
            bearer_token = f.read()

        session.set_header("Authorization", f"Bearer {bearer_token}")
        status, data = await session.get("/package/self")
        if status != 401:
            return

    status, data = await session.get("/user/login?method=github&redirect-uri=http%3A%2F%2Flocalhost%3A3977%2F")
    if status != 200:
        log.error(f"Server returned invalid status code {status}. Authentication failed.")
        raise Exit

    print("Please visit the following URL to authenticate:")
    print(f"  {data['authorize-url']}")

    with open(ape_token_filename, "w") as f:
        f.write(data["bearer-token"])
    session.set_header("Authorization", f"Bearer {data['bearer-token']}")

    await Authenticate.wait_for_code()
