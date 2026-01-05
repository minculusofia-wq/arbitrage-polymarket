"""
Platform Credentials Interface - Abstract base class for platform credentials.

This module defines the credential interfaces that each platform must implement,
enabling secure and validated credential management across platforms.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Tuple, Optional
import re


class IPlatformCredentials(ABC):
    """
    Abstract base class for platform credentials.

    All platform-specific credential classes must implement this interface
    to enable unified credential management and validation.
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the platform name (e.g., 'polymarket', 'kalshi')."""
        pass

    @abstractmethod
    def validate(self) -> Tuple[bool, str]:
        """
        Validate the credentials.

        Returns:
            Tuple of (is_valid, error_message).
            If valid, error_message is empty string.
        """
        pass

    @abstractmethod
    def to_client_kwargs(self) -> Dict:
        """
        Convert credentials to kwargs for client initialization.

        Returns:
            Dictionary of keyword arguments for the platform client.
        """
        pass

    @abstractmethod
    def to_env_dict(self) -> Dict[str, str]:
        """
        Convert credentials to environment variable dictionary.

        Returns:
            Dictionary mapping env var names to values.
        """
        pass

    @abstractmethod
    def is_complete(self) -> bool:
        """
        Check if all required credentials are present.

        Returns:
            True if all required fields have values.
        """
        pass


@dataclass
class PolymarketCredentials(IPlatformCredentials):
    """
    Polymarket API credentials.

    Required for:
    - API Key, Secret, Passphrase: CLOB API authentication
    - Private Key: Wallet signing for order execution
    """
    api_key: str = ""
    api_secret: str = ""
    passphrase: str = ""
    private_key: str = ""

    @property
    def platform_name(self) -> str:
        return "polymarket"

    def validate(self) -> Tuple[bool, str]:
        """Validate Polymarket credentials."""
        if not self.api_key:
            return False, "Missing Polymarket API Key"
        if not self.api_secret:
            return False, "Missing Polymarket API Secret"
        if not self.passphrase:
            return False, "Missing Polymarket Passphrase"
        if not self.private_key:
            return False, "Missing Polymarket Private Key"

        # Validate private key format
        pk = self.private_key
        if pk.startswith("0x"):
            pk = pk[2:]

        if len(pk) != 64:
            return False, f"Invalid private key length: {len(pk)} (expected 64 hex chars)"

        if not re.match(r'^[0-9a-fA-F]+$', pk):
            return False, "Private key must be hexadecimal"

        return True, ""

    def to_client_kwargs(self) -> Dict:
        """Convert to py_clob_client initialization kwargs."""
        pk = self.private_key
        if pk.startswith("0x"):
            pk = pk[2:]

        return {
            "key": self.api_key.strip(),
            "secret": self.api_secret.strip(),
            "passphrase": self.passphrase.strip(),
            "private_key": pk.strip()
        }

    def to_env_dict(self) -> Dict[str, str]:
        """Convert to .env format."""
        return {
            "POLY_API_KEY": self.api_key,
            "POLY_API_SECRET": self.api_secret,
            "POLY_API_PASSPHRASE": self.passphrase,
            "PRIVATE_KEY": self.private_key
        }

    def is_complete(self) -> bool:
        """Check if all required Polymarket credentials are present."""
        return all([
            self.api_key,
            self.api_secret,
            self.passphrase,
            self.private_key
        ])

    @classmethod
    def from_env(cls, env_dict: Dict[str, str]) -> 'PolymarketCredentials':
        """Create credentials from environment variables."""
        return cls(
            api_key=env_dict.get("POLY_API_KEY", "").strip(),
            api_secret=env_dict.get("POLY_API_SECRET", "").strip(),
            passphrase=env_dict.get("POLY_API_PASSPHRASE", "").strip(),
            private_key=env_dict.get("PRIVATE_KEY", "").strip()
        )


@dataclass
class KalshiCredentials(IPlatformCredentials):
    """
    Kalshi API credentials.

    Required for API v2 RSA-PSS authentication:
    - api_key_id: The API key ID from Kalshi dashboard
    - private_key_path: Path to the RSA private key PEM file
    - private_key_pem: The RSA private key content (alternative to path)
    """
    api_key_id: str = ""
    private_key_path: str = ""
    private_key_pem: str = ""

    @property
    def platform_name(self) -> str:
        return "kalshi"

    def validate(self) -> Tuple[bool, str]:
        """Validate Kalshi credentials."""
        if not self.api_key_id:
            return False, "Missing Kalshi API Key ID"

        # Need either path or PEM content
        if not self.private_key_path and not self.private_key_pem:
            return False, "Missing Kalshi private key (provide path or PEM content)"

        # If path provided, check it looks valid
        if self.private_key_path:
            import os
            if not os.path.exists(self.private_key_path):
                return False, f"Private key file not found: {self.private_key_path}"

        # If PEM content provided, validate format
        if self.private_key_pem:
            if "-----BEGIN" not in self.private_key_pem:
                return False, "Invalid PEM format (missing BEGIN marker)"
            if "PRIVATE KEY" not in self.private_key_pem:
                return False, "Invalid PEM format (not a private key)"

        return True, ""

    def get_private_key_pem(self) -> str:
        """Get the private key PEM content."""
        if self.private_key_pem:
            return self.private_key_pem

        if self.private_key_path:
            import os
            with open(os.path.expanduser(self.private_key_path), 'r') as f:
                return f.read()

        return ""

    def to_client_kwargs(self) -> Dict:
        """Convert to KalshiClient initialization kwargs."""
        return {
            "api_key_id": self.api_key_id.strip(),
            "private_key_pem": self.get_private_key_pem()
        }

    def to_env_dict(self) -> Dict[str, str]:
        """Convert to .env format."""
        return {
            "KALSHI_API_KEY_ID": self.api_key_id,
            "KALSHI_PRIVATE_KEY_PATH": self.private_key_path,
        }

    def is_complete(self) -> bool:
        """Check if all required Kalshi credentials are present."""
        return bool(self.api_key_id and (self.private_key_path or self.private_key_pem))

    @classmethod
    def from_env(cls, env_dict: Dict[str, str]) -> 'KalshiCredentials':
        """Create credentials from environment variables."""
        return cls(
            api_key_id=env_dict.get("KALSHI_API_KEY_ID", "").strip(),
            private_key_path=env_dict.get("KALSHI_PRIVATE_KEY_PATH", "").strip(),
            private_key_pem=env_dict.get("KALSHI_PRIVATE_KEY_PEM", "").strip()
        )


class CredentialsManager:
    """
    Manager for handling credentials across multiple platforms.

    Provides unified interface for loading, validating, and saving
    credentials for all supported platforms.
    """

    def __init__(self):
        self._credentials: Dict[str, IPlatformCredentials] = {}

    def set_credentials(self, credentials: IPlatformCredentials) -> None:
        """Store credentials for a platform."""
        self._credentials[credentials.platform_name] = credentials

    def get_credentials(self, platform: str) -> Optional[IPlatformCredentials]:
        """Get credentials for a specific platform."""
        return self._credentials.get(platform)

    def validate_all(self) -> Dict[str, Tuple[bool, str]]:
        """Validate all stored credentials."""
        results = {}
        for platform, creds in self._credentials.items():
            results[platform] = creds.validate()
        return results

    def get_enabled_platforms(self) -> list:
        """Get list of platforms with complete credentials."""
        return [
            platform for platform, creds in self._credentials.items()
            if creds.is_complete() and creds.validate()[0]
        ]

    def to_env_dict(self) -> Dict[str, str]:
        """Get combined environment dictionary for all platforms."""
        env_dict = {}
        for creds in self._credentials.values():
            env_dict.update(creds.to_env_dict())

        # Add enabled platforms
        enabled = self.get_enabled_platforms()
        env_dict["ENABLED_PLATFORMS"] = ",".join(enabled)

        return env_dict

    @classmethod
    def from_env(cls, env_dict: Dict[str, str]) -> 'CredentialsManager':
        """Create manager with credentials loaded from environment."""
        manager = cls()

        # Load Polymarket credentials
        poly_creds = PolymarketCredentials.from_env(env_dict)
        if poly_creds.is_complete():
            manager.set_credentials(poly_creds)

        # Load Kalshi credentials
        kalshi_creds = KalshiCredentials.from_env(env_dict)
        if kalshi_creds.is_complete():
            manager.set_credentials(kalshi_creds)

        return manager
