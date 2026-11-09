# BCSS Swimming Optimizer - How It Works

## Overview

This optimizer finds the **mathematically optimal** lineup for BCSS Swimming Provincials using constraint programming (OR-Tools CP-SAT solver). It guarantees the highest possible expected points given your roster and benchmark data.

---

## High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              MAIN PIPELINE                                   │
└─────────────────────────────────────────────────────────────────────────────┘

     ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
     │   INPUT      │      │   PROCESS    │      │   OUTPUT     │
     │   FILES      │ ──▶  │   (Solver)   │ ──▶  │   LINEUP     │
     └──────────────┘      └──────────────┘      └──────────────┘
           │                      │                     │
           ▼                      ▼                     ▼
     ┌──────────┐          ┌──────────────┐      ┌──────────────┐
     │Roster.csv│          │ Optimization │      │optimal_lineup│
     │2025.csv  │          │   Model      │      │    .txt      │
     └──────────┘          └──────────────┘      └──────────────┘
```

---

## Detailed Component Breakdown

### 1. DATA LOADING (`main.py` + `solver.py`)

```
┌─────────────────────────────────────────────────────────────────┐
│                    DATA LOADING PHASE                            │
└─────────────────────────────────────────────────────────────────┘

                    ┌─────────────────┐
                    │   Roster.csv    │
                    │                 │
                    │ • swimmer_id    │
                    │ • name          │
                    │ • gender        │
                    │ • category      │
                    │ • max_events    │
                    │ • times (50_Free│
                    │   100_Free, etc)│
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  load_roster()  │
                    │                 │
                    │ Creates Swimmer │
                    │ objects with    │
                    │ all their times │
                    └────────┬────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │     List[Swimmer]            │
              │                              │
              │  Each swimmer has:           │
              │  - ID, name, gender, category│
              │  - max_events (usually 4)    │
              │  - times dict {event: time}  │
              └──────────────────────────────┘


                    ┌─────────────────┐
                    │   2025.csv      │
                    │  (Benchmark)    │
                    │                 │
                    │ • event         │
                    │ • gender        │
                    │ • category      │
                    │ • place_1 time  │
                    │ • place_2 time  │
                    │ • ...           │
                    │ • place_16 time │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │load_benchmark() │
                    │                 │
                    │ Loads historical│
                    │ times for each  │
                    │ place (1-16)    │
                    └────────┬────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │     DataFrame                │
              │                              │
              │  For each event/gender/cat:  │
              │  - Time needed for 1st place │
              │  - Time needed for 2nd place │
              │  - ... up to 16th place      │
              └──────────────────────────────┘
```

---

### 2. EXPECTED POINTS CALCULATION (`solver.py`)

```
┌─────────────────────────────────────────────────────────────────┐
│                 POINTS CALCULATION PHASE                         │
└─────────────────────────────────────────────────────────────────┘

For each swimmer + event combination:

    ┌─────────────────┐
    │ Swimmer's Time  │
    │   (e.g. 25.5s)  │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────────────────────────────┐
    │     Compare to Benchmark Times          │
    │                                         │
    │  Benchmark for Boys B 50 Free:          │
    │  ┌─────────────────────────────────┐    │
    │  │ Place │ Time   │ Points         │    │
    │  │   1   │ 24.0s  │  20 pts        │    │
    │  │   2   │ 24.5s  │  17 pts        │    │
    │  │   3   │ 25.0s  │  16 pts        │    │
    │  │   4   │ 25.5s  │  15 pts  ◀──── │    │
    │  │  ...  │  ...   │  ...           │    │
    │  │  16   │ 30.0s  │   1 pt         │    │
    │  │  17+  │ >30.0s │   0 pts        │    │
    │  └─────────────────────────────────┘    │
    └────────────────────┬────────────────────┘
                         │
                         ▼
    ┌─────────────────────────────────────────┐
    │     Linear Interpolation                │
    │                                         │
    │  If swimmer time falls BETWEEN places:  │
    │                                         │
    │  Time = 25.25s (between 3rd & 4th)      │
    │  Points = 16 + (16-15) × fraction       │
    │         = 15.5 pts                      │
    │                                         │
    └────────────────────┬────────────────────┘
                         │
                         ▼
    ┌─────────────────────────────────────────┐
    │  Store: (swimmer_id, event) → points    │
    │                                         │
    │  Example:                               │
    │  ("BA01", Boys_B_50_Free) → 15.5 pts    │
    │  ("BA02", Boys_B_50_Free) → 18.2 pts    │
    │  ("BA01", Boys_B_100_Free) → 12.0 pts   │
    │  ...                                    │
    └─────────────────────────────────────────┘
```

---

### 3. RELAY TEAM ENUMERATION (`solver.py`)

```
┌─────────────────────────────────────────────────────────────────┐
│                 RELAY TEAM GENERATION                            │
└─────────────────────────────────────────────────────────────────┘

For each relay event (200 Free Relay, 200 Medley Relay, 400 Free Relay):

    ┌─────────────────────────────────────────┐
    │  Get all eligible swimmers              │
    │  (same gender + category)               │
    │                                         │
    │  Example: Boys B has 8 swimmers         │
    └────────────────────┬────────────────────┘
                         │
                         ▼
    ┌─────────────────────────────────────────┐
    │  Generate ALL possible 4-person combos  │
    │                                         │
    │  C(8,4) = 70 combinations               │
    │                                         │
    │  Team 1: [S1, S2, S3, S4]               │
    │  Team 2: [S1, S2, S3, S5]               │
    │  Team 3: [S1, S2, S3, S6]               │
    │  ...                                    │
    └────────────────────┬────────────────────┘
                         │
                         ▼
    ┌─────────────────────────────────────────┐
    │  For MEDLEY relays: try all orders      │
    │                                         │
    │  Order matters! (Back→Breast→Fly→Free)  │
    │  Find best swimmer assignment:          │
    │                                         │
    │  [S1-Back, S2-Breast, S3-Fly, S4-Free]  │
    │  vs                                     │
    │  [S2-Back, S1-Breast, S3-Fly, S4-Free]  │
    │  vs ... (24 permutations per combo)     │
    │                                         │
    │  Keep only the FASTEST arrangement      │
    └────────────────────┬────────────────────┘
                         │
                         ▼
    ┌─────────────────────────────────────────┐
    │  Calculate expected points for team     │
    │                                         │
    │  Sum individual split times → team time │
    │  Compare to relay benchmark             │
    │  Interpolate to get expected points     │
    │                                         │
    │  Note: Relay points are DOUBLED!        │
    └────────────────────┬────────────────────┘
                         │
                         ▼
    ┌─────────────────────────────────────────┐
    │  Store all viable relay teams           │
    │                                         │
    │  (event, team_idx) → RelayTeam object   │
    │  - swimmer_ids: (S1, S2, S3, S4)        │
    │  - expected_points: 38.5                │
    │  - proxy_time: 102.3s                   │
    └─────────────────────────────────────────┘
```

---

### 4. OPTIMIZATION MODEL (`solver.py`)

```
┌─────────────────────────────────────────────────────────────────┐
│              CONSTRAINT PROGRAMMING MODEL                        │
└─────────────────────────────────────────────────────────────────┘

                    DECISION VARIABLES
    ┌─────────────────────────────────────────┐
    │                                         │
    │  x[swimmer, event] ∈ {0, 1}             │
    │  "Does this swimmer swim this event?"   │
    │                                         │
    │  y[event, team_idx] ∈ {0, 1}            │
    │  "Is this relay team selected?"         │
    │                                         │
    │  z[swimmer, event, team] ∈ {0, 1}       │
    │  "Is swimmer on selected relay team?"   │
    │  (linking variable)                     │
    │                                         │
    └─────────────────────────────────────────┘

                      CONSTRAINTS
    ┌─────────────────────────────────────────┐
    │                                         │
    │  1. MAX EVENTS PER SWIMMER              │
    │     ─────────────────────────           │
    │     For each swimmer:                   │
    │     Σ(individual events) +              │
    │     Σ(relay participations) ≤ 4         │
    │                                         │
    │     Example: Eric can do at most        │
    │     4 total events (ind + relay)        │
    │                                         │
    │  2. MAX RELAY TEAMS PER EVENT           │
    │     ─────────────────────────           │
    │     For each relay event:               │
    │     Σ(selected teams) ≤ 2               │
    │                                         │
    │  3. MUST ENTER ALL RELAYS               │
    │     ─────────────────────────           │
    │     For each relay event:               │
    │     Σ(selected teams) ≥ 1               │
    │                                         │
    │  4. SWIMMER ON ONE TEAM PER RELAY       │
    │     ─────────────────────────           │
    │     A swimmer can only be on ONE        │
    │     team per relay event                │
    │                                         │
    │  5. LINKING CONSTRAINTS                 │
    │     ─────────────────────────           │
    │     z[s,e,t] = y[e,t] if s is on team t │
    │     (swimmer participates iff team      │
    │      is selected)                       │
    │                                         │
    └─────────────────────────────────────────┘

                      OBJECTIVE
    ┌─────────────────────────────────────────┐
    │                                         │
    │  MAXIMIZE:                              │
    │                                         │
    │  Σ points[s,e] × x[s,e]                 │
    │    (individual event points)            │
    │                                         │
    │  + Σ points[e,t] × y[e,t]               │
    │    (relay team points - already 2x)     │
    │                                         │
    └─────────────────────────────────────────┘
```

---

### 5. SOLVING PROCESS

```
┌─────────────────────────────────────────────────────────────────┐
│                    SOLVING PHASE                                 │
└─────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────┐
    │         OR-Tools CP-SAT Solver          │
    │                                         │
    │  Uses advanced techniques:              │
    │  • Branch and bound                     │
    │  • Constraint propagation               │
    │  • Conflict-driven clause learning      │
    │  • Parallel search (8 workers)          │
    │                                         │
    └────────────────────┬────────────────────┘
                         │
                         ▼
    ┌─────────────────────────────────────────┐
    │         Search Tree Exploration         │
    │                                         │
    │              [Root]                     │
    │             /      \                    │
    │      x[S1,E1]=1  x[S1,E1]=0             │
    │         /  \        /  \                │
    │       ...  ...    ...  ...              │
    │                                         │
    │  Explores millions of possibilities     │
    │  Prunes branches that can't be optimal  │
    │                                         │
    └────────────────────┬────────────────────┘
                         │
                         ▼
    ┌─────────────────────────────────────────┐
    │         OPTIMAL SOLUTION FOUND          │
    │                                         │
    │  Returns:                               │
    │  • Which x[s,e] = 1 (individual swims)  │
    │  • Which y[e,t] = 1 (relay teams)       │
    │  • Total points achieved                │
    │                                         │
    │  GUARANTEE: No other valid lineup       │
    │  can score more points!                 │
    │                                         │
    └─────────────────────────────────────────┘
```

---

### 6. REPORT GENERATION (`generate_lineup.py`)

```
┌─────────────────────────────────────────────────────────────────┐
│                 REPORT GENERATION                                │
└─────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────┐
    │  Solution from Solver                   │
    │                                         │
    │  individual_assignments:                │
    │  {event → [(swimmer, points), ...]}     │
    │                                         │
    │  relay_assignments:                     │
    │  {event → [(team, points), ...]}        │
    │                                         │
    └────────────────────┬────────────────────┘
                         │
                         ▼
    ┌─────────────────────────────────────────┐
    │  Generate Human-Readable Report         │
    │                                         │
    │  • Group by gender/category             │
    │  • Show relay teams with splits         │
    │  • Show individual events with times    │
    │  • Calculate top performers             │
    │  • Points summary                       │
    │  • Swimmer utilization                  │
    │  • Validation report                    │
    │                                         │
    └────────────────────┬────────────────────┘
                         │
                         ▼
    ┌─────────────────────────────────────────┐
    │       optimal_lineup.txt                │
    └─────────────────────────────────────────┘
```

---

## File Structure

```
bcssOptimizer 1.0/
│
├── main.py              # Entry point - CLI interface
│                        # Loads data, runs optimizer, generates reports
│
├── solver.py            # Core optimization logic
│   │
│   ├── Swimmer          # Data class for swimmer info
│   ├── EventKey         # Data class for event identification
│   ├── RelayTeam        # Data class for relay team candidates
│   │
│   ├── load_benchmark() # Load historical benchmark times
│   ├── load_roster()    # Load swimmer roster
│   │
│   └── BcssOptimizer    # Main optimizer class
│       ├── __init__()           # Initialize with data
│       ├── _build_event_keys()  # Create event identifiers
│       ├── _compute_expected_points()  # Calculate all points
│       ├── _enumerate_relay_teams()    # Generate relay combos
│       ├── build_model()        # Create optimization model
│       ├── _add_constraints()   # Add all constraints
│       ├── _set_objective()     # Set maximization goal
│       └── solve()              # Run solver, return solution
│
├── generate_lineup.py   # Report generation
│   ├── generate_lineup_report()  # Create detailed text report
│   └── print_console_summary()   # Print summary to console
│
├── Roster.csv           # Your swimmers and their times
├── 2025.csv             # Benchmark times from previous years
│
└── out/
    └── optimal_lineup.txt  # Generated optimal lineup
```

---

## Key Concepts

### Why Constraint Programming?

The problem of finding the optimal lineup is **NP-hard** - there are exponentially many possible lineups. For example:
- 8 swimmers × 7 events = 56 individual choices
- 70+ relay team combinations per relay
- 2^100+ possible lineups to consider

**Brute force** would take years. **Constraint programming** uses smart pruning to find the optimal solution in seconds.

### What Makes This Optimal?

1. **Complete search**: The solver explores the entire solution space
2. **Proof of optimality**: When it finishes, it has mathematically proven no better solution exists
3. **No heuristics**: Unlike greedy algorithms, this doesn't make local decisions that might miss the global optimum

### Limitations

- Points are **estimated** based on benchmark interpolation
- Relay times use **proxy times** (50m splits summed)
- Doesn't account for **fatigue**, **event order**, or **DQ risk**
- Assumes benchmark data accurately predicts competition
