#!/usr/bin/env python3
"""
BCSS Swimming Provincials Optimal Lineup Solver
Uses OR-Tools CP-SAT for guaranteed global optimality
"""

import pandas as pd
import numpy as np
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Set
from ortools.sat.python import cp_model

@dataclass
class Swimmer:
    swimmer_id: str
    name: str
    gender: str
    category: str
    max_events: int
    times: Dict[str, float]
    
    def __hash__(self):
        # Hash based on immutable fields only
        return hash((self.swimmer_id, self.name, self.gender, self.category, self.max_events))

@dataclass(frozen=True)
class EventKey:
    gender: str
    category: str
    distance: int
    stroke: str
    is_relay: bool
    
    def __str__(self):
        return f"{self.gender}_{self.category}_{self.distance}_{self.stroke}"

@dataclass
class RelayTeam:
    swimmer_ids: Tuple[str, ...]
    expected_points: float
    proxy_time: float

def load_benchmark(filepath: str) -> pd.DataFrame:
    """Load and normalize benchmark data"""
    df = pd.read_csv(filepath)
    
    # Filter to Boys/Girls only
    df = df[df['gender'].isin(['Boys', 'Girls'])].copy()
    
    # Normalize OPEN -> A, filter to A/B only
    df['category'] = df['category'].replace('OPEN', 'A')
    df = df[df['category'].isin(['A', 'B'])].copy()
    
    # Only keep valid times
    df = df[df['timeseconds'].notna()].copy()
    
    # Filter out invalid (e.g. DQ'd) benchmark entries
    if 'valid' in df.columns:
        df = df[df['valid'].astype(str).str.upper() != 'FALSE'].copy()
    
    # Add relay flag
    df['is_relay'] = df['stroke'].str.contains('Relay')
    
    return df

def _parse_time(raw) -> Optional[float]:
    """Parse a time value that may be seconds (59.17) or M:SS.ss (1:05.34) or M:SS (1:05)."""
    if pd.isna(raw):
        return None
    s = str(raw).strip()
    if not s:
        return None
    if ':' in s:
        parts = s.split(':')
        try:
            minutes = int(parts[0])
            seconds = float(parts[1])
            return minutes * 60 + seconds
        except (ValueError, IndexError):
            return None
    try:
        return float(s)
    except ValueError:
        return None

def load_roster(filepath: str) -> List[Swimmer]:
    """Load roster data"""
    df = pd.read_csv(filepath)
    
    # Strip whitespace from string columns
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].str.strip()
    
    swimmers = []
    time_cols = ['50_Free', '100_Free', '50_Back', '100_Back', '50_Fly', 
                 '100_Fly', '50_Breast', '100_Breast', '100_IM', '200_IM']
    
    for _, row in df.iterrows():
        if pd.isna(row['swimmer_id']):
            continue
        times = {}
        for col in time_cols:
            if col in row:
                val = _parse_time(row[col])
                if val is not None:
                    times[col] = val
        
        swimmers.append(Swimmer(
            swimmer_id=row['swimmer_id'],
            name=row['name'].strip() if isinstance(row['name'], str) else row['name'],
            gender=row['gender'].strip() if isinstance(row['gender'], str) else row['gender'],
            category=row['category'].strip() if isinstance(row['category'], str) else row['category'],
            max_events=int(row['max_events']),
            times=times
        ))
    
    return swimmers

class BcssOptimizer:
    def __init__(self, benchmark_df: pd.DataFrame, swimmers: List[Swimmer],
                 max_entries_individual: int = 3, max_teams_relay: int = 1,
                 must_enter_all_relays: bool = True, force_two_relays: bool = False):
        self.benchmark_df = benchmark_df
        self.swimmers = swimmers
        self.swimmer_map = {s.swimmer_id: s for s in swimmers}
        self.max_entries_individual = max_entries_individual
        self.max_teams_relay = max_teams_relay
        self.must_enter_all_relays = must_enter_all_relays
        self.force_two_relays = force_two_relays
        
        # Build event keys
        self.individual_events = []
        self.relay_events = []
        self._build_event_keys()
        
        # Pre-compute expected points
        self.individual_points = {}  # (swimmer_id, event_key) -> points
        self.relay_teams = {}  # (event_key, team_idx) -> RelayTeam
        self._compute_expected_points()
        
        # Model variables
        self.model = None
        self.x_vars = {}  # Individual assignment variables
        self.y_vars = {}  # Relay team selection variables
        self.z_vars = {}  # Swimmer-relay linking variables
        
    def _build_event_keys(self):
        """Extract all unique events from benchmark"""
        events = self.benchmark_df.groupby(['gender', 'category', 'distance', 'stroke']).first().reset_index()
        
        for _, row in events.iterrows():
            event_key = EventKey(
                gender=row['gender'],
                category=row['category'],
                distance=int(row['distance']),
                stroke=row['stroke'],
                is_relay='Relay' in row['stroke']
            )
            
            if event_key.is_relay:
                self.relay_events.append(event_key)
            else:
                self.individual_events.append(event_key)
    
    def _compute_expected_points(self):
        """Pre-compute expected points for all swimmer-event combinations"""
        print("📊 Computing expected points...")
        
        # Individual events
        for swimmer in self.swimmers:
            for event_key in self.individual_events:
                if swimmer.gender != event_key.gender or swimmer.category != event_key.category:
                    continue
                
                points = self._get_individual_expected_points(swimmer, event_key)
                if points > 0:
                    self.individual_points[(swimmer.swimmer_id, event_key)] = points
        
        print(f"   ✓ {len(self.individual_points)} individual scoring combinations")
        
        # Relay teams - enumerate top candidates
        print("🏊 Enumerating relay teams...")
        for event_key in self.relay_events:
            teams = self._enumerate_relay_teams(event_key)  # All scoring teams
            for idx, team in enumerate(teams):
                self.relay_teams[(event_key, idx)] = team
        
        print(f"   ✓ {len(self.relay_teams)} relay team candidates")
    
    def _get_individual_expected_points(self, swimmer: Swimmer, event_key: EventKey) -> float:
        """Calculate expected points for individual event"""
        # Map event to roster column
        stroke_map = {
            'Freestyle': 'Free',
            'Backstroke': 'Back',
            'Butterfly': 'Fly',
            'Breaststroke': 'Breast',
            'IM': 'IM'
        }
        
        stroke_short = stroke_map.get(event_key.stroke, event_key.stroke)
        time_col = f"{event_key.distance}_{stroke_short}"
        
        if time_col not in swimmer.times:
            return 0.0
        
        swimmer_time = swimmer.times[time_col]
        
        # Get benchmark data
        event_benchmark = self.benchmark_df[
            (self.benchmark_df['gender'] == event_key.gender) &
            (self.benchmark_df['category'] == event_key.category) &
            (self.benchmark_df['distance'] == event_key.distance) &
            (self.benchmark_df['stroke'] == event_key.stroke)
        ]
        
        if event_benchmark.empty:
            return 0.0
        
        # Sort by time and interpolate
        sorted_rows = event_benchmark.sort_values('timeseconds')
        times = sorted_rows['timeseconds'].values
        points = sorted_rows['points_earned'].values
        
        # 16th place cutoff
        if len(times) >= 16:
            time_16th = times[15]
            if swimmer_time >= time_16th:
                return 0.0
        
        # Linear interpolation
        if swimmer_time <= times[0]:
            return float(points[0])
        elif swimmer_time >= times[-1]:
            return 0.0
        else:
            for i in range(len(times) - 1):
                if times[i] <= swimmer_time <= times[i + 1]:
                    t1, p1 = times[i], points[i]
                    t2, p2 = times[i + 1], points[i + 1]
                    ratio = (swimmer_time - t1) / (t2 - t1)
                    return p1 + ratio * (p2 - p1)
        
        return 0.0
    
    def _enumerate_relay_teams(self, event_key: EventKey) -> List[RelayTeam]:
        """Generate all relay team candidates that score points"""
        from itertools import combinations, permutations
        
        is_medley = 'Medley' in event_key.stroke
        # Use 100_Free for 400m relays, 50_Free for 200m relays
        free_col = '100_Free' if event_key.distance == 400 else '50_Free'
        
        # Get eligible swimmers based on relay type
        # B swimmers can swim up to A relays; A swimmers cannot swim B relays
        def _relay_eligible(s):
            if s.gender != event_key.gender:
                return False
            if event_key.category == 'A':
                return s.category in ('A', 'B')
            else:
                return s.category == event_key.category
        
        if is_medley:
            # Medley relay: need at least one of the stroke times
            medley_cols = ['50_Back', '50_Breast', '50_Fly', '50_Free']
            eligible = [s for s in self.swimmers 
                       if _relay_eligible(s)
                       and any(c in s.times for c in medley_cols)]
        else:
            # Freestyle relay: need the appropriate free time
            eligible = [s for s in self.swimmers 
                       if _relay_eligible(s)
                       and free_col in s.times]
        
        if len(eligible) < 4:
            return []
        
        # Get benchmark for points calculation — filter by distance too
        relay_benchmark = self.benchmark_df[
            (self.benchmark_df['gender'] == event_key.gender) &
            (self.benchmark_df['category'] == event_key.category) &
            (self.benchmark_df['distance'] == event_key.distance) &
            (self.benchmark_df['stroke'] == event_key.stroke)
        ]
        
        if relay_benchmark.empty:
            return []
        
        # Generate all valid 4-swimmer combinations (no duplicates)
        candidates = []  # (swimmer_ids, points, proxy_time) for all valid combos
        for combo in combinations(eligible, 4):
            # Ensure all 4 swimmers are unique
            swimmer_ids = tuple(s.swimmer_id for s in combo)
            if len(set(swimmer_ids)) != 4:
                continue
            
            if is_medley:
                # Medley relay: find best assignment of swimmers to legs
                # Legs: Back, Breast, Fly, Free
                best_time = float('inf')
                best_order = None
                
                for perm in permutations(combo):
                    # perm[0]=Back, perm[1]=Breast, perm[2]=Fly, perm[3]=Free
                    # Only valid if swimmers have the required stroke times
                    back_time = perm[0].times.get('50_Back')
                    breast_time = perm[1].times.get('50_Breast')
                    fly_time = perm[2].times.get('50_Fly')
                    free_time = perm[3].times.get('50_Free')
                    
                    # Skip if any swimmer doesn't have their required stroke time
                    if back_time is None or breast_time is None or fly_time is None or free_time is None:
                        continue
                    
                    time = back_time + breast_time + fly_time + free_time
                    
                    if time < best_time:
                        best_time = time
                        best_order = perm
                
                # Skip this combo if no valid assignment found
                if best_order is None:
                    continue
                
                proxy_time = best_time
                swimmer_ids = tuple(s.swimmer_id for s in best_order)
            else:
                # Freestyle relay: sum of appropriate free times
                proxy_time = sum(s.times[free_col] for s in combo)
            
            points = self._get_relay_expected_points(proxy_time, relay_benchmark)
            candidates.append((swimmer_ids, points, proxy_time))
        
        # Keep all scoring teams
        teams = [RelayTeam(swimmer_ids=ids, expected_points=pts, proxy_time=pt)
                 for ids, pts, pt in candidates if pts > 0]
        teams.sort(key=lambda t: t.expected_points, reverse=True)
        
        # If relays are required but no team scores, still field the fastest team
        if not teams and self.must_enter_all_relays and candidates:
            best = min(candidates, key=lambda c: c[2])
            teams.append(RelayTeam(swimmer_ids=best[0], expected_points=0.0, proxy_time=best[2]))
        
        return teams
    
    def _get_relay_expected_points(self, proxy_time: float, relay_benchmark: pd.DataFrame) -> float:
        """Calculate expected relay points from proxy time"""
        sorted_rows = relay_benchmark.sort_values('timeseconds')
        times = sorted_rows['timeseconds'].values
        points = sorted_rows['points_earned'].values
        
        # 16th place cutoff
        if len(times) >= 16:
            time_16th = times[15]
            if proxy_time >= time_16th:
                return 0.0
        
        # Linear interpolation
        if proxy_time <= times[0]:
            return float(points[0])
        elif proxy_time >= times[-1]:
            return 0.0
        else:
            for i in range(len(times) - 1):
                if times[i] <= proxy_time <= times[i + 1]:
                    t1, p1 = times[i], points[i]
                    t2, p2 = times[i + 1], points[i + 1]
                    ratio = (proxy_time - t1) / (t2 - t1)
                    return p1 + ratio * (p2 - p1)
        
        return 0.0
    
    def build_model(self):
        """Build the CP-SAT optimization model"""
        print("🔧 Building optimization model...")
        self.model = cp_model.CpModel()
        
        # Create individual assignment variables
        for (swimmer_id, event_key), points in self.individual_points.items():
            var_name = f"x_{swimmer_id}_{event_key}"
            self.x_vars[(swimmer_id, event_key)] = self.model.NewBoolVar(var_name)
        
        # Create relay team selection variables
        for (event_key, team_idx), relay_team in self.relay_teams.items():
            var_name = f"y_{event_key}_{team_idx}"
            self.y_vars[(event_key, team_idx)] = self.model.NewBoolVar(var_name)
            
            # Create linking variables for swimmer participation
            for swimmer_id in relay_team.swimmer_ids:
                link_name = f"z_{swimmer_id}_{event_key}_{team_idx}"
                self.z_vars[(swimmer_id, event_key, team_idx)] = self.model.NewBoolVar(link_name)
        
        # Add constraints
        self._add_constraints()
        
        # Set objective
        self._set_objective()
        
        print(f"   ✓ {len(self.x_vars)} individual variables")
        print(f"   ✓ {len(self.y_vars)} relay team variables")
        print(f"   ✓ {len(self.z_vars)} linking variables")
    
    def _add_constraints(self):
        """Add all optimization constraints"""
        print("   Adding constraints...")
        
        # 1. Max events per swimmer (CRITICAL: count each relay EVENT once, not each team)
        for swimmer in self.swimmers:
            # Individual events
            individual_vars = [
                self.x_vars[(swimmer.swimmer_id, event_key)]
                for event_key in self.individual_events
                if (swimmer.swimmer_id, event_key) in self.x_vars
            ]
            
            # Relay events - create helper variable for each relay event
            # A swimmer participates in a relay event if ANY team they're on is selected
            # Check all same-gender relays (B swimmers may be on A relay teams)
            relay_participation_vars = []
            for event_key in self.relay_events:
                if swimmer.gender != event_key.gender:
                    continue
                
                # Get all teams this swimmer is on for this relay event
                swimmer_teams = [
                    self.z_vars[(swimmer.swimmer_id, event_key, team_idx)]
                    for (sid, ek, team_idx) in self.z_vars.keys()
                    if sid == swimmer.swimmer_id and ek == event_key
                ]
                
                if swimmer_teams:
                    # Create a helper variable: swimmer participates in this relay event
                    relay_var = self.model.NewBoolVar(f"relay_part_{swimmer.swimmer_id}_{event_key}")
                    # relay_var = 1 if swimmer is on any selected team for this event
                    self.model.AddMaxEquality(relay_var, swimmer_teams)
                    relay_participation_vars.append(relay_var)
            
            # Total events = individual + relay participation
            all_vars = individual_vars + relay_participation_vars
            if all_vars:
                self.model.Add(sum(all_vars) <= swimmer.max_events)
        
        # 2. Max entries per individual event
        for event_key in self.individual_events:
            event_vars = [
                var for (sid, ek), var in self.x_vars.items()
                if ek == event_key
            ]
            if event_vars:
                self.model.Add(sum(event_vars) <= self.max_entries_individual)
        
        # 3. Max teams per relay event
        for event_key in self.relay_events:
            team_vars = [
                self.y_vars[(event_key, team_idx)]
                for (ek, team_idx) in self.y_vars.keys()
                if ek == event_key
            ]
            if team_vars:
                self.model.Add(sum(team_vars) <= self.max_teams_relay)
        
        # 4. Must enter all relays (if required) - at least 1 team per relay
        if self.must_enter_all_relays:
            for event_key in self.relay_events:
                team_vars = [
                    self.y_vars[(event_key, team_idx)]
                    for (ek, team_idx) in self.y_vars.keys()
                    if ek == event_key
                ]
                if team_vars:
                    self.model.Add(sum(team_vars) >= 1)
        
        # 5. Linking constraints: swimmer participates if team selected
        for (event_key, team_idx), relay_team in self.relay_teams.items():
            team_var = self.y_vars[(event_key, team_idx)]
            for swimmer_id in relay_team.swimmer_ids:
                link_var = self.z_vars[(swimmer_id, event_key, team_idx)]
                # z = y (swimmer is on team iff team is selected)
                self.model.Add(link_var == team_var)
        
        # 6. Each swimmer can only be on ONE team per relay event
        for swimmer in self.swimmers:
            for event_key in self.relay_events:
                if swimmer.gender != event_key.gender:
                    continue
                
                # Get all teams this swimmer is on for this relay event
                swimmer_teams = [
                    self.z_vars[(swimmer.swimmer_id, event_key, team_idx)]
                    for (sid, ek, team_idx) in self.z_vars.keys()
                    if sid == swimmer.swimmer_id and ek == event_key
                ]
                
                if swimmer_teams:
                    # Swimmer can be on at most 1 team for this event
                    self.model.Add(sum(swimmer_teams) <= 1)
    
    def _set_objective(self):
        """Set the optimization objective"""
        # Scale points to integers (multiply by 100 for 2 decimal precision)
        SCALE = 100
        
        # Individual points
        individual_objective = sum(
            int(points * SCALE) * self.x_vars[(swimmer_id, event_key)]
            for (swimmer_id, event_key), points in self.individual_points.items()
        )
        
        # Relay points
        relay_objective = sum(
            int(relay_team.expected_points * SCALE) * self.y_vars[(event_key, team_idx)]
            for (event_key, team_idx), relay_team in self.relay_teams.items()
        )
        
        self.model.Maximize(individual_objective + relay_objective)
        self.objective_scale = SCALE
    
    def solve(self, time_limit: int = 30) -> Tuple[Dict, Dict, float]:
        """Solve the optimization problem"""
        print(f"🚀 Solving optimization problem (time limit: {time_limit}s)...")
        
        # Set solver parameters
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit
        solver.parameters.num_search_workers = 8
        solver.parameters.log_search_progress = False
        
        # Solve
        result = solver.Solve(self.model)
        
        if result == cp_model.OPTIMAL:
            print(f"   ✓ Optimal solution found!")
        elif result == cp_model.FEASIBLE:
            print(f"   ⚠️  Feasible solution found (time limit reached)")
        else:
            print(f"   ❌ No solution found")
            return {}, {}, 0.0
        
        # Extract solution
        individual_assignments = defaultdict(list)
        relay_assignments = defaultdict(list)
        
        # Individual events
        for (swimmer_id, event_key), var in self.x_vars.items():
            if solver.Value(var) == 1:
                swimmer = self.swimmer_map[swimmer_id]
                points = self.individual_points[(swimmer_id, event_key)]
                individual_assignments[event_key].append((swimmer, points))
        
        # Relay events - now stores list of teams per event
        for (event_key, team_idx), var in self.y_vars.items():
            if solver.Value(var) == 1:
                relay_team = self.relay_teams[(event_key, team_idx)]
                swimmers = [self.swimmer_map[sid] for sid in relay_team.swimmer_ids]
                relay_assignments[event_key].append((swimmers, relay_team.expected_points))
        
        total_points = solver.ObjectiveValue() / self.objective_scale
        
        print(f"   Total expected points: {total_points:.1f}")
        
        return individual_assignments, relay_assignments, total_points
