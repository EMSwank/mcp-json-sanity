# JSON Sanity — Legal

**Last Updated:** April 24, 2026

This document contains the Terms of Service and Privacy Policy for JSON Sanity ("the Service"), an MCP (Model Context Protocol) server operated as a sole proprietorship ("we," "us," or "our"). By creating an account or invoking any tool provided by the Service, you ("you" or "Customer") agree to both documents below.

---

## Part 1 — Terms of Service

### 1. The Service

JSON Sanity is a cloud-based MCP server that provides JSON validation, repair, and sanitation tools intended for use by developers building with large language models (LLMs). The Service is accessed programmatically via the MCP protocol and is designed to be invoked by LLM agents and developer tooling.

### 2. Accounts and API Keys

To use the Service, you must register for an account. Upon registration, you will be issued one or more API keys. Each API key is identified internally by an `api_key_id`, which is linked to your Stripe Customer ID for billing purposes.

**Your API key is your responsibility.** Specifically:

- You are responsible for keeping your API key confidential. Do not commit it to public repositories, share it in client-side code, or otherwise expose it.
- All tool invocations made with your `api_key_id` are attributed to you, regardless of who actually initiated the call. You are liable for charges incurred under your key, including charges resulting from compromised or leaked credentials.
- If you believe your key has been compromised, you must rotate it immediately through your account dashboard. We are not responsible for usage charges incurred before you rotate a compromised key.
- Your `api_key_id` is bound to the Stripe Customer ID associated with your account. You may not transfer an API key to another party or another Stripe account without first rotating the key and updating billing information.

You must be at least 18 years old and legally capable of entering into a binding contract to use the Service.

### 3. Billing and Payment

The Service uses a **metered billing model**. You are charged based on the number of tool invocations made under your `api_key_id` during each billing period.

- **Payment processor.** All payments are handled exclusively through Stripe. We do not store or process your payment card information directly. Your use of Stripe is governed by Stripe's own terms, available at stripe.com.
- **Metering.** Tool invocations are counted on our servers at the time of request. A request counts toward your usage whether or not it returns a successful result, provided the request was authenticated and reached our metering layer. Invalid or unauthenticated requests are not metered.
- **Invoicing.** Charges accrue during each billing cycle and are charged to your payment method on file at the end of the cycle, or when usage thresholds are met, as configured on your plan.
- **Failed payments.** If a payment fails, we will attempt to retry the charge in accordance with Stripe's standard retry schedule. Continued non-payment may result in suspension or termination under Section 6.
- **Price changes.** We may adjust pricing with at least 30 days' notice. Continued use of the Service after a price change takes effect constitutes acceptance of the new pricing.

### 4. Acceptable Use

You agree not to:

- Use the Service to process content that is unlawful, infringing, or that you do not have the right to submit.
- Attempt to disrupt, degrade, or overwhelm the Service, including through intentional denial-of-service attacks, excessive concurrent requests designed to exhaust capacity, or automated probing for vulnerabilities.
- Reverse engineer, decompile, or attempt to extract the source code or internal logic of the Service.
- Resell the Service or wrap it as a competing product without a separate written agreement.
- Use the Service to process data you are not legally permitted to process, including certain categories of regulated data (e.g., PHI under HIPAA, cardholder data under PCI-DSS) unless you have confirmed in writing that the Service is appropriate for that use case.

### 5. Service Availability and Disclaimers

**The Service is provided "AS IS" and "AS AVAILABLE."** We make no warranties, express or implied, regarding the Service, including but not limited to:

- **Repair accuracy.** JSON Sanity operates on data that is often produced by LLMs, which are probabilistic systems. We do not guarantee that any repair, validation, or sanitation operation will produce a correct, complete, or semantically accurate result. You are responsible for validating the output of the Service before relying on it in production systems.
- **Uptime.** We do not guarantee any specific uptime or availability target unless explicitly stated in a separate written service level agreement. The Service may experience downtime for maintenance, upgrades, or reasons beyond our control.
- **Fitness for purpose.** We disclaim all implied warranties of merchantability, fitness for a particular purpose, and non-infringement to the fullest extent permitted by law.

### 6. Suspension and Termination

We reserve the right to suspend or terminate your access to the Service, in whole or in part, at our discretion, including in the following situations:

- **Non-payment.** If your payment method fails and the balance remains unpaid after reasonable retry attempts, we may suspend your `api_key_id` until payment is resolved.
- **Abuse.** If we detect behavior that constitutes abuse — including but not limited to intentional denial-of-service activity, attempts to bypass rate limits or billing, or violations of the Acceptable Use section — we may suspend or terminate your account immediately and without prior notice.
- **Legal requirement.** If we are required to do so by law or by a valid legal order.

You may terminate your account at any time by canceling through your account dashboard. Termination does not waive any outstanding balance owed for usage prior to termination.

### 7. Limitation of Liability

To the maximum extent permitted by law, our total liability to you for any claim arising out of or relating to the Service is limited to the greater of (a) the amount you paid us for the Service during the three (3) months preceding the event giving rise to the claim, or (b) one hundred US dollars ($100).

We are not liable for indirect, incidental, consequential, special, or punitive damages, including lost profits, lost data, or business interruption, even if we have been advised of the possibility of such damages.

Some jurisdictions do not allow the exclusion or limitation of certain damages, so some of the above may not apply to you.

### 8. Indemnification

You agree to indemnify and hold us harmless from any claims, damages, or expenses (including reasonable attorneys' fees) arising out of your use of the Service, your violation of these Terms, or your violation of any rights of a third party.

### 9. Changes to These Terms

We may update these Terms from time to time. When we do, we will update the "Last Updated" date at the top of this document and, for material changes, provide notice through the Service or via email. Continued use of the Service after changes take effect constitutes acceptance of the updated Terms.

### 10. Governing Law

These Terms are governed by the laws of the State of Colorado, USA, without regard to its conflict of laws principles. Any dispute arising under these Terms will be resolved in the state or federal courts located in Colorado.

### 11. Contact

Questions about these Terms can be directed to the contact address listed on our website.

---

## Part 2 — Privacy Policy

### 1. Scope

This Privacy Policy explains what information we collect when you use JSON Sanity, how we use it, and how long we keep it. It applies to all users of the Service.

### 2. What We Collect

**Account information.** When you register, we collect the information necessary to create and bill your account: email address, account identifier, and the Stripe Customer ID associated with your `api_key_id`. We do not store your payment card details — those are held by Stripe.

**Request metadata.** For each tool invocation, we log metadata in Supabase for billing, rate limiting, and audit purposes. This metadata includes:

- The `api_key_id` associated with the request
- The name of the tool invoked (e.g., `validate`, `repair`, `sanitize`)
- The size of the input payload (byte length)
- Timestamp of the request
- Response status (success, error, or rate-limited)

**What we do not log.** We do **not** persistently store the content of the JSON payloads you send to the Service. Payload content exists only in memory during the immediate processing window and is discarded once the response is returned. We do not retain copies of your input or output JSON in logs, databases, or backups.

### 3. How We Use This Information

We use the information we collect to:

- Authenticate requests and enforce rate limits
- Calculate and invoice metered usage
- Investigate abuse, fraud, and security incidents
- Communicate with you about your account (e.g., billing issues, service changes)

### 4. Model Training

**We do not train AI models on your data.** Payload content is processed transiently and is never used to train, fine-tune, or evaluate any machine learning model, whether ours or a third party's.

### 5. Sharing With Third Parties

We share information with a small number of service providers who are necessary to operate the Service:

- **Stripe** — payment processing. Stripe receives billing information and payment details.
- **Supabase** — database and logging infrastructure for request metadata and account records.
- **Cloud hosting provider** — the infrastructure on which the Service runs.

We do not sell your information to third parties and we do not share it for advertising purposes.

We may also disclose information if required by law, valid legal process, or to protect the rights, safety, or property of us or our users.

### 6. Data Retention

- **Request metadata** (the fields described in Section 2) is retained for up to 24 months for billing, audit, and dispute-resolution purposes, after which it is deleted or aggregated in a non-identifiable form.
- **Account records** are retained for as long as your account is active and for a reasonable period afterward to satisfy tax, accounting, and legal obligations.
- **Payload content** is not retained beyond the immediate processing window, as described above.

### 7. Security

We use industry-standard security practices to protect the information we collect, including encryption in transit, access controls, and logging of administrative access. No system is perfectly secure, however, and we cannot guarantee absolute security.

### 8. Your Rights

Depending on where you live, you may have rights to access, correct, delete, or export the personal information we hold about you. To exercise these rights, contact us through the address on our website. We will respond within the timeframe required by applicable law.

### 9. International Users

The Service is operated from the United States. If you access the Service from outside the US, you understand that your information will be transferred to, stored, and processed in the US.

### 10. Changes to This Policy

We may update this Privacy Policy from time to time. When we do, we will update the "Last Updated" date at the top of this document. For material changes, we will provide notice through the Service or via email.

### 11. Contact

Privacy-related questions can be directed to the contact address on our website.
