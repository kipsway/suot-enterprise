import socket
from typing import Any, Dict, List, Optional, Tuple
from xmlrpc.client import ServerProxy

from services.database import DatabaseManager


class LDAPConfig:
    HOST = ""
    PORT = 389
    BASE_DN = ""
    USERNAME_ATTR = "sAMAccountName"
    EMAIL_ATTR = "mail"
    FULL_NAME_ATTR = "displayName"
    TLS = False
    TIMEOUT = 10


class LDAPAuthProvider:
    def __init__(self) -> None:
        self.db = DatabaseManager()
        self._load_config()

    def _load_config(self) -> None:
        LDAPConfig.HOST = self.db.get_setting("ldap_host", "")
        try:
            LDAPConfig.PORT = int(self.db.get_setting("ldap_port", "389"))
        except ValueError:
            LDAPConfig.PORT = 389
        LDAPConfig.BASE_DN = self.db.get_setting("ldap_base_dn", "")
        LDAPConfig.TLS = self.db.get_setting("ldap_tls", "0") == "1"

    def is_configured(self) -> bool:
        return bool(LDAPConfig.HOST and LDAPConfig.BASE_DN)

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        if not self.is_configured():
            return None

        try:
            import ldap3
        except ImportError:
            return None

        server = ldap3.Server(
            LDAPConfig.HOST,
            port=LDAPConfig.PORT,
            use_ssl=LDAPConfig.TLS,
            connect_timeout=LDAPConfig.TIMEOUT,
        )

        user_dn = f"{LDAPConfig.USERNAME_ATTR}={username},{LDAPConfig.BASE_DN}"

        try:
            conn = ldap3.Connection(server, user=user_dn, password=password)
            if not conn.bind():
                return None

            conn.search(
                search_base=LDAPConfig.BASE_DN,
                search_filter=f"({LDAPConfig.USERNAME_ATTR}={username})",
                attributes=[LDAPConfig.FULL_NAME_ATTR, LDAPConfig.EMAIL_ATTR],
            )

            entry = conn.entries[0] if conn.entries else None
            full_name = (
                str(getattr(entry, LDAPConfig.FULL_NAME_ATTR, username))
                if entry
                else username
            )
            email = str(getattr(entry, LDAPConfig.EMAIL_ATTR, "")) if entry else ""

            conn.unbind()

            role_map_raw = self.db.get_setting("ldap_role_map", "{}")
            try:
                import json

                role_map = json.loads(role_map_raw)
            except (json.JSONDecodeError, TypeError):
                role_map = {}

            groups = self._get_user_groups(conn, username) if False else []
            role = "Inspector"
            for group_pattern, mapped_role in role_map.items():
                if group_pattern in str(groups):
                    role = mapped_role
                    break

            return {
                "username": username,
                "full_name": full_name,
                "email": email,
                "role": role,
                "auth_provider": "ldap",
            }

        except Exception:
            return None

    @staticmethod
    def _get_user_groups(conn, username: str) -> List[str]:
        try:
            conn.search(
                search_base=LDAPConfig.BASE_DN,
                search_filter=f"(&(objectClass=group)(member=*{username}*))",
                attributes=["cn"],
            )
            return [str(entry.cn) for entry in conn.entries]
        except Exception:
            return []

    def save_config(
        self, host: str, port: int, base_dn: str, tls: bool = False
    ) -> None:
        self.db.upsert_setting("ldap_host", host)
        self.db.upsert_setting("ldap_port", str(port))
        self.db.upsert_setting("ldap_base_dn", base_dn)
        self.db.upsert_setting("ldap_tls", "1" if tls else "0")
        self._load_config()
