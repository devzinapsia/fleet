from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .fleet_vehicle_log_contract import (
    DEFAULT_EXPIRY_NOTICE_DAYS,
    EXPIRY_NOTICE_DAYS_PARAM,
    MAX_EXPIRY_NOTICE_DAYS,
    MIN_EXPIRY_NOTICE_DAYS,
)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    fleet_contract_expiry_notice_days = fields.Integer(
        string="Contract expiry notice (days before)",
        default=DEFAULT_EXPIRY_NOTICE_DAYS,
        config_parameter=EXPIRY_NOTICE_DAYS_PARAM,
        help="Number of days before the expiration date of a running contract "
        "from which its responsibles receive the expiry notice email.",
    )

    @api.constrains("fleet_contract_expiry_notice_days")
    def _check_fleet_contract_expiry_notice_days(self):
        for settings in self:
            days = settings.fleet_contract_expiry_notice_days
            if not MIN_EXPIRY_NOTICE_DAYS <= days <= MAX_EXPIRY_NOTICE_DAYS:
                raise ValidationError(
                    _(
                        "The contract expiry notice must be between %(min)s and "
                        "%(max)s days before the expiration date.",
                        min=MIN_EXPIRY_NOTICE_DAYS,
                        max=MAX_EXPIRY_NOTICE_DAYS,
                    )
                )
