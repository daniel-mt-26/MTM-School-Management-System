# MTM n8n communication setup

These workflow definitions are foundations for an n8n instance. They are not a
claim that WhatsApp is live. Configure the following only in n8n credential or
environment storage, never in this repository:

- `MTM_API_BASE_URL` (the HTTPS MTM API base URL)
- `MTM_N8N_INTEGRATION_SECRET` (the same server-to-server value configured on MTM)
- a WhatsApp Business Cloud credential, phone-number ID, and approved template mapping

The outbox workflow claims only messages already selected and populated by Django.
It must report the Meta provider message ID to MTM after a successful send and
report a safe, non-secret failure reason otherwise. Template keys are MTM keys,
not hardcoded Meta template names: `school_announcement`, `payment_receipt`,
`fee_reminder`, and `report_card_available` must be mapped in n8n configuration.

The delivery-status workflow receives a provider status after n8n verifies the
incoming webhook according to the Meta configuration, then posts only the
provider message ID, normalized status, and optional safe reason to MTM.

No workflow queries MTM finance tables, calculates balances, creates fees, or
chooses a tenant or recipient. The optional fee-reminder workflow calls the
school-admin-operated MTM endpoint only when an authenticated MTM-side process
has selected the target school; it is intentionally disabled by default because
automatic due-date scheduling needs an operational policy.
