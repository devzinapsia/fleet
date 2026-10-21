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
