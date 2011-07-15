class GitlistsError(Exception):
    """Base class for internal errors.
    """


class TODO(GitlistsError):
    """Raised when we're not done with something, yet.
    """


class InvalidFormData(GitlistsError):
    """Raised when a form is submitted w/ invalid data.
    """


class InternalError(GitlistsError):
    """Raised when we get in a weird state.
    """


class AssertionFailure(InternalError):
    """Raised when we fail an assertion.
    """
