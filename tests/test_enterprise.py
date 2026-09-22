"""Tests for new Enterprise modules: permissions, audit, predictive, glass widgets."""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch


class TestPermissions(unittest.TestCase):
    def setUp(self) -> None:
        from services.permissions import UserPermissions

        self.Perms = UserPermissions

    def test_admin_full_access(self) -> None:
        p = self.Perms("Administrator")
        for mod in ["employees", "violations", "settings", "users", "audit"]:
            for act in ["view", "create", "edit", "delete", "export"]:
                self.assertTrue(
                    p.can(mod, act), f"{mod}.{act} should be True for Admin"
                )

    def test_inspector_limited(self) -> None:
        p = self.Perms("Inspector")
        self.assertTrue(p.can_view("employees"))
        self.assertFalse(p.can_delete("employees"))
        self.assertTrue(p.can_create("incidents"))  # override
        self.assertTrue(p.can_edit("incidents"))  # override

    def test_viewer_readonly(self) -> None:
        p = self.Perms("Viewer")
        self.assertTrue(p.can_view("employees"))
        self.assertFalse(p.can_create("employees"))
        self.assertFalse(p.can_create("incidents"))

    def test_unknown_role_falls_back(self) -> None:
        p = self.Perms("NonExistent")
        self.assertTrue(p.can_view("employees"))
        self.assertFalse(p.can_delete("employees"))

    def test_roles_list(self) -> None:
        roles = self.Perms.roles()
        self.assertIn("Administrator", roles)
        self.assertIn("Inspector", roles)
        self.assertIn("Viewer", roles)

    def test_modules_list(self) -> None:
        mods = self.Perms.modules()
        self.assertIn("employees", mods)
        self.assertIn("settings", mods)
        self.assertIn("ai", mods)


class TestAuditService(unittest.TestCase):
    def setUp(self) -> None:
        from services.audit_service import AuditService

        self.db = MagicMock()
        self.audit = AuditService(user={"username": "tester", "role": "Admin"})
        self.audit.db = self.db

    def test_log_login_success(self) -> None:
        self.audit.log_login("user1", True)
        self.db.log_event.assert_called_once()
        args = self.db.log_event.call_args[0]
        self.assertIn("Успешный", args[0])
        self.assertEqual(args[1], "INFO")

    def test_log_login_failure(self) -> None:
        self.audit.log_login("user1", False, "bad password")
        args = self.db.log_event.call_args[0]
        self.assertIn("Неудачный", args[0])
        self.assertEqual(args[1], "WARNING")

    def test_log_permission_denied(self) -> None:
        self.audit.log_permission_denied("employees", "delete")
        args = self.db.log_event.call_args[0]
        self.assertIn("Отказ в доступе", args[0])
        self.assertEqual(args[1], "WARNING")

    def test_log_create(self) -> None:
        self.audit.log_create("employees", 42, "Ivanov")
        args = self.db.log_event.call_args[0]
        self.assertIn("Создание", args[0])

    def test_log_export(self) -> None:
        self.audit.log_export("violations", 100)
        args = self.db.log_event.call_args[0]
        self.assertIn("Экспорт", args[0])


class TestPredictiveModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.db_path = tempfile.mktemp(suffix=".db")
        from services.database import DatabaseManager

        cls.db = DatabaseManager(database_path=cls.db_path)
        cls._seed_data_cls(cls.db)

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.db.close()
        except Exception:
            pass
        if os.path.exists(cls.db_path):
            try:
                os.unlink(cls.db_path)
            except Exception:
                pass

    @classmethod
    def _seed_data_cls(cls, db) -> None:
        tables = ["violations", "incidents", "training", "ppe"]
        for t in tables:
            db.execute(f"""CREATE TABLE IF NOT EXISTS {t} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_json TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                user_id INTEGER DEFAULT 0
            )""")
        for month in range(1, 7):
            m = f"2026-{month:02d}"
            for _ in range(month * 2):
                db.save_json_record(
                    "violations",
                    0,
                    {
                        "date": f"{m}-15",
                        "fine": "500",
                        "status": "Открыто",
                    },
                )
            for _ in range(month):
                db.save_json_record(
                    "incidents",
                    0,
                    {
                        "date": f"{m}-10",
                        "severity": "3",
                        "status": "Активно",
                    },
                )

    def test_forecast_returns_data(self) -> None:
        from services.predictive import PredictiveModel

        pm = PredictiveModel()
        pm.db = self.__class__.db
        result = pm.forecast("violations")
        self.assertNotIn("error", result)
        self.assertIn("current_month_count", result)
        self.assertIn("forecast", result)
        self.assertGreater(result["total_records"], 0)

    def test_forecast_insufficient_data(self) -> None:
        from services.predictive import PredictiveModel

        pm = PredictiveModel()
        pm.db = self.__class__.db
        result = pm.forecast("training")
        self.assertIn("error", result)

    def test_risk_score_returns_breakdown(self) -> None:
        from services.predictive import PredictiveModel

        pm = PredictiveModel()
        pm.db = self.__class__.db
        risk = pm.risk_score()
        self.assertIn("total_risk", risk)
        self.assertIn("level", risk)
        self.assertIn("breakdown", risk)

    def test_linear_trend(self) -> None:
        from services.predictive import PredictiveModel

        trend = PredictiveModel._linear_trend([1.0, 2.0, 3.0, 4.0, 5.0])
        self.assertAlmostEqual(trend, 1.0, places=1)
        trend = PredictiveModel._linear_trend([5.0, 4.0, 3.0, 2.0, 1.0])
        self.assertAlmostEqual(trend, -1.0, places=1)


class TestGlassWidgets(unittest.TestCase):
    """Verify glass widget modules can be imported without Qt app."""

    def test_glass_button_import(self) -> None:
        from widgets.glass_button import GlassButton

        self.assertTrue(
            hasattr(GlassButton, "VARIANTS")
            or callable(getattr(GlassButton, "__init__", None))
        )

    def test_glass_checkbox_import(self) -> None:
        from widgets.glass_checkbox import GlassCheckBox

    def test_glass_tooltip_import(self) -> None:
        from widgets.glass_tooltip import GlassTooltip

    def test_glass_slider_import(self) -> None:
        from widgets.glass_slider import GlassSlider

    def test_glass_table_import(self) -> None:
        from widgets.glass_table import apply_glass_table

    def test_glass_scrollbar_import(self) -> None:
        from widgets.glass_scrollbar import apply_glass_scrollbars

    def test_ribbon_import(self) -> None:
        from widgets.ribbon import RibbonWidget

    def test_icon_manager_import(self) -> None:
        from widgets.icon_manager import IconManager

        names = IconManager.names()
        self.assertGreater(len(names), 10)
        self.assertIn("search", names)

    def test_onboarding_import(self) -> None:
        from widgets.onboarding import OnboardingDialog


class TestLDAPAuth(unittest.TestCase):
    def setUp(self) -> None:
        from services.ldap_auth import LDAPAuthProvider, LDAPConfig

        LDAPConfig.HOST = ""
        LDAPConfig.BASE_DN = ""
        patcher = patch("services.ldap_auth.DatabaseManager")
        mock_db_class = patcher.start()
        mock_db = MagicMock()
        mock_db.get_setting.return_value = ""
        mock_db_class.return_value = mock_db
        self.addCleanup(patcher.stop)
        self.provider = LDAPAuthProvider()
        self.provider.db = mock_db

    def tearDown(self) -> None:
        from services.ldap_auth import LDAPConfig

        LDAPConfig.HOST = ""
        LDAPConfig.BASE_DN = ""

    def test_not_configured(self) -> None:
        result = self.provider.authenticate("user", "pass")
        self.assertIsNone(result)

    def test_is_configured(self) -> None:
        from services.ldap_auth import LDAPConfig

        LDAPConfig.HOST = "ldap.example.com"
        LDAPConfig.BASE_DN = "dc=example,dc=com"
        self.assertTrue(self.provider.is_configured())
        LDAPConfig.HOST = ""
        self.assertFalse(self.provider.is_configured())

    def test_save_config(self) -> None:
        self.provider.save_config("ldap.test.com", 636, "dc=test,dc=com", True)
        self.provider.db.upsert_setting.assert_called()


if __name__ == "__main__":
    unittest.main()
