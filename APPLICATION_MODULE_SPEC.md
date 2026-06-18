# ProxiServe — Existing Module Inventory

## Database Tables (migrations through `3f7a9c2e1b4d`)

**Auth:** users, staff_profiles, refresh_tokens, trusted_devices, password_reset_tokens, terms_acceptances, login_attempts, backup_codes

**Services:** services, service_steps, service_document_requirements, service_form_fields, service_pricing_tiers

**Applications:** applications, application_status_history, application_assignment_history

**Documents:** application_documents

**Messages:** application_messages

**Assignments:** agent_settings

## Existing API Endpoints

See `app/main.py` router includes. Modules: auth, services (public + admin), applications (client, agent, admin, tracker, legacy), documents, messages, assignments (agent settings), admin (agents).

## Modules Not Yet Built (closeout)

payments, oversight, audit, broadcasts, platform, agent_service_skills table, analytics rewrite, auto-assignment, client summary, agent metrics.
