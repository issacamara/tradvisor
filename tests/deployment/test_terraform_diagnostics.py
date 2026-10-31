from scripts.deployment.sanitize_terraform_diagnostics import sanitize


def test_diagnostics_redact_openrouter_keys_secrets_and_authorization_headers() -> None:
    output = sanitize(
        """Authorization: Bearer header-token
OPENROUTER_API_KEY=sk-or-v1-private-value
secret_data: "sensitive-value"
{"authorization": "Bearer json-header-token", "secret_value": "json-secret"}
request https://example.test/path?token=query-value
"""
    )

    assert "header-token" not in output
    assert "sk-or-v1-private-value" not in output
    assert "sensitive-value" not in output
    assert "json-header-token" not in output
    assert "json-secret" not in output
    assert "query-value" not in output
    assert "Authorization: <redacted>" in output
    assert "OPENROUTER_API_KEY=<redacted>" in output

