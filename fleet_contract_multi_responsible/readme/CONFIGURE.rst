Go to **Fleet ‣ Configuration ‣ Settings**, section **Fleet Management**:

* **Contract expiry notice (days before)**: how many days before the
  expiration date of a running contract its responsibles are emailed.
  Between 1 and 60, 5 by default. 0 days (the expiration day itself) is
  always part of the window. Stored as the system parameter
  ``fleet_contract_multi_responsible.expiry_notice_days``.

This setting is independent from Fleet's own **End Date Contract Alert**,
just above it, which only drives the **Contract to Renew** activity.

The email is sent by the scheduled action **Fleet: send contract expiry
notice emails** (**Settings ‣ Technical ‣ Automation ‣ Scheduled
Actions**, developer mode). It is active by default and runs once a day
at 10:00 UTC (07:00 in Argentina); change its **Next Execution Date** to
run it at another time.

The email content can be adjusted in **Settings ‣ Technical ‣ Email ‣
Templates**, template **Fleet: contract expiry notice** (it is not
overwritten by module updates).

Make sure each company has an email address and, optionally, its own
logo (**Settings ‣ Companies**), and that every responsible has an email
address and the right language in their preferences.
