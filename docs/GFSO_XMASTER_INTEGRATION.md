# GFSO v3.0: The Unified Architecture

**Version:** 3.5 (Tri-State Execution Strategy)
**Date:** January 2026
**Status:** **Single Source of Truth**

---

## 1. Conceptual Integration

*   **GFSO:** Strategic Control & Topology.
*   **X-Master:** Tactical Power (Swarm Intelligence).
*   **SGR:** Execution Protocol (Structured Reasoning).

---

## 2. The Integrated Topology

This graph illustrates the **Three Execution Strategies**: Direct, Swarm, and Recursive.

```mermaid
graph TD
    %% GLOBAL CONTROL
    subgraph Control_Layer ["Layer 1: Strategic Control"]
        direction TB
        User((User)) --> Head
        
        Head{{The Head / Supervisor}}
        Head -->|Initiates| Architect
        Architect -->|Blueprint DAG| Engine[Execution Engine]
        
        %% Closing the Loop
        Engine -->|All Steps Complete| Head
        Head -->|Final Synthesis| Output([Final Output])
        
        %% Error Handling
        Feedback -.->|Max Retries Exceeded| Head
    end

    %% EXECUTION ROUTING
    subgraph Routing ["Execution Routing"]
        Engine -->|Check Strategy| Strategy{Strategy?}
        
        Strategy -- "RECURSIVE" --> SubArch["Call Architect (Sub-DAG)"]
        SubArch --> Engine
        
        Strategy -- "DIRECT" --> Single[Single Worker]
        
        Strategy -- "SWARM" --> Scatter[X-Master Unit]
    end

    %% TACTICAL SWARM (X-MASTER)
    subgraph XMaster_Engine ["Layer 2: Tactical Swarm (X-Master)"]
        direction TB
        Scatter --> Lanes
        
        subgraph Lanes ["Parallel Lanes (N=3)"]
            direction TB
            W1[Worker 1] --> C1[Critic 1] --> R1
            W2[Worker 2] --> C2[Critic 2] --> R2
            W3[Worker 3] --> C3[Critic 3] --> R3
        end
        
        R1 & R2 & R3 --> Rewriter[Rewriter / Synthesis]
    end

    %% VALIDATION
    subgraph GFSO_Validation ["Layer 3: Topological Validation"]
        direction TB
        Rewriter --> Val1
        Single --> Val1
        
        Val1{"Validator (η)"} -- "Pass" --> Commit[Commit]
        Val1 -- "Fail" --> Feedback[Feedback]
        
        Commit --> Engine
        Feedback -.->|Retry| Engine
    end
```

---

## 3. Critical Logic: The Execution Strategy

The Architect must classify each Node into one of three strategies. We replace the ambiguous `is_complex` flag with `execution_strategy`.

| Strategy | Definition | When to use? |
| :--- | :--- | :--- |
| **`DIRECT`** | **Atomic & Simple** | Mechanical tasks. No ambiguity. (e.g. "Parse JSON", "Sort list") |
| **`SWARM`** | **Atomic & Hard** | Tasks requiring **Search**, **Math**, or **Deep Reasoning** (HLE style). Result is one object, but finding it is hard. |
| **`RECURSIVE`** | **Composite / Large** | Tasks too big for one context. **Planned Lazy Decomposition**. (e.g. "Write Game Engine" -> decomposed into Physics, Rendering, Logic). |

### 3.1. Decision Logic (Architect Prompt)
The Architect prompt must be updated:
> "Analyze the node complexity.
> - If it is a large scope requiring multiple artifacts, use **RECURSIVE**.
> - If it is a specific hard problem (logic/math/code) requiring exploration, use **SWARM**.
> - If it is trivial, use **DIRECT**."

---

## 4. Component Roles

| Component | Role | Mechanism |
| :--- | :--- | :--- |
| **The Head** | **Manager & Finalizer** | Orchestrates the process and **synthesizes the final structured output**. |
| **Architect** | **Strategist** | Generates DAG, Strict Contracts, and selects **Strategy**. |
| **Worker** | **Proposer** | Uses **SGR Schema** (`think` -> `code` -> `verify`) to propose solutions. |
| **Local Critic** | **Fixer** | Checks code validity *before* synthesis. Prevents garbage-in. |
| **Rewriter** | **Synthesizer** | "Wisdom of the Crowd". Combines valid proposals into one. |
| **Validator** | **Judge** | Runs Architect's tests. Binary Pass/Fail. |

---

## 5. Implementation Roadmap

1.  **Tools:** Implement `PythonExecutor` (Sandbox).
2.  **Mechanisms:** 
    *   Update `Architect` schema to output `strategy` (enum).
    *   Update `Worker` (SGR).
    *   Implement `Rewriter` & `LocalCritic`.
3.  **Core:** 
    *   Rewrite `GFSOUnit` (or `Engine`) to handle the 3-way routing.
    *   Implement `asyncio.gather` for Swarm.
4.  **Head:** Implement `Supervisor` with Final Synthesis.
5.  **Test:** Validate on HLE Task #1 (Chess).

---

**This document is the Final Reference.**
