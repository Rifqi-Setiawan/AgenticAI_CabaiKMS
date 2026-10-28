class KmsError(Exception):
    """Safe, operator-facing error without credentials or raw SQL."""


class Conflict(KmsError):
    pass


class InvalidState(KmsError):
    pass


class NotFound(KmsError):
    pass
