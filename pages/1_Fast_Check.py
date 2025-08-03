import streamlit as st
import pandas as pd
import datetime
from PO.po_handler import POHandler

try:
    from streamlit_qrcode_scanner import qrcode_scanner
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

BARCODE_COLUMN = "barcode"

@st.cache_data
def load_locids():
    LOCID_CSV_PATH = "assets/locid_list.csv"
    df = pd.read_csv(LOCID_CSV_PATH)
    filtered = set(str(l).strip() for l in df["locid"].dropna().unique())
    return df, filtered

locid_df, FILTERED_LOCIDS = load_locids()

@st.cache_resource
def get_po_handler():
    return POHandler()

@st.cache_data
def get_latest_estimated_price(item_id):
    po_handler = POHandler()
    price_df = po_handler.fetch_data("""
        SELECT estimatedprice FROM purchaseorderitems
        WHERE itemid = %s AND estimatedprice IS NOT NULL AND estimatedprice > 0
        ORDER BY poitemid DESC LIMIT 1
    """, (int(item_id),))
    if not price_df.empty and pd.notnull(price_df.iloc[0]["estimatedprice"]):
        return float(price_df.iloc[0]["estimatedprice"])
    return 0.0

def manual_po_page():
    st.header("📝 Manual Purchase Orders – Add Items")

    po_handler = get_po_handler()

    @st.cache_data
    def get_items():
        return po_handler.fetch_data("SELECT * FROM item")
    @st.cache_data
    def get_mapping():
        return po_handler.get_item_supplier_mapping()
    @st.cache_data
    def get_suppliers():
        return po_handler.get_suppliers()

    items_df = get_items()
    mapping_df = get_mapping()
    suppliers_df = get_suppliers()

    if "po_items" not in st.session_state:
        st.session_state["po_items"] = []
    if "confirm_feedback" not in st.session_state:
        st.session_state["confirm_feedback"] = ""

    if BARCODE_COLUMN not in items_df.columns:
        st.error(f"'{BARCODE_COLUMN}' column NOT FOUND in your item table!")
        st.stop()

    barcode_to_item = {
        str(row[BARCODE_COLUMN]).strip(): row
        for _, row in items_df.iterrows()
        if pd.notnull(row[BARCODE_COLUMN]) and str(row[BARCODE_COLUMN]).strip()
    }

    if st.session_state["confirm_feedback"]:
        st.success(st.session_state["confirm_feedback"])
        st.session_state["confirm_feedback"] = ""

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
        item_id = int(found_row["itemid"])
        suppliers_for_item = mapping_df[mapping_df["itemid"] == item_id]["supplierid"].tolist()
        if not suppliers_for_item:
            st.warning(f"No supplier found for item '{found_row['itemnameenglish']}'.")
            return
        supplierid = int(suppliers_for_item[0])
        suppliername = suppliers_df[suppliers_df["supplierid"] == supplierid]["suppliername"].values[0]
        already_added = any(
            po["item_id"] == item_id and po["supplierid"] == supplierid
            for po in st.session_state["po_items"]
        )
        est_price = get_latest_estimated_price(item_id)
        if not already_added:
            st.session_state["po_items"].append({
                "item_id": item_id,
                "itemname": found_row["itemnameenglish"],
                "barcode": code,
                "quantity": 1,  # Default qty
                "estimated_price": est_price,
                "supplierid": supplierid,
                "suppliername": suppliername,
                "possible_suppliers": suppliers_for_item,
                "classcat": found_row.get("classcat", ""),
                "departmentcat": found_row.get("departmentcat", ""),
                "sectioncat": found_row.get("sectioncat", ""),
                "familycat": found_row.get("familycat", ""),
            })
            st.success(f"Added: {found_row['itemnameenglish']}")
            st.rerun()
        else:
            st.info(f"Item '{found_row['itemnameenglish']}' (Supplier: {suppliername}) already added.")

    with tab1:
        st.markdown("**Scan barcode with your webcam**")
        barcode_camera = ""
        if QR_AVAILABLE:
            barcode_camera = qrcode_scanner(key="barcode_camera") or ""
            if barcode_camera:
                add_item_by_barcode(barcode_camera)
        else:
            st.warning("Camera barcode scanning requires `streamlit-qrcode-scanner`. Please install it or use the next tab.")

    with tab2:
        st.markdown("**Or enter barcode manually**")
        with st.form("add_barcode_form", clear_on_submit=True):
            bc_col1, bc_col2 = st.columns([5,1])
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

    if st.button("✅ Confirm"):
        if not po_items:
            st.error("Please add at least one item before confirming.")
        else:
            # --- CREATE PURCHASE ORDERS IN DATABASE ---
            po_by_supplier = {}
            for po in po_items:
                supid = po["supplierid"]
                if supid not in po_by_supplier:
                    po_by_supplier[supid] = {
                        "suppliername": po["suppliername"],
                        "items": []
                    }
                po_by_supplier[supid]["items"].append({
                    "item_id": po["item_id"],
                    "quantity": po["quantity"],
                    "estimated_price": po["estimated_price"],
                    "itemname": po["itemname"],
                    "barcode": po["barcode"],
                })
            expected_dt = datetime.datetime.now()
            created_by = st.session_state.get("user_email", "ManualUser")
            any_success = False
            for supid, supinfo in po_by_supplier.items():
                try:
                    poid = po_handler.create_manual_po(
                        supid, expected_dt, supinfo["items"], created_by)
                    any_success = True
                except Exception as e:
                    pass  # Optionally, handle/log failed PO creation
            if any_success:
                st.session_state["confirm_feedback"] = "✅ All items confirmed and purchase orders created!"
            else:
                st.session_state["confirm_feedback"] = "❌ Failed to create any purchase order."
            st.session_state["po_items"] = []
            st.rerun()

manual_po_page()
