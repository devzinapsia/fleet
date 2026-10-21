{
    "name": "Responsables múltiples y aviso de vencimiento de contratos de flota",
    "version": "19.0.1.0.0",
    "summary": "Permite cargar responsables adicionales en los contratos de "
    "vehículos y les avisa por correo antes del vencimiento.",
    "author": "Zinapsia",
    "website": "https://www.zinapsia.com",
    "license": "AGPL-3",
    "category": "Human Resources/Fleet",
    "depends": ["fleet", "mail"],
    "data": [
        "data/ir_cron_data.xml",
        "data/mail_template_data.xml",
        "views/fleet_vehicle_log_contract_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
