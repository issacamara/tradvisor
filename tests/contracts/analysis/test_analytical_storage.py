from backend.contracts.analytical_storage import (
    ANNUAL_FINANCIAL_REVISIONS_V1,
    ANALYTICAL_SOURCE_TABLES,
    SHARE_PRICE_REVISIONS_V1,
    TableSpec,
)


def test_share_revision_contract_is_additive_and_revision_keyed() -> None:
    fields = {field.name: field for field in SHARE_PRICE_REVISIONS_V1.fields}

    assert SHARE_PRICE_REVISIONS_V1.table_name == "share_price_revisions_v1"
    assert SHARE_PRICE_REVISIONS_V1.immutable_key == (
        "symbol",
        "session_date",
        "revision_id",
    )
    assert fields["session_date_status"].mode == "REQUIRED"
    assert fields["trade_status"].mode == "REQUIRED"
    assert {"source_observation_id", "source_revision_id", "collected_at", "known_at"} <= set(fields)
    assert "financials" not in {table.table_name for table in (SHARE_PRICE_REVISIONS_V1,)}


def test_annual_financial_contract_preserves_period_scope_and_source_revisions() -> None:
    fields = {field.name: field for field in ANNUAL_FINANCIAL_REVISIONS_V1.fields}
    non_financial_amount_fields = {
        "interest_bearing_debt",
        "unrestricted_cash",
        "current_assets",
        "current_liabilities",
    }

    assert ANNUAL_FINANCIAL_REVISIONS_V1.table_name == "annual_financial_revisions_v1"
    assert ANNUAL_FINANCIAL_REVISIONS_V1.immutable_key == (
        "company_id",
        "fiscal_period_start",
        "fiscal_period_end",
        "report_scope",
        "source_id",
        "source_observation_id",
        "revision_id",
    )
    assert fields["ordinary_owner_earnings"].field_type == "NUMERIC"
    assert fields["opening_equity"].field_type == "NUMERIC"
    assert (fields["accounting_basis"].field_type, fields["accounting_basis"].mode) == (
        "STRING",
        "NULLABLE",
    )
    assert (
        fields["opening_equity_date"].field_type,
        fields["opening_equity_date"].mode,
    ) == ("DATE", "NULLABLE")
    assert {
        name: (fields[name].field_type, fields[name].mode)
        for name in non_financial_amount_fields
    } == {name: ("NUMERIC", "NULLABLE") for name in non_financial_amount_fields}
    assert fields["publication_status"].mode == "REQUIRED"
    assert {
        "revenue",
        "ordinary_owner_earnings",
        "equity",
        "opening_equity",
        "opening_equity_date",
        "accounting_basis",
        "publication_status",
        "reason_codes",
        "source_revision_id",
        "collected_at",
        "known_at",
        "original_scale",
    } <= set(fields)
    assert fields["reason_codes"].mode == "REPEATED"
    assert ANNUAL_FINANCIAL_REVISIONS_V1.partition_candidates == (
        "fiscal_period_end",
        "collected_at",
    )
    assert "financials" not in {table.table_name for table in ANALYTICAL_SOURCE_TABLES}


def test_table_contract_rejects_invalid_key_and_partition_candidates() -> None:
    try:
        TableSpec(
            table_name="invalid_v1",
            version=1,
            fields=(),
            immutable_key=("missing",),
            partition_candidates=(),
        )
    except ValueError as error:
        assert "immutable key" in str(error)
    else:
        raise AssertionError("invalid immutable key should be rejected")
