import streamlit as st
import pandas as pd
import datetime
import plotly.graph_objects as go
from PO.po_handler import POHandler

try:
    from streamlit_qrcode_scanner import qrcode_scanner
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

try:
    from shelf_map.shelf_map_handler import ShelfMapHandler
except ImportError:
    ShelfMapHandler = None

BARCODE_COLUMN = "barcode"

# --- LOCID filter setup ---
@st.cache_data
def load_locids():
    LOCID_CSV_PATH = "assets/locid_list.csv"
    df = pd.read_csv(LOCID_CSV_PATH)
    filtered = set(str(l).strip() for l in df["locid"].dropna().unique())
    return df, filtered

locid_df, FILTERED_LOCIDS = load_locids()

@st.cache_data
def load_shelf_map():
    if ShelfMapHandler:
        return ShelfMapHandler().get_locations()
    return []

def map_with_highlights_and_textlabels(locs, highlight_locs, allowed_locids):
    # ... (Unchanged plotting code)
    # [keep as is]
    # ...
    return fig, polygons, trace_text

@st.cache_data
def get_latest_estimated_price(po_handler, item_id):
    """Returns latest nonzero estimated price for an item, or 0 if none."""
    price_df = po_handler.fetch_data("""
        SELECT estimatedprice FROM purchaseorderitems
        WHERE itemid = %s AND estimatedprice IS NOT NULL AND estimatedprice > 0
        ORDER BY poitemid DESC LIMIT 1
    """, (int(item_id),))
    if not price_df.empty and pd.notnull(price_df.iloc[0]["estimatedprice"]):
        return float(price_df.iloc[0]["estimatedprice"])
    return 0.0

@st.cache_resource
def get_po_handler():
    return POHandler()

def manual_po_page():
    st.header("📝 Manual Purchase Orders – Add Items")

    po_handler = get_po_handler()
    shelf_map = load_shelf_map()
    # Cache items, mapping, and suppliers for snappier UX!
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
    if "po_feedback" not in st.session_state:
        st.session_state["po_feedback"] = ""
    if "latest_po_results" not in st.session_state:
        st.session_state["latest_po_results"] = []

    if BARCODE_COLUMN not in items_df.columns:
        st.error(f"'{BARCODE_COLUMN}' column NOT FOUND in your item table!")
        st.stop()

    barcode_to_item = {
        str(row[BARCODE_COLUMN]).strip(): row
        for _, row in items_df.iterrows()
        if pd.notnull(row[BARCODE_COLUMN]) and str(row[BARCODE_COLUMN]).strip()
    }

    if st.session_state["po_feedback"]:
        st.success(st.session_state["po_feedback"])
        st.session_state["po_feedback"] = ""

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
        est_price = get_latest_estimated_price(po_handler, item_id)
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

                # --- Shelf map for the item ---
                if shelf_map:
                    itemid = po["item_id"]
                    item_shelf_locs = [row for row in shelf_map if str(row.get("itemid", "")) == str(itemid) or "itemid" not in row]
                    highlights = []
                    if "locid" in mapping_df.columns:
                        highlights = [str(loc) for loc in mapping_df[(mapping_df["itemid"] == itemid) & (mapping_df["locid"].isin(FILTERED_LOCIDS))]["locid"].unique()]
                    st.markdown("<div style='margin-top:6px;'><b>🗺️ Shelf Map (highlighted if available):</b></div>", unsafe_allow_html=True)
                    fig, polygons, _ = map_with_highlights_and_textlabels(shelf_map, highlights, FILTERED_LOCIDS)
                    st.plotly_chart(fig, use_container_width=True)
                st.markdown("---")
        if to_remove:
            for idx in reversed(to_remove):
                st.session_state["po_items"].pop(idx)
            st.rerun()

    st.write("### 📅 Delivery Info")
    date_col, time_col = st.columns(2)
    delivery_date = date_col.date_input("Delivery Date", value=datetime.date.today(), min_value=datetime.date.today())
    delivery_time = time_col.time_input("Delivery Time", value=datetime.time(9,0))

    if st.button("🧾 Generate Purchase Orders"):
        if not po_items:
            st.error("Please add at least one item before generating purchase orders.")
        else:
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
                    "estimated_price": po["estimated_price"] if po["estimated_price"] > 0 else None,
                    "itemname": po["itemname"],
                    "barcode": po["barcode"],
                })
            expected_dt = datetime.datetime.combine(delivery_date, delivery_time)
            created_by = st.session_state.get("user_email", "ManualUser")
            results = []
            any_success = False
            for supid, supinfo in po_by_supplier.items():
                try:
                    poid = po_handler.create_manual_po(
                        supid, expected_dt, supinfo["items"], created_by)
                    results.append((supid, supinfo["suppliername"], poid, supinfo["items"]))
                    any_success = True
                except Exception as e:
                    results.append((supid, supinfo["suppliername"], None, supinfo["items"]))
            if any_success:
                st.session_state["po_feedback"] = "✅ Purchase Orders generated successfully!"
            else:
                st.session_state["po_feedback"] = "❌ Failed to generate any purchase order."
            st.session_state["po_items"] = []
            st.session_state["latest_po_results"] = results
            st.rerun()

    results = st.session_state["latest_po_results"]
    st.header("📄 Generated Purchase Orders")
    if not results:
        st.info("No purchase orders generated yet.")
    else:
        for supid, supname, poid, items in results:
            with st.expander(f"Supplier: {supname} (PO ID: {poid if poid else 'FAILED'})"):
                for po in items:
                    row = f"🛒 **{po['itemname']}**  \nBarcode: `{po['barcode']}`  \nQty: {po['quantity']}  \nEst. Price: {po['estimated_price'] if po['estimated_price'] else 'N/A'}"
                    st.markdown(row)
                st.markdown("---")

manual_po_page()
