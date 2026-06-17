"""Tests for secret management (keyring + env + file fallback chain).

All keyring interactions are mocked — we never touch the real OS keychain.
File fallback writes to a tmp_path so nothing leaks to the real home dir.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from app import secrets as secrets_mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def clean_env(monkeypatch):
    """Remove HOMEDOCTOR_LLM_API_KEY from the environment for the test."""
    monkeypatch.delenv("HOMEDOCTOR_LLM_API_KEY", raising=False)
    yield


@pytest.fixture
def fake_secrets_dir(tmp_path, monkeypatch):
    """Redirect the on-disk secrets dir to a temp location."""
    fake_dir = tmp_path / "secrets"
    monkeypatch.setattr(secrets_mod, "SECRETS_DIR", fake_dir)
    return fake_dir


# ---------------------------------------------------------------------------
# get_secret — priority chain
# ---------------------------------------------------------------------------
class TestGetSecret:
    """Verify the resolution priority: env > keyring > file > default."""

    def test_env_var_wins(self, monkeypatch, fake_secrets_dir):
        """Environment variable has highest priority."""
        monkeypatch.setenv("HOMEDOCTOR_LLM_API_KEY", "env-value")

        # Even if keyring and file have different values, env wins
        with mock.patch.object(secrets_mod, "HAS_KEYRING", True):
            with mock.patch("keyring.get_password", return_value="keyring-value"):
                # also write a file
                fake_secrets_dir.mkdir(parents=True, exist_ok=True)
                (fake_secrets_dir / "llm_api_key").write_text("file-value")

                result = secrets_mod.get_secret(
                    "llm_api_key", "HOMEDOCTOR_LLM_API_KEY"
                )

        assert result == "env-value"

    def test_keyring_used_when_no_env(self, monkeypatch, fake_secrets_dir):
        """When env var absent, keyring value is returned."""
        monkeypatch.delenv("HOMEDOCTOR_LLM_API_KEY", raising=False)

        with mock.patch.object(secrets_mod, "HAS_KEYRING", True):
            with mock.patch("keyring.get_password", return_value="kr-secret"):
                result = secrets_mod.get_secret(
                    "llm_api_key", "HOMEDOCTOR_LLM_API_KEY"
                )

        assert result == "kr-secret"

    def test_file_used_when_no_env_no_keyring(self, monkeypatch, fake_secrets_dir):
        """When env and keyring absent, file value is returned."""
        monkeypatch.delenv("HOMEDOCTOR_LLM_API_KEY", raising=False)
        fake_secrets_dir.mkdir(parents=True, exist_ok=True)
        (fake_secrets_dir / "llm_api_key").write_text("  file-secret  \n")

        with mock.patch.object(secrets_mod, "HAS_KEYRING", False):
            result = secrets_mod.get_secret(
                "llm_api_key", "HOMEDOCTOR_LLM_API_KEY"
            )

        assert result == "file-secret"  # stripped

    def test_file_used_when_no_env_and_keyring_returns_none(
        self, monkeypatch, fake_secrets_dir
    ):
        """When keyring returns None, fall through to file."""
        monkeypatch.delenv("HOMEDOCTOR_LLM_API_KEY", raising=False)
        fake_secrets_dir.mkdir(parents=True, exist_ok=True)
        (fake_secrets_dir / "llm_api_key").write_text("file-val")

        with mock.patch.object(secrets_mod, "HAS_KEYRING", True):
            with mock.patch("keyring.get_password", return_value=None):
                result = secrets_mod.get_secret(
                    "llm_api_key", "HOMEDOCTOR_LLM_API_KEY"
                )

        assert result == "file-val"

    def test_default_returned_when_nothing_found(
        self, monkeypatch, fake_secrets_dir
    ):
        """When no source has the secret, default is returned."""
        monkeypatch.delenv("HOMEDOCTOR_LLM_API_KEY", raising=False)

        with mock.patch.object(secrets_mod, "HAS_KEYRING", False):
            result = secrets_mod.get_secret(
                "llm_api_key", "HOMEDOCTOR_LLM_API_KEY", default="fallback"
            )

        assert result == "fallback"

    def test_empty_default(self, monkeypatch, fake_secrets_dir):
        """Default default is empty string."""
        monkeypatch.delenv("HOMEDOCTOR_LLM_API_KEY", raising=False)

        with mock.patch.object(secrets_mod, "HAS_KEYRING", False):
            result = secrets_mod.get_secret(
                "llm_api_key", "HOMEDOCTOR_LLM_API_KEY"
            )

        assert result == ""

    def test_keyring_exception_falls_through_to_file(
        self, monkeypatch, fake_secrets_dir
    ):
        """If keyring raises, we gracefully fall through to file."""
        monkeypatch.delenv("HOMEDOCTOR_LLM_API_KEY", raising=False)
        fake_secrets_dir.mkdir(parents=True, exist_ok=True)
        (fake_secrets_dir / "llm_api_key").write_text("file-val")

        with mock.patch.object(secrets_mod, "HAS_KEYRING", True):
            with mock.patch(
                "keyring.get_password", side_effect=Exception("D-Bus error")
            ):
                result = secrets_mod.get_secret(
                    "llm_api_key", "HOMEDOCTOR_LLM_API_KEY"
                )

        assert result == "file-val"

    def test_use_keyring_false_skips_keyring(self, monkeypatch, fake_secrets_dir):
        """When use_keyring=False, keyring is never consulted."""
        monkeypatch.delenv("HOMEDOCTOR_LLM_API_KEY", raising=False)
        fake_secrets_dir.mkdir(parents=True, exist_ok=True)
        (fake_secrets_dir / "llm_api_key").write_text("file-val")

        mock_get = mock.Mock(return_value="should-not-see-this")
        with mock.patch.object(secrets_mod, "HAS_KEYRING", True):
            with mock.patch("keyring.get_password", mock_get):
                result = secrets_mod.get_secret(
                    "llm_api_key",
                    "HOMEDOCTOR_LLM_API_KEY",
                    use_keyring=False,
                )

        assert result == "file-val"
        mock_get.assert_not_called()

    def test_empty_env_var_does_not_short_circuit(self, monkeypatch, fake_secrets_dir):
        """An empty-string env var should not count as 'set'."""
        monkeypatch.setenv("HOMEDOCTOR_LLM_API_KEY", "")

        with mock.patch.object(secrets_mod, "HAS_KEYRING", True):
            with mock.patch("keyring.get_password", return_value="kr-val"):
                result = secrets_mod.get_secret(
                    "llm_api_key", "HOMEDOCTOR_LLM_API_KEY"
                )

        assert result == "kr-val"


# ---------------------------------------------------------------------------
# set_secret
# ---------------------------------------------------------------------------
class TestSetSecret:
    """Verify secret storage — keyring first, file fallback."""

    def test_set_via_keyring_when_available(self, monkeypatch, fake_secrets_dir):
        """When keyring is available, it's used and no file is written."""
        monkeypatch.delenv("HOMEDOCTOR_LLM_API_KEY", raising=False)

        mock_set = mock.Mock()
        with mock.patch.object(secrets_mod, "HAS_KEYRING", True):
            with mock.patch("keyring.set_password", mock_set):
                ok = secrets_mod.set_secret("llm_api_key", "my-secret")

        assert ok is True
        mock_set.assert_called_once_with(
            secrets_mod.KEYRING_SERVICE, "llm_api_key", "my-secret"
        )
        # File should NOT have been written
        assert not (fake_secrets_dir / "llm_api_key").exists()

    def test_file_fallback_when_keyring_unavailable(
        self, monkeypatch, fake_secrets_dir
    ):
        """When keyring not installed, write to file with 0600 perms."""
        with mock.patch.object(secrets_mod, "HAS_KEYRING", False):
            ok = secrets_mod.set_secret("llm_api_key", "my-secret")

        assert ok is True
        written = (fake_secrets_dir / "llm_api_key").read_text()
        assert written == "my-secret"

    def test_file_fallback_when_keyring_fails(self, monkeypatch, fake_secrets_dir):
        """When keyring raises, fall back to file."""
        with mock.patch.object(secrets_mod, "HAS_KEYRING", True):
            with mock.patch(
                "keyring.set_password", side_effect=Exception("no backend")
            ):
                ok = secrets_mod.set_secret("llm_api_key", "my-secret")

        assert ok is True
        written = (fake_secrets_dir / "llm_api_key").read_text()
        assert written == "my-secret"


# ---------------------------------------------------------------------------
# delete_secret
# ---------------------------------------------------------------------------
class TestDeleteSecret:
    """Verify deletion from all stores."""

    def test_delete_removes_keyring_and_file(self, monkeypatch, fake_secrets_dir):
        """delete_secret removes from keyring and file."""
        fake_secrets_dir.mkdir(parents=True, exist_ok=True)
        secret_file = fake_secrets_dir / "llm_api_key"
        secret_file.write_text("to-delete")

        mock_del = mock.Mock()
        with mock.patch.object(secrets_mod, "HAS_KEYRING", True):
            with mock.patch("keyring.delete_password", mock_del):
                ok = secrets_mod.delete_secret("llm_api_key")

        assert ok is True
        mock_del.assert_called_once_with(
            secrets_mod.KEYRING_SERVICE, "llm_api_key"
        )
        assert not secret_file.exists()

    def test_delete_when_file_missing(self, monkeypatch, fake_secrets_dir):
        """Deleting when nothing exists still returns True (idempotent)."""
        with mock.patch.object(secrets_mod, "HAS_KEYRING", False):
            ok = secrets_mod.delete_secret("nonexistent")

        assert ok is True

    def test_delete_keyring_failure_returns_true_if_file_gone(
        self, monkeypatch, fake_secrets_dir
    ):
        """If keyring delete fails but file removed, still success."""
        fake_secrets_dir.mkdir(parents=True, exist_ok=True)
        (fake_secrets_dir / "llm_api_key").write_text("x")

        with mock.patch.object(secrets_mod, "HAS_KEYRING", True):
            with mock.patch(
                "keyring.delete_password",
                side_effect=Exception("not found"),
            ):
                ok = secrets_mod.delete_secret("llm_api_key")

        assert ok is True
        assert not (fake_secrets_dir / "llm_api_key").exists()


# ---------------------------------------------------------------------------
# Round-trip integration
# ---------------------------------------------------------------------------
class TestRoundTrip:
    """set → get round-trip with file fallback (no keyring)."""

    def test_set_then_get_file_only(self, monkeypatch, fake_secrets_dir):
        """Set via file fallback, then get returns the same value."""
        monkeypatch.delenv("HOMEDOCTOR_LLM_API_KEY", raising=False)

        with mock.patch.object(secrets_mod, "HAS_KEYRING", False):
            secrets_mod.set_secret("llm_api_key", "round-trip-value")
            result = secrets_mod.get_secret(
                "llm_api_key", "HOMEDOCTOR_LLM_API_KEY"
            )

        assert result == "round-trip-value"


# ---------------------------------------------------------------------------
# Config integration
# ---------------------------------------------------------------------------
class TestConfigIntegration:
    """Verify Settings resolves LLM_API_KEY via the secret chain."""

    def test_settings_env_var(self, monkeypatch, tmp_path):
        """Settings picks up env var directly (Docker path)."""
        monkeypatch.setenv("HOMEDOCTOR_LLM_API_KEY", "from-env-123")

        # Import fresh to avoid cached singleton
        import importlib
        import app.config as config_mod

        importlib.reload(config_mod)
        assert config_mod.settings.LLM_API_KEY == "from-env-123"

    def test_settings_file_fallback(self, monkeypatch, tmp_path):
        """When no env var, Settings resolves via file fallback."""
        monkeypatch.delenv("HOMEDOCTOR_LLM_API_KEY", raising=False)

        # Point secrets dir at tmp
        fake_dir = tmp_path / "secrets"
        fake_dir.mkdir(parents=True)
        (fake_dir / "llm_api_key").write_text("from-file-456")

        monkeypatch.setattr(secrets_mod, "SECRETS_DIR", fake_dir)

        with mock.patch.object(secrets_mod, "HAS_KEYRING", False):
            import importlib
            import app.config as config_mod

            importlib.reload(config_mod)

        assert config_mod.settings.LLM_API_KEY == "from-file-456"

    def test_settings_keyring_disabled(self, monkeypatch, tmp_path):
        """KEYRING_ENABLED=False skips keyring, still uses env/file."""
        monkeypatch.delenv("HOMEDOCTOR_LLM_API_KEY", raising=False)
        monkeypatch.setenv("HOMEDOCTOR_KEYRING_ENABLED", "false")

        # Ensure keyring would have returned a value we don't want
        mock_get = mock.Mock(return_value="should-not-see")
        with mock.patch.object(secrets_mod, "HAS_KEYRING", True):
            with mock.patch("keyring.get_password", mock_get):
                import importlib
                import app.config as config_mod

                importlib.reload(config_mod)

        assert config_mod.settings.KEYRING_ENABLED is False
        assert config_mod.settings.LLM_API_KEY == ""
        mock_get.assert_not_called()
