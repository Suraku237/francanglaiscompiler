from contextlib import ExitStack
from unittest.mock import patch


def block_outbound_http(stack: ExitStack):
    sync = stack.enter_context(patch(
        "httpx.HTTPTransport.handle_request",
        side_effect=AssertionError("Compiler workflows must not make outbound HTTP requests."),
    ))
    asynchronous = stack.enter_context(patch(
        "httpx.AsyncHTTPTransport.handle_async_request",
        side_effect=AssertionError("Compiler workflows must not make outbound HTTP requests."),
    ))
    return sync, asynchronous
