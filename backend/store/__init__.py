"""Versioned application-store repository boundaries."""

from backend.store.repositories import (
    DocumentKey,
    GenerationConflict,
    OwnerContext,
    Page,
    PaperRepositories,
    PublicationRepositories,
    RepositoryError,
    SnapshotChanged,
    VersionConflict,
    VersionedDocument,
    WriteRequest,
    consistent_read,
)
from backend.store.firestore import FirestoreConflict, FirestoreRestStore, SnapshotExpired
from backend.store.firestore_sdk import FirestoreSdkStore
from backend.store.transactions import TransactionRunner, run_transaction

__all__ = [
    "DocumentKey",
    "GenerationConflict",
    "FirestoreConflict",
    "FirestoreRestStore",
    "FirestoreSdkStore",
    "SnapshotExpired",
    "OwnerContext",
    "Page",
    "PaperRepositories",
    "PublicationRepositories",
    "RepositoryError",
    "SnapshotChanged",
    "TransactionRunner",
    "VersionedDocument",
    "WriteRequest",
    "VersionConflict",
    "consistent_read",
    "run_transaction",
]
