# BANANA BOT --- Plan

## Goal

Build a minimal personal automation bot.

The goal is **not** to build something as powerful as OpenClaw or a
general-purpose autonomous agent.

The goal is simple:

> **Give Banana a job and let it get the job done.**

Keep the system minimal and practical.

------------------------------------------------------------------------

## Basic Flow

``` text
Message
(from GUI / Telegram / etc.)
        ↓
    Detector
        ↓
      Prompt
        ↓
 ┌──────┼────────┐
 ↓      ↓        ↓
Given  Context  System
       ↓
    CLI Code (opencode)  <- LLM adapter is opencode, no separate LLM provider
       ↓
     ACTION
```

------------------------------------------------------------------------

## Message

Banana can receive a message from different interfaces, for example:

-   GUI
-   Telegram
-   Other interfaces later

The message is the user's instruction or an event that should trigger
Banana.

------------------------------------------------------------------------

## Detector

The Detector is responsible for triggering Banana.

Possible triggers:

-   User message
-   CRON

The Detector passes the relevant information into the prompt system.

------------------------------------------------------------------------

## Prompt

The Prompt is built from three main parts.

### Given

The actual instruction/data given by the user or trigger.

### Context

Relevant Banana context, including:

-   Files
-   Commands
-   `SKILL.md`
-   `Agent.md`
-   `Prompt.md`
-   Other relevant context when needed

### System

The system-level instructions and configuration, including:

-   `SOUL.md`
-   `AGENT.md`
-   `USER.md`
-   `ENTRY.md`
-   `SKILL.md`

The Prompt combines these parts and sends them to the CLI Code layer (opencode) — opencode IS the LLM adapter. No separate LLM provider.

------------------------------------------------------------------------

## CLI Code

Banana uses CLI coding/agent tools as its LLM adapter. No separate LLM provider.

For now: **opencode only**. Claude Code / Codex / others are future options, not MVP.

The purpose is to make Banana cheap and easy to use rather than
implementing everything itself.

The CLI/code layer (opencode) is responsible for turning the Prompt into
actual work and driving the ACTION.

------------------------------------------------------------------------

## ACTION

The Action layer performs the actual task.

Tasks can involve:

-   Python
-   Node.js
-   Bash
-   Other command-line tools

The focus is on getting the actual job done rather than making Banana
unnecessarily complex.

------------------------------------------------------------------------

# `/instances`

Instances are used for recent tasks and repetitive work.

## Temporary Instances

Temporary instances are refreshed/removed after a limited period.

Initial idea:

> Temporary instances refresh after **72 hours**.

A temporary instance may contain:

-   Current context
-   Current tasks
-   Relevant state needed to continue recent work

Before refreshing/removing an instance, Banana should check whether
there is a reason to keep its information.

Example structure:

``` text
/instances/temp/
    - TASKS
```

------------------------------------------------------------------------

## Permanent Instances

Permanent instances remain until explicitly deleted.

They can contain persistent tasks/context that Banana should keep using.

Example:

``` text
/instances/permanent/
    - TASKS
```

------------------------------------------------------------------------

# `/tasks`

Tasks are the actual jobs Banana can perform.

The main implementation can use:

-   Python
-   Node.js
-   Bash
-   Other scripts/tools when necessary

The task system should stay simple.

Examples of tasks:

``` text
/tasks
    task-1
    task-2
    task-3
```

An instance can reference or use tasks when performing work.

------------------------------------------------------------------------

# Initial Architecture

The first version should stay focused on this:

``` text
Message / CRON
      ↓
  Detector
      ↓
    Prompt
      ↓
 CLI Code (opencode)  <- opencode IS the LLM adapter
      ↓
    ACTION
      ↓
   /TASKS
      ↑
 /INSTANCES
```

------------------------------------------------------------------------

# Principles

1.  **Minimalism**
    -   Build only what is needed.
2.  **Job first**
    -   Banana exists to get work done.
3.  **Use existing tools**
    -   Don't reinvent CLI coding/automation tools unnecessarily.
4.  **Keep state simple**
    -   Use instances for temporary and permanent context.
5.  **Keep tasks executable**
    -   Python, Node.js, Bash, and similar tools should do the actual
        work.
6.  **Don't build OpenClaw**
    -   Banana does not need to become a giant autonomous-agent
        framework.

------------------------------------------------------------------------

# Deployment

Whole thing will run INSIDE docker container.

------------------------------------------------------------------------

# MVP

The first working Banana should be able to:

-   Receive a message.
-   Receive a CRON trigger.
-   Detect/trigger a task.
-   Build a prompt from the given input, context, and system files.
-   Use opencode CLI as LLM adapter (no separate LLM provider).
-   Execute tasks via opencode.
-   Store relevant task state in instances.
-   Maintain temporary and permanent instances.
-   Return the result of the action.

Anything beyond this can wait until it is actually needed.
