import docker


class DockerClient:
    """Wrapper around Docker SDK client."""

    def __init__(self, base_url=None):
        """Connect to Docker daemon.

        Args:
            base_url: Docker daemon URL (e.g. 'tcp://192.168.1.100:2375').
                      If None, uses the local Docker socket.
        """
        if base_url:
            self._client = docker.DockerClient(base_url=base_url)
        else:
            self._client = docker.from_env()

    @property
    def client(self):
        return self._client

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
