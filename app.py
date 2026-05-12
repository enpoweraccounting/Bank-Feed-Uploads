import streamlit as st
import pandas as pd
import re
from datetime import datetime, date
 
st.set_page_config(page_title="Bank Feed Uploads", layout="centered")
st.title("Bank Feed Uploads")
 
PLATFORM_CONFIG = {
    "Banquest": {
        "date_col": "Cleared Time in Statement (MT)",
        "desc_cols": ["Clean Merchant Name", "Card Name", "Card Last 4"],
        "amount_col": "Amount",
    },
    "Clearent": {
        "date_col": "Cleared Time in Statement (MT)",
        "desc_cols": ["Clean Merchant Name", "Card Name", "Card Last 4"],
        "amount_col": "Amount",
    },
    "Divvy": {
        "date_col": "Cleared Time in Statement (MT)",
        "desc_cols": ["Clean Merchant Name", "Card Name", "Card Last 4"],
        "amount_col": "Amount",
    },
    "Donors Fund": {
        "date_col": "Cleared Time in Statement (MT)",
        "desc_cols": ["Clean Merchant Name", "Card Name", "Card Last 4"],
        "amount_col": "Amount",
    },
}
 
def ordinal(n):
    s = ["th", "st", "nd", "rd"]
    v = n % 100
    return f"{n}{s[(v - 20) % 10] if (v - 20) % 10 < 4 else s[v] if v < 4 else s[0]}"
 
def friendly_date_range(start: date, end: date) -> str:
    months = ["January","February","March","April","May","June",
              "July","August","September","October","November","December"]
    s = f"{months[start.month - 1]}_{ordinal(start.day)}"
    e = f"{months[end.month - 1]}_{ordinal(end.day)}"
    return f"{s}_thru_{e}"
 
def parse_slash_date(s: str):
    s = s.strip()
    m = re.match(r'^(\d{4}-\d{2}-\d{2})\s+(\d{2}):(\d{2}):(\d{2})(AM|PM)$', s, re.IGNORECASE)
    if not m:
        return None
    hours = int(m.group(2))
    ampm = m.group(5).upper()
    if ampm == "PM" and hours != 12:
        hours += 12
    if ampm == "AM" and hours == 12:
        hours = 0
    try:
        return datetime.strptime(f"{m.group(1)} {hours:02d}:{m.group(3)}:{m.group(4)}", "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None
 
def parse_amount(val: str, negate: bool) -> str:
    cleaned = str(val).replace("$", "").replace(",", "").strip()
    if re.match(r'^\(.*\)$', cleaned):
        parsed = -float(cleaned.replace("(", "").replace(")", ""))
    else:
        try:
            parsed = float(cleaned)
        except ValueError:
            return ""
    if negate:
        return str(-parsed)
    return cleaned
 
def parse_date_flexible(val: str):
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y",
                "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(str(val).strip(), fmt)
        except ValueError:
            continue
    return None
 
def load_file(uploaded) -> pd.DataFrame:
    name = uploaded.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded, dtype=str).fillna("")
    elif name.endswith(".xlsx"):
        return pd.read_excel(uploaded, dtype=str).fillna("")
    return None
 
def process(df: pd.DataFrame, config: dict, start: date, end: date) -> pd.DataFrame:
    output = []
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())
 
    for _, row in df.iterrows():
        if "exclude_types" in config:
            if row.get("Type", "").strip() in config["exclude_types"]:
                continue
        if config.get("exclude_wex_na"):
            if row.get(config["desc_cols"][1], "").strip() == "N/A":
                continue
        if "exclude_if_empty_col" in config:
            if not row.get(config["exclude_if_empty_col"], "").strip():
                continue
        if "exclude_statuses" in config:
            if row.get("Status", "").strip().upper() in config["exclude_statuses"]:
                continue
 
        desc_check = row.get(config["desc_cols"][0], "").strip().lower()
        if desc_check == "wire deposit":
            continue
 
        raw_date = row.get(config["date_col"], "").strip()
        if not raw_date:
            continue
 
        if config.get("slash_date"):
            tx_date = parse_slash_date(raw_date)
        else:
            tx_date = parse_date_flexible(raw_date)
 
        if tx_date is None:
            continue
        if not (start_dt <= tx_date <= end_dt):
            continue
 
        formatted_date = tx_date.strftime("%-m/%-d/%Y")
 
        merchant = row.get(config["desc_cols"][0], "").strip()
        card_name = row.get(config["desc_cols"][1], "").strip()
        card_last_raw = str(row.get(config["desc_cols"][2], "")).strip()
        if config.get("wex_last4"):
            card_last = card_last_raw[-4:]
        else:
            card_last = card_last_raw.lstrip("'").rstrip(".0") if card_last_raw.endswith(".0") else card_last_raw.lstrip("'")
        description = " - ".join(filter(bool, [merchant, card_name, card_last]))
 
        amount = parse_amount(row.get(config["amount_col"], ""), config.get("negate_amount", False))
        output.append({"Date": formatted_date, "Description": description, "Amount": amount})
 
    result = pd.DataFrame(output, columns=["Date", "Description", "Amount"])
    if not result.empty:
        result["_sort"] = pd.to_datetime(result["Date"], errors="coerce")
        result = result.sort_values("_sort", ascending=False).drop(columns=["_sort"])
    return result
 
def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")
 
def reset():
    st.session_state["reset_counter"] = st.session_state.get("reset_counter", 0) + 1
 
if "reset_counter" not in st.session_state:
    st.session_state["reset_counter"] = 0
 
rc = st.session_state["reset_counter"]
platform = st.selectbox("Platform", [""] + sorted(PLATFORM_CONFIG.keys()), key=f"platform_{rc}")
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Start date", value=None, key=f"start_date_{rc}")
with col2:
    end_date = st.date_input("End date", value=None, key=f"end_date_{rc}")
 
st.divider()
uploaded_file = st.file_uploader("Source file", type=["csv", "xlsx"], key=f"uploader_{rc}")
 
col_btn1, col_btn2 = st.columns([2, 1])
with col_btn1:
    convert_clicked = st.button("Convert", type="primary", disabled=not all([platform, start_date, end_date, uploaded_file]))
with col_btn2:
    if st.button("Clear / Reset", use_container_width=True):
        reset()
        st.rerun()
 
if convert_clicked:
    config = PLATFORM_CONFIG.get(platform)
    if not config:
        st.error("Platform mapping not found.")
    else:
        with st.spinner("Processing..."):
            df = load_file(uploaded_file)
            if df is None:
                st.error("Could not read file.")
            else:
                result = process(df, config, start_date, end_date)
                if result.empty:
                    st.error("No transactions found in that date range.")
                else:
                    platform_clean = platform.replace(" ", "_")
                    date_range = friendly_date_range(start_date, end_date)
                    base_name = f"{platform_clean}_{date_range}"
 
                    st.success(f"{len(result)} transactions exported.")
                    st.download_button(
                        label=f"Download {base_name}.csv",
                        data=df_to_csv_bytes(result),
                        file_name=f"{base_name}.csv",
                        mime="text/csv"
                    )
