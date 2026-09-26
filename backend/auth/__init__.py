"""Request authentication and current admission checks."""

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
    "FirebaseIdTokenVerifier",
    "FirestoreAdmissionRepository",
    "authenticate_request",
]
