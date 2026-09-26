"""Request authentication and current admission checks."""

from backend.auth.current_user import (
    CurrentUserRepository,
    CurrentUserState,
    CurrentUserUnavailable,
    FirestoreCurrentUserRepository,
)
from backend.auth.identity import (
    AdmittedIdentity,
    AuthenticationError,
    FirebaseIdTokenVerifier,
    FirestoreAdmissionRepository,
    authenticate_request,
)

__all__ = [
    "AdmittedIdentity",
    "AuthenticationError",
    "CurrentUserRepository",
    "CurrentUserState",
    "CurrentUserUnavailable",
    "FirebaseIdTokenVerifier",
    "FirestoreAdmissionRepository",
    "FirestoreCurrentUserRepository",
    "authenticate_request",
]
