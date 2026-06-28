import streamlit as st
import pandas as pd
import re
from datetime import datetime, date
 
st.set_page_config(page_title="Bank Feed Uploads", layout="centered")
st.title("Bank Feed Uploads")
 
PLATFORM_CONFIG = {
    "Banquest": {
        "date_col": "Date",
        "desc_cols": ["Description"],
        "amount_col": "TotalAmount",
        "banquest": True,
    },
    "Brickyard Bank": {
        "date_col": "Date",
        "desc_cols": ["Description"],
        "amount_col": None,
        "brickyard": True,
    },
    "Clearent": {
        "date_col": "Transaction Date",
        "desc_cols": ["Customer Name", "Order ID", "Description"],
        "amount_col": "Amount",
        "clearent": True,
    },
    "Divvy": {
        "date_col": "Cleared Time in Statement (MT)",
        "desc_cols": ["Clean Merchant Name", "Card Name", "Card Last 4"],
        "amount_col": "Amount",
    },
    "Donors Fund": {
        "date_col": "Date",
        "desc_cols": ["Shared Name", "Shared Fund Name", "Memo"],
        "amount_col": "Amount",
        "donors_fund": True,
    },
    "Double Giving (Stripe)": {
        "date_col": "Date",
        "desc_cols": ["First name", "Last name", "Campaign", "Comment"],
        "amount_col": "Amount",
        "double_giving": True,
        "exclude_statuses": ["Failed", "Offline"],
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
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
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
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())
    if config.get("banquest"):
        tuition_pattern = re.compile(r'tu[it]+[ia]?[oi]?[ou]?n|fee s?|registr', re.IGNORECASE)
        total_4010 = 0.0
        total_5180 = 0.0
        formatted_date = start_dt.strftime("%-m/%-d/%Y")
        for _, row in df.iterrows():
            amt_raw = row.get("TotalAmount", "").strip()
            try:
                amt = float(amt_raw)
            except ValueError:
                continue
            desc = row.get("Description", "").strip()
            if tuition_pattern.search(desc):
                total_5180 += amt
            else:
                total_4010 += amt
        output = []
        if total_4010:
            output.append({"Customer": "Banquest Income", "Date": formatted_date, "Deposit To": "1499 Undeposited Funds", "Product/Service": "4010 Individual Contributions", "Qty": 1, "Rate": round(total_4010, 2)})
        if total_5180:
            output.append({"Customer": "Banquest Income", "Date": formatted_date, "Deposit To": "1499 Undeposited Funds", "Product/Service": "5180 Tuition Fee", "Qty": 1, "Rate": round(total_5180, 2)})
        return pd.DataFrame(output, columns=["Customer", "Date", "Deposit To", "Product/Service", "Qty", "Rate"])
 
    output = []
 
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
 
        desc_check = row.get(config["desc_cols"][0], "").strip().lower() if config.get("desc_cols") else ""
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
 
        if config.get("double_giving"):
            first = row.get("First name", "").strip()
            last = row.get("Last name", "").strip()
            full_name = " ".join(filter(bool, [first, last]))
            campaign = row.get("Campaign", "").strip()
            comment = row.get("Comment", "").strip()
            description = " - ".join(filter(bool, [full_name, campaign, comment]))
            amount = parse_amount(row.get("Amount", ""), False)
            output.append({"Date": formatted_date, "Description": description, "Amount": amount})
            continue
 
        if config.get("brickyard"):
            description = row.get("Description", "").strip()
            debit = row.get("Debit", "").strip()
            credit = row.get("Credit", "").strip()
            if debit:
                amount = parse_amount(debit, True)
            elif credit:
                amount = parse_amount(credit, False)
            else:
                continue
            output.append({"Date": formatted_date, "Description": description, "Amount": amount})
            continue
 
        if config.get("clearent"):
            customer = row.get("Customer Name", "").strip()
            order_id = row.get("Order ID", "").strip()
            desc_field = row.get("Description", "").strip()
            if re.match(r'^\d+$', order_id):
                order_id = ""
            description = " - ".join(filter(bool, [customer, order_id, desc_field]))
            amount = parse_amount(row.get("Amount", ""), False)
            output.append({"Date": formatted_date, "Description": description, "Amount": amount})
            continue
 
        if config.get("donors_fund"):
            shared_name = row.get("Shared Name", "").strip()
            shared_fund = row.get("Shared Fund Name", "").strip()
            memo = row.get("Memo", "").strip()
            payment_type = row.get("Payment Type", "").strip()
            conf_num = str(row.get("Confirmation Number", "")).strip()
            base_parts = list(filter(bool, [shared_name, shared_fund]))
            description = " - ".join(base_parts)
            suffix_parts = list(filter(bool, [payment_type, conf_num, memo]))
            if suffix_parts:
                description += f" ({', '.join(suffix_parts)})"
            gross_amount = parse_amount(row.get("Amount", ""), False)
            output.append({"Date": formatted_date, "Description": description, "Amount": gross_amount})
            fee_raw = row.get("Fees", "").strip()
            if fee_raw and fee_raw not in ("", "0", "0.0"):
                try:
                    fee_val = float(fee_raw)
                    if fee_val != 0:
                        output.append({"Date": formatted_date, "Description": description, "Amount": str(fee_val)})
                except ValueError:
                    pass
            continue
 
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
account_name = st.text_input("Account Name (Optional)", key=f"account_name_{rc}")
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
                    if account_name.strip():
                        base_name = f"{platform_clean} ({account_name.strip()})_{date_range}"
                    else:
                        base_name = f"{platform_clean}_{date_range}"
 
                    st.success(f"{len(result)} transactions exported.")
                    st.download_button(
                        label=f"Download {base_name}.csv",
                        data=df_to_csv_bytes(result),
                        file_name=f"{base_name}.csv",
                        mime="text/csv"
                    )
 
