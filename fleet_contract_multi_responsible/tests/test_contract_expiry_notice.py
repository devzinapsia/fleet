from datetime import date, timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import format_date

from odoo.addons.fleet_contract_multi_responsible.models.fleet_vehicle_log_contract import (
    EXPIRY_NOTICE_DAYS_PARAM,
)

MODEL_MODULE = "odoo.addons.fleet_contract_multi_responsible.models.fleet_vehicle_log_contract"
LOGGER = MODEL_MODULE
TODAY = date(2026, 3, 10)
# 12:00 UTC is 09:00 in Buenos Aires: same calendar day in both timezones.
NOW = "2026-03-10 12:00:00"
# 1x1 transparent PNG, so the company does not use Odoo's default logo.
PNG_1PX = (
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


@tagged("post_install", "-at_install")
class TestContractExpiryNotice(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("es_AR")
        cls.env["res.lang"]._activate_lang("en_US")
        cls.env["ir.module.module"]._load_module_terms(
            ["fleet", "fleet_contract_multi_responsible"], ["es_AR"], overwrite=True
        )
        # Distinct date formats, to check each email uses its recipient's one.
        cls.env["res.lang"]._lang_get("es_AR").date_format = "%d/%m/%Y"
        cls.env["res.lang"]._lang_get("en_US").date_format = "%m/%d/%Y"
        cls.env["ir.config_parameter"].sudo().set_param(EXPIRY_NOTICE_DAYS_PARAM, 5)
        cls.Contract = cls.env["fleet.vehicle.log.contract"]

        cls.company = cls.env.company
        cls.company.write({"email": "fleet@company-a.example.com"})
        cls.company.partner_id.tz = "America/Argentina/Buenos_Aires"

        brand = cls.env["fleet.vehicle.model.brand"].create({"name": "Toyota"})
        model = cls.env["fleet.vehicle.model"].create(
            {"name": "Hilux", "brand_id": brand.id}
        )
        cls.vehicle = cls.env["fleet.vehicle"].create(
            {"model_id": model.id, "license_plate": "AB123CD"}
        )
        cls.contract_type = cls.env["fleet.service.type"].create(
            {"name": "Seguro", "category": "contract"}
        )
        cls.vendor = cls.env["res.partner"].create({"name": "Seguros del Sur"})

        def user(login, name, lang, **kwargs):
            return new_test_user(
                cls.env,
                login=login,
                name=name,
                email=f"{login}@example.com",
                lang=lang,
                groups="base.group_user,fleet.fleet_group_user",
                **kwargs,
            )

        cls.user_main = user("fcmr_main", "Juan Pérez", "es_AR")
        cls.user_en = user("fcmr_en", "Mary Smith", "en_US")
        cls.user_es = user("fcmr_es", "Ana Gómez", "es_AR")
        cls.user_no_email = user("fcmr_no_email", "Pedro Sin Mail", "es_AR")
        cls.user_no_email.email = False
        cls.user_inactive = user("fcmr_inactive", "Laura Inactiva", "es_AR")
        cls.user_inactive.active = False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_contract(self, days=5, **vals):
        values = {
            "vehicle_id": self.vehicle.id,
            "cost_subtype_id": self.contract_type.id,
            "ins_ref": "POL-1",
            "start_date": TODAY - timedelta(days=300),
            "expiration_date": TODAY + timedelta(days=days)
            if days is not None
            else False,
            "state": "open",
            "user_id": self.user_main.id,
            "additional_responsible_ids": [Command.set(self.user_en.ids)],
            **vals,
        }
        with freeze_time(NOW):
            return self.Contract.create(values)

    def _run_cron(self, now=NOW):
        with freeze_time(now):
            self.Contract._cron_send_expiry_notices()

    def _mails(self, contract):
        return self.env["mail.mail"].search(
            [("model", "=", contract._name), ("res_id", "=", contract.id)],
            order="id",
        )

    def _logged_info(self, logger_mock):
        return "\n".join(call.args[0] % call.args[1:] for call in logger_mock.info.call_args_list)

    def _mail_for(self, contract, user):
        return self._mails(contract).filtered(
            lambda m: m.recipient_ids == user.partner_id
        )

    # ------------------------------------------------------------------
    # Field
    # ------------------------------------------------------------------

    def test_field_accepts_several_users_and_keeps_user_id(self):
        contract = self._create_contract(
            additional_responsible_ids=[Command.set((self.user_en | self.user_es).ids)]
        )
        self.assertEqual(contract.additional_responsible_ids, self.user_en | self.user_es)
        self.assertEqual(contract.user_id, self.user_main)
        contract.additional_responsible_ids = [Command.unlink(self.user_en.id)]
        self.assertEqual(contract.user_id, self.user_main)

    # ------------------------------------------------------------------
    # Recipients
    # ------------------------------------------------------------------

    def test_recipients_union_without_duplicates(self):
        contract = self._create_contract(
            additional_responsible_ids=[
                Command.set((self.user_main | self.user_en | self.user_es).ids)
            ]
        )
        recipients = contract._get_expiry_notice_recipients()
        self.assertEqual(recipients, self.user_main | self.user_en | self.user_es)
        self._run_cron()
        self.assertEqual(len(self._mails(contract)), 3)
        self.assertEqual(len(self._mail_for(contract, self.user_main)), 1)

    def test_recipients_skip_inactive_and_without_email(self):
        # The many2many drops archived users by itself; the main responsible
        # (many2one) can still point to one.
        contract = self._create_contract(
            user_id=self.user_inactive.id,
            additional_responsible_ids=[
                Command.set((self.user_en | self.user_no_email | self.user_inactive).ids)
            ],
        )
        self.assertNotIn(self.user_inactive, contract.additional_responsible_ids)
        with patch(f"{MODEL_MODULE}._logger") as logger_mock:
            recipients = contract._get_expiry_notice_recipients()
        self.assertEqual(recipients, self.user_en)
        output = self._logged_info(logger_mock)
        self.assertIn("fcmr_inactive", output)
        self.assertIn("inactive user", output)
        self.assertIn("fcmr_no_email", output)
        self.assertIn("user without email", output)

    def test_no_recipients_does_not_fail(self):
        contract = self._create_contract(
            user_id=self.user_inactive.id,
            additional_responsible_ids=[Command.set(self.user_no_email.ids)],
        )
        with patch(f"{MODEL_MODULE}._logger") as logger_mock:
            self._run_cron()
        self.assertFalse(self._mails(contract))
        self.assertFalse(contract.expiry_notice_sent_on)
        self.assertIn("no valid recipient", self._logged_info(logger_mock))

    # ------------------------------------------------------------------
    # Window and marker
    # ------------------------------------------------------------------

    def test_window(self):
        notified = {days: self._create_contract(days) for days in (5, 3, 1, 0)}
        not_notified = {
            "6 days": self._create_contract(6),
            "past date": self._create_contract(-1),
            "no date": self._create_contract(None),
            "closed": self._create_contract(2, state="closed"),
            "expired": self._create_contract(2, state="expired"),
        }
        self._run_cron()
        for days, contract in notified.items():
            self.assertEqual(len(self._mails(contract)), 2, f"{days} days left")
            self.assertEqual(contract.expiry_notice_sent_on, TODAY)
        for label, contract in not_notified.items():
            self.assertFalse(self._mails(contract), label)
            self.assertFalse(contract.expiry_notice_sent_on, label)

    def test_contract_loaded_late_is_notified_on_next_run(self):
        contract = self._create_contract(2)
        self.assertFalse(self._mails(contract))
        self._run_cron()
        self.assertEqual(len(self._mails(contract)), 2)

    def test_no_double_notice_and_reset_on_new_date(self):
        contract = self._create_contract(5)
        self._run_cron()
        self._run_cron()
        self._run_cron("2026-03-11 12:00:00")
        self.assertEqual(len(self._mails(contract)), 2)

        # Writing the same date keeps the marker.
        with freeze_time(NOW):
            contract.expiration_date = TODAY + timedelta(days=5)
        self.assertEqual(contract.expiry_notice_sent_on, TODAY)

        # A corrected date resets it and notifies again.
        with freeze_time(NOW):
            contract.expiration_date = TODAY + timedelta(days=4)
        self.assertFalse(contract.expiry_notice_sent_on)
        self._run_cron()
        self.assertEqual(len(self._mails(contract)), 4)
        self.assertEqual(contract.expiry_notice_sent_on, TODAY)

    def test_parameter_changes_window(self):
        contract = self._create_contract(8)
        self._run_cron()
        self.assertFalse(self._mails(contract))
        self.env["ir.config_parameter"].sudo().set_param(EXPIRY_NOTICE_DAYS_PARAM, 10)
        self._run_cron()
        self.assertEqual(len(self._mails(contract)), 2)

    def test_parameter_validation(self):
        Settings = self.env["res.config.settings"]
        for days in (0, 61, -3):
            with self.assertRaises(ValidationError, msg=days):
                Settings.create({"fleet_contract_expiry_notice_days": days})
        for days in (1, 60):
            Settings.create({"fleet_contract_expiry_notice_days": days}).execute()
            self.assertEqual(self.Contract._get_expiry_notice_days(), days)

    # ------------------------------------------------------------------
    # Email content
    # ------------------------------------------------------------------

    def test_one_mail_per_recipient_in_its_language(self):
        contract = self._create_contract(5)
        self._run_cron()
        mail_es = self._mail_for(contract, self.user_main)
        mail_en = self._mail_for(contract, self.user_en)
        self.assertEqual(len(mail_es), 1)
        self.assertEqual(len(mail_en), 1)
        self.assertEqual(
            mail_es.subject,
            "[Flota] El contrato Seguro (POL-1) de Toyota Hilux vence en 5 días",
        )
        self.assertEqual(
            mail_en.subject,
            "[Fleet] Contract Seguro (POL-1) for Toyota Hilux expires in 5 days",
        )
        self.assertIn("Hola Juan,", mail_es.body_html)
        self.assertIn("Ver contrato", mail_es.body_html)
        self.assertIn("Hello Mary,", mail_en.body_html)
        self.assertIn("View contract", mail_en.body_html)

    def test_subject_variants(self):
        tomorrow = self._create_contract(1)
        today = self._create_contract(0)
        self._run_cron()
        self.assertEqual(
            self._mail_for(tomorrow, self.user_main).subject,
            "[Flota] El contrato Seguro (POL-1) de Toyota Hilux vence mañana",
        )
        self.assertEqual(
            self._mail_for(today, self.user_main).subject,
            "[Flota] El contrato Seguro (POL-1) de Toyota Hilux vence hoy",
        )
        self.assertEqual(
            self._mail_for(today, self.user_en).subject,
            "[Fleet] Contract Seguro (POL-1) for Toyota Hilux expires today",
        )

    def test_body_content_and_link(self):
        contract = self._create_contract(
            5,
            insurer_id=self.vendor.id,
            cost_generated=1500.0,
            cost_frequency="monthly",
        )
        self._run_cron()
        body_es = self._mail_for(contract, self.user_main).body_html
        body_en = self._mail_for(contract, self.user_en).body_html
        expiration = TODAY + timedelta(days=5)
        for body, lang in ((body_es, "es_AR"), (body_en, "en_US")):
            self.assertIn("Toyota Hilux", body)
            self.assertIn("AB123CD", body)
            self.assertIn(format_date(self.env, expiration, lang_code=lang), body)
            self.assertIn("Seguros del Sur", body)
            self.assertIn("POL-1", body)
            self.assertIn("Juan Pérez", body)
            self.assertIn("Mary Smith", body)
            self.assertIn(
                f"{contract.get_base_url()}/mail/view?model=fleet.vehicle.log.contract"
                f"&amp;res_id={contract.id}",
                body,
            )
        self.assertIn("15/03/2026", body_es)
        self.assertIn("03/15/2026", body_en)
        self.assertIn(">Proveedor<", body_es)
        self.assertIn(">Costo<", body_es)
        self.assertIn("(mensual)", body_es)
        self.assertIn(">Vendor<", body_en)
        self.assertIn("(monthly)", body_en)

    def test_body_omits_rows_without_data(self):
        contract = self._create_contract(
            5, cost_subtype_id=False, ins_ref=False, cost_frequency="no"
        )
        self._run_cron()
        body = self._mail_for(contract, self.user_main).body_html
        self.assertIn(">Vehículo<", body)
        self.assertIn(">Vencimiento<", body)
        self.assertIn(">Responsables<", body)
        for label in (">Tipo de contrato<", ">Proveedor<", ">Referencia<", ">Costo<"):
            self.assertNotIn(label, body)

    # ------------------------------------------------------------------
    # Robustness, multi-company and side effects
    # ------------------------------------------------------------------

    def test_error_on_one_contract_does_not_block_others(self):
        broken = self._create_contract(5)
        healthy = self._create_contract(4)
        original = type(self.Contract)._send_expiry_notice

        def send(contract):
            if contract == broken:
                raise ValueError("Simulated failure")
            return original(contract)

        with (
            patch.object(
                type(self.Contract), "_send_expiry_notice", autospec=True, side_effect=send
            ),
            self.assertLogs(LOGGER, level="ERROR") as logs,
        ):
            self._run_cron()
        self.assertIn(f"id {broken.id}", "\n".join(logs.output))
        self.assertFalse(self._mails(broken))
        self.assertFalse(broken.expiry_notice_sent_on)
        self.assertEqual(len(self._mails(healthy)), 2)

    def test_multi_company_sender_and_logo(self):
        company_b = self.env["res.company"].create(
            {
                "name": "Company B",
                "email": "fleet@company-b.example.com",
                "logo": PNG_1PX,
            }
        )
        company_b.partner_id.tz = "America/Argentina/Buenos_Aires"
        self.assertFalse(company_b.uses_default_logo)
        vehicle_b = self.vehicle.copy({"company_id": company_b.id})
        contract_a = self._create_contract(5)
        contract_b = self._create_contract(
            5, vehicle_id=vehicle_b.id, company_id=company_b.id
        )
        self._run_cron()
        mail_a = self._mail_for(contract_a, self.user_main)
        mail_b = self._mail_for(contract_b, self.user_main)
        self.assertIn("fleet@company-a.example.com", mail_a.email_from)
        self.assertIn("fleet@company-b.example.com", mail_b.email_from)
        self.assertIn(f"/logo.png?company={company_b.id}", mail_b.body_html)
        self.assertIn("Company B", mail_b.body_html)
        self.assertNotIn(f"/logo.png?company={company_b.id}", mail_a.body_html)

    def test_cron_does_not_change_state_nor_create_activities(self):
        contract = self._create_contract(0)
        activities_before = contract.activity_ids
        self._run_cron()
        self.assertEqual(len(self._mails(contract)), 2)
        self.assertEqual(contract.state, "open")
        self.assertEqual(contract.activity_ids, activities_before)

    def test_chatter_note_without_notifying_followers(self):
        contract = self._create_contract(5)
        contract.message_subscribe(partner_ids=self.user_es.partner_id.ids)
        self._run_cron()
        note = contract.message_ids.filtered(
            lambda m: m.message_type == "notification"
            and "Juan Pérez" in (m.body or "")
            and "Mary Smith" in (m.body or "")
        )
        self.assertEqual(len(note), 1)
        self.assertEqual(note.subtype_id, self.env.ref("mail.mt_note"))
        self.assertFalse(note.notification_ids)
        self.assertFalse(note.partner_ids)
        # Only the two responsibles get an email, not the follower.
        self.assertFalse(self._mail_for(contract, self.user_es))
