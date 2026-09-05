# UMI — Technical Requirements Document (TRD)

**Project:** UMI
**Document:** Technical Requirements Document
**Version:** 1.0
**Status:** Draft for Architecture Review

---

# 1. Technical Overview

UMI will be implemented as a modular AI application consisting of:

* Next.js frontend
* Python backend
* Supabase/PostgreSQL database
* LLM reasoning layer
* Tool execution framework
* Memory system
* Authentication/authorization
* External integrations
* Voice subsystem
* Future vision subsystem
* Future physical interface

The architecture must separate:

> **Reasoning from execution.**

The LLM should not directly control infrastructure or sensitive systems.

---

# 2. Intended Technology Stack

| Layer        | Technology                           |
| ------------ | ------------------------------------ |
| Frontend     | Next.js                              |
| Backend      | Python                               |
| Database     | Supabase / PostgreSQL                |
| LLM          | NVIDIA Nemotron 3 Ultra              |
| Coding Agent | Claude Code                          |
| API style    | REST initially                       |
| Architecture | Modular service-oriented application |

The exact Python framework should be selected during Phase 0 based on current requirements.

---

# 3. Frontend Requirements

The frontend should provide:

* Chat interface
* Conversation history
* Authentication interface
* Task interface
* Memory interface
* Settings
* Integration status
* Tool execution status
* Future voice interface
* Future UMI visualizer
* Future gesture interface

The frontend should not contain core AI orchestration logic.

---

# 4. Backend Requirements

The backend is responsible for:

* Authentication
* Authorization
* API endpoints
* Conversation management
* Orchestration
* LLM communication
* Memory management
* Tool execution
* Permission enforcement
* External integrations
* Tasks
* Scheduling
* Logging
* Error handling

---

# 5. Core Backend Components

Recommended logical modules:

```text
backend/
│
├── api/
├── core/
├── auth/
├── orchestrator/
├── llm/
├── memory/
├── context/
├── tools/
├── integrations/
├── database/
├── permissions/
├── tasks/
├── voice/
├── vision/
├── logging/
└── tests/
```

This is a logical starting point, not an immutable requirement.

---

# 6. Request Processing Requirements

Every request should conceptually follow:

```text
Input
 ↓
Authentication
 ↓
Request Validation
 ↓
Orchestrator
 ↓
Context Retrieval
 ↓
Memory Retrieval
 ↓
LLM
 ↓
Tool Decision
 ↓
Permission Check
 ↓
Tool Execution
 ↓
Tool Result
 ↓
LLM Response Generation
 ↓
Persistence
 ↓
Output
```

Not every request requires tool execution.

---

# 7. Orchestrator

The orchestrator is the central coordination layer.

Responsibilities:

* Receive normalized user requests
* Retrieve context
* Retrieve relevant memory
* Invoke LLM
* Interpret structured model output
* Determine whether tools are needed
* Request permission when necessary
* Execute tools through the tool manager
* Feed results back to the LLM
* Generate final response
* Persist appropriate state

The orchestrator must NOT contain every tool implementation.

---

# 8. LLM Layer

The LLM manager should abstract communication with the model provider.

Responsibilities:

* Model requests
* System instructions
* Context construction
* Structured outputs
* Tool-call interpretation
* Error handling
* Retry behavior where appropriate
* Token/usage tracking

The rest of the backend should not depend directly on provider-specific implementation details wherever practical.

---

# 9. Tool Architecture

Tools should follow a consistent contract.

Conceptually:

```text
Tool
├── name
├── description
├── input schema
├── permission requirements
├── execute()
├── validation
├── error handling
└── audit information
```

Potential tools:

```text
WebSearchTool
GmailTool
CalendarTool
TaskTool
ReminderTool
FileTool
WeatherTool
ComputerTool
NotificationTool
```

Future:

```text
VisionTool
GestureTool
IoTTool
RobotTool
```

---

# 10. Tool Execution

The LLM should request a tool.

The backend should:

1. Validate the request.
2. Validate tool arguments.
3. Check permissions.
4. Determine whether confirmation is required.
5. Execute the tool.
6. Validate the tool result.
7. Log the operation.
8. Return the result to the orchestrator.

---

# 11. Permission System

Permission levels should distinguish:

### Read

Low-risk information retrieval.

### Write

Non-destructive modifications.

### Sensitive

Actions involving private or externally visible information.

### Destructive

Potentially irreversible actions.

Examples:

```text
Read email             → Read
Create task            → Write
Draft email            → Write
Send email             → Sensitive
Delete email           → Sensitive/Destructive
Delete files           → Destructive
Execute shell command  → Highly Sensitive
```

Exact classifications should be defined per tool.

---

# 12. Confirmation System

Sensitive actions should support a confirmation flow.

Example:

```text
User
 ↓
UMI
 ↓
Tool request
 ↓
Permission check
 ↓
Confirmation required
 ↓
UMI asks user
 ↓
User confirms
 ↓
Tool executes
```

Confirmation should be explicit.

Do not rely on vague conversational statements for destructive actions.

---

# 13. Memory Architecture

Memory should be divided logically into:

```text
Conversation Memory
Long-Term Memory
User Preferences
Task/Project Memory
Document Knowledge
```

Memory operations:

```text
Create
Retrieve
Update
Delete
```

Memory should be selectively retrieved.

Do not send the entire database to the LLM.

---

# 14. Context Manager

The context manager should determine relevant information for the current request.

Potential context sources:

* Current conversation
* Recent conversation
* Relevant memories
* User preferences
* Current tasks
* Current project
* Tool results
* Retrieved documents

The context manager should prioritize relevance.

---

# 15. Database Requirements

Supabase/PostgreSQL should initially contain entities such as:

```text
users
conversations
messages
memories
preferences
tasks
reminders
projects
integrations
audit_logs
```

Exact schema must be finalized during architecture review.

---

# 16. API Requirements

Initial API may include:

```text
GET    /health

POST   /chat

GET    /conversations
GET    /conversations/{id}

GET    /tasks
POST   /tasks
PATCH  /tasks/{id}
DELETE /tasks/{id}

GET    /memories
POST   /memories
DELETE /memories/{id}

GET    /integrations
```

Additional endpoints should be added only when necessary.

Every endpoint must define:

* Authentication
* Authorization
* Request schema
* Response schema
* Validation
* Errors
* Rate limits where appropriate

---

# 17. Authentication

The system should authenticate users before accessing protected resources.

Authentication architecture should be compatible with the selected Supabase/auth strategy.

Credentials must never be hard-coded.

---

# 18. External Integrations

External services should be isolated behind integration modules.

Example:

```text
integrations/
├── gmail/
├── calendar/
├── weather/
└── web/
```

The tool layer calls the integration layer.

This separates:

**What UMI wants to do**

from:

**How an external API performs it.**

---

# 19. Gmail Architecture

Conceptual:

```text
UMI
 ↓
Gmail Tool
 ↓
Gmail Integration
 ↓
OAuth
 ↓
Google Gmail API
 ↓
Result
```

User manually handles:

* Google Cloud configuration
* API enablement
* OAuth configuration
* Consent
* Credentials

Code handles:

* OAuth flow
* Token handling
* API requests
* Parsing
* Error handling

---

# 20. Calendar Architecture

Similar structure:

```text
UMI
 ↓
Calendar Tool
 ↓
Calendar Integration
 ↓
OAuth
 ↓
Google Calendar API
```

---

# 21. Voice Architecture

Future architecture:

```text
Microphone
 ↓
Voice Activity Detection
 ↓
Speech-to-Text
 ↓
UMI Backend
 ↓
Orchestrator
 ↓
LLM
 ↓
Response
 ↓
Text-to-Speech
 ↓
Speaker
```

Voice provider should remain replaceable.

---

# 22. Physical Display

The physical display should act as an interface rather than the main intelligence.

```text
Display
 ↓
Frontend / Interface
 ↓
Backend
 ↓
UMI Core
```

The backend remains the source of intelligence.

---

# 23. Vision

Future vision subsystem:

```text
Camera
 ↓
Vision Processing
 ↓
Visual Context
 ↓
UMI Orchestrator
 ↓
LLM
```

Vision should be modular and replaceable.

---

# 24. Gesture

Future:

```text
Camera
 ↓
Gesture Detection
 ↓
Gesture Event
 ↓
Frontend / UMI Backend
 ↓
Action
```

Gesture recognition should not directly perform privileged backend actions.

---

# 25. Error Handling

Each subsystem must fail independently where possible.

Example:

If Gmail is unavailable:

UMI should say:

> "I can't access Gmail right now."

It should not crash the entire assistant.

Errors should be:

* Logged
* Categorized
* Traceable
* Safe for users

---

# 26. Observability

Implement:

* Structured logs
* Request IDs
* Tool execution logs
* Error logs
* Latency measurements
* LLM usage metrics
* External API failure metrics

Sensitive data must not be unnecessarily logged.

---

# 27. Testing

Testing layers:

### Unit tests

Individual functions/modules.

### Integration tests

Backend + database + integrations.

### Tool tests

Tool input/output behavior.

### API tests

Endpoint behavior.

### End-to-end tests

User → frontend → backend → LLM/tool → response.

### Security tests

Permission boundaries and malicious inputs.

---

# 28. Security Requirements

Must include:

* Secret management
* OAuth security
* Authentication
* Authorization
* Input validation
* Tool argument validation
* Rate limiting
* Prompt injection defenses
* Least privilege
* Confirmation workflows
* Audit logs

---

# 29. Deployment Requirements

Deployment architecture should be simple initially.

Potential:

```text
User
 ↓
Next.js deployment
 ↓
Python backend
 ↓
Supabase
 ↓
LLM provider
 ↓
External integrations
```

Specific hosting provider should be selected after evaluating requirements.

---

# 30. Scalability

Initial system can optimize for a single user.

However:

* Modules should be stateless where possible.
* Database access should be structured.
* Long-running operations should eventually be asynchronous.
* Tool execution should be isolated.
* External integrations should be replaceable.

Do not prematurely introduce microservices.

---

# 31. Technical Principles

1. Modular architecture
2. Separation of concerns
3. Least privilege
4. Secure secrets
5. Explicit permissions
6. Human confirmation
7. Provider abstraction
8. Observable execution
9. Testability
10. Extensibility
11. Simplicity
12. Maintainability

---

# 32. Technical Decisions Requiring Review

Before implementation, review:

* Python framework
* Authentication implementation
* LLM API interface
* Database schema
* Memory retrieval mechanism
* Tool interface
* Permission model
* Hosting
* Voice provider
* Background task system

These decisions should not be finalized blindly.
