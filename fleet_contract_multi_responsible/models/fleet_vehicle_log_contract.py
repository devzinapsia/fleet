import logging
from datetime import timedelta

from markupsafe import Markup

from odoo import Command, _, api, fields, models
from odoo.tools import format_amount, format_list

_logger = logging.getLogger(__name__)

EXPIRY_NOTICE_DAYS_PARAM = "fleet_contract_multi_responsible.expiry_notice_days"
DEFAULT_EXPIRY_NOTICE_DAYS = 5
MIN_EXPIRY_NOTICE_DAYS = 1
MAX_EXPIRY_NOTICE_DAYS = 60
# Only running contracts are notified, like Fleet's own renewal activity.
EXPIRY_NOTICE_STATES = ("open",)


class FleetVehicleLogContract(models.Model):
    _inherit = "fleet.vehicle.log.contract"

    additional_responsible_ids = fields.Many2many(
        comodel_name="res.users",
        relation="fleet_contract_additional_responsible_rel",
        column1="contract_id",
        column2="user_id",
        string="Additional responsibles",
        domain=[("share", "=", False)],
        help="Internal users who share responsibility for this contract with "
        "the main responsible. All of them receive the expiry notice email.",
    )
    expiry_notice_sent_on = fields.Date(
        string="Expiry notice sent on",
        readonly=True,
        copy=False,
        help="Date the expiry notice email was sent for the current expiration "
        "date. It is cleared automatically when the expiration date changes.",
    )
    # Helpers for the expiry notice email, rendered in the recipient's language.
    expiry_notice_when = fields.Char(
        string="Expiry notice: when", compute="_compute_expiry_notice_labels"
    )
    expiry_notice_contract_label = fields.Char(
        string="Expiry notice: contract", compute="_compute_expiry_notice_labels"
    )
    expiry_notice_vehicle_label = fields.Char(
        string="Expiry notice: vehicle", compute="_compute_expiry_notice_labels"
    )
    expiry_notice_cost_label = fields.Char(
        string="Expiry notice: cost", compute="_compute_expiry_notice_labels"
    )
    expiry_notice_responsible_names = fields.Char(
        string="Expiry notice: responsibles",
        compute="_compute_expiry_notice_labels",
    )

    @api.depends(
        "expiration_date",
        "company_id",
        "cost_subtype_id",
        "ins_ref",
        "name",
        "vehicle_id.model_id",
        "vehicle_id.name",
        "cost_generated",
        "cost_frequency",
        "currency_id",
        "user_id",
        "additional_responsible_ids",
    )
    @api.depends_context("lang")
    def _compute_expiry_notice_labels(self):
        frequencies = dict(
            self._fields["cost_frequency"]._description_selection(self.env)
        )
        for contract in self:
            days_left = contract._get_expiry_notice_days_left()
            if days_left is None or days_left < 0:
                when = False
            elif days_left == 0:
                when = _("today")
            elif days_left == 1:
                when = _("tomorrow")
            else:
                when = _("in %(days)s days", days=days_left)
            contract.expiry_notice_when = when

            contract_type = contract.cost_subtype_id.name
            if contract_type and contract.ins_ref:
                contract_label = f"{contract_type} ({contract.ins_ref})"
            else:
                contract_label = contract_type or contract.name
            contract.expiry_notice_contract_label = contract_label

            vehicle_model = contract.vehicle_id.model_id
            contract.expiry_notice_vehicle_label = (
                " ".join(filter(None, [vehicle_model.brand_id.name, vehicle_model.name]))
                or contract.vehicle_id.name
            )

            if contract.cost_frequency != "no" and contract.cost_generated:
                contract.expiry_notice_cost_label = _(
                    "%(amount)s (%(frequency)s)",
                    amount=format_amount(
                        contract.env, contract.cost_generated, contract.currency_id
                    ),
                    frequency=frequencies[contract.cost_frequency].lower(),
                )
            else:
                contract.expiry_notice_cost_label = False

            contract.expiry_notice_responsible_names = format_list(
                contract.env, contract._get_expiry_notice_responsibles().mapped("name")
            )

    def write(self, vals):
        rescheduled = self.env[self._name]
        if "expiration_date" in vals and "expiry_notice_sent_on" not in vals:
            new_date = fields.Date.to_date(vals["expiration_date"])
            rescheduled = self.filtered(
                lambda c: c.expiry_notice_sent_on and c.expiration_date != new_date
            )
        res = super().write(vals)
        if rescheduled:
            # A new expiration date has not been notified yet.
            rescheduled.write({"expiry_notice_sent_on": False})
        return res

    # ------------------------------------------------------------------
    # Expiry notice: rule
    # ------------------------------------------------------------------

    @api.model
    def _get_expiry_notice_days(self):
        value = (
            self.env["ir.config_parameter"].sudo().get_param(EXPIRY_NOTICE_DAYS_PARAM)
        )
        if not value:
            # Never saved from the settings yet.
            return DEFAULT_EXPIRY_NOTICE_DAYS
        try:
            days = int(value)
        except (TypeError, ValueError):
            days = DEFAULT_EXPIRY_NOTICE_DAYS
        if not MIN_EXPIRY_NOTICE_DAYS <= days <= MAX_EXPIRY_NOTICE_DAYS:
            _logger.warning(
                "Invalid %s value %r, using %s instead.",
                EXPIRY_NOTICE_DAYS_PARAM,
                value,
                DEFAULT_EXPIRY_NOTICE_DAYS,
            )
            days = DEFAULT_EXPIRY_NOTICE_DAYS
        return days

    def _get_expiry_notice_company(self):
        self.ensure_one()
        return self.company_id or self.env.company

    def _get_expiry_notice_today(self):
        """Today in the timezone of the contract's company (falling back to
        the current user's timezone, then UTC), so the window does not shift
        depending on the server time the cron runs at.
        """
        self.ensure_one()
        company = self._get_expiry_notice_company()
        tz = company.partner_id.tz or self.env.user.tz or "UTC"
        return fields.Date.context_today(self.with_context(tz=tz))

    def _get_expiry_notice_days_left(self):
        self.ensure_one()
        if not self.expiration_date:
            return None
        return (self.expiration_date - self._get_expiry_notice_today()).days

    def _is_expiry_notice_due(self, notice_days):
        self.ensure_one()
        if (
            self.state not in EXPIRY_NOTICE_STATES
            or self.expiry_notice_sent_on
            or not self.expiration_date
        ):
            return False
        return 0 <= self._get_expiry_notice_days_left() <= notice_days

    def _get_expiry_notice_responsibles(self):
        """Every responsible of the contract, main one first, without duplicates."""
        self.ensure_one()
        return self.user_id | self.additional_responsible_ids

    def _get_expiry_notice_recipients(self):
        self.ensure_one()
        recipients = self.env["res.users"]
        for user in self._get_expiry_notice_responsibles():
            if not user.active:
                reason = "inactive user"
            elif not user.email:
                reason = "user without email"
            else:
                recipients |= user
                continue
            _logger.info(
                "Contract expiry notice: skipping %s (id %s) on contract %s (id %s): %s.",
                user.login,
                user.id,
                self.display_name,
                self.id,
                reason,
            )
        return recipients

    # ------------------------------------------------------------------
    # Expiry notice: cron and sending
    # ------------------------------------------------------------------

    @api.model
    def _cron_send_expiry_notices(self):
        notice_days = self._get_expiry_notice_days()
        # Coarse prefilter in UTC with one day of margin on each side; the exact
        # window is checked per contract in its company's timezone.
        today = fields.Date.today()
        contracts = self.search(
            [
                ("state", "in", EXPIRY_NOTICE_STATES),
                ("expiry_notice_sent_on", "=", False),
                ("expiration_date", ">=", today - timedelta(days=1)),
                ("expiration_date", "<=", today + timedelta(days=notice_days + 1)),
            ]
        )
        for contract in contracts:
            try:
                with self.env.cr.savepoint():
                    if contract._is_expiry_notice_due(notice_days):
                        contract._send_expiry_notice()
            except Exception:
                _logger.exception(
                    "Contract expiry notice: failed for contract %s (id %s).",
                    contract.display_name,
                    contract.id,
                )

    def _send_expiry_notice(self):
        """Send one email per recipient, rendered in the recipient's language,
        and mark the current expiration date as notified.

        :return: the recipients notified (empty if there was nobody to notify)
        """
        self.ensure_one()
        recipients = self._get_expiry_notice_recipients()
        if not recipients:
            _logger.info(
                "Contract expiry notice: no valid recipient for contract %s (id %s), "
                "nothing sent.",
                self.display_name,
                self.id,
            )
            return recipients
        # The labels depend on "today", which is not a field dependency.
        self.invalidate_recordset(["expiry_notice_when"])
        company = self._get_expiry_notice_company()
        template = self.env.ref(
            "fleet_contract_multi_responsible.mail_template_contract_expiry_notice"
        ).with_company(company)
        for user in recipients:
            template.with_context(
                expiry_notice_lang=user.lang,
                expiry_notice_first_name=user.name.split()[0],
            ).send_mail(
                self.id,
                email_values={
                    "email_to": False,
                    "recipient_ids": [Command.link(user.partner_id.id)],
                },
            )
        self.expiry_notice_sent_on = self._get_expiry_notice_today()
        self._log_expiry_notice(recipients)
        _logger.info(
            "Contract expiry notice: sent for contract %s (id %s) to %s.",
            self.display_name,
            self.id,
            ", ".join(recipients.mapped("login")),
        )
        return recipients

    def _log_expiry_notice(self, recipients):
        """Leave an internal note on the contract listing who was notified,
        without notifying the followers.
        """
        self.ensure_one()
        lang = self._get_expiry_notice_company().partner_id.lang or self.env.lang
        contract = self.with_context(lang=lang)
        body = Markup("%s<br/>%s") % (
            contract.env._("Contract expiry notice email sent to:"),
            format_list(contract.env, recipients.mapped("name")),
        )
        contract._message_log(body=body)
