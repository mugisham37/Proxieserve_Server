# ProxiServe — Backend Closeout Build Prompt

This document is the final, comprehensive instruction set for completing the ProxiServe FastAPI backend. Everything that was foundational — authentication, service templates, application submission, document upload, messaging, agent case management, and basic assignments — has already been built. What remains is the layer that makes the platform fully operational at production quality: payment processing, intelligent agent assignment, real-time analytics, platform governance, compliance tooling, and the data connections that tie every module together into a coherent end-to-end experience.

You are being given this prompt because you are a capable AI coding assistant and this is a senior-engineer-level task. Read every instruction completely before writing a single line. Build in the exact order given. Verify each phase before advancing. Deploy focused sub-tasks for each module and complete them fully before moving on. There is no room for stubs, placeholders, or TODO comments in the final output.

The frontend is fully designed and waiting. The TypeScript types, page components, API endpoint expectations, and data shapes have already been locked in by the design. Your backend must produce responses that exactly match what the frontend expects to receive — not approximately, not structurally similar, but exactly. Where this document describes a response field, that field must exist with that name, that type, and that value range.


## Section One: Mandatory Analysis — Read Everything Before Writing Anything

Before writing any code, you must read the following files completely and understand them deeply. This is not optional. The codebase has established patterns that you must follow identically.

Read the file CURSOR_BUILD_PROMPT.md in this same directory. It describes the architecture, the five-layer module pattern, the ApiResponse envelope, the AppError exception hierarchy, how dependencies are composed, how ARQ jobs work, how async SQLAlchemy sessions must be used, and the non-negotiable rules. All of those rules apply here as well.

Read APPLICATION_MODULE_SPEC.md in this same directory. It describes every module already built, all existing database tables, and all existing API endpoints. You must not duplicate anything that already exists.

Read every file in app/modules/ including all five files in auth, services, applications, documents, messages, and assignments. Understand what each one does and how it connects to the others.

Read app/core/exceptions.py to understand all existing exception types. Read app/core/config.py for all existing settings. Read app/main.py to understand how all routers are currently wired. Read app/worker.py to understand the ARQ job registration pattern. Read migrations/versions/ to understand what tables currently exist.

Read app/modules/applications/schemas.py carefully. Find the AnalyticsResponse class — it currently returns by_status, by_service, total_applications, sla_compliance_rate, and payment_pending_count. This shape is wrong for the frontend. You will rebuild it completely. Read app/modules/assignments/models.py — the AgentSettings model has no expertise or skill fields. You will add a new agent_service_skills table to fix this.

After completing this analysis, you should be able to answer: What is the current sla_state calculation and why is it wrong? What columns are missing from the Application model for proper SLA tracking? What does the frontend AdminMetric type look like and does the current analytics endpoint return anything close to it? What payment tables exist right now? If you cannot answer these confidently, re-read the relevant files.


## Section Two: The Complete Picture — What Is Built and What Must Be Added

The system connects five types of actors through a single application process. A client submits an application for a service. The system assigns it to an agent using an intelligent scoring algorithm. The agent processes the case, communicates with the client, and updates its status through a defined state machine. Payment is collected from the client either before or during processing. The admin oversees everything — creating services, monitoring performance, managing agents, reviewing audit trails, and broadcasting communications.

```
CLIENT
  │ submits application via 5-step wizard
  │ uploads documents
  │ pays via card or mobile money
  │ receives status updates
  ▼
APPLICATION (database record with PRX code)
  │ auto-assignment algorithm selects agent
  │ OR admin manually assigns
  │ SLA deadline computed from tier at submission
  ▼
AGENT
  │ receives assigned case notification
  │ processes case through status machine
  │ communicates with client
  │ marks QC on documents
  │ completes or rejects application
  ▼
PAYMENT
  │ initiated by client after submission
  │ processed via gateway (MoMo push or card 3DS)
  │ status synced back to application record
  │ receipt generated on confirmation
  ▼
ADMIN
  │ creates and configures service templates
  │ manages agents and their skill profiles
  │ monitors real-time analytics dashboard
  │ reviews audit log of all actions
  │ oversees SLA compliance and escalations
  │ sends broadcasts to user segments
  │ controls global platform settings
```

What currently exists fully: auth, services, applications (submit/track/manage), documents, messages, agent assignment (basic manual only), agent settings (basic).

What must be built in this session:
- Payment module with gateway abstraction, fee calculation, status polling, and receipt generation
- SLA deadline infrastructure across the application and analytics layers
- Agent expertise skill profiles and intelligent auto-assignment scoring algorithm
- Admin analytics with the exact shape the frontend renders
- Admin oversight board with escalation tracking
- Admin audit log with tamper-evident append-only entries
- Admin broadcasts with audience targeting and delivery tracking
- Admin platform settings as a singleton configuration record
- Agent performance metrics and cross-agent leaderboard
- Client dashboard summary aggregate endpoint
- Status display mapping layer for frontend compatibility
- Payment status synchronization between the payments module and the application record


## Section Three: The Smart Assignment Algorithm — Design Before You Build

The assignment algorithm is the most architecturally important new piece. Before building it, you must understand exactly how it works and make deliberate design decisions based on that understanding.

When a new application is submitted, the system should attempt to automatically assign it to the best available agent. This is done through a scoring function that evaluates every eligible agent and selects the highest-scoring one. An eligible agent is any agent whose is_active flag is true, whose accepting_cases setting is true, whose daily_case_cap (if set) has not been reached today, and who has at least one active session in the last seven days (to avoid assigning to an agent who has effectively gone offline).

The scoring function gives each eligible agent a score from zero to one hundred. The score is composed of four weighted components.

The first component is service category expertise and it carries forty percent of the total weight. Look up the application's service category from the services table. Then look up the agent's skill profile from the agent_service_skills table. If the agent has a skill record for this exact service category, their expertise score is their proficiency_level divided by five (the maximum), multiplied by one hundred. If the agent has no skill record for this category, their expertise score is twenty-five (they can attempt the work but are not specialized). An agent with proficiency level five in the matching category scores forty points on this component. An agent with no matching skill scores ten points.

The second component is current workload and it carries thirty percent of the total weight. Compute the agent's active case count — the number of applications assigned to them where the status is not completed, rejected, or cancelled. If the agent has no daily_case_cap, compute a workload ratio using a soft cap of twenty cases as the baseline. Workload score equals one hundred minus (active_case_count divided by soft_cap multiplied by one hundred), clamped between zero and one hundred. An agent with zero active cases scores thirty points on this component. An agent at their cap scores zero points on this component.

The third component is recent SLA compliance and it carries twenty percent of the total weight. Look at the agent's applications that were completed or rejected in the last thirty days. For each one, check if it was completed before its sla_deadline. SLA compliance rate equals on_time_count divided by total_completed_in_period, multiplied by one hundred. If the agent has no completions in the last thirty days, give them fifty (neutral score). An agent with one hundred percent SLA compliance scores twenty points on this component.

The fourth component is queue urgency and it carries ten percent of the total weight. This component does not depend on the agent — it depends on the application itself. Specifically, it gives priority to routing urgent-tier applications to agents who have demonstrated they can handle fast turnaround. For urgent tier, prefer agents with higher SLA scores. For standard tier, this component has a flat value of ten for all agents (it does not differentiate). For express tier, it gives a five-point bonus to agents whose SLA compliance rate is above eighty percent.

The total score is the sum of all four weighted component scores. The system selects the agent with the highest total score. If multiple agents are tied, select the one who was last assigned an application the longest ago (to distribute work evenly over time). If no agent scores above a minimum threshold of fifteen points, the application stays unassigned and the admin receives an email notification with the application code and the reason no agent was selected (no available agents, all at capacity, or no agents with matching skills).

This scoring calculation must be implemented in the assignments service layer as a private async method called _score_agents. It takes the application record as input, runs queries to gather the necessary data for all eligible agents in as few database round-trips as possible (prefer a single query joining agent_settings, agent_service_skills, and application counts rather than N queries per agent), computes the scores, and returns the winning agent's user_id or None if no agent qualifies.

The auto-assignment is triggered as an ARQ background job called auto_assign_application_job. This job is enqueued by the application submission service immediately after the application is inserted and committed. The job receives the application_id as its argument. It opens a fresh session, runs the scoring algorithm, and if a winner is found, calls the same assignment logic used by admin_assign_application (so all the same side effects — status transition, history record, system message, email notifications — happen identically whether the assignment is manual or automatic).

The admin can also trigger a manual re-run of the algorithm at any time for a specific application via POST /api/admin/applications/{code}/auto-assign. This is useful when an application has sat unassigned because no agents were available and the admin wants to try again after an agent has come back online.

```
New Application Submitted
         │
         ▼
Auto-Assign Job Enqueued (ARQ)
         │
         ▼
Collect All Eligible Agents
(active, accepting_cases, under daily cap, seen recently)
         │
         ├─── No eligible agents ──► Stay Unassigned + Admin Alert Email
         │
         ▼
Score Each Agent:
  [Expertise Match x 0.40]
  + [Workload Room   x 0.30]
  + [SLA Performance x 0.20]
  + [Queue Urgency   x 0.10]
         │
         ├─── All scores < 15 ──► Stay Unassigned + Admin Alert Email
         │
         ▼
Select Highest Score
(tiebreak: longest time since last assignment)
         │
         ▼
Assign: update application.assigned_agent_id
        insert assignment_history record
        transition status to under_review
        create system message
        send notification emails
```


## Section Four: Payment Architecture — Design Decisions

The payment module must be built as a proper abstraction so that a real payment gateway can be plugged in without rewriting the business logic. Define a PaymentGateway abstract base class or Protocol in app/core/payments.py with the following interface: an async method to initiate a mobile money push (taking phone number, amount, currency, transaction reference), an async method to check transaction status (taking provider transaction ID, returning current status), and an async method to process a card charge (taking tokenized card data, amount, currency, returning transaction result). Implement a StubPaymentGateway that returns plausible fake responses for development purposes — the stub should simulate successful payments immediately, allow testing of the failure path via a special phone number or card number pattern.

The fee structure the frontend displays must be computed by the backend and stored on the payment record. When a client calls the initiate endpoint, the backend reads the application's service and tier to compute: the service_fee in Rwandan Francs (this is the platform_fee from the ServicePricingTier record), the government_fee in Rwandan Francs (the government_fee from the same tier record), and the vat_rate (which is eighteen percent expressed as 0.18). The total amount the client pays is the service_fee plus any applicable platform_fee (currently zero). The government_fee is displayed separately as a passthrough amount the client will pay directly to the authority — it is not collected by the platform.

For mobile money (both MTN MoMo and Airtel Money), the flow is: client calls the initiate endpoint with their phone number and operator, backend calls gateway.initiate_momo_push(), gateway sends a push notification to the client's phone, backend creates a payment record with status "processing" and an expires_at of now plus one hundred and twenty seconds, backend enqueues an ARQ job called payment_timeout_job to fire after one hundred and twenty seconds. The client then polls GET /api/payments/{transaction_id}/status on an interval (the frontend polls every five seconds based on the countdown timer). The timeout job runs after one hundred and twenty seconds — if the payment is still in "processing" state, it sets status to "timed_out" and sends the client an email saying the payment window expired with a link to try again.

For card payment, the flow is: client calls the initiate endpoint to get a payment intent, backend creates the payment record in "pending" state and returns the transaction_id and a 3DS session token, the frontend renders the 3DS verification frame using that token, the 3DS frame calls back to the gateway which calls a webhook endpoint on the backend when verification completes, the webhook handler updates the payment record to "paid" and triggers the post-payment flow. For development with the stub gateway, simulate the webhook callback by having the initiate endpoint also schedule an ARQ job that fires after three seconds and updates the payment to "paid".

When a payment reaches "paid" status (via any method), the backend must: update the payment record's paid_at, set the application record's payment_status to "paid" and payment_amount to the collected amount, create a system message in the application's conversation thread saying payment was received, and enqueue a payment confirmation email to the client. These four things must happen atomically in a single transaction.

The receipt endpoint reads the payment record and the associated application record and returns the complete receipt data shape that the frontend receipt page renders: serviceName, trackingCode, amount, governmentFee, vatAmount (computed as amount minus amount divided by one plus vatRate), method (human-readable: "MTN Mobile Money", "Airtel Money", "Visa Card", "Mastercard", "Agent Cash"), transactionId, receiptNumber, paidAt, applicationCode.


## Section Five: New Database Tables

All new tables are created in a single new Alembic migration file. The migration must be applied after the existing application_process_schema migration. Create tables in this order.

The agent_service_skills table stores agent expertise profiles. Columns: id as String(64) PK prefixed "ask_", agent_id as String(64) not null foreign key to users with ON DELETE CASCADE, service_category as String(64) not null (must be one of: identity, business, tax, welfare, permits, other), proficiency_level as Integer not null with a check constraint that it is between one and five inclusive, notes as Text nullable (the agent or admin can add context about their experience), created_at and updated_at as DateTime with timezone. Unique constraint on (agent_id, service_category) — one skill record per category per agent. Index on agent_id.

The payments table stores all payment transactions. Columns: payment_id as String(64) PK prefixed "pay_", application_id as String(64) not null foreign key to applications with ON DELETE RESTRICT (you cannot delete an application that has a payment), amount_rwf as Integer not null (the platform-collected service fee in Rwandan Francs), government_fee_rwf as Integer not null defaulting to zero (passthrough, not collected), platform_fee_rwf as Integer not null defaulting to zero, vat_rate as Numeric(4,3) not null defaulting to 0.18, currency as String(8) not null defaulting to "RWF", method as String(32) not null (mtn-momo, airtel-money, card, agent), provider_transaction_id as String(256) nullable (the gateway's reference), receipt_number as String(64) nullable unique (generated on payment success), status as String(32) not null defaulting to "pending" (enum: pending, processing, paid, failed, refunded, timed_out), card_brand as String(16) nullable (visa or mastercard), masked_phone as String(32) nullable (last four digits for display), paid_at as DateTime with timezone nullable, expires_at as DateTime with timezone nullable (for momo push window), created_at and updated_at. Indexes on application_id and status.

The application_escalations table stores oversight escalation records. Columns: id as String(64) PK prefixed "esc_", application_id as String(64) not null foreign key to applications, escalated_by as String(64) not null foreign key to users, reason as Text not null, oversight_status as String(32) not null defaulting to "escalated" (enum: escalated, resolved), resolved_at as DateTime nullable, resolved_by as String(64) nullable foreign key to users, resolution_note as Text nullable, created_at. Index on application_id. Index on oversight_status.

The audit_log table stores the immutable action trail. Columns: id as String(64) PK prefixed "aud_", actor_id as String(64) nullable foreign key to users (nullable for system actions), actor_role as String(32) nullable, action as String(128) not null (a verb describing what happened, e.g. "agent.assigned", "payment.processed", "service.published", "settings.updated"), resource_type as String(64) not null (e.g. "application", "service", "agent", "payment", "platform_settings"), resource_id as String(128) nullable (the ID or code of the affected resource), details as JSON not null (a dictionary with contextual before/after data or relevant metadata), ip_address as String(64) nullable, kind as String(32) not null (one of: Privileged, Money, Config, Assignment — used for the admin filter), created_at as DateTime with timezone not null. The table is insert-only — no update, no delete endpoints exist. Indexes on actor_id, kind, and created_at.

The broadcasts table stores mass communication records. Columns: id as String(64) PK prefixed "brc_", created_by as String(64) not null foreign key to users, audience_description as String(255) not null (human-readable label like "All active clients" or "Clients with applications for passport-renewal"), audience_filter as JSON not null (machine-readable criteria: {service_slug, status_filter, date_from, date_to} or {all: true}), channels as JSON not null (array of strings: ["email", "sms"]), message as Text not null, scheduled_at as DateTime nullable, sent_at as DateTime nullable, actual_reach as Integer nullable, estimated_reach as Integer nullable, broadcast_status as String(32) not null defaulting to "draft" (enum: draft, scheduled, sending, sent, failed), created_at.

The platform_settings table stores global platform configuration as a singleton. Columns: id as String(16) PK defaulting to "global" (always one row), accept_new_apps as Boolean not null defaulting to true, guest_apps as Boolean not null defaulting to false, data_retention_months as Integer not null defaulting to 24, enforce_2fa as Boolean not null defaulting to true, session_timeout_minutes as Integer not null defaulting to 60, ip_allowlist as Text nullable (comma-separated IPs, null means no restriction), maintenance_mode as Boolean not null defaulting to false, updated_by as String(64) nullable foreign key to users, updated_at as DateTime with timezone not null.

You must also modify two existing tables via the same migration. Add the sla_deadline column to the applications table: it is DateTime with timezone, nullable. This deadline is computed at submission time by taking submitted_at and adding the chosen tier's eta_business_days converted to calendar days (multiply by 1.4 to account for non-business days, rounding up to the nearest day). Add the sla_breached_at column to the applications table: it is DateTime with timezone nullable, set by a background job or computed query when now exceeds sla_deadline and the application is not yet in a terminal status.


## Section Six: Build Phases

Build in this exact order. Complete and verify each phase before starting the next. Do not combine phases. Do not leave a phase partially done.


Phase One: Database Migrations and Model Updates

Write a single new Alembic migration file that creates all five new tables (agent_service_skills, payments, application_escalations, audit_log, broadcasts, platform_settings) and adds sla_deadline and sla_breached_at to the applications table. The migration must include all constraints, indexes, and the check constraint on proficiency_level. Write the complete downgrade function. Apply the migration and confirm it runs without errors. After the migration, update the Application SQLAlchemy model in app/modules/applications/models.py to include the sla_deadline and sla_breached_at columns. Update the ApplicationDetailResponse and AgentCaseSummary schemas to include sla_deadline and a computed sla_state field that compares sla_deadline against the current UTC time rather than using the hardcoded 10/14 day thresholds.

Acceptance criteria: alembic upgrade head completes without errors. The applications table in the database now has sla_deadline and sla_breached_at columns. The Application SQLAlchemy model reflects these columns.


Phase Two: Agent Expertise Skills Module

Create the AgentServiceSkill SQLAlchemy model in app/modules/assignments/models.py alongside the existing AgentSettings model. Add the relationship assignment_service_skills to the User model or manage it directly via the assignments repository. Add new Pydantic schemas: AgentSkillItem (service_category, proficiency_level, notes), AgentSkillsResponse (agent_id, skills list of AgentSkillItem), SetAgentSkillsRequest (skills list). Add repository methods: get_agent_skills(agent_id), upsert_agent_skills(agent_id, skills) which replaces all skill records for that agent atomically (delete all, insert new in one transaction). Add service methods. Add routes to the assignments router: GET /api/admin/agents/{agent_id}/skills (REQUIRE_ADMIN), PATCH /api/admin/agents/{agent_id}/skills (REQUIRE_ADMIN). Agents cannot set their own skills — only admins can. Also add GET /api/agent/skills (REQUIRE_AGENT) so an agent can see their own profile.

Add new exception types in core/exceptions.py: AgentSkillNotFoundError (404) and InvalidServiceCategoryError (422).

Acceptance criteria: Admin can set skills for an agent via the PATCH endpoint. The agent can read their own skills via GET /api/agent/skills. The agentskills are stored correctly in the database with the unique constraint preventing duplicate categories per agent.


Phase Three: SLA Deadline Computation

Update the application submission service method in app/modules/applications/service.py. After creating the application record, look up the ServicePricingTier for the chosen tier and read its eta_business_days. Compute sla_deadline as submitted_at plus eta_business_days multiplied by 1.4, rounded up to the nearest full day. Store this value in the sla_deadline column at the time of insertion. Ensure this is included in the same database transaction as the application insert.

Update the sla_state calculation throughout the codebase. Remove the hardcoded threshold function. Replace it with: if sla_deadline is None, return "ok". If the application is in a terminal status (completed, rejected, cancelled), return "ok". If now (UTC) is greater than sla_deadline, return "over". If now (UTC) is within twenty-four hours of sla_deadline, return "warn". Otherwise return "ok".

Update the analytics service to compute sla_compliance_rate correctly: count applications that were completed with completed_at less than or equal to sla_deadline, divided by total completed applications, multiplied by one hundred. If there are no completed applications, return one hundred (perfect score, no violations yet).

Acceptance criteria: Submit a test application for a service with an express tier of three business days. The application record in the database has sla_deadline set to approximately four calendar days from submission. The sla_state for that application is "ok" initially, "warn" within 24 hours of the deadline, and "over" after the deadline passes.


Phase Four: Smart Assignment Algorithm and Auto-Assignment Job

In app/modules/assignments/service.py, implement the private async method _score_agents(application: Application) -> tuple[str | None, float]. This method must:

First, query all eligible agents in a single efficient database call. An eligible agent is a User with role "staff:agent" and is_active true, joined with their AgentSettings record where accepting_cases is true, joined with a subquery that counts their active non-terminal applications. Filter out agents who have reached their daily_case_cap.

Second, for each eligible agent, compute the four scoring components described in Section Three. Batch the skill lookups and SLA history lookups to avoid N+1 queries — fetch all agent_service_skills records for all eligible agent IDs in one query, fetch all recent application completion records for all eligible agent IDs in one query, then do the scoring computation in Python without additional database calls.

Third, return the user_id of the highest-scoring agent and their score, or (None, 0.0) if no agent scores above fifteen.

Create the new ARQ background job function auto_assign_application_job in app/modules/assignments/jobs.py. The job takes application_id as an argument, opens a fresh database session, fetches the application, calls _score_agents, and if a winner is found calls the existing _do_assign internal method that handles all the side effects. If no winner is found, enqueues an admin alert email.

Register auto_assign_application_job in app/worker.py alongside the other jobs.

Update the application submission service to enqueue auto_assign_application_job immediately after committing the new application.

Add the POST /api/admin/applications/{code}/auto-assign route to the admin applications router. This route calls a service method that re-runs the scoring algorithm for an already-submitted application that is still unassigned.

Acceptance criteria: Submit a new application. Check that auto_assign_application_job is enqueued. Run the ARQ worker. Check that the application gets assigned to an agent (assuming at least one eligible agent exists with matching skills or neutral skills). Verify the assignment history record was created and the status moved to under_review. Verify the agent received a notification email.


Phase Five: Payment Module

Create the directory app/modules/payments/ with all standard files: models.py, schemas.py, repository.py, service.py, router.py, and jobs.py. Also create app/core/payments.py with the gateway abstraction.

In app/core/payments.py, define a PaymentGateway Protocol with three async methods: initiate_momo_push returning a provider transaction ID string, check_transaction_status returning a status string and optional additional data, and process_card_charge returning transaction result. Implement StubPaymentGateway that returns a fake provider_transaction_id on initiate, always returns "paid" on status check, and simulates 3DS approval on card charge. Expose get_payment_gateway() that returns the stub by default, reading a PAYMENT_GATEWAY env var (values: stub, future-real-provider) from Settings.

Add PAYMENT_GATEWAY to Settings in app/core/config.py with default "stub" and add it to .env.example.

Add new exception types: PaymentNotFoundError (404), PaymentAlreadyPaidError (409), PaymentExpiredError (410), PaymentGatewayError (502).

The Payment SQLAlchemy model goes in app/modules/payments/models.py.

The service layer must implement:

initiate_payment(application_code, method, phone_or_card_token, client_id) — verifies the application belongs to this client, verifies payment_status is not already "paid", looks up the tier pricing to compute fees, calls the gateway to initiate the transaction, creates the payment record, for momo enqueues payment_timeout_job to fire after 120 seconds, returns payment_id and transaction metadata to the frontend.

get_payment_status(transaction_id, client_id) — verifies ownership, calls gateway.check_transaction_status, if the gateway returns "paid" and the payment record is still in "processing", calls _confirm_payment internally, returns the current payment status.

_confirm_payment(payment_id) — internal method called when a payment is confirmed as paid: sets payment.status to "paid", sets payment.paid_at, generates a unique receipt_number (format: RCP-YYYYMMDD-XXXXX using the same alphabet as PRX codes), updates the application's payment_status and payment_amount in the same transaction, creates a system message in the application conversation, enqueues a payment confirmation email.

get_receipt(application_code, client_id) — returns the full receipt shape including all fee breakdowns and a computed vat_amount field.

The router must define: POST /api/payments/initiate (REQUIRE_CLIENT, rate limit 5/minute), GET /api/payments/{transaction_id}/status (REQUIRE_CLIENT, rate limit 60/minute), POST /api/payments/card/webhook (no auth — webhook from payment gateway, verify with a secret header), GET /api/applications/{code}/payment/receipt (REQUIRE_CLIENT).

Wire the payments router into main.py.

Acceptance criteria: Call POST /api/payments/initiate as a client with an application code and method "mtn-momo". Receive back a transaction_id. Call GET /api/payments/{transaction_id}/status and receive "processing". Wait for the ARQ timeout job OR manually trigger the stub confirmation. Call GET /api/applications/{code}/payment/receipt and receive the full receipt shape. Verify the application record's payment_status is now "paid".


Phase Six: Analytics Rewrite

The existing GET /api/admin/analytics endpoint must be completely rewritten. The current AnalyticsResponse schema returns a shape the frontend cannot use. Replace it entirely.

The new AnalyticsResponse schema must contain exactly these fields, matching the TypeScript interfaces from the frontend:

metrics is a list of six AdminMetric objects. Each AdminMetric has id (string), label (string), value (string or number), delta (optional string like "+12%"), deltaDir (optional string: "up", "down", or "flat"), and deltaColor (optional string: "ok", "warn", "danger", or "muted"). The six metrics are: total applications this month (compute from submitted_at in current month), completed this week (compute from completed_at in current week), average turnaround in hours (average of completed_at minus submitted_at for completions this month), SLA compliance percentage (computed correctly using sla_deadline), total collected revenue this month in RWF (sum of payment.amount_rwf where payment.status is paid), and count of agents currently active (users with role staff:agent and is_active true and accepting_cases true).

weekly_bars is a list of ten WeeklyBar objects covering the last ten weeks. Each WeeklyBar has week (string in format "Mon DD" representing the Monday of that week, e.g. "Jun 09") and count (integer count of applications submitted during that week). Compute by generating the ten Monday dates going backward from today and counting applications per week.

service_mix is a list of ServiceMixBar objects, one per service that has received at least one application in the last thirty days. Each ServiceMixBar has service (the service name string), pct (the percentage of total applications this service represents, as a float zero to one hundred), and color (use the service's color field from the services table).

payment_mix is a list of PaymentMixBar objects showing payment method distribution. Each PaymentMixBar has method (the method string, human-readable: "MTN Mobile Money", "Airtel Money", "Card", "Agent Cash", "Pending"), pct (percentage), and color (assign fixed colors: MTN yellow, Airtel red, Card blue, Agent Cash green, Pending gray). Count applications by their associated payment method or "Pending" if no payment record exists.

status_breakdown is a list of StatusBreakdown objects for all statuses that have at least one application. Each has label (human-friendly status name), count, pct, and color (assign fixed colors per status).

alerts is a list of AlertItem objects generated dynamically from database queries. Each AlertItem has id, message, severity ("warn", "danger", or "info"), optional cta label, and optional ctaHref. Generate alerts for: applications with sla_state "over" (one alert per such application, severity "danger"), documents with qc_status "fail" that are still associated with active applications (severity "warn"), the unassigned queue count if greater than five (severity "warn", message "N applications awaiting assignment").

agents is a list of AdminAgent objects for all active agents. Each AdminAgent has id, fullName, initials (first letter of first and last name), email, skills (list of service category strings from agent_service_skills), load (active case count), capacity (daily_case_cap or 20 as default), twoFa (from StaffProfile.twofa_enabled), role (always "AGENT" unless you add a seniority concept later), status ("active" if accepting_cases and seen in last 24h, "away" if accepting_cases but not seen in 24h, "offline" if not accepting_cases), activeCases (count), completedTotal (all time count of completed applications), avgTurnaround (average turnaround as a string like "2.5h" or "3.2d"), slaPercent (float), rating (hardcode 4.5 until a ratings module exists).

This is a complex aggregation query. Write it efficiently: use a single SQL query with multiple CTEs (Common Table Expressions) or subqueries where possible to avoid making dozens of individual queries. Aggregate at the database level, not in Python loops.

Acceptance criteria: Call GET /api/admin/analytics as admin. Receive a response with all seven top-level keys: metrics, weekly_bars, service_mix, payment_mix, status_breakdown, alerts, agents. Each must be a correctly populated list matching the described shape. The SLA compliance rate must reflect actual deadline-based compliance.


Phase Seven: Admin Oversight Board

Create a new module app/modules/oversight/ with models.py (importing and using the ApplicationEscalations model from the applications models or defining it here), schemas.py, repository.py, service.py, and router.py.

The oversight cases query must identify applications in one of three oversight states. SLA-breached cases are applications where sla_deadline is not null, sla_deadline is in the past, and the status is not completed, rejected, or cancelled. Disputed cases are applications that have an active record in the application_escalations table with oversight_status "escalated". Attention cases are any case in either of the above categories plus cases where a document has qc_status "fail" and is still active.

The GET /api/admin/oversight/cases endpoint accepts a tab query parameter (all, attention, sla, disputes) and returns a list of OversightCase objects. Each OversightCase has code, serviceName, agentName (nullable), clientName (from personal_info.fullName), status (one of: "in-progress", "sla-breach", "disputed", "escalated", "resolved"), and issue (a human-readable string explaining why this case is in oversight, e.g. "SLA deadline passed 3 days ago" or "Document quality check failed for national_id").

The PATCH /api/admin/oversight/cases/{code}/escalate endpoint (REQUIRE_ADMIN) creates a new ApplicationEscalations record. The body accepts a reason string.

The PATCH /api/admin/oversight/cases/{code}/resolve endpoint (REQUIRE_ADMIN) sets the escalation's oversight_status to "resolved", sets resolved_at and resolved_by.

Wire the oversight router into main.py.

Acceptance criteria: Submit a test application and then manually set its sla_deadline to a time in the past. Call GET /api/admin/oversight/cases?tab=sla and verify the application appears. Call the escalate endpoint and verify a record is created. Call GET /api/admin/oversight/cases?tab=disputes and verify the escalated application appears.


Phase Eight: Admin Audit Log

Create app/modules/audit/models.py with the AuditLog SQLAlchemy model. Create app/modules/audit/repository.py with a single method: insert_audit_entry and list_audit_entries(kind_filter, limit, offset). Create app/modules/audit/schemas.py with AuditEntry (id, timestamp as ISO string, actor, actorType, description, kind) and AuditLogResponse (entries, total, has_more).

The audit log must be written automatically for key actions. Implement this as a utility function write_audit_entry(session, actor_id, actor_role, action, resource_type, resource_id, details, ip_address, kind) that service layer methods call directly after their main operation. Do not attempt to do this via middleware — call it explicitly in the service methods for the following operations: any admin action that changes agent status or password (kind: Privileged), any payment processing or refund event (kind: Money), any change to platform_settings or service status (kind: Config), any application assignment or reassignment (kind: Assignment). Call write_audit_entry within the same session transaction so that if the main operation rolls back, the audit entry also rolls back.

Add the GET /api/admin/audit-log route (REQUIRE_ADMIN) with kind and limit and offset query parameters.

Wire the audit router into main.py.

Acceptance criteria: Perform an admin assignment. Check GET /api/admin/audit-log?kind=Assignment and verify a new entry appears with the correct actor, action, and resource details.


Phase Nine: Admin Broadcasts

Create app/modules/broadcasts/ with all standard files plus jobs.py. The broadcast_send_job ARQ function takes broadcast_id as its argument. It fetches the broadcast record, queries the database for users matching the audience_filter criteria, and enqueues individual send_email_job calls for each matching user. Update the broadcast's actual_reach count and sent_at when all sends are dispatched. The job must handle partial failures gracefully — if some sends fail, still update the record with how many succeeded.

Routes: GET /api/admin/broadcasts returns the list. POST /api/admin/broadcasts (REQUIRE_ADMIN) accepts audience_description, audience_filter (a dict), channels (array), message (string), and an optional scheduled_at. If scheduled_at is null, enqueue the broadcast_send_job immediately. If scheduled_at is set, schedule the job for that time using ARQ's job scheduling with a defer_until parameter. Set estimated_reach by counting users matching the audience_filter at creation time.

Wire into main.py.

Acceptance criteria: Create a broadcast via the admin endpoint. Verify it appears in GET /api/admin/broadcasts. With the ARQ worker running, verify the broadcast_send_job fires and emails are sent to matching users (check Mailpit in development).


Phase Ten: Admin Platform Settings

Create app/modules/platform/ with the standard files. The platform_settings record is a singleton — the repository must implement a get_or_create() method that either fetches the single "global" row or creates it with all defaults if it does not exist. There is no endpoint to create settings — only read and update.

Routes: GET /api/admin/settings (REQUIRE_ADMIN) returns the current settings. PATCH /api/admin/settings (REQUIRE_ADMIN) updates specific fields. After any update, write an audit entry with kind Config.

Add a maintenance mode check to the FastAPI middleware stack. In app/core/middleware.py, add a check that runs on every non-admin request: if the platform_settings.maintenance_mode is true, return a 503 response with message "The platform is temporarily unavailable for maintenance." Cache the maintenance_mode value in Redis with a five-second TTL to avoid hitting the database on every request.

Wire into main.py. Add the settings router before other non-admin routers so the maintenance check happens early.

Acceptance criteria: Call GET /api/admin/settings and receive the defaults. Call PATCH /api/admin/settings with maintenance_mode true. Call any public endpoint (e.g. GET /api/services) and verify a 503 is returned. Call PATCH /api/admin/settings with maintenance_mode false and verify public endpoints work again.


Phase Eleven: Agent Performance Metrics

Add two new route methods to the assignments router or create a separate metrics module. The implementation is simpler than a full module — the data is computed from the applications table.

GET /api/agent/metrics (REQUIRE_AGENT) returns an AgentMetricsResponse with: completedCount (applications completed this calendar month where the agent was the assigned agent), completedDelta (percentage change versus last month, formatted as "+12%" or "-5%"), avgTurnaround (average of completed_at minus submitted_at for completions this month, as a float in hours), avgTurnaroundDelta (same as completedDelta but for turnaround), onTimeSLAPercent (completions this month where completed_at was before sla_deadline, as float 0-100), clientRating (hardcoded 4.5 for now with a note in the code that this will be replaced when a ratings module exists), weeklyBars (last ten weeks of this agent's own completions, same WeeklyBar shape as analytics), leaderboard (all agents ranked by onTimeSLAPercent this month, each entry having rank, agentInitials, agentId matches current user or shows "You", slaPercent — do not show full names except for the current agent).

GET /api/admin/agents/leaderboard (REQUIRE_ADMIN) returns the same leaderboard data with full agent names visible.

Acceptance criteria: As an agent who has at least one completed application, call GET /api/agent/metrics and receive all fields with computed values. The leaderboard should show the agent's own rank.


Phase Twelve: Client Dashboard Summary

Add GET /api/applications/summary to the client applications router. This endpoint (REQUIRE_CLIENT) queries the database for the calling client's applications and returns: active_count (applications in received, under_review, in_progress, submitted_to_authority, awaiting_response, awaiting_client), completed_count (applications in completed status), document_count (count of active documents across all the client's applications), avg_turnaround_days (average of completed_at minus submitted_at in days for completed applications, rounded to one decimal, null if no completions yet), unread_message_count (count of ApplicationMessage records for this client's applications where is_internal is false and is_system is false and sender_role is "staff:agent" and is_read_by_client is false).

Also update the ApplicationDetailResponse schema to include two new fields: status_display (a computed mapping of the internal status to the frontend display status using the mapping described below) and payment_info (a nullable nested object containing the payment method, amount, government_fee, vat_rate, paid_at, and receipt_number if a payment record exists for this application).

The status_display mapping function must be a shared utility in app/modules/applications/constants.py:
- received → "in-progress"
- under_review → "in-progress"
- in_progress → "in-progress"
- submitted_to_authority → "in-progress"
- awaiting_response → "on-hold"
- awaiting_client → "action-required"
- completed → "completed"
- rejected → "discontinued"
- cancelled → "discontinued"

Acceptance criteria: As a client with at least one submitted application, call GET /api/applications/summary and receive all five fields. Call GET /api/applications/{code} and verify the response includes status_display and payment_info fields.


Phase Thirteen: Final Wiring and Migration

At this point, twelve build phases are complete. Now consolidate everything.

Write the new Alembic migration including all tables from Phase One if it was not written already. Run alembic upgrade head and verify all tables are created without error.

Update app/main.py to include all new routers: payments router, oversight router, audit router, broadcasts router, platform settings router.

Update app/worker.py to register: auto_assign_application_job, payment_timeout_job, broadcast_send_job.

Update app/seed.py to seed a "global" platform_settings row alongside the admin user and the dev services, so the maintenance mode middleware never fails on a missing row.

Update app/core/config.py to add PAYMENT_GATEWAY setting.

Update .env.example with PAYMENT_GATEWAY=stub.

Add any new exception types to core/exceptions.py that were identified but not yet added during the phase builds.

Run the application with make dev and confirm it starts without import errors.


Phase Fourteen: End-to-End Verification

Perform the following complete user journeys and verify each step produces the expected result.

Admin journey: Log in as admin via staff login and 2FA. Call GET /api/admin/analytics and confirm you receive metrics, weekly_bars, service_mix, payment_mix, status_breakdown, alerts, and agents. Set skills for an agent via PATCH /api/admin/agents/{agent_id}/skills with category "identity" and proficiency_level 4. Call GET /api/admin/settings and confirm the defaults are returned. Update maintenance_mode to true via PATCH /api/admin/settings and confirm public service listing returns 503. Restore maintenance_mode to false.

Client application and payment journey: Log in as a client. Call GET /api/applications/summary and confirm it returns five fields with zero counts. Submit a new application for the identity-category service via POST /api/applications/submit. Confirm the application is returned with a PRX code. Wait for the auto-assignment ARQ job to run (watch the worker logs). Confirm the application now has assigned_agent_id set. Call POST /api/payments/initiate with method "mtn-momo" and a test phone number. Receive a transaction_id. Call GET /api/payments/{transaction_id}/status. Confirm status is "processing". Wait for the ARQ timeout job (in stub mode it resolves quickly). Call GET /api/payments/{transaction_id}/status again and confirm status is "paid". Call GET /api/applications/{code}/payment/receipt and confirm the receipt data is complete. Call GET /api/applications/{code} and confirm payment_status is "paid" and status_display is "in-progress".

Agent journey: Log in as the agent who was auto-assigned the above application. Call GET /api/agent/cases and confirm the application appears. Call GET /api/agent/cases/{code} and confirm the full case detail including documents and messages. Call PATCH /api/agent/cases/{code}/status with status "in_progress". Call GET /api/agent/metrics and confirm completedCount and other metrics appear (even if zero for now). Call GET /api/agent/skills and confirm the skills set by the admin are returned.

Oversight journey: As admin, call GET /api/admin/oversight/cases?tab=sla. If no SLA breaches exist, manually update a test application's sla_deadline to a past date in the database and call again. Confirm the application appears. Call the escalate endpoint for that application. Call GET /api/admin/oversight/cases?tab=disputes and confirm it appears there.

Broadcast journey: As admin, call POST /api/admin/broadcasts with a message targeting all clients. Wait for the ARQ worker to process broadcast_send_job. Check Mailpit (development SMTP server) and confirm emails were sent.

Audit journey: As admin, perform several operations (assign an application, change settings, process a payment). Call GET /api/admin/audit-log and confirm entries appear for each action with correct kind classification.


## Section Seven: Complete New Endpoint Reference

Every endpoint listed here must be implemented. No stubs. No placeholders.

Payment endpoints: POST /api/payments/initiate (REQUIRE_CLIENT), GET /api/payments/{transaction_id}/status (REQUIRE_CLIENT), POST /api/payments/card/webhook (no auth, secret header validation), GET /api/applications/{code}/payment/receipt (REQUIRE_CLIENT).

Assignment and skills endpoints: GET /api/admin/agents/{agent_id}/skills (REQUIRE_ADMIN), PATCH /api/admin/agents/{agent_id}/skills (REQUIRE_ADMIN), GET /api/agent/skills (REQUIRE_AGENT), POST /api/admin/applications/{code}/auto-assign (REQUIRE_ADMIN).

Analytics endpoint: GET /api/admin/analytics (REQUIRE_ADMIN) — complete rewrite returning the full seven-section response.

Oversight endpoints: GET /api/admin/oversight/cases (REQUIRE_ADMIN, query param: tab), PATCH /api/admin/oversight/cases/{code}/escalate (REQUIRE_ADMIN), PATCH /api/admin/oversight/cases/{code}/resolve (REQUIRE_ADMIN).

Audit endpoint: GET /api/admin/audit-log (REQUIRE_ADMIN, query params: kind, limit, offset).

Broadcast endpoints: GET /api/admin/broadcasts (REQUIRE_ADMIN), POST /api/admin/broadcasts (REQUIRE_ADMIN).

Platform settings endpoints: GET /api/admin/settings (REQUIRE_ADMIN), PATCH /api/admin/settings (REQUIRE_ADMIN).

Agent metrics endpoints: GET /api/agent/metrics (REQUIRE_AGENT), GET /api/admin/agents/leaderboard (REQUIRE_ADMIN).

Client summary endpoint: GET /api/applications/summary (REQUIRE_CLIENT).


## Section Eight: Efficiency and Senior Engineer Standards

Every decision must be made as a senior engineer who values performance, clarity, and maintainability above all else.

Never make N plus one queries. Any operation that iterates over a list of records and needs data from related tables must use a single JOIN query or a batch-fetch approach, not a loop with individual queries. The analytics endpoint is the most critical example — all seven sections must be computed with as few round-trips as possible.

Never duplicate business logic across modules. The status display mapping lives in one place: a function in applications/constants.py. Call it from every schema that needs it rather than writing the mapping inline in multiple places.

The payment gateway abstraction must be a true interface — the gateway is injected into the payment service as a constructor argument, not called via a module-level singleton. This makes the service independently testable.

The audit log write_audit_entry call must be within the same database transaction as the operation it records. Never commit the main operation first and then write the audit entry — if the audit write fails, the operation should also roll back.

The maintenance mode Redis cache must use a TTL short enough to not leave users locked out for long (five seconds is correct) but long enough to avoid hammering the database on every request.

The auto-assignment scoring must be computed in Python after fetching all required data in minimal queries — do not run the scoring logic as a SQL subquery or stored procedure. Fetch the data, compute in Python, select the winner.

Do not add any new feature that was not explicitly specified in this document. Build exactly what is described, nothing more. If you notice something that seems missing or incorrect in this spec, add a comment to the relevant service method describing the concern, but do not deviate from the specified behavior.

Type annotations must be complete. Every function parameter and return type must be annotated. Run mypy after each phase if possible and fix any type errors before advancing.

Keep individual files focused. If a service.py file grows beyond four hundred lines, consider splitting it into a service.py and a private _service_impl.py or breaking the module into sub-modules. Do not let a single file try to do too much.

Use existing shared infrastructure. The rate_limit dependency, the success_response function, the AppError hierarchy, the ARQ job_queue_manager — all of these are already tested and working. Do not reinvent them.


## Section Nine: This Build Is the Closeout

When all fourteen phases are complete and the verification in Phase Fourteen passes, the ProxiServe backend is production-ready. Every frontend page will have a real API to call. Every user journey — client submitting and paying for an application, agent processing it, admin overseeing the platform — will function end-to-end without any mock data or stub responses.

The only things intentionally deferred are: a real payment gateway integration (the stub can be replaced by reading the PAYMENT_GATEWAY env var), client ratings and feedback (the 4.5 hardcode is marked for replacement), and real-time WebSocket messaging (the current request-response pattern is sufficient; WebSocket can be added as a separate enhancement without changing any existing endpoint).

Do not consider the work done until every endpoint in Section Seven returns real data from the database, every Phase Fourteen test passes, and the application starts cleanly with make dev without any import errors or warnings.
