# ProxiServe — Application Process Module Specification

This document is the definitive specification for building the application process module in the ProxiServe FastAPI backend. It covers the current state of the project, the complete role hierarchy and the power dynamics between each role, how the application process is designed conceptually and technically, every new database table that must be created, every API endpoint that must be exposed, all new Python dependencies required, and the FastAPI patterns and best practices that must be followed in building this module. An AI builder reading this document should be able to implement the entire feature from scratch with full confidence in what to build, how to structure it, and how it must behave under every scenario.


## Part One: Project Context and Current State

ProxiServe is a government and administrative services platform. It exists to digitize and streamline application processes that would otherwise require physical visits to offices — services such as passport renewals, business registrations, tax filings, permit applications, and similar bureaucratic workflows. Clients (ordinary members of the public) submit applications through a structured multi-step wizard on the web frontend. Those applications are then assigned to trained staff agents who process them, liaise with relevant authorities, and update the client on progress. The platform owner (admin) controls everything about how those processes are structured.

The backend is a FastAPI application running on Python 3.12 with SQLAlchemy 2.0 in fully async mode, PostgreSQL 16 as the primary database, Redis 7 as the cache and job broker, and ARQ as the background task queue. The codebase follows a strict per-module layered pattern: every domain area lives in its own folder under app/modules/, and each folder contains models.py (SQLAlchemy ORM definitions), schemas.py (Pydantic v2 request and response DTOs), repository.py (all database queries), service.py (business logic that orchestrates repository calls and side effects), and router.py (FastAPI route handlers that inject services via Depends()). There is also a core/ layer for shared infrastructure: the database session, Redis client, ARQ job queue manager, SMTP email notifier, JWT and Argon2 security utilities, rate limiting, middleware, structured logging, and the uniform ApiResponse envelope that wraps every HTTP response in the format {"success": bool, "errorType": string or null, "message": string, "data": object or null}.

The authentication module is fully implemented and battle-hardened. It supports three roles — client, staff:agent, and staff:admin — with distinct login flows, token lifetimes, and security requirements. Clients log in with email or phone and a password followed by an OTP challenge. Staff members go through a two-factor authentication flow with TOTP, SMS code, or backup codes after their password check. Access tokens are short-lived JWTs stored in HTTP-only cookies, with a rotating refresh token family stored in Redis. The auth module exposes FastAPI dependency factories that can be composed onto any route to enforce role access: REQUIRE_ADMIN, REQUIRE_AGENT, REQUIRE_AGENT_OR_ADMIN, and REQUIRE_CLIENT are ready to import and use.

What currently exists in the applications module is a stub. There is a fixture-based service that pretends to look up a hardcoded application code (PRX-2026-00483) and claim it. There is no real database table, no real submission, no real document handling, and no real agent assignment. This stub will be completely replaced by the real implementation described in this document. The admin module currently handles only agent CRUD (creating, listing, updating, and disabling agents) and that will remain untouched. File upload infrastructure does not yet exist anywhere in the codebase. Notification emails flow through the ARQ job queue using an SMTP notifier that is already wired up and working.

The web frontend is a Next.js 16 application with a component-rich UI. The admin's service schema builder, the client's five-step application wizard, the agent's case queue and case detail view, and the public application tracker are all built and visually complete — but they are all currently running on mock data or empty states because the backend has not yet delivered the real APIs. This specification drives the backend that will power all of that.


## Part Two: Role Hierarchy and Power Dynamics

There are three roles in the system and their capabilities relative to the application process are precisely defined and non-overlapping in authority.

```
                    ┌──────────────────────────────────────┐
                    │          staff:admin                 │
                    │  Creates and controls the process    │
                    │  Assigns agents to applications      │
                    │  Can override any status             │
                    │  Sees everything across all users    │
                    └─────────────┬────────────────────────┘
                                  │ defines
                                  ▼
                    ┌──────────────────────────────────────┐
                    │       Service Templates               │
                    │  (the blueprint for applications)    │
                    └──────────┬──────────────┬────────────┘
                    consumed   │              │  assigned
                    by         ▼              ▼
          ┌─────────────────────────┐  ┌──────────────────────────────┐
          │        client           │  │       staff:agent            │
          │  Fills out application  │  │  Processes assigned cases    │
          │  Uploads documents      │  │  Updates statuses            │
          │  Tracks progress        │  │  Communicates with client    │
          │  Messages agent         │  │  Reviews documents           │
          └─────────────────────────┘  └──────────────────────────────┘
```

The admin is the architect of the entire process. The admin creates what the system calls a service — a complete template that defines every aspect of an application process from start to finish. When the admin creates a service, they define its name, category, description, base fees for each pricing tier, estimated turnaround times, the ordered list of steps the application will go through, which documents the applicant will be required to upload, and the dynamic form fields that determine what service-specific information gets collected in step two of the wizard. The admin also controls the published status of a service: a service can be in draft while being designed, then published to become visible to clients, then paused if there is temporary unavailability, or archived when it is permanently retired. The admin can see every application that has ever been submitted across all services and all clients. The admin can override any application's status, reassign it between agents, and access all documents. Critically, neither agents nor clients have any ability to create or modify service templates. The process architecture is exclusively in the admin's hands.

The agent is the operational processor. An agent is a staff member who has been created by the admin, has received their temporary password by email, and has completed their first-time password change and 2FA setup. Agents see only applications that have been assigned to them — either by the admin or by claiming from the unassigned queue. An agent cannot see applications assigned to another agent unless they are the admin. Within their assigned cases, agents have significant power: they can update the status of an application (moving it through the defined lifecycle), upload documents on behalf of the applicant if needed, send messages to the client, write internal notes visible only to staff, mark documents as having passed or failed quality checks, and complete or reject applications. An agent cannot create a new service template, cannot access the admin's analytics or broadcast tools, and cannot reassign a case to another agent (that is an admin action).

The client is the end user who submits and tracks their own applications. A client can browse the catalogue of services, choose one, go through the five-step wizard to submit an application, upload their required documents, pay the applicable fee, and then track the status of their application. The client can see and send messages within their own applications, and they can see any documents they have uploaded and those shared with them by the agent. A client can only see their own applications. A client cannot modify the structure or flow of the application process in any way — they are a passenger in a vehicle whose route was determined entirely by the admin.


## Part Three: The Application Process — Conceptual Model

An application is an instance of a service template filled out by a specific client. The relationship between a service template and an application is identical to the relationship between a form template and a completed form submission. The admin creates the form template once. Every time a client applies for that service, a new application instance is born, inheriting all structural rules from the template but carrying the client's own data.

When a client chooses a service, they go through a five-step wizard. In step one they provide their personal identifying information: full legal name, national ID number, date of birth, phone number, email address, and preferred language. In step two they answer the dynamic questions that the admin defined for that specific service — these questions vary completely between services and might be things like "What type of company structure do you want to register?" or "Is this a renewal or a new passport application?" In step three they upload the documents that the service requires, such as a scanned national ID card, a passport-sized photograph, or a business plan. In step four they review everything and agree to the platform's terms. In step five the application is submitted and a unique PRX code is generated — a human-readable code like PRX-20260617-A4B9C that the client can use to track their application even without logging in.

After submission, the application enters the received status. The admin sees it in their dashboard and assigns it to an agent. Once assigned, the agent receives a notification and the application moves to under review status. The agent examines the personal info, the service-specific responses, and the uploaded documents. If everything looks correct and complete, the agent begins active processing and the status moves to in progress. If the agent needs something from the client — an additional document, a correction to some information — the status moves to awaiting client and the agent sends a message explaining what is needed. Once the agent has done all the work they can do on the platform and submits to an external authority (e.g., a government ministry), the status moves to submitted to authority. While waiting for the authority to respond, the status is awaiting response. When the authority responds positively, the agent marks the application as completed. If rejected, the agent marks it rejected and explains why. A client can cancel an application in the early stages before an agent has started working.

The key insight for the implementation is that the structure of what gets collected — which documents, which form fields, in what order — is defined dynamically by the service template. The backend does not hardcode "passport renewal requires a national ID and a photo." Instead it reads the requirements from the service_document_requirements table and the service_form_fields table for whatever service the client is applying to. This is what makes the admin the architect of the process.


## Part Four: Service Template Architecture

A service template is the blueprint that governs an entire category of application. It is created and managed exclusively by the admin and consists of five interconnected layers: the core record, the process steps, the document requirements, the form fields, and the pricing tiers.

The core service record carries the immutable identity of the service: its unique slug (used in URLs, e.g., "passport-renewal"), its display name, its category (one of: identity, business, tax, welfare, permits, or other), a full description and a short description, a hex color code used for visual presentation on the frontend, a base icon name for display, and status flags controlling visibility. The status field can be active (visible and accepting submissions), paused (visible but not accepting new submissions), unavailable (temporarily offline), or archived (permanently retired). A version integer tracks how many times the service template has been significantly updated, which is important for maintaining consistency between a service's configuration at the time of submission and any later changes. The record also tracks which admin user created it and when.

The process steps are an ordered list of human-readable milestone names that describe the journey an application goes through. Examples for passport renewal might be: "Identity Verification", "Document Review", "Authority Submission", "Processing", "Collection Ready". These steps are purely informational from the backend's perspective — they are used to show the client a progress indicator on the frontend that says "Your application is on step 2 of 5." They are not the same as the application wizard steps (which are fixed at five), nor are they the same as the application statuses (which are the internal state machine). They are the admin's way of communicating milestones to the client in plain language. Each step has a step number, a title, and an optional description.

The document requirements define which files the client must upload during step three of the wizard. Each requirement has a machine-readable key (like "national_id" or "passport_photo" or "business_plan") that uniquely identifies it within this service, a human-readable label, a description explaining what the document should show, a type from the enumeration (id, certificate, photo, form, proof, other), a flag for whether it is required or optional, the maximum allowed file size in megabytes, a list of allowed MIME types, and a sort order controlling the display sequence. This table is what tells the wizard component which upload slots to show and what constraints to apply.

The form fields define the dynamic questions in step two of the wizard. Each field has a machine-readable key (like "company_type" or "application_reason"), a human-readable label, a field type from the enumeration (text, textarea, select, radio_card, date, switch, checkbox), help text explaining the question, whether it is required, a JSON object carrying options for select and radio_card types (an array of {value, label} pairs), conditional display logic (a field key and value that must be present for this field to appear), a sort order, a maximum character length for text types, and a placeholder string. The form field definitions are what the wizard uses to dynamically render step two — the frontend reads the field definitions from the service API and builds the form at runtime.

The pricing tiers define the cost and timeline options the client can choose from. There are three named tiers: standard, express, and urgent. Each tier has its own fee (the platform service fee in the smallest currency unit, e.g., Rwandan francs), a separate government fee (the statutory amount paid to the authority), an estimated turnaround in business days, a list of features (things the tier includes, rendered as a bullet list on the frontend pricing section), and an availability flag (so the admin can disable express or urgent if not currently offered for a given service).


## Part Five: Application Lifecycle and Status Machine

Every application has a status field that tracks exactly where it is in its processing journey. The status is a string enumeration with eight values. Below is the complete state machine including who can trigger each transition and under what condition.

```
                        [CLIENT submits wizard]
                                │
                                ▼
                          ┌──────────┐
                          │ received │ ◄─── initial state after submission
                          └──────────┘
                           │        │
              [ADMIN assigns agent] │ [CLIENT cancels]
                           │        │
                           ▼        ▼
                   ┌─────────────┐  ┌───────────┐
                   │ under_review│  │ cancelled │ ◄── terminal
                   └─────────────┘
                    │           │
        [AGENT starts] │       │ [AGENT needs more from client]
                    │           │
                    ▼           ▼
             ┌───────────┐  ┌─────────────────┐
             │in_progress│  │awaiting_client  │◄──────────────────┐
             └───────────┘  └─────────────────┘                   │
              │    │   │         │         │                       │
              │    │   │  [CLIENT  │  [CLIENT cancels]             │
              │    │   │  responds]│                               │
              │    │   │         │         ▼                       │
              │    │   │         │    ┌───────────┐               │
              │    │   │         │    │ cancelled │◄── terminal   │
              │    │   │         │                                  │
              │    │   │         └──► [AGENT continues] ──────────┘
              │    │   │              back to in_progress
              │    │   │
    [AGENT    │    │   │ [AGENT
    submits   │    │   │  needs
    to        │    │   │  more]──────► awaiting_client (above)
    authority]│    │   │
              │    │   │[AGENT rejects]
              ▼    │   ▼
  ┌────────────────┐  ┌──────────┐
  │submitted_to_   │  │ rejected │◄── terminal
  │authority       │  └──────────┘
  └────────────────┘
         │
  [AGENT logs response pending]
         │
         ▼
  ┌──────────────────┐
  │awaiting_response │
  └──────────────────┘
         │           │
  [authority    [authority
   approves]     rejects]
         │           │
         ▼           ▼
  ┌───────────┐  ┌──────────┐
  │ completed │  │ rejected │◄── terminal
  └───────────┘  └──────────┘
  terminal
```

The status transitions are enforced in the service layer, not in the router or repository. When an agent or admin requests a status change, the service layer looks up the current status and checks whether the requested target status is in the set of valid transitions from the current state. If the transition is invalid, the service throws a custom StatusTransitionError (a new AppError subclass with HTTP 422). This ensures that no amount of API calls can put an application into an illogical state.

Each status transition must be logged in the application_status_history table. The log entry records the new status, who made the change (by user ID), their role at the time, an optional note explaining the reason, and the timestamp. This log is the audit trail for the entire application lifecycle and it powers the history tab visible to both agents and clients.

The status visible to the client on the frontend maps to a human-readable headline and subheading. For example, "awaiting_client" displays as "We need something from you" with a subheading like "Your agent has requested an additional document." These display strings are a frontend concern derived from the status enum value — the backend sends the raw status string and the frontend maps it to friendly UI text.


## Part Six: Document Handling Architecture

Documents are central to the application process. Every application will have documents uploaded by the client during the wizard and potentially additional documents uploaded or requested by the agent during processing. The document handling subsystem must handle file upload, storage, metadata, access control, quality checking, and versioning robustly.

For file upload, FastAPI natively supports streaming multipart file uploads via its UploadFile abstraction powered by the python-multipart library. File uploads must never be buffered entirely in memory, because even a modest number of concurrent uploads of 10 MB PDF files would exhaust RAM. The implementation must stream each upload directly to disk using aiofiles, writing chunks as they arrive from the HTTP request body. The maximum file size should be enforced both at the HTTP layer (using a middleware that inspects Content-Length) and at the application layer (accumulating bytes written and aborting if the limit is exceeded).

The storage backend must be abstracted behind a StorageBackend interface with two methods: one to store a file given a stream and a destination path, and one to retrieve a file given a path and return a stream. This abstraction allows the development environment to use local filesystem storage while a production environment can swap in an S3-compatible backend (AWS S3, Google Cloud Storage, or MinIO) by changing an environment variable without touching application code. For the initial implementation, local filesystem storage is sufficient. The storage root directory must be configured via an environment variable called UPLOAD_DIR, with a sensible default of /tmp/proxiserve_uploads for development. Files are stored in a hierarchy: upload_dir/applications/{application_id}/documents/{document_id}/{filename}, which prevents filename collisions and makes it trivial to delete all files for an application.

For file type validation, the server must never trust the Content-Type header sent by the client. Instead, after writing the file to disk the system must read the first few kilobytes of the file back and check the magic bytes to determine the actual file type. The filetype Python library (a pure-Python port of the magic byte detection approach) or python-magic (a wrapper around libmagic) can do this detection reliably. The detected MIME type must be compared against the allowed MIME types defined in the service_document_requirements record for that requirement key. If the detected MIME type is not in the allowed list, the file must be deleted from disk and a validation error returned. This protection prevents clients from uploading executable files disguised as PDFs by changing the file extension.

Each uploaded document is recorded in the application_documents table. A document record has its own unique ID, links to its application, identifies which requirement slot it fills (via the requirement_key field matching the service_document_requirements key), stores the original filename the client submitted, the path where the file is stored, the detected MIME type, the file size in bytes, who uploaded it and in what role, a version integer (starting at 1 and incrementing each time the document is replaced), a QC status field (pending initially, then pass, warn, or fail after quality checking), a JSON field for QC notes, a flag indicating whether this is the current active version, a nullable reference to the document that replaced this one, and timestamps.

When a client replaces a document (e.g., after an agent flags it as poor quality), the old document record is not deleted. Instead, its is_active flag is set to false and its replaced_by field is populated with the ID of the new document record. The new record has version incremented by one. This versioning allows agents and admins to see the history of what was submitted and when, which is critical for compliance and for handling disputes.

After a document is successfully uploaded and its metadata saved to the database, the upload endpoint enqueues a background job via ARQ to perform quality checking. For image files (JPEG, PNG, WEBP), the quality checking job uses Pillow to verify that the image meets minimum resolution requirements (at least 400 pixels in each dimension), is not blank or nearly uniform in color, and has a reasonable aspect ratio for the document type. For photos specifically, additional checks can be run to detect if the image appears to be a photograph of a screen (moiré patterns) or a photocopy. The QC job updates the qc_status and qc_notes fields on the document record when it completes. If qc_status is set to warn or fail, the application's assigned agent is notified via an ARQ email job.

Access control for document retrieval must be enforced at the service layer, not by relying on obscure storage paths. When a GET request arrives for a document, the service layer first fetches the document record by ID, then verifies that the requesting user has a valid reason to see it: either the user is the client who owns the application this document belongs to, or the user is the agent assigned to this application, or the user is an admin. If none of these conditions is satisfied, a ForbiddenError is raised. The actual file is then streamed back as a streaming response with appropriate Content-Type and Content-Disposition headers. For download, Content-Disposition is set to attachment with the original filename. For preview (inline viewing in the browser), Content-Disposition is set to inline.


## Part Seven: Conversation and Messaging System

Every application has a conversation thread: a chronological sequence of messages between the client and the assigned agent. The messaging system also supports internal notes visible only to staff and system-generated messages for status transitions.

The application_messages table stores all messages. Each message belongs to one application, is sent by one user (identified by user_id and sender_role), has a text content field, a flag indicating whether it is an internal note (visible only to staff:agent and staff:admin, never to the client), a flag indicating whether it is a system message (generated automatically when a status changes, not sent by a human), a JSON array of document IDs for any attached files referenced in the message, a flag for whether the client has read it (is_read_by_client, defaulting to false for agent messages), an agent read timestamp (read_by_agent_at, set when the agent first loads the conversation after the message was sent by the client), and a creation timestamp. There is no updated_at — messages are immutable once sent, which is important for maintaining an honest audit trail.

When the client fetches the conversation for their application, the query returns all messages where is_internal is false, ordered by creation timestamp ascending. When an agent fetches the conversation for their case, the query returns all messages (internal and public), ordered the same way. This single difference in the query is the mechanism that keeps internal notes private: no separate table or complex ACL, just a boolean filter.

System messages are created automatically by the service layer whenever a status transition occurs. When the application moves from received to under_review, the system writes a message with is_system set to true and content like "Your application has been assigned to an agent and is now under review." When it moves to awaiting_client, the system writes a message notifying the client that action is required. When it moves to completed, the system writes a congratulatory message. These system messages appear in the client's conversation view as neutral center-aligned bubbles distinct from agent and client messages, giving the client a clear narrative of what happened without requiring agents to manually write status announcements.

When a client sends a message, the endpoint enqueues an ARQ email notification job to alert the assigned agent that there is a new message. Similarly, when an agent sends a non-internal message, an email notification is sent to the client. These notifications should include a preview of the message content and a link to the application.


## Part Eight: Agent Assignment System

Applications enter the system in received status with no agent assigned. The admin is responsible for assigning agents, though agents can also claim unassigned applications themselves.

The assignment information lives directly on the applications table: a nullable assigned_agent_id foreign key column and an assigned_at timestamp column. This makes it trivial to query "all applications assigned to agent X" and "all applications with no agent." It also makes the common path (reading application detail including who is assigned) a single JOIN rather than requiring a subquery into an assignment history table.

To preserve the history of assignments (for audit and for the history tab), there is a separate application_assignment_history table. Every time an assignment changes — whether an agent is assigned for the first time, reassigned to a different agent, or the assignment is removed — a record is written to this history table with the application ID, the previous agent ID (null if this is the first assignment), the new agent ID (null if the assignment is being cleared), who performed the action and their role, an optional note, and a timestamp. The history table is append-only.

The admin can assign an application to any active agent from the admin's application detail view. The admin can also reassign at any time, even after work has begun. Reassignment sends an email notification to both the outgoing agent (if any) and the incoming agent. When an application is reassigned, the previous agent loses visibility into that case immediately — they can no longer see it in their case list.

Agents can claim applications from the unassigned queue. The unassigned queue endpoint returns all applications in received status with no assigned_agent_id, ordered by submission timestamp ascending (oldest first). An agent POSTs to a claim endpoint with the application code, and the service layer assigns the application to that agent atomically using a database-level lock to prevent two agents from claiming the same application simultaneously. The claim also triggers the status transition from received to under_review and generates a system message and an email notification to the client.

Agents have a settings field for their availability status and their daily case cap. These settings live in the staff profiles or in a new agent_settings table. The availability flag (accepting_new_cases boolean) is checked before allowing an agent to claim from the unassigned queue — an unavailable agent is not shown in the admin's assignment dropdown and cannot claim from the queue. The daily case cap (max_daily_cases integer) is checked against the count of applications assigned to that agent that transitioned to under_review today, preventing overloading.


## Part Nine: New Backend Modules and Their Internal Structure

The following five new modules must be created under app/modules/. Each follows the same file structure as the auth module: models.py, schemas.py, repository.py, service.py, and router.py. Any module-specific constants should live in a constants.py file within that module.

The services module is responsible for service template management. It has no router of its own for the read path because public GET endpoints for services can be added directly to the admin module's router and a new public router. The admin routes under this module are all protected by REQUIRE_ADMIN. The service layer methods cover: creating a new service (which validates uniqueness of the slug), updating a service's core fields, managing form fields (add, update, remove, reorder), managing document requirements (same), managing pricing tiers (update fee and ETA for each tier, toggle availability), changing service status (publish, pause, unpause, archive), and listing or fetching services with filters.

The applications module replaces the existing stub entirely. The stub files in app/modules/applications/ must be deleted and rebuilt. The new module's repository handles all application database operations: inserting a new application record, fetching an application by code, fetching applications by client ID, fetching applications by assigned agent ID, fetching applications with no agent (the unassigned queue), and fetching all applications with optional filters for admin use (by service, by status, by date range, by agent). The service layer coordinates the submission flow: validating the submitted data against the service template's form fields and document requirements, generating the unique PRX code, inserting the application record, creating the initial status history entry, creating a system message, and enqueuing a submission confirmation email to the client.

The documents module handles everything related to file storage. It imports python-multipart (which FastAPI already requires for UploadFile to work), aiofiles for async disk I/O, and either filetype or python-magic for MIME detection. The module also imports ARQ's job queue to enqueue quality-checking jobs. The router exposes upload and download endpoints. The service layer implements the upload logic (validate file size, stream to disk, check MIME, create DB record, enqueue QC job) and the download logic (check authorization, stream file from disk with appropriate headers). The QC background job function lives in a jobs.py file inside this module and is registered with the ARQ worker in app/worker.py alongside the email jobs.

The messages module is straightforward. Its repository has two main queries: fetch all non-internal messages for a client-facing view, and fetch all messages for a staff-facing view. The service layer handles creating messages, creating system messages (called internally by other service layers when statuses change), and marking messages as read. The router exposes endpoints for fetching and posting messages, with the returned set determined by the caller's role (the dependency injects the current user, and the service layer applies the appropriate filter based on their role).

The assignments module is minimal but critical for atomicity. Its service layer method for claiming an unassigned application must use a SELECT FOR UPDATE SKIP LOCKED pattern via SQLAlchemy's .with_for_update(skip_locked=True) to ensure that two concurrent agent claims on the same application are safe — one will succeed and the other will get a NotFoundError because the row is now locked or already assigned. The service layer method for admin assignment is simpler (no concurrency concern since admins do this manually). Both methods write to the assignment history table and enqueue notifications.


## Part Ten: Database Schema Design

The following tables must be created via Alembic migrations. They should be added in a single migration file to minimize the number of migration operations, since they all depend on each other via foreign keys and it is cleaner to create them together.

The services table has the following columns: service_id as a String(64) primary key prefixed with "svc_", slug as a unique String(128) not nullable, name as a String(255) not nullable, category as a String(64) not nullable (enum-like, validated at the application layer), short_description as Text, description as Text, color as String(16) (a hex color like "#F5A623"), icon as String(64) (an icon identifier string), status as String(32) not nullable defaulting to "draft" (values: draft, active, paused, unavailable, archived), version as Integer not nullable defaulting to 1, is_featured as Boolean not nullable defaulting to false, created_by as String(64) nullable foreign key referencing users.user_id (set to null if the creating admin user is ever deleted — though that should be prevented by business logic), created_at and updated_at as DateTime with timezone.

The service_steps table has: id as String(64) PK prefixed "sst_", service_id as String(64) not null foreign key to services.service_id with ON DELETE CASCADE (if the service is deleted, its steps go with it — though service deletion should be replaced by archiving), step_number as Integer not null, title as String(255) not null, description as Text nullable, unique constraint on (service_id, step_number). An index on service_id for fast ordered retrieval.

The service_document_requirements table has: id as String(64) PK prefixed "sdr_", service_id foreign key to services with ON DELETE CASCADE, key as String(128) not null (machine-readable, e.g., "national_id"), label as String(255) not null, description as Text nullable, doc_type as String(32) not null (enum: id, certificate, photo, form, proof, other), is_required as Boolean not null defaulting to true, max_size_mb as Integer not null defaulting to 10, allowed_mime_types as JSONB not null (a JSON array of MIME type strings like ["image/jpeg", "image/png"]), sort_order as Integer not null defaulting to 0, unique constraint on (service_id, key). An index on service_id.

The service_form_fields table has: id as String(64) PK prefixed "sff_", service_id foreign key with ON DELETE CASCADE, field_key as String(128) not null, label as String(255) not null, field_type as String(32) not null (enum: text, textarea, select, radio_card, date, switch, checkbox), help_text as Text nullable, is_required as Boolean not null defaulting to true, options as JSONB nullable (used for select and radio_card types — a JSON array of objects each with a "value" string and "label" string), conditional_on_field as String(128) nullable (references another field_key in the same service), conditional_on_value as String(255) nullable (the value the conditional_on_field must have for this field to appear), sort_order as Integer not null defaulting to 0, max_length as Integer nullable, placeholder as String(255) nullable, unique constraint on (service_id, field_key). An index on service_id.

The service_pricing_tiers table has: id as String(64) PK prefixed "spt_", service_id foreign key with ON DELETE CASCADE, tier as String(32) not null (enum: standard, express, urgent), display_name as String(128) not null, description as Text nullable, platform_fee as Integer not null (in smallest currency unit, e.g., Rwandan francs), government_fee as Integer not null defaulting to 0, eta_business_days as Integer not null, features as JSONB not null (a JSON array of feature description strings), is_available as Boolean not null defaulting to true, unique constraint on (service_id, tier). An index on service_id.

The applications table has: application_id as String(64) PK prefixed "app_", code as String(32) unique not null (the human-readable PRX code like "PRX-20260617-A4B9C"), service_id as String(64) foreign key to services (not cascading — if a service is archived the applications still exist), service_slug as String(128) not null (denormalized copy of the service slug at submission time, so the application always knows what service it was for even if the service is later renamed), service_name as String(255) not null (same denormalization reason), tier as String(32) not null (the chosen pricing tier: standard, express, urgent), status as String(32) not null defaulting to "received", client_id as String(64) foreign key to users.user_id not null, assigned_agent_id as String(64) nullable foreign key to users.user_id, assigned_at as DateTime with timezone nullable, personal_info as JSONB not null (stores the step 1 form data: name, national_id, date_of_birth, phone, email, whatsapp_consent, language), service_data as JSONB not null (stores the step 2 dynamic form responses as a key-value map where keys are field_keys), payment_status as String(32) not null defaulting to "pending" (enum: pending, paid, failed, waived), payment_amount as Integer nullable (in smallest currency unit), submission_ip as String(64) nullable, submitted_at as DateTime with timezone not null, completed_at as DateTime with timezone nullable, rejected_at as DateTime with timezone nullable, cancelled_at as DateTime with timezone nullable, rejection_reason as Text nullable, cancellation_reason as Text nullable, created_at and updated_at. Indices on: client_id, assigned_agent_id, status, service_id, code (unique index), submitted_at.

The application_status_history table has: id as String(64) PK prefixed "ash_", application_id as String(64) foreign key to applications with ON DELETE CASCADE, status as String(32) not null, changed_by as String(64) nullable foreign key to users.user_id (nullable because system transitions may not have a human actor), changed_by_role as String(32) nullable (snapshot of the role at time of change: client, staff:agent, staff:admin, system), note as Text nullable, created_at as DateTime with timezone not null. An index on application_id.

The application_assignment_history table has: id as String(64) PK prefixed "aah_", application_id as String(64) foreign key to applications with ON DELETE CASCADE, previous_agent_id as String(64) nullable foreign key to users.user_id (nullable if this is the first assignment), new_agent_id as String(64) nullable foreign key to users.user_id (nullable if the assignment is being cleared), performed_by as String(64) not null foreign key to users.user_id, performed_by_role as String(32) not null, note as Text nullable, created_at as DateTime with timezone not null. An index on application_id.

The application_documents table has: document_id as String(64) PK prefixed "doc_", application_id as String(64) foreign key to applications with ON DELETE CASCADE, requirement_key as String(128) not null (matches a service_document_requirements.key for this application's service), original_filename as String(512) not null, storage_path as String(1024) not null (the relative path within the UPLOAD_DIR), mime_type as String(128) not null, file_size_bytes as Integer not null, uploaded_by as String(64) foreign key to users.user_id not null, uploaded_by_role as String(32) not null, version as Integer not null defaulting to 1, qc_status as String(32) not null defaulting to "pending" (enum: pending, pass, warn, fail), qc_notes as JSONB nullable (a JSON object with check names as keys and result objects as values), is_active as Boolean not null defaulting to true, replaced_by as String(64) nullable foreign key to application_documents.document_id (self-referential), created_at as DateTime with timezone not null. Indices on: application_id, (application_id, requirement_key) where is_active is true (a partial index if PostgreSQL is being used, or just index the two columns).

The application_messages table has: message_id as String(64) PK prefixed "msg_", application_id as String(64) foreign key to applications with ON DELETE CASCADE, sender_id as String(64) nullable foreign key to users.user_id (nullable for system messages), sender_role as String(32) nullable, content as Text not null, is_internal as Boolean not null defaulting to false, is_system as Boolean not null defaulting to false, attachments as JSONB not null defaulting to an empty array (a JSON array of document_id strings), is_read_by_client as Boolean not null defaulting to false, read_by_agent_at as DateTime with timezone nullable, created_at as DateTime with timezone not null. An index on application_id. A partial index on (application_id) where is_read_by_client is false for efficient unread count queries.

The agent_settings table has: user_id as String(64) PK and foreign key to users.user_id with ON DELETE CASCADE, accepting_cases as Boolean not null defaulting to true, daily_case_cap as Integer nullable (null means no cap), notification_new_case as Boolean not null defaulting to true, notification_client_reply as Boolean not null defaulting to true, notification_sla_alert as Boolean not null defaulting to true, notification_daily_summary as Boolean not null defaulting to true, created_at and updated_at. This table is created lazily when an agent first saves their settings or when they are created by the admin.


## Part Eleven: PRX Code Generation

The unique application code (PRX code) that identifies each application to the client must be collision-resistant, human-readable, and non-sequential (so clients cannot guess other application codes). The format is PRX followed by the eight-digit date in YYYYMMDD format followed by a hyphen followed by five uppercase alphanumeric characters chosen from a restricted character set that excludes ambiguous characters (no I, O, 1, 0 which can be confused with each other or with letters). This gives 29 to the 5th power = approximately 20 million unique codes per day, which is vastly more than needed. The generation function produces a candidate, checks the database for a collision (extremely rare but must be handled), and retries if one is found. The maximum number of retries should be bounded (e.g., 10 attempts), after which a generation failure error is raised — in practice this will never be reached.


## Part Twelve: API Surface

All API endpoints follow the existing patterns: they return the ApiResponse envelope, use HTTP status codes correctly (200 for success, 201 for creation, 400 for bad input, 401 for unauthenticated, 403 for forbidden, 404 for not found, 409 for conflict, 422 for validation or business logic rejection), and apply rate limiting where appropriate.

Public endpoints (no authentication required) include: GET /api/services which returns a list of all services with status "active" with their core fields and pricing tiers but not their form fields or document requirements; GET /api/services/{slug} which returns the full detail of a single active service including steps, document requirements, form fields, and pricing tiers (this is what the wizard reads to build step two and step three); and GET /api/track/{code} which returns a limited view of an application's current status, the current step number and name from the service's steps list, and the estimated completion date — no personal info, no documents, no messages are included in this public response.

Client-authenticated endpoints (requires REQUIRE_CLIENT dependency) include: POST /api/applications/submit which accepts the complete five-step form data (personal_info, service_slug, tier, service_data, document keys of already-uploaded documents) and creates the application, returning the new application code and ID; GET /api/applications which returns the list of the authenticated client's applications with summary fields (code, service name, status, tier, submitted date, thumbnail fields); GET /api/applications/{code} which returns full detail of one of the client's own applications including status history, documents list (without storage paths), and message thread (public messages only); POST /api/applications/{code}/documents which accepts a multipart file upload for a specific requirement_key, streams and validates the file, saves to disk, creates the document record, and enqueues the QC job; DELETE /api/applications/{code}/documents/{document_id} which marks a document as replaced (by later replacing, not actually deleted) and allows re-upload only while the application is in received or awaiting_client status; GET /api/documents/{document_id} which streams the document file for download or inline preview, enforcing ownership; POST /api/applications/{code}/messages which posts a new client message to the conversation thread, enqueuing a notification to the assigned agent; PATCH /api/applications/{code}/messages/read which marks all unread agent messages in this conversation as read by the client; and POST /api/applications/{code}/cancel which cancels the application if it is in received or awaiting_client status.

Agent-authenticated endpoints (requires REQUIRE_AGENT) include: GET /api/agent/cases which returns the authenticated agent's list of assigned applications with queue-relevant summary fields including status, SLA state (whether the estimated turnaround time has been exceeded), client name, service name, most recent message preview, and unread message count; GET /api/agent/cases/{code} which returns full case detail including all messages (both public and internal), all documents, full personal info, full service data, and status history; GET /api/agent/cases/unassigned which returns applications in received status with no assigned agent, sorted oldest first, with a count of how many there are; POST /api/agent/cases/unassigned/{code}/claim which atomically assigns the calling agent to the application and transitions it to under_review; PATCH /api/agent/cases/{code}/status which transitions the application to a new status (validated against the status machine), records the status history entry, creates a system message, and enqueues a client notification; POST /api/agent/cases/{code}/documents which allows the agent to upload a document on behalf of the client or upload a document from an authority (e.g., the completed passport) with an agent role marker; PATCH /api/agent/cases/{code}/documents/{document_id}/qc which allows the agent to manually set the QC status of a document (overriding any automated check) and post a note; POST /api/agent/cases/{code}/messages which allows the agent to post either a public message to the client or an internal note, distinguished by an is_internal boolean in the request body; GET /api/agent/settings which returns the authenticated agent's settings; PUT /api/agent/settings which updates the authenticated agent's settings.

Admin-authenticated endpoints (requires REQUIRE_ADMIN) include all of the following: GET /api/admin/services which returns all services regardless of status with full detail; POST /api/admin/services which creates a new service template in draft status, returning the new service ID and slug; GET /api/admin/services/{slug} which returns a single service with full detail for the schema builder view; PATCH /api/admin/services/{slug} which updates core service fields (name, category, description, color, icon, is_featured); POST /api/admin/services/{slug}/steps which replaces the entire ordered list of steps for a service with a new ordered list provided in the request body; POST /api/admin/services/{slug}/document-requirements which replaces the document requirements for a service; POST /api/admin/services/{slug}/form-fields which replaces the form fields for a service; PATCH /api/admin/services/{slug}/pricing/{tier} which updates a single pricing tier; PATCH /api/admin/services/{slug}/status which transitions the service status (draft to active, active to paused, active to archived, etc.); GET /api/admin/applications which returns all applications across all clients and services with rich filtering (by status, service, agent, date range, tier, payment status) and pagination; GET /api/admin/applications/{code} which returns any application's full detail with all related data; PATCH /api/admin/applications/{code}/assign which assigns or reassigns an application to a specific agent by agent ID; PATCH /api/admin/applications/{code}/status which allows the admin to force any status transition regardless of the normal state machine rules; GET /api/admin/analytics which returns aggregate metrics (application counts by status, by service, by week, payment metrics, SLA compliance rate, agent performance summaries).


## Part Thirteen: New Dependencies

The following Python packages must be added to pyproject.toml under the main dependencies section.

python-multipart at the latest stable version is required for FastAPI to handle multipart form data and file uploads. Without this package FastAPI's UploadFile type does not function.

aiofiles at the latest stable version provides async file I/O wrappers compatible with Python's asyncio event loop. Writing files synchronously inside an async FastAPI route handler would block the event loop, degrading performance for all concurrent requests. Aiofiles solves this by wrapping file operations in a thread pool executor transparently.

filetype at the latest stable version provides magic-byte-based file type detection. It requires no system library (unlike python-magic which wraps libmagic) making it simpler to install in Docker containers. It detects over 165 file types reliably from the first 128 bytes of the file.

Pillow at the latest stable version is the Python imaging library, used in the QC background job to open image files, check their dimensions, and perform basic quality analysis. Pillow is a well-maintained fork of PIL with broad image format support.

If S3 storage is desired (either now or in a future iteration), boto3 at the latest stable version provides the AWS SDK for Python, which also works with S3-compatible services like MinIO. For development, MinIO can be added as a service in docker-compose.yml alongside PostgreSQL and Redis. For the initial implementation, local filesystem storage using aiofiles is sufficient and boto3 is optional.

No other new dependencies are required. All other necessary tools (SQLAlchemy async, asyncpg, Alembic, Pydantic, ARQ, structlog, etc.) are already present.


## Part Fourteen: FastAPI Patterns and Best Practices for This Module

Every new module must follow the same layered pattern established by the auth module. Routes only inject dependencies and call service methods. Services orchestrate business logic and call repository methods. Repositories execute database queries and return ORM model instances or None. This separation must not be violated — in particular, no SQL queries should appear in router files and no HTTP-specific logic (status codes, cookie manipulation, response envelopes) should appear in service files.

SQLAlchemy async relationships must be loaded explicitly. Because the project uses async sessions with expire_on_commit set to false, SQLAlchemy will not automatically lazy-load related objects. When a route needs an application along with its documents and messages, the repository method must use selectinload or joinedload options on the query to eagerly load the needed relationships in the same database round-trip. Attempting to access relationship attributes after a session has been closed will raise a MissingGreenlet or greenlet_spawn error in async code. Every repository method that returns an object which the caller will need to access related objects on must explicitly declare which relationships to load.

File upload routes must declare their parameters as Form fields combined with UploadFile rather than as JSON body, because multipart requests cannot be JSON. The application_id or code should be a path parameter, the requirement_key should be a Form field, and the file itself should be the UploadFile parameter. The route handler must receive the file, call the document service, and return the created document metadata. The route must not perform any disk I/O itself — that is the service's responsibility.

For streaming file downloads, FastAPI's StreamingResponse should be used with a generator function that reads the file in chunks using aiofiles. The chunk size should be 64 kilobytes. The Content-Length header should be set from the file size stored in the document record. This combination ensures that large files are delivered without loading them entirely into memory.

Background jobs for QC and notifications must be enqueued using the existing JobQueueManager (app/core/jobs.py) and the enqueue pattern established by the email and SMS jobs. The QC job function must be defined in app/modules/documents/jobs.py and registered in app/worker.py's WorkerSettings functions list alongside the existing send_email_job and send_sms_job. The job receives the document_id as its argument, re-fetches the document from the database using a fresh session (because jobs run in a separate process from the web server), reads the file, performs the quality checks, and updates the document record.

Custom exception types for this module should be added to app/core/exceptions.py following the existing pattern. New exceptions needed include: ServiceNotFoundError (404), ApplicationNotFoundError (404), DocumentNotFoundError (404), ApplicationAccessForbiddenError (403), InvalidStatusTransitionError (422 with a body field listing valid transitions), ServiceSlugConflictError (409), DocumentTypeNotAllowedError (422), FileTooLargeError (413), ApplicationAlreadyAssignedError (409 — for when two agents try to claim simultaneously), and AgentUnavailableError (409 — for when an admin tries to assign to an inactive or unavailable agent).

Rate limiting should be applied to the document upload endpoint (e.g., 20 uploads per minute per client), the application submission endpoint (e.g., 5 submissions per 10 minutes per client), and the message posting endpoint (e.g., 30 messages per minute). The existing rate_limit dependency factory accepts a name, limit, and window_seconds and is composed via Depends() exactly like the auth dependencies.

JSONB columns (service_data in applications, options and features in service tables, qc_notes in documents, attachments in messages) must be mapped using SQLAlchemy's JSON type on the column definition. In Pydantic schemas, these correspond to dict or list fields with appropriate type annotations. Validation of service_data (verifying that required fields from the service template are present and match expected types) should happen in the application submission service method, not in the Pydantic schema, because the validation rules are dynamic (read from the service template at runtime).


## Part Fifteen: Integration with Existing Authentication

The auth dependencies REQUIRE_ADMIN, REQUIRE_AGENT, REQUIRE_AGENT_OR_ADMIN, and REQUIRE_CLIENT from app/modules/auth/dependencies.py can be imported directly and used as-is via FastAPI's Depends() on any new route. These dependencies validate the access token cookie, decode the JWT, check the role, and return the decoded token payload (which contains user_id, role, isEmailVerified, and language) as the injected value. This token payload is everything the route handler needs to pass to the service layer to identify the caller.

On top of role checking, the service layer must enforce ownership and assignment checks. A client route for GET /api/applications/{code} is protected at the route level by REQUIRE_CLIENT (ensuring the caller is authenticated as a client), but the service method must additionally verify that the application's client_id matches the calling user's user_id. Failing this check raises ApplicationAccessForbiddenError (403). Similarly, an agent route for GET /api/agent/cases/{code} is protected by REQUIRE_AGENT at the route level, but the service method must verify that the application's assigned_agent_id matches the calling agent's user_id. Admins bypass these ownership checks by using REQUIRE_ADMIN routes that have their own service methods which do not apply ownership filters.

This two-layer pattern — role check at the route level, ownership check at the service level — is the correct approach. It keeps the router lean and the service self-contained for testing. A service method for fetching an application can be tested with a mock session and a user ID without needing to simulate an HTTP request with cookies.

The existing event bus (app/core/events.py) and the ApplicationClaimRequested event type in the auth module can be used as a reference for how to publish domain events. The application process module may choose to use domain events for cross-module side effects (for example, when an application is submitted, the auth module's signup flow could listen for it to update some registration state), but for the initial implementation direct service calls are simpler and preferable. The ARQ job queue is the correct mechanism for all async side effects (notifications, QC jobs).


## Part Sixteen: Notification Flows

The following events must trigger notification emails dispatched through the ARQ job queue using the existing send_email_job function.

When a client successfully submits an application, they receive an email with the subject "Application Submitted — {service name}" containing the PRX code, a summary of what they applied for, the next steps they should expect, and an estimated timeline based on their chosen tier.

When an admin or agent assigns an application to an agent, the agent receives an email with the subject "New Case Assigned — {PRX code}" containing a link to the case in the agent workspace and basic case summary (service name, client name, tier).

When the application status changes to under_review (which happens on assignment), the client receives an email with the subject "Your application is being reviewed — {PRX code}" informing them an agent is now handling their case.

When the application status changes to awaiting_client, the client receives an email with the subject "Action Required — {PRX code}" telling them their agent needs something and asking them to log in and check their messages.

When the application status changes to completed, the client receives an email with the subject "Your application is complete — {PRX code}" congratulating them and telling them what to expect next (e.g., when to collect their document).

When the application status changes to rejected, the client receives an email with the subject "Application Update — {PRX code}" informing them of the rejection and the reason provided by the agent.

When an agent sends a non-internal message in a case, the client receives an email with the subject "New message from your agent — {PRX code}" containing a preview of the message.

When a client sends a message in an application, the assigned agent receives an email with the subject "Client replied — {PRX code}" containing a preview of the message.

When a document's QC status is set to warn or fail (either by the automated QC job or by the agent manually), the client receives an email explaining that one of their documents needs attention and asking them to log in to replace it.

All these email jobs follow the existing pattern: they enqueue via job_queue.enqueue("send_email_job", to=recipient_email, subject=..., body=...) where body is a plain-text or simple HTML string. Email template rendering can be done with a simple Python f-string or with Jinja2 (which is already indirectly available as a FastAPI dependency) for more structured templates.


## Part Seventeen: Alembic Migration Strategy

The new database tables must be added in a single new Alembic migration file to keep the migration history clean. The existing migrations are: 9ac72f2643fd (initial auth schema) and 2b4c8a1e3f5d (add is_active to users). The new migration should be numbered as the third migration and should be created using `alembic revision --autogenerate -m "add_application_process_schema"` after all SQLAlchemy model classes are defined, or written manually if autogenerate cannot be trusted to produce the correct JSONB column types and partial indexes.

The migration must create tables in dependency order: services first (no foreign key dependencies on new tables), then service_steps, service_document_requirements, service_form_fields, and service_pricing_tiers (all depending on services), then applications (depending on services and users which already exist), then application_status_history and application_assignment_history and agent_settings (depending on applications and users), then application_documents (depending on applications and users, with a self-referential FK for replaced_by that must be added after the table is created or defined as a deferred constraint), and finally application_messages (depending on applications and users).

JSONB columns must be typed explicitly in the migration using sa.JSON() rather than letting autogenerate choose. PostgreSQL will use the native JSONB storage type for JSON columns. Indexes on JSONB columns (e.g., a GIN index on service_data for text search later) can be added in a follow-up migration when needed — do not add them prematurely.

The old stub files in app/modules/applications/ (the fixture-based router.py, schemas.py, and service.py) must be replaced as part of implementing the new module. Because these files are currently wired into the FastAPI router in main.py via an include_router call, the swap must be done atomically — remove the old include_router call and add the new one in the same commit to avoid a period where the stub is gone but the real implementation is not yet wired up.

The admin seed function in app/main.py creates a hardcoded admin user on startup. This must continue to work after the migration — the seed function does not need to change. However, the seed function is a good place to also seed a few example service templates for development and demonstration purposes. These seed services should mirror the ones currently hardcoded in the frontend's services-data.ts file (e.g., passport renewal, company registration, business license, tax returns, social welfare benefit) so that the frontend can immediately query real data once connected to the real API.


## Part Eighteen: End-to-End Verification Checklist

After implementing this module, the following scenarios must work correctly to verify the implementation is complete and correct.

An admin must be able to log in via the staff login flow, then call the create service endpoint to create a new service with steps, document requirements, form fields, and pricing tiers. The service must then appear in the public GET /api/services list. The full detail of the service including all its nested data must be retrievable via GET /api/services/{slug}.

A client must be able to sign up, complete OTP verification, and then call GET /api/services to see available services. The client must be able to call GET /api/services/{slug} to get the service detail including form fields and document requirements. The client must be able to upload documents (POST /api/applications/{code}/documents) — but wait, the code does not exist until submission. Actually the upload endpoint exists at a separate pre-submission path or the wizard uploads documents as part of the submission body. Given the frontend design where documents are uploaded in step three before submission, the correct approach is to have a pre-submission document staging endpoint (POST /api/staging/documents) that accepts a file, stores it temporarily, and returns a staging document ID — or alternatively the client submits the entire wizard in one POST to /api/applications/submit and uploads documents separately after receiving the code. The simpler approach that matches the frontend's current design is for the wizard to submit all form data first to create the application and get the code, then immediately upload documents to the newly created application. The five-step wizard can be adjusted on the frontend to do the submission at step four (review) and show document upload confirmation after receiving the code.

A newly submitted application must appear in the admin's GET /api/admin/applications list. The admin must be able to call PATCH /api/admin/applications/{code}/assign with a valid agent ID and have the application assigned to that agent.

The assigned agent must be able to call GET /api/agent/cases and see the newly assigned application in their queue. The agent must be able to call GET /api/agent/cases/{code} and see the full case detail including the client's personal info, the service data responses, and the uploaded documents list. The agent must be able to call PATCH /api/agent/cases/{code}/status with body {"status": "in_progress", "note": "Starting work on this application"} and have the status update recorded with a history entry and a system message created in the conversation.

The client must be able to call GET /api/applications/{code} and see the updated status, the status history, and the system messages in the conversation thread. The client must not be able to see any internal notes.

A document upload by the client must result in a QC job being enqueued. The QC job must run (with the ARQ worker running) and update the document's qc_status field. If the document is an image, the check must run Pillow operations on it. The agent must be able to see the QC result when viewing the case documents.

The agent must be able to complete the application via PATCH /api/agent/cases/{code}/status with {"status": "completed"} and the client must receive an email notification (verifiable through Mailpit in the development environment, which is the SMTP testing server configured by default in the docker-compose setup). The application must appear in the client's GET /api/applications list with status "completed".

The public tracker must return a limited view of the application's status via GET /api/track/{code} without requiring any authentication, verifiable by calling the endpoint without any cookies and seeing a successful response with the status and step information but no personal data.


## Summary

This document has described every aspect of the application process module that must be built in the ProxiServe FastAPI backend. The module spans five new database modules (services, applications, documents, messages, assignments), nine new database tables plus five service-related sub-tables, roughly forty new API endpoints across public, client, agent, and admin roles, new Python dependencies (python-multipart, aiofiles, filetype, Pillow), a background job for document quality checking, a comprehensive notification email system for all lifecycle events, and a complete status state machine with enforced transitions. All of this must be built following the exact layered patterns (models → repository → service → router) and infrastructure conventions (ApiResponse envelopes, AppError exception hierarchy, ARQ job queue, rate limiting, structlog, REQUIRE_ROLE dependencies) already established in the auth and admin modules.
