class BackendUnavailableError(RuntimeError):
    pass


class BackendTimeoutError(RuntimeError):
    pass


class UpstreamProtocolError(RuntimeError):
    pass
