# UMI — Product Requirements Document (PRD)

**Project:** UMI
**Document:** Product Requirements Document
**Version:** 1.0
**Status:** Draft for Architecture Review
**Primary Goal:** Define what UMI is, who it is for, what it should do, and how it should evolve.

---

# 1. Executive Summary

UMI is a personal AI assistant designed to evolve from a conversational software assistant into a multimodal intelligent system capable of interacting with digital and eventually physical environments.

UMI is inspired by the concept of advanced fictional AI assistants, but it is an original engineering project.

UMI should not simply answer questions like a conventional chatbot.

Instead, UMI should be capable of:

* Natural conversation
* Context understanding
* Memory
* Tool usage
* Email management
* Calendar interaction
* Task management
* Web research
* File interaction
* Voice interaction
* Proactive notifications
* Computer interaction
* Computer vision
* Gesture interaction
* Physical display interaction
* Future IoT and robotics interaction

The fundamental product philosophy is:

> **The LLM is UMI's reasoning engine, not UMI itself.**

UMI consists of multiple coordinated systems:

* User interfaces
* Backend
* Orchestrator
* LLM
* Memory
* Tools
* Permissions
* External integrations
* Voice
* Vision
* Future hardware

---

# 2. Product Vision

## Vision Statement

Build a personal AI system that can naturally communicate with the user, understand context, remember useful information, perform actions through controlled tools, proactively assist the user, and eventually interact with the physical world.

Long-term:

> **UMI should become a multimodal personal AI capable of perceiving, reasoning, remembering, communicating, and acting.**

---

# 3. Product Philosophy

UMI should follow these principles:

1. Natural interaction
2. Useful intelligence rather than artificial complexity
3. User control
4. Privacy
5. Security
6. Transparency
7. Modularity
8. Extensibility
9. Human confirmation for sensitive actions
10. Progressive development

UMI should not pretend to be human.

UMI should clearly operate as an AI system while providing a natural conversational experience.

---

# 4. Target User

Initial target user:

> A single personal user who wants an intelligent assistant capable of managing information, tasks, communication, and digital workflows.

The first version is intentionally optimized for a single-user environment.

Future versions may support additional users if required.

---

# 5. Problem Statement

Current AI chat interfaces often require users to:

* Open an application
* Ask questions manually
* Copy information between applications
* Manage separate productivity tools
* Repeatedly provide context
* Manually execute actions after receiving AI suggestions

UMI aims to reduce this friction.

Instead of:

> Ask AI → Receive answer → Manually execute action

UMI should eventually support:

> Communicate naturally → UMI understands → UMI reasons → UMI uses appropriate tools → UMI completes or proposes the action.

---

# 6. Product Goals

## Primary Goals

UMI should:

* Provide natural conversational interaction.
* Maintain useful conversational context.
* Store and retrieve appropriate long-term memories.
* Execute controlled tools.
* Integrate with external services.
* Manage tasks and reminders.
* Read and summarize emails.
* Understand calendar information.
* Provide proactive assistance.
* Support voice interaction.
* Provide a visual interface.
* Eventually support vision and gestures.

---

# 7. Non-Goals

The following are NOT initial goals:

* Building AGI
* Creating a human-equivalent intelligence
* Autonomous unrestricted computer control
* Autonomous financial activity
* Fully autonomous physical robotics
* Building every feature simultaneously
* Creating a complicated multi-agent architecture without necessity

UMI should remain practical.

---

# 8. Core User Experience

The user should eventually be able to say:

> "UMI, what do I have today?"

UMI should retrieve appropriate calendar/task information and respond naturally.

Example:

> "You have two important tasks today and a Physics test at 10 AM."

The user may continue:

> "How prepared am I?"

UMI should understand the context.

---

# 9. Core Capabilities

## 9.1 Conversation

UMI should:

* Understand natural language.
* Maintain conversation context.
* Handle follow-up questions.
* Ask clarification when necessary.
* Provide concise or detailed answers based on context.

---

## 9.2 Memory

UMI should support:

* Conversation history
* Long-term memory
* User preferences
* Task/project memory
* Document knowledge

Memory must be selective.

UMI should not automatically permanently store every conversation.

---

## 9.3 Tools

UMI should eventually support:

* Web search
* Gmail
* Google Calendar
* Tasks
* Reminders
* Files
* Weather
* Computer control
* Notifications
* Vision
* Gesture
* IoT
* Robotics

---

## 9.4 Productivity

UMI should eventually:

* Create tasks
* List tasks
* Update tasks
* Complete tasks
* Create reminders
* Read calendar events
* Summarize schedules

---

## 9.5 Gmail

UMI should eventually:

* Read emails
* Search emails
* Summarize emails
* Identify important emails
* Draft responses
* Send emails with confirmation

---

## 9.6 Calendar

UMI should eventually:

* Read events
* Summarize schedules
* Create events
* Modify events
* Delete events with confirmation

---

## 9.7 Voice

UMI should eventually support:

* Speech input
* Natural voice output
* Streaming
* Interruption
* Voice activity detection
* Optional wake-word interaction

---

## 9.8 Physical Display

UMI should eventually have a physical visual interface.

Possible information:

* Conversation state
* UMI visualizer
* Tasks
* Calendar
* Notifications
* System state
* Tool execution state
* Listening state
* Thinking state

---

## 9.9 Vision

Future UMI should support:

* Object recognition
* Visual question answering
* Screen understanding
* Document understanding
* Environment awareness

---

## 9.10 Gesture Interaction

Future UMI should support:

* Pointing
* Swiping
* Pinching
* Selection
* Cursor interaction

---

# 10. Proactive Assistance

UMI should eventually be capable of proactive assistance.

Examples:

> "Good morning. You have three important tasks today."

> "You have an important email that may require your attention."

> "You have a test tomorrow and your planned revision is incomplete."

Proactive behavior must not become spammy.

The user should be able to configure notification behavior.

---

# 11. User Stories

### Conversation

* As a user, I want to talk naturally with UMI.
* As a user, I want UMI to understand follow-up questions.
* As a user, I want UMI to remember relevant context.

### Memory

* As a user, I want UMI to remember useful information.
* As a user, I want to see stored memories.
* As a user, I want to delete memories.

### Email

* As a user, I want UMI to summarize important emails.
* As a user, I want UMI to search my emails.
* As a user, I want UMI to draft emails.
* As a user, I want confirmation before UMI sends an email.

### Calendar

* As a user, I want UMI to tell me my schedule.
* As a user, I want UMI to create calendar events.
* As a user, I want confirmation before destructive calendar actions.

### Tasks

* As a user, I want to create tasks naturally.
* As a user, I want UMI to remind me about tasks.

---

# 12. Functional Requirements

## FR-001 Conversation

UMI must accept user input and produce an appropriate response.

## FR-002 Context

UMI must maintain relevant conversation context.

## FR-003 Memory

UMI must support persistent memory.

## FR-004 Tools

UMI must support controlled tool execution.

## FR-005 Permissions

UMI must enforce tool permissions.

## FR-006 Authentication

Protected functionality must require authentication.

## FR-007 Logging

Important system operations must be logged.

## FR-008 Error Handling

Failures must produce safe and understandable responses.

## FR-009 Confirmation

Sensitive operations must support explicit user confirmation.

---

# 13. Non-Functional Requirements

## Security

The system must:

* Protect credentials.
* Use secure authentication.
* Apply least privilege.
* Validate inputs.
* Protect against prompt injection.
* Log sensitive actions appropriately.

## Performance

The system should minimize unnecessary latency.

## Reliability

A failure in one tool should not crash the entire system.

## Maintainability

Components should be modular.

## Extensibility

New tools should be addable without rewriting the core system.

## Observability

Important operations should be traceable.

---

# 14. MVP

The initial MVP should be intentionally small.

Recommended MVP:

* Next.js frontend
* Python backend
* Basic authentication
* LLM integration
* Conversation interface
* Conversation persistence
* Basic logging
* Error handling
* Basic architecture for future tools

Do NOT include:

* Robotics
* Gesture recognition
* Advanced computer vision
* Complex proactive automation
* Full computer control

in the initial MVP.

---

# 15. Future Roadmap

### UMI V0.1

Core conversation

### UMI V0.2

Memory

### UMI V0.3

Tool framework

### UMI V0.4

Tasks/productivity

### UMI V0.5

Gmail + Calendar

### UMI V0.6

Voice

### UMI V0.7

Physical display

### UMI V0.8

Vision

### UMI V0.9

Gesture

### UMI V1.0

Multimodal UMI

### Future

IoT
Robotics
AR/HUD
Advanced physical systems

---

# 16. Success Criteria

UMI should be considered successful when:

* Conversations feel natural.
* Context is maintained correctly.
* Memory is useful and controllable.
* Tools execute reliably.
* Sensitive operations require appropriate confirmation.
* The system is easy to extend.
* Failures are observable.
* The user understands what UMI is doing.

---

# 17. Product Principles

UMI should prioritize:

**Reliability > complexity**

**Security > convenience**

**Understandability > abstraction**

**User control > autonomy**

**Useful features > feature count**

**Modularity > monolithic implementation**

---

# 18. Open Product Questions

These should be resolved during architecture/design:

* Exact voice provider
* Exact authentication model
* Exact hosting platform
* Exact model/API configuration
* Memory retrieval strategy
* Proactive notification strategy
* Physical display hardware
* Vision model
* Gesture technology
* Future computer-control boundaries

---

# 19. Final Product Definition

UMI is not simply an LLM interface.

UMI is a software system whose architecture combines:

**Reasoning + Memory + Tools + Permissions + Interfaces + External Services + Future Sensors + Future Actuators.**

The LLM provides reasoning.

The backend controls execution.

The tools provide capabilities.

The interfaces provide interaction.

Future hardware provides physical interaction.

This separation should remain fundamental throughout development.
