import streamlit as st
import pandas as pd
import datetime

# Barcode scanner (optional dependency)
try:
    from streamlit_qrcode_scanner import qrcode_scanner
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

from PO.po_handler import POHandler

BARCODE_COLUMN = "barcode"

# ---------- Helpers to make DB frames cache-safe ----------
def _to_pickle_safe(val):
    """Convert values that break pickle (e.g., memoryview, bytes) into safe types."""
    if isinstance(val, memoryview):
        try:
            val = bytes(val)
        except Exception:
            return None
    if isinstance(val, (bytes, bytearray)):
        # Try UTF-8; if not decodable, store as hex string
        try:
            return val.decode("utf-8")
        except Exception:
            try:
                return bytes(val).hex()
            except Exception:
                return None
    return val

def sanitize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Apply _to_pickle_safe elementwise so st.cache_data can pickle the result."""
    if df is None or df.empty:
        return df
    return df.applymap(_to_pickle_safe)

# ---------- Cached utilities ----------
@st.cache_data
def load_locids():
    LOCID_CSV_PATH = "assets/locid_list.csv"
    df = pd.read_csv(LOCID_CSV_PATH)
    filtered = set(str(l).strip() for l in df["locid"].dropna().unique())
    return df, filtered

@st.cache_resource
def get_po_handler():
    return POHandler()

@st.cache_data
def get_latest_estimated_price(item_id: int) -> float:
    po_handler = get_po_handler()
    price_df = po_handler.fetch_data("""
        SELECT estimatedprice FROM purchaseorderitems
        WHERE itemid = %s AND estimatedprice IS NOT NULL AND estimatedprice > 0
        ORDER BY poitemid DESC LIMIT 1
    """, (int(item_id),))
    price_df = sanitize_df(price_df)
    if not price_df.empty and pd.notnull(price_df.iloc[0]["estimatedprice"]):
        return float(price_df.iloc[0]["estimatedprice"])
    return 0.0

# ---- DB accessors (cached) made pickle-safe and not capturing outer variables
@st.cache_data
def get_items():
    po_handler = get_po_handler()
    df = po_handler.fetch_data("SELECT * FROM item")
    df = sanitize_df(df)

    # Ensure barcode is clean string
    if BARCODE_COLUMN in df.columns:
        df[BARCODE_COLUMN] = df[BARCODE_COLUMN].apply(
            lambda x: "" if pd.isna(x) else str(x).strip()
        )

    # Normalize common text columns that might arrive as bytes
    for col in ("itemnameenglish", "classcat", "departmentcat", "sectioncat", "familycat"):
        if col in df.columns:
            df[col] = df[col].apply(_to_pickle_safe).astype(str)

    # Ensure integer types
    if "itemid" in df.columns:
        df["itemid"] = pd.to_numeric(df["itemid"], errors="coerce").astype("Int64")

    return df

@st.cache_data
def get_mapping():
    po_handler = get_po_handler()
    df = po_handler.get_item_supplier_mapping()
    df = sanitize_df(df)

    for col in ("itemid", "supplierid"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    return df

@st.cache_data
def get_suppliers():
    po_handler = get_po_handler()
    df = po_handler.get_suppliers()
    df = sanitize_df(df)

    if "supplierid" in df.columns:
        df["supplierid"] = pd.to_numeric(df["supplierid"], errors="coerce").astype("Int64")
    if "suppliername" in df.columns:
        df["suppliername"] = df["suppliername"].apply(_to_pickle_safe).astype(str)
    return df

def manual_po_page():
    st.header("📝 Manual Purchase Orders – Add Items")

    items_df = get_items()
    mapping_df = get_mapping()
    suppliers_df = get_suppliers()

    # Initialize session state
    for key, val in {
        "po_items": [],
        "confirm_feedback": "",
        "clear_after_confirm": False,
        "just_confirmed": False,
    }.items():
        if key not in st.session_state:
            st.session_state[key] = val

    # Check for barcode column
    if BARCODE_COLUMN not in items_df.columns:
        st.error(f"'{BARCODE_COLUMN}' column NOT FOUND in your item table!")
        st.stop()

    # Build a lookup dict: barcode -> row
    barcode_to_item = {}
    for _, row in items_df.iterrows():
        bc = row[BARCODE_COLUMN]
        if pd.notnull(bc) and str(bc).strip():
            barcode_to_item[str(bc).strip()] = row

    # If just confirmed, clear items and stop here (no debug, no UI shown)
    if st.session_state["clear_after_confirm"]:
        st.session_state["po_items"] = []
        st.session_state["clear_after_confirm"] = False
        st.session_state["just_confirmed"] = True
        st.success("✅ All items confirmed and purchase orders created!")
        st.stop()
    else:
        st.session_state["just_confirmed"] = False

    # Show confirmation feedback
    if st.session_state["confirm_feedback"]:
        msg = st.session_state["confirm_feedback"]
        if msg.startswith("❌"):
            st.error(msg)
        elif msg.startswith("✅"):
            st.success(msg)
        st.session_state["confirm_feedback"] = ""

    # UI: Add item via barcode (camera or manual)
    tab1, tab2 = st.tabs(["📷 Camera Scan", "⌨️ Type Barcode"])

    def add_item_by_barcode(barcode):
        code = str(barcode).strip()
        if not code:
            return

        found_row = barcode_to_item.get(code, None)
        if found_row is None and code.lstrip('0') != code:
            found_row = barcode_to_item.get(code.lstrip('0'), None)
        if found_row is None:
            st.warning(f"Barcode '{code}' not found.")
            return

        # Extract fields safely
        item_id = int(found_row["itemid"]) if pd.notnull(found_row["itemid"]) else None
        if item_id is None:
            st.warning("Item ID missing for this barcode.")
            return

        suppliers_for_item = (
            mapping_df[mapping_df["itemid"] == item_id]["supplierid"]
            .dropna()
            .astype(int)
            .tolist()
        )
        if not suppliers_for_item:
            name_eng = str(found_row.get("itemnameenglish", "Unnamed"))
            st.warning(f"No supplier found for item '{name_eng}'.")
            return

        supplierid = int(suppliers_for_item[0])
        sup_name_series = suppliers_df[suppliers_df["supplierid"] == supplierid]["suppliername"]
        suppliername = str(sup_name_series.values[0]) if not sup_name_series.empty else f"Supplier {supplierid}"

        already_added = any(
            po["item_id"] == item_id and po["supplierid"] == supplierid
            for po in st.session_state["po_items"]
        )

        est_price = get_latest_estimated_price(item_id)

        if not already_added:
            st.session_state["po_items"].append({
                "item_id": item_id,
                "itemname": str(found_row.get("itemnameenglish", "")),
                "barcode": code,
                "quantity": 1,
                "estimated_price": float(est_price),
                "supplierid": supplierid,
                "suppliername": suppliername,
                "possible_suppliers": suppliers_for_item,
                "classcat": str(found_row.get("classcat", "")),
                "departmentcat": str(found_row.get("departmentcat", "")),
                "sectioncat": str(found_row.get("sectioncat", "")),
                "familycat": str(found_row.get("familycat", "")),
            })
            st.success(f"Added: {str(found_row.get('itemnameenglish', ''))}")
            st.rerun()
        else:
            st.info(f"Item '{str(found_row.get('itemnameenglish', ''))}' (Supplier: {suppliername}) already added.")

    with tab1:
        st.markdown("**Scan barcode with your webcam**")
        barcode_camera = ""
        if QR_AVAILABLE:
            barcode_camera = qrcode_scanner(key="barcode_camera") or ""
            if barcode_camera:
                add_item_by_barcode(barcode_camera)
        else:
            st.warning("Camera barcode scanning requires streamlit-qrcode-scanner. Please install it or use the next tab.")

    with tab2:
        st.markdown("**Or enter barcode manually**")
        with st.form("add_barcode_form", clear_on_submit=True):
            bc_col1, bc_col2 = st.columns([5, 1])
            barcode_in = bc_col1.text_input(
                "Scan/Enter Barcode",
                value="",
                label_visibility="visible",
                autocomplete="off",
                key="barcode_input"
            )
            add_click = bc_col2.form_submit_button("Add Item")
            if add_click and barcode_in:
                add_item_by_barcode(barcode_in)

    # List current items and allow removal
    st.write("### Current Items")
    po_items = st.session_state["po_items"]
    if not po_items:
        st.info("No items added yet. Scan a barcode to begin.")
    else:
        to_remove = []
        for idx, po in enumerate(po_items):
            cols = st.columns([10, 1])
            with cols[0]:
                st.markdown(
                    f"<div style='font-size:18px;font-weight:700;color:#174e89;margin-bottom:2px;'>🛒 {po['itemname']}</div>"
                    f"<div style='font-size:14px;color:#086b37;margin-bottom:3px;'>Barcode: <code>{po['barcode']}</code></div>"
                    f"<div style='font-size:13px;color:#098A23;margin-bottom:2px;'>Supplier: {po['suppliername']}</div>",
                    unsafe_allow_html=True,
                )
                tags = [
                    f"<span style='background:#fff3e0;color:#C61C1C;border-radius:7px;padding:3px 12px 3px 12px;font-size:13.5px;margin-right:6px;'><b>Class:</b> {po.get('classcat','')}</span>",
                    f"<span style='background:#e3f2fd;color:#004CBB;border-radius:7px;padding:3px 12px;font-size:13.5px;margin-right:6px;'><b>Department:</b> {po.get('departmentcat','')}</span>",
                    f"<span style='background:#eafaf1;color:#098A23;border-radius:7px;padding:3px 12px;font-size:13.5px;margin-right:6px;'><b>Section:</b> {po.get('sectioncat','')}</span>",
                    f"<span style='background:#fff8e1;color:#FF8800;border-radius:7px;padding:3px 12px;font-size:13.5px;'><b>Family:</b> {po.get('familycat','')}</span>",
                ]
                st.markdown(f"<div style='margin-bottom:4px;'>{''.join(tags)}</div>", unsafe_allow_html=True)
            with cols[1]:
                if st.button("❌", key=f"rm_{idx}"):
                    to_remove.append(idx)
            st.markdown("---")
        if to_remove:
            for idx in reversed(to_remove):
                st.session_state["po_items"].pop(idx)
            st.rerun()

    # Confirm button to create PO(s)
    if st.button("✅ Confirm"):
        if not st.session_state["po_items"]:
            st.error("Please add at least one item before confirming.")
        else:
            po_by_supplier = {}
            for po in st.session_state["po_items"]:
                supid = po["supplierid"]
                if supid not in po_by_supplier:
                    po_by_supplier[supid] = {
                        "suppliername": po["suppliername"],
                        "items": []
                    }
                item_dict = {
                    "item_id": po["item_id"],
                    "quantity": po["quantity"],
                    "estimated_price": po["estimated_price"],
                    "itemname": po["itemname"],
                    "barcode": po["barcode"]
                }
                po_by_supplier[supid]["items"].append(item_dict)

            expected_dt = datetime.datetime.now()
            created_by = st.session_state.get("user_email", "ManualUser")

            any_success = False
            po_handler = get_po_handler()
            for supid, supinfo in po_by_supplier.items():
                try:
                    _ = po_handler.create_manual_po(
                        supid, expected_dt, supinfo["items"], created_by
                    )
                    any_success = True
                except Exception:
                    any_success = False

            if any_success:
                st.session_state["confirm_feedback"] = "✅ All items confirmed and purchase orders created!"
            else:
                st.session_state["confirm_feedback"] = "❌ Failed to create any purchase order."

            st.session_state["clear_after_confirm"] = True
            st.rerun()

manual_po_page()
