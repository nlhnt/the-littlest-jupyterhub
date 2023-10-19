import asyncio
import json

from functools import partial
from textwrap import dedent

import os
import ssl

from datetime import datetime, timezone
from packaging.version import Version as V
from tornado.httpclient import AsyncHTTPClient, HTTPRequest
from tornado.httputil import url_concat
from tornado.ioloop import IOLoop, PeriodicCallback
from tornado.log import app_log
from tornado.options import define, options, parse_command_line

from tornado.options import define, options, parse_command_line

__version__ = "0.0.1.dev1"
STATE_FILTER_MIN_VERSION = V("1.3.0")

async def get_users_idle(
    url,
    api_token,
    timeout=3600,
    concurrency=10,
    ssl_enabled=False,
    internal_certs_location="",
    api_page_size=0,
):
    """Get number of active users with kernels in ready and active state.

    :param url: _description_
    :type url: _type_
    :param api_token: _description_
    :type api_token: _type_
    :param concurrency: _description_, defaults to 10
    :type concurrency: int, optional
    :param ssl_enabled: _description_, defaults to False
    :type ssl_enabled: bool, optional
    :param api_page_size: _description_, defaults to 0
    :type api_page_size: int, optional
    """
    defaults = {
        "request_timeout": int(os.environ.get("JUPYTERHUB_REQUEST_TIMEOUT") or 60)
    }
    if ssl_enabled:
        ssl_context = make_ssl_context(
            f"{internal_certs_location}/hub-internal/hub-internal.key",
            f"{internal_certs_location}/hub-internal/hub-internal.crt",
            f"{internal_certs_location}/hub-ca/hub-ca.crt",
        )

        app_log.debug("ssl_enabled is Enabled: %s", ssl_enabled)
        app_log.debug("internal_certs_location is %s", internal_certs_location)
        defaults["ssl_options"] = ssl_context
    
    AsyncHTTPClient.configure(None, defaults=defaults)
    client = AsyncHTTPClient()

    if concurrency:
        semaphore = asyncio.Semaphore(concurrency)

        async def fetch(req):
            """client.fetch wrapped in a semaphore to limit concurrency"""
            await semaphore.acquire()
            try:
                return await client.fetch(req)
            finally:
                semaphore.release()
    else:
        fetch = client.fetch

    async def fetch_paginated(req):
        """Make a paginated API request

        async generator, yields all items from a list endpoint
        """
        req.headers["Accept"] = "application/jupyterhub-pagination+json"
        url = req.url
        resp_future = asyncio.ensure_future(fetch(req))
        page_no = 1
        item_count = 0
        while resp_future is not None:
            response = await resp_future
            resp_future = None
            resp_model = json.loads(response.body.decode("utf8", "replace"))

            if isinstance(resp_model, list):
                # handle pre-2.0 response, no pagination
                items = resp_model
            else:
                # paginated response
                items = resp_model["items"]

                next_info = resp_model["_pagination"]["next"]
                if next_info:
                    page_no += 1
                    app_log.info(f"Fetching page {page_no} {next_info['url']}")
                    # submit next request
                    req.url = next_info["url"]
                    resp_future = asyncio.ensure_future(fetch(req))

            for item in items:
                item_count += 1
                yield item
    
        app_log.debug(f"Fetched {item_count} items from {url} in {page_no} pages")

    # Starting with jupyterhub 1.3.0 the users can be filtered in the server
    # using the `state` filter parameter. "ready" means all users who have any
    # ready servers (running, not pending).
    auth_header = {"Authorization": f"token {api_token}"}
    resp = await fetch(HTTPRequest(url=f"{url}/", headers=auth_header))

    resp_model = json.loads(resp.body.decode("utf8", "replace"))
    state_filter = V(resp_model["version"]) >= STATE_FILTER_MIN_VERSION

    now = utcnow()

    async def handle_user(user):
        app_log.info(f"Got user: {user}")

    futures = []

    params = {}
    if api_page_size:
        params["limit"] = str(api_page_size)

    # If we filter users by state=ready then we do not get back any which
    # are inactive, so if we're also culling users get the set of users which
    # are inactive and see if they should be culled as well.
    users_url = f"{url}/users"

    active_params = {"state": "ready"}
    active_params.update(params)

    req = HTTPRequest(
        url=url_concat(users_url, params),
        headers=auth_header,
    )

    n_users = 0
    async for user in fetch_paginated(req):
        n_users += 1
        futures.append((user["name"], handle_user(user)))

    if state_filter:
        app_log.debug(f"Got {n_users} users with ready servers")
    else:
        app_log.debug(f"Got {n_users} users")

    for name, f in futures:
        try:
            result = await f
        except Exception:
            app_log.exception(f"Error processing {name}")
        else:
            if result:
                app_log.debug("Finished culling %s", name)

def make_ssl_context(keyfile, certfile, cafile=None, verify=True, check_hostname=True):
    """Setup context for starting an https server or making requests over ssl."""
    if not keyfile or not certfile:
        return None
    purpose = ssl.Purpose.SERVER_AUTH if verify else ssl.Purpose.CLIENT_AUTH
    ssl_context = ssl.create_default_context(purpose, cafile=cafile)
    ssl_context.load_default_certs(purpose)
    ssl_context.load_cert_chain(certfile, keyfile)
    ssl_context.check_hostname = check_hostname
    return ssl_context

def utcnow():
    """Return timezone-aware datetime for right now"""
    # Only a standalone function for mocking purposes
    return datetime.now(timezone.utc)

def main():
    define(
        "url",
        default=os.environ.get("JUPYTERHUB_API_URL"),
        help=dedent(
            """
            The JupyterHub API URL.
            """
        ).strip(),
    )
    define(
        "timeout",
        type=int,
        default=600,
        help=dedent(
            """
            The idle timeout (in seconds).
            """
        ).strip(),
    )
    define(
        "fetch_every",
        type=int,
        default=5,
        help=dedent(
            """
            The interval (in seconds) for checking for idle servers to cull.
            """
        ).strip(),
    )
    define(
        "concurrency",
        type=int,
        default=10,
        help=dedent(
            """
            Limit the number of concurrent requests made to the Hub.

            Deleting a lot of users at the same time can slow down the Hub,
            so limit the number of API requests we have outstanding at any given time.
            """
        ).strip(),
    )
    define(
        "ssl_enabled",
        type=bool,
        default=False,
        help=dedent(
            """
            Whether the Jupyter API endpoint has TLS enabled.
            """
        ).strip(),
    )
    define(
        "internal_certs_location",
        type=str,
        default="internal-ssl",
        help=dedent(
            """
            The location of generated internal-ssl certificates (only needed with --ssl-enabled=true).
            """
        ).strip(),
    )
    define(
        "api_page_size",
        type=int,
        default=0,
        help=dedent(
            """
            Number of users to request per page,
            when using JupyterHub 2.0's paginated user list API.
            Default: user the server-side default configured page size.
            """
        ).strip(),
    )

    parse_command_line()
    if not options.fetch_every:
        options.fetch_every = options.timeout // 2

    # get local token
    api_token = os.environ["JUPYTERHUB_API_TOKEN"]

    try:
        AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")
    except ImportError as e:
        app_log.warning(
            f"Could not load pycurl: {e}\n"
            "pycurl is recommended if you have a large number of users."
        )

    loop = IOLoop.current()
    get_users = partial(
        get_users_idle,
        url=options.url,
        api_token=api_token,
        timeout=options.timeout,
        concurrency=options.concurrency,
        ssl_enabled=options.ssl_enabled,
        internal_certs_location=options.internal_certs_location,
        api_page_size=options.api_page_size,
    )
    
    # schedule first get_users immediately
    # because PeriodicCallback doesn't start until the end of the first interval
    loop.add_callback(get_users)
    
    # schedule periodic get_users
    pc = PeriodicCallback(get_users, 1e3 * options.fetch_every)
    pc.start()
    try:
        loop.start()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()