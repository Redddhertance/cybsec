# pipeline stages. each module's testable on its own + raises StageError (or returns a
# result) rather than touching http directly.


class StageError(Exception):
    # a stage raises this to bail the pipeline w an http status. orchestrator turns
    # it into an error response + audit row.

    def __init__(self, stage: str, status_code: int, detail: str, *, headers: dict | None = None):
        super().__init__(detail)
        self.stage = stage
        self.status_code = status_code
        self.detail = detail
        self.headers = headers or {}
