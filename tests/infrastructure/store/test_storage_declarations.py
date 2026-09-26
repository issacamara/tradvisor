import json
from pathlib import Path


ROOT = Path(__file__).parents[3]


def test_firebase_cli_maps_firestore_declarations() -> None:
    firebase = json.loads((ROOT / "firebase.json").read_text())

    assert firebase["firestore"] == {
        "rules": "firestore.rules",
        "indexes": "firestore.indexes.json",
    }


def test_firestore_rules_deny_all_direct_client_access() -> None:
    rules = (ROOT / "firestore.rules").read_text()

    assert "rules_version = '2';" in rules
    assert "match /{document=**}" in rules
    assert "allow read, write: if false;" in rules
    assert "if request.auth" not in rules


def test_firestore_indexes_are_limited_to_declared_queries() -> None:
    indexes = json.loads((ROOT / "firestore.indexes.json").read_text())["indexes"]
    collection_group_orders = [
        index
        for index in indexes
        if index["collectionGroup"] == "orders"
        and index["queryScope"] == "COLLECTION_GROUP"
    ]

    assert collection_group_orders == [
        {
            "collectionGroup": "orders",
            "queryScope": "COLLECTION_GROUP",
            "fields": [
                {"fieldPath": "status", "order": "ASCENDING"},
                {"fieldPath": "intended_session", "order": "ASCENDING"},
            ],
        }
    ]
    assert len(indexes) == 5


def test_firestore_database_and_daily_backup_are_protected() -> None:
    firestore = (ROOT / "terraform" / "firestore.tf").read_text()

    assert 'resource "google_firestore_database" "v1"' in firestore
    assert 'type        = "FIRESTORE_NATIVE"' in firestore
    assert 'name        = "(default)"' in firestore
    assert 'resource "google_firestore_backup_schedule" "v1_daily"' in firestore
    assert 'retention = "604800s"' in firestore
    assert "daily_recurrence {}" in firestore
    assert firestore.count("prevent_destroy = true") == 2


def test_recovery_register_is_private_versioned_and_has_separate_cleanup_role() -> None:
    terraform = (ROOT / "terraform" / "recovery_register.tf").read_text()
    variables = (ROOT / "terraform" / "variables.tf").read_text()
    writer_permissions = terraform.split(
        'resource "google_project_iam_custom_role" "recovery_register_writer"', 1
    )[1].split("\n}", 1)[0]
    cleanup_permissions = terraform.split(
        'resource "google_project_iam_custom_role" "recovery_register_cleanup"', 1
    )[1].split("\n}", 1)[0]

    assert 'resource "google_storage_bucket" "v1_recovery_register"' in terraform
    assert "uniform_bucket_level_access = true" in terraform
    assert 'public_access_prevention    = "enforced"' in terraform
    assert "force_destroy               = false" in terraform
    assert "versioning {\n    enabled = true\n  }" in terraform
    assert "prevent_destroy = true" in terraform
    assert '"storage.objects.create"' in writer_permissions
    assert '"storage.objects.delete"' not in writer_permissions
    assert '"storage.objects.delete"' in cleanup_permissions
    assert "var.recovery_register_cleanup_members" in terraform
    assert 'default     = []' in variables
    assert (
        'resource "google_storage_bucket_iam_member" "recovery_register_runtime_writer"'
        in terraform
    )
