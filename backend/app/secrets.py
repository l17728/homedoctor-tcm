"""Secret management — keyring first, env var fallback, file fallback.

Priority order for *resolving* a secret (get_secret):
    1. Environment variable  (always works — essential for Docker / CI)
    2. OS keyring            (local desktop, if keyring package installed)
    3. Local file            (~/.homedoctor/secrets/<name>, headless without keyring)
    4. Default value

Keyring is an *optional* dependency. If the ``keyring`` package is not
installed (common in Docker/headless containers), the module silently
falls back to env var + file. This keeps Docker deployments working
unchanged while enabling OS-native secret storage on developer laptops.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional keyring import — gracefully degrade if unavailable
# ---------------------------------------------------------------------------
try:
    import keyring  # type: ignore[import]

    HAS_KEYRING = True
except ImportError:  # pragma: no cover - environment dependent
    HAS_KEYRING = False
    logger.info(
        "keyring package not installed — using env/file fallback for secrets"
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
KEYRING_SERVICE = "homedoctor"
KEYRING_USERNAME = "llm_api_key"

SECRETS_DIR = Path.home() / ".homedoctor" / "secrets"


def _file_path(name: str) -> Path:
    """Return the on-disk fallback path for a named secret."""
    return SECRETS_DIR / name


def get_secret(
    name: str,
    env_var: str,
    default: str = "",
    *,
    use_keyring: bool = True,
) -> str:
    """Resolve a secret value using the priority chain.

    Priority order:
        1. Environment variable (Docker, CI/CD) — highest
        2. OS keyring (local desktop, if available and ``use_keyring``)
        3. Local file ``~/.homedoctor/secrets/<name>`` (headless fallback)
        4. ``default``

    Args:
        name: Logical secret name for keyring/file storage (e.g. "llm_api_key").
        env_var: Environment variable name (e.g. "HOMEDOCTOR_LLM_API_KEY").
        default: Value returned when no source has the secret.
        use_keyring: If ``False``, skip the OS keyring source entirely
            (useful when the deployment wants env/file only).

    Returns:
        The secret string, or ``default`` if not found anywhere.
    """
    # 1. Environment variable (Docker, CI/CD) — always wins
    val = os.environ.get(env_var, "")
    if val:
        return val

    # 2. OS keyring (local desktop)
    if use_keyring and HAS_KEYRING:
        try:
            kr_val = keyring.get_password(KEYRING_SERVICE, name)
            if kr_val:
                return kr_val
        except Exception as exc:  # noqa: BLE001 — keyring backends vary wildly
            logger.debug("Keyring access failed for %s: %s", name, exc)

    # 3. Local file fallback (headless without keyring)
    file_path = _file_path(name)
    if file_path.exists():
        try:
            return file_path.read_text(encoding="utf-8").strip()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Secret file read failed for %s: %s", name, exc)

    # 4. Default
    return default


def set_secret(name: str, value: str) -> bool:
    """Store a secret. Returns ``True`` if stored successfully.

    Tries the OS keyring first (most secure). If keyring is unavailable or
    fails (e.g. no D-Bus in headless Linux), falls back to writing a
    mode-0600 file under ``~/.homedoctor/secrets/``.
    """
    # Try keyring first
    if HAS_KEYRING:
        try:
            keyring.set_password(KEYRING_SERVICE, name, value)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Keyring storage failed for %s: %s", name, exc)

    # Fallback: write to local file with restricted permissions
    file_path = _file_path(name)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(value, encoding="utf-8")
        try:
            file_path.chmod(0o600)  # Owner read/write only
        except Exception:  # pragma: no cover — Windows / non-POSIX
            # Windows doesn't support POSIX chmod; file ACLs are separate.
            pass
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to write secret file for %s: %s", name, exc)
        return False


def delete_secret(name: str) -> bool:
    """Delete a secret from all stores.

    Removes the secret from both the OS keyring (if available) and the
    local file fallback. Returns ``True`` if at least one store was
    successfully cleared (or already empty).
    """
    success = True

    if HAS_KEYRING:
        try:
            keyring.delete_password(KEYRING_SERVICE, name)
        except Exception:  # noqa: BLE001 — already absent is fine
            pass

    file_path = _file_path(name)
    if file_path.exists():
        try:
            file_path.unlink()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to delete secret file for %s: %s", name, exc)
            success = False

    return success
