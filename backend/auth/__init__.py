"""Request authentication and current admission checks."""

from backend.auth.identity import (
    AdmittedIdentity,
    RegisterAdmissionDenyFence,
    AuthenticationError,
    FirebaseIdTokenVerifier,
    FirestoreAdmissionRepository,
    authenticate_request,
)

__all__ = [
    "AdmittedIdentity",
    "RegisterAdmissionDenyFence",
    "AuthenticationError",
    "FirebaseIdTokenVerifier",
    "FirestoreAdmissionRepository",
    "authenticate_request",
]
