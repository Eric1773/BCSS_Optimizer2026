# BCSS Swim Optimizer 3.0

**[Launch the live optimizer →](https://bcss-optimizer-3.streamlit.app/)**

Build a lineup for BCSS swimming provincials. The optimizer uses your roster and meet benchmarks to estimate points and assign swimmers to individual events and relays within your entry limits.

## Use the app

1. Open the live app and download the blank roster template under **CSV format and templates**.
2. Fill in one row per swimmer. Enter times in seconds or as `M:SS.ss`. Leave unavailable times blank.
3. Upload your roster and set your meet constraints. The app uses the included 2025 benchmark by default, or you can upload your own.
4. Select **Generate lineup** to see the projected score and download the lineup report.

### Relay settings

- **Maximum relay teams per event** caps the number of teams the solver can enter in a relay.
- **Require all eligible relay events** requires at least one team wherever the solver can form a valid team. If that conflicts with swimmers’ event limits, try turning this option off.
- **Require two relay teams when possible** is visible in the current app, but the solver does not yet enforce it.

## Run locally

From the repository root, install the dependencies and start the app:

```sh
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

For command-line usage and more detail about the scoring model, see the [optimizer documentation](bcssOptimizer%203.0/README.md).
