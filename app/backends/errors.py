class BackendUnavailableError(RuntimeError):
    pass


class BackendTimeoutError(RuntimeError):
    pass


class BackendResourceExhaustedError(RuntimeError):
    """上游因 CUDA OOM、KV Cache 耗尽等资源压力无法继续服务。"""


class UpstreamProtocolError(RuntimeError):
    pass
