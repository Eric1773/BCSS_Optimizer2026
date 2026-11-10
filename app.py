from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import pandas as pd
import streamlit as st
from solver import BcssOptimizer, load_benchmark, load_roster
from generate_lineup import generate_lineup_report

st.set_page_config(page_title="BCSS Swim Optimizer 3.0", page_icon="🏊", layout="wide")
st.title("🏊 BCSS Swim Optimizer 3.0")
st.subheader("Find your team’s strongest lineup")
st.write("Optimize individual entries and relay teams together. Upload a roster, set your meet constraints, and get a detailed lineup report.")
st.caption("Your uploaded roster is processed for this run and is not saved to a shared database.")
TIME_COLUMNS=["50_Free","100_Free","50_Back","100_Back","50_Fly","100_Fly","50_Breast","100_Breast","100_IM","200_IM"]
ROSTER_COLUMNS=["swimmer_id","name","gender","category","max_events"]
BENCHMARK_COLUMNS=["gender","category","distance","stroke","timeseconds","points_earned"]
def validate_csv(data,columns,label):
    df=pd.read_csv(BytesIO(data)); missing=set(columns)-set(df.columns)
    if missing: raise ValueError(f"{label} is missing columns: {', '.join(sorted(missing))}")
    if df.empty: raise ValueError(f"{label} has no rows.")
    return df
with st.expander("CSV format and templates"):
    st.write("Roster: one swimmer per row. Gender must be Boys or Girls; category must be A or B. Times accept seconds or M:SS.ss. Leave unavailable times blank.")
    st.download_button("Download blank roster template",pd.DataFrame(columns=ROSTER_COLUMNS+TIME_COLUMNS).to_csv(index=False),"roster_template.csv","text/csv")
    st.download_button("Download 2025 benchmark",Path(__file__).with_name("2025.csv").read_bytes(),"2025.csv","text/csv")
with st.form("optimizer"):
    left,right=st.columns(2); roster_upload=left.file_uploader("Swimmer roster CSV",type=["csv"]); benchmark_upload=right.file_uploader("Benchmark CSV (optional; defaults to 2025)",type=["csv"])
    a,b,c=st.columns(3); max_entries=a.number_input("Maximum individual entries per event",1,10,3); relay_teams=b.number_input("Maximum relay teams per event",1,2,2); time_limit=c.number_input("Solver time limit (seconds)",5,120,30,step=5)
    must_relays=st.checkbox("Require all eligible relay events",value=True); force_two=st.checkbox("Require two relay teams when possible",value=False); submitted=st.form_submit_button("Generate lineup",type="primary")
if submitted:
    st.session_state.pop("result",None)
    if roster_upload is None: st.error("Upload a roster CSV to continue.")
    elif force_two and relay_teams<2: st.error("Select two relay teams before requiring two teams.")
    else:
        try:
            rb=roster_upload.getvalue(); bb=benchmark_upload.getvalue() if benchmark_upload else Path(__file__).with_name("2025.csv").read_bytes(); rdf=validate_csv(rb,ROSTER_COLUMNS+TIME_COLUMNS,"Roster"); validate_csv(bb,BENCHMARK_COLUMNS,"Benchmark")
            if rdf[ROSTER_COLUMNS].isna().any().any(): raise ValueError("All roster identity and event-limit fields must be filled in.")
            if rdf.swimmer_id.astype(str).str.strip().duplicated().any(): raise ValueError("Each swimmer_id must be unique.")
            if not rdf.gender.astype(str).str.strip().isin(["Boys","Girls"]).all(): raise ValueError("Roster gender must be Boys or Girls.")
            if not rdf.category.astype(str).str.strip().isin(["A","B"]).all(): raise ValueError("Roster category must be A or B.")
            with st.spinner("Optimizing your lineup…"),TemporaryDirectory() as folder:
                root=Path(folder); (root/"roster.csv").write_bytes(rb); (root/"benchmark.csv").write_bytes(bb); swimmers=load_roster(str(root/"roster.csv"))
                if not swimmers or not any(s.times for s in swimmers): raise ValueError("The roster needs at least one swimmer with a valid event time.")
                benchmark=load_benchmark(str(root/"benchmark.csv"))
                if benchmark.empty: raise ValueError("Benchmark contains no eligible rows with valid times.")
                optimizer=BcssOptimizer(benchmark,swimmers,int(max_entries),int(relay_teams),must_relays,force_two); optimizer.build_model(); individual,relays,points=optimizer.solve(int(time_limit))
                if not individual and not relays: raise ValueError("No feasible lineup was found. Try relaxing relay requirements or increasing the time limit.")
                report=generate_lineup_report(individual,relays,swimmers,points,str(root/"lineup.txt")); st.session_state.result={"points":points,"swimmers":len(swimmers),"report":report}
        except Exception as exc: st.error(f"Could not generate a lineup: {exc}")
if "result" in st.session_state:
    result=st.session_state.result; st.divider(); st.header("Your optimized lineup"); a,b=st.columns(2); a.metric("Expected points",f"{result['points']:.1f}"); b.metric("Swimmers in roster",result['swimmers'])
    st.info("This is the best lineup found within the selected solver time limit; optimality is not independently confirmed by this version of the solver.")
    st.download_button("Download lineup report",result['report'],"optimal_lineup.txt","text/plain",type="primary"); st.code(result['report'],language=None)
