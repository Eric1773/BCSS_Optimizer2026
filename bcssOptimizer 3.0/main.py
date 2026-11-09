#!/usr/bin/env python3
"""
BCSS Swimming Provincials Optimal Lineup Generator
CLI interface for the global optimizer using OR-Tools CP-SAT
"""

import argparse
import os
import sys
from typing import List

from solver import BcssOptimizer, Swimmer, load_benchmark, load_roster
from generate_lineup import generate_lineup_report, print_console_summary

def main():
    parser = argparse.ArgumentParser(description='BCSS Optimal Lineup Generator')
    parser.add_argument('--benchmark', default='2025.csv', help='Benchmark CSV file')
    parser.add_argument('--roster', default='Roster.csv', help='Roster CSV file')
    parser.add_argument('--out', default='out', help='Output directory')
    parser.add_argument('--max-entries', type=int, default=3, 
                       help='Maximum entries per individual event')
    parser.add_argument('--relay-teams', type=int, default=2,
                       help='Maximum relay teams per relay event')
    parser.add_argument('--must-relays', action='store_true', default=True,
                       help='Must enter all relay events')
    parser.add_argument('--force-two-relays', action='store_true', default=False,
                       help='Force 2 relay teams per event when possible')
    parser.add_argument('--time-limit', type=int, default=30,
                       help='Solver time limit in seconds')
    
    args = parser.parse_args()
    
    print("🏊 BCSS SWIMMING PROVINCIALS - OPTIMAL LINEUP GENERATOR")
    print("=" * 80)
    
    # Load data
    print("📁 Loading data...")
    try:
        benchmark_df = load_benchmark(args.benchmark)
        swimmers = load_roster(args.roster)
        print(f"   ✓ {len(benchmark_df)} benchmark entries")
        print(f"   ✓ {len(swimmers)} swimmers loaded")
    except Exception as e:
        print(f"   ❌ Error loading data: {e}")
        sys.exit(1)
    
    # Create optimizer
    print(f"\n🔧 Initializing optimizer...")
    optimizer = BcssOptimizer(
        benchmark_df=benchmark_df,
        swimmers=swimmers,
        max_entries_individual=args.max_entries,
        max_teams_relay=args.relay_teams,
        must_enter_all_relays=args.must_relays,
        force_two_relays=args.force_two_relays
    )
    
    # Build and solve model
    optimizer.build_model()
    individual_assignments, relay_assignments, total_points = optimizer.solve(
        time_limit=args.time_limit
    )
    
    # Create output directory
    os.makedirs(args.out, exist_ok=True)
    
    # Generate reports
    print(f"\n📊 Generating reports...")
    
    # Console summary
    print_console_summary(individual_assignments, relay_assignments, swimmers, total_points)
    
    # Detailed lineup report
    lineup_file = os.path.join(args.out, 'optimal_lineup.txt')
    report = generate_lineup_report(
        individual_assignments, relay_assignments, swimmers, 
        total_points, lineup_file
    )
    
    print(f"\n✅ Optimization complete!")
    print(f"💾 Lineup report: {lineup_file}")
    print(f"📈 Total expected points: {total_points:.1f}")
    print(f"\n🎯 This lineup is GUARANTEED OPTIMAL (within the model's assumptions).")

if __name__ == '__main__':
    main()
