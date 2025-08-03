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
                "quantity": 1,
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
            card = st.container()
            with card:
                st.markdown(
                    f"<div style='font-size:18px;font-weight:700;color:#174e89;margin-bottom:2px;'>🛒 {po['itemname']}</div>"
                    f"<div style='font-size:14px;color:#086b37;margin-bottom:3px;'>Barcode: <code>{po['barcode']}</code></div>",
                    unsafe_allow_html=True,
                )
                tags = [
                    f"<span style='background:#fff3e0;color:#C61C1C;border-radius:7px;padding:3px 12px 3px 12px;font-size:13.5px;margin-right:6px;'><b>Class:</b> {po.get('classcat','')}</span>",
                    f"<span style='background:#e3f2fd;color:#004CBB;border-radius:7px;padding:3px 12px;font-size:13.5px;margin-right:6px;'><b>Department:</b> {po.get('departmentcat','')}</span>",
                    f"<span style='background:#eafaf1;color:#098A23;border-radius:7px;padding:3px 12px;font-size:13.5px;margin-right:6px;'><b>Section:</b> {po.get('sectioncat','')}</span>",
                    f"<span style='background:#fff8e1;color:#FF8800;border-radius:7px;padding:3px 12px;font-size:13.5px;'><b>Family:</b> {po.get('familycat','')}</span>",
                ]
                st.markdown(f"<div style='margin-bottom:4px;'>{''.join(tags)}</div>", unsafe_allow_html=True)
                c1, c2, c3, c4, c5 = st.columns([2,2,3,2,1])
                qty = c1.number_input("Qty", min_value=1, value=po["quantity"], step=1, key=f"qty_{idx}")
                price = c2.number_input("Est. Price", min_value=0.0, value=po["estimated_price"], step=0.01, key=f"price_{idx}")

                supplier_options = []
                supplier_id_to_name = {}
                for sid in po["possible_suppliers"]:
                    sname = suppliers_df[suppliers_df["supplierid"] == sid]["suppliername"].values[0]
                    supplier_options.append(sname)
                    supplier_id_to_name[sid] = sname
                if len(supplier_options) > 1:
                    selected_supplier_name = c3.selectbox(
                        "Supplier", supplier_options,
                        index=supplier_options.index(po["suppliername"]),
                        key=f"supplier_{idx}"
                    )
                    selected_sid = [sid for sid, name in supplier_id_to_name.items() if name == selected_supplier_name][0]
                    po["supplierid"] = selected_sid
                    po["suppliername"] = selected_supplier_name
                else:
                    c3.markdown(f"**Supplier:** {po['suppliername']}")

                remove = c5.button("Remove", key=f"rm_{idx}")
                po["quantity"] = qty
                po["estimated_price"] = price
            st.markdown("---")
        if to_remove:
            for idx in reversed(to_remove):
                st.session_state["po_items"].pop(idx)
            st.rerun()

    if st.button("✅ Confirm"):
        if not po_items:
            st.error("Please add at least one item before confirming.")
        else:
            current_datetime = datetime.datetime.now()
            st.session_state["confirm_feedback"] = (
                f"✅ Items confirmed! (Confirmed at {current_datetime.strftime('%Y-%m-%d %H:%M:%S')})"
            )
            st.session_state["po_items"] = []
            st.rerun()

manual_po_page()
