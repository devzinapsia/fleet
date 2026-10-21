===================================================================
Responsables múltiples y aviso de vencimiento de contratos de flota
===================================================================

Lets a vehicle contract (**Fleet ‣ Fleet ‣ Contracts**) have more than one
responsible, and emails every one of them before the contract expires.

* **Additional responsibles**: a new field on the contract, next to the
  existing **Responsible**, holding any number of active internal users.
  It does not replace or change **Responsible**. It is searchable from the
  contracts search bar and available as an optional (hidden by default)
  column in the contracts list.
* **Expiry notice email**: a daily scheduled action emails the
  **Responsible** and every **Additional responsible** (without
  duplicates) when a running contract is about to expire. Each recipient
  gets their own email, in their own language, greeting them by first
  name, with the contract details (vehicle and license plate, contract
  type, vendor, reference, expiration date, recurring cost and the full
  list of responsibles) and a **View contract** button.

**Table of contents**

.. contents::
   :local:

Notice rule
===========

A contract is notified when **all** of these conditions are met:

* it has an expiration date;
* its status is **Running** (``open``). New, expired and cancelled
  contracts are never notified;
* its expiration date is between today and *N* days from today, both
  included, *N* being the **Contract expiry notice (days before)** setting
  (5 by default). "Today" is computed in the timezone of the contract's
  company (its partner's timezone), falling back to UTC;
* that expiration date has not been notified yet.

Once sent, the contract's **Expiry notice sent on** date is set (shown
read-only on the form, below the responsibles) and the same expiration
date is never notified again. Changing the expiration date clears it
automatically, so an extended or corrected contract is notified again
when its new date enters the window. A renewal that creates a new
contract is notified on its own expiration date.

Recipients that are archived or have no email address are skipped (and
logged on the server). If no recipient is left, nothing is sent, the
contract is not marked, and a message is written to the server log; it
is retried on the next run, so adding a valid responsible in time is
enough.

Each contract is processed on its own: an error on one contract is
logged and does not prevent notifying the others.

After sending, an internal note on the contract's chatter lists who was
notified. It does not notify the followers. While the emails wait in the
outgoing queue they are also visible in the chatter; they are removed
automatically once sent.

Sender and company
==================

The email is sent from the email address of the contract's company,
shows that company's name and logo (the logo is omitted while the
company uses Odoo's default one), and the **View contract** button opens
the contract through ``/mail/view``, which also enables the contract's
company for users allowed on several companies. Contracts without a
company ("Visible to all") use the main company of the scheduled action.

Coexistence with Fleet's own alerts
===================================

Fleet already has its own, independent reminder, which this module does
not change:

* Fleet's daily scheduled action **Fleet: Generate contracts costs based
  on costs frequency** schedules a **Contract to Renew** activity for the
  main **Responsible** only, for running contracts expiring within the
  **End Date Contract Alert** delay (30 days by default, system parameter
  ``hr_fleet.delay_alert_contract``);
* the same action moves contracts to **Expired** the day after their
  expiration date, and between **New** and **Running** according to their
  start date.

This module never changes a contract's status, never creates activities,
and does not read Fleet's delay: both reminders run side by side, Fleet's
activity well in advance for the main responsible, and this module's
email close to the date for every responsible.

Configuration
=============

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

Usage
=====

#. Open a contract in **Fleet ‣ Fleet ‣ Contracts**.
#. Next to **Responsible**, add one or more users in **Additional
   responsibles**.
#. Every day the scheduled action emails all the responsibles of each
   running contract that expires within the configured number of days.

To find contracts by additional responsible, type a user's name in the
contracts search bar and pick **Search Additional responsibles**. To see
them in the list, enable the **Additional responsibles** optional column.

Testing it manually
-------------------

#. Set a running contract's expiration date within the window (e.g. 5
   days from today) and add a couple of additional responsibles with an
   email address.
#. Enable the developer mode and go to **Settings ‣ Technical ‣
   Automation ‣ Scheduled Actions**.
#. Open **Fleet: send contract expiry notice emails** and click **Run
   Manually**.
#. Check the generated emails in **Settings ‣ Technical ‣ Email ‣
   Emails** (one per recipient), and the internal note on the contract's
   chatter. The contract's **Expiry notice sent on** field is now set:
   running the action again sends nothing more for that expiration date.
#. To send it again, change the contract's expiration date (or clear the
   date and set it back), then run the action once more.

On a test database, make sure outgoing emails cannot reach real people
(e.g. no outgoing mail server, or a local fake SMTP server).

Bug Tracker
===========

Bugs are tracked on
`GitHub Issues <https://github.com/devzinapsia/fleet/issues>`_.
In case of trouble, please check there if your issue has already been
reported.

Credits
=======

Authors
-------

* Zinapsia

Maintainers
-----------

This module is maintained by Zinapsia.

This module is part of the
`fleet <https://github.com/devzinapsia/fleet>`_
project.
