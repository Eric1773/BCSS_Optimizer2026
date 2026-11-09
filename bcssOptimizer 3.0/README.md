# BCSS Points Optimizer

A Python CLI tool that maximizes total expected points for BCSS swimming championships using integer linear programming with OR-Tools.

## Features

- **Data Validation**: Validates benchmark and roster data with comprehensive checks
- **Expected Points Modeling**: Converts swimmer times to expected points using linear interpolation on benchmark data
- **Relay Optimization**: Generates and evaluates relay team combinations using 50-free time calibration
- **ILP Solver**: Uses OR-Tools to find optimal event assignments under BCSS constraints
- **Comprehensive Output**: Generates detailed CSV reports and validation summaries

## Requirements

- Python 3.7+
- Dependencies listed in `requirements.txt`

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python3 main.py --benchmark 2025.csv --roster Roster.csv --out out --max-per-event 3 --relay-team-options 80
```

### Parameters

- `--benchmark`: Path to benchmark CSV file (required)
- `--roster`: Path to roster CSV file (required)  
- `--out`: Output directory for results (required)
- `--max-per-event`: Maximum individual entries per event (default: 3)
- `--relay-team-options`: Number of relay team combinations to consider (default: 80)

## Input Files

### Benchmark CSV (e.g., 2025.csv)
Required columns:
- `event`: Event number
- `gender`: Boys/Girls
- `category`: A/B/OPEN (OPEN normalized to A)
- `distance`: Event distance in meters
- `stroke`: Stroke type (includes "Relay" for relay events)
- `placement`: Final placement (1-N)
- `timeraw`: Raw time string
- `timeseconds`: Time in seconds (numeric)
- `valid`: TRUE/FALSE
- `points_earned`: Points awarded (already doubled for relays)

### Roster CSV (e.g., Roster.csv)
Required columns:
- `swimmer_id`: Unique swimmer identifier
- `name`: Swimmer name
- `gender`: Boys/Girls
- `category`: A/B
- `max_events`: Maximum events per swimmer (includes relays)
- Event time columns: `50_Free`, `100_Free`, `50_Back`, `100_Back`, `50_Fly`, `100_Fly`, `50_Breast`, `100_Breast`, `100_IM`, `200_IM`

## Output Files

### entries_individual.csv
Individual event assignments with expected points and predicted times.

### entries_relays.csv  
Relay team selections with calibration details and expected points.

### summary.csv
Overall statistics including total points and breakdowns by category.

### validation_report.txt
Data validation summary and event counts.

## BCSS Rules Implemented

- **Gender Separation**: Boys and Girls never compete together
- **Category Separation**: A swimmers only score in A events, B swimmers only in B events
- **Event Limits**: Each swimmer limited to `max_events` total swims (individual + relays)
- **Entry Caps**: Maximum `max_per-event` individual entries per event per gender/category
- **Relay Teams**: One 4-person relay team per relay event per gender/category
- **Point System**: Uses benchmark points ladder with linear interpolation

## Optimization Model

The tool uses integer linear programming with:
- Binary decision variables for individual event entries
- Binary variables for relay team selection from pre-computed combinations
- Constraints for event limits, entry caps, and eligibility
- Objective function maximizing total expected points

## Relay Calibration

Relay performance is estimated using:
1. Sum of 4 swimmers' 50-free times as proxy
2. Calibration factor based on benchmark relay vs roster 50-free ratios
3. Linear interpolation on benchmark relay point curve

## Example Results

```
============================================================
BCSS OPTIMIZATION RESULTS
============================================================

Total Expected Points: 83.72

Top Individual Events by Points:
   20.00 | Nina Patel      | Girls_A_200_IM
   15.73 | Sienna Wong     | Girls_B_100_IM
   12.73 | Sophie Martin   | Girls_A_200_IM
   12.46 | Owen Park       | Boys_A_200_IM
    9.49 | Miles Johnson   | Boys_B_100_IM
```

## License

This tool is designed for BCSS swimming championship optimization.
