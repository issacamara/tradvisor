"""Offline checks for static hosting and development identity configuration."""

from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[3]


class HostingConfigurationTests(unittest.TestCase):
    def test_hosting_serves_static_export_and_falls_back_for_unknown_paths(self) -> None:
        config = json.loads((ROOT / "firebase.json").read_text())
        hosting = config["hosting"]

        self.assertEqual(hosting["public"], "frontend/out")
        self.assertIn("**/node_modules/**", hosting["ignore"])
        self.assertEqual(
            hosting["rewrites"],
            [{"source": "**", "destination": "/index.html"}],
        )
        self.assertNotIn("redirects", hosting)

    def test_workspace_routes_are_static_and_refreshable(self) -> None:
        next_config = (ROOT / "frontend/next.config.ts").read_text()
        self.assertRegex(next_config, r'output\s*:\s*"export"')
        self.assertRegex(next_config, r'trailingSlash\s*:\s*true')

        for route in ("swing", "long-term", "paper"):
            with self.subTest(route=route):
                self.assertTrue((ROOT / "frontend/src/app" / route / "page.tsx").is_file())

        app_sources = list((ROOT / "frontend/src/app").rglob("*.tsx"))
        for source in app_sources:
            with self.subTest(source=source.relative_to(ROOT)):
                text = source.read_text()
                self.assertNotRegex(text, r"(?m)^\s*['\"]use server['\"]")
                self.assertNotRegex(text, r"(?m)^\s*export\s+async\s+function\s+\w+Action")

    def test_identity_configuration_is_opt_in_and_development_only(self) -> None:
        identity = (ROOT / "terraform/hosting_identity.tf").read_text()

        self.assertRegex(
            identity,
            r'variable "configure_v1_identity"\s*\{[^}]*default\s*=\s*false',
        )
        self.assertRegex(
            identity,
            r"count\s*=\s*var\.configure_v1_identity \? 1 : 0",
        )
        self.assertIn("enabled           = true", identity)
        self.assertIn("password_required = true", identity)
        self.assertIn("authorized_domains = var.v1_identity_authorized_domains", identity)
        self.assertIn('domain == "${var.project_id}.web.app"', identity)
        self.assertIn('domain == "${var.project_id}.firebaseapp.com"', identity)
        self.assertIn('condition     = var.project_id == "dev-tradvisor"', identity)
        self.assertNotRegex(identity, r"https?://[^\s\"]+")

    def test_sign_in_configuration_does_not_grant_application_admission(self) -> None:
        identity = (ROOT / "terraform/hosting_identity.tf").read_text()
        self.assertRegex(
            identity,
            r"precondition\s*\{\s*condition\s*=\s*length\(var\.v1_identity_authorized_domains\) > 0",
        )
        self.assertIn(
            "Identity redirect domains must be local or belong to the configured development Firebase project.",
            identity,
        )

        self.assertIn("Sign-in establishes identity only.", identity)
        self.assertIn("Backend verified-email and manual allowlist", identity)


if __name__ == "__main__":
    unittest.main()
