import streamlit as st
import pandas as pd
import datetime
from PO.po_handler import POHandler

st.set_page_config(page_title="Manual Purchase Orders", layout="wide")
po_handler = POHandler()
BARCODE_COLUMN = "barcode"

def manual_po_page():
    st.header("📝 Manual Purchase Orders – Add Items")

    # --- Session state ---
    if "po_items" not in st.session_state:
        st.session_state["po_items"] = []
    if "po_feedback" not in st.session_state:
        st.session_state["po_feedback"] = ""
    if "latest_po_results" not in st.session_state:
        st.session_state["latest_po_results"] = []

    # --- Data ---
    items_df = po_handler.fetch_data("SELECT * FROM item")
    mapping_df = po_handler.get_item_supplier_mapping()
    suppliers_df = po_handler.get_suppliers()

    if BARCODE_COLUMN not in items_df.columns:
        st.error(f"'{BARCODE_COLUMN}' column NOT FOUND in your item table!")
        st.stop()

    barcode_to_item = {
        str(row[BARCODE_COLUMN]).strip(): row
        for _, row in items_df.iterrows()
        if pd.notnull(row[BARCODE_COLUMN]) and str(row[BARCODE_COLUMN]).strip()
    }

    # --- Feedback ---
    if st.session_state["po_feedback"]:
        st.success(st.session_state["po_feedback"])
        st.session_state["po_feedback"] = ""

    # --- Barcode input (always visible) ---
    bc_col1, bc_col2 = st.columns([5,1])
    barcode_in = bc_col1.text_input("Scan/Enter Barcode", key="barcode_input", label_visibility="visible", value="", autocomplete="off")
    add_click = bc_col2.button("Add Item")
    if add_click or (barcode_in and st.session_state.get("last_barcode", None) != barcode_in):
        code = str(barcode_in).strip()
        found_row = barcode_to_item.get(code, None)
        if found_row is None and code.lstrip('0') != code:
            found_row = barcode_to_item.get(code.lstrip('0'), None)
        if found_row is None:
            st.warning(f"Barcode '{code}' not found.")
        else:
            item_id = int(found_row["itemid"])
            if not any(po["item_id"] == item_id for po in st.session_state["po_items"]):
                mapping = mapping_df[mapping_df["itemid"] == item_id]
                if not mapping.empty:
                    supplierid = int(mapping.iloc[0]["supplierid"])
                    suppliername = suppliers_df[suppliers_df["supplierid"] == supplierid]["suppliername"].values[0]
                    st.session_state["po_items"].append({
                        "item_id": item_id,
                        "itemname": found_row["itemnameenglish"],
                        "barcode": code,
                        "quantity": 1,
                        "estimated_price": 0.0,
                        "supplierid": supplierid,
                        "suppliername": suppliername
                    })
        st.session_state["barcode_input"] = ""
        st.session_state["last_barcode"] = code
        st.rerun()

    # --- Card-style items panel ---
    st.write("### Current Items")
    po_items = st.session_state["po_items"]
    if not po_items:
        st.info("No items added yet. Scan a barcode to begin.")
    else:
        to_remove = []
        for idx, po in enumerate(po_items):
            card = st.container()
            with card:
                c1, c2, c3, c4, c5 = st.columns([3,2,2,2,1])
                c1.markdown(f"**🛒 {po['itemname']}**  \nBarcode: `{po['barcode']}`")
                qty = c2.number_input("Qty", min_value=1, value=po["quantity"], step=1, key=f"qty_{idx}")
                price = c3.number_input("Est. Price", min_value=0.0, value=po["estimated_price"], step=0.01, key=f"price_{idx}")
                c4.markdown(f"**Supplier:** {po['suppliername']}")
                remove = c5.button("Remove", key=f"rm_{idx}")
                po["quantity"] = qty
                po["estimated_price"] = price
                if remove:
                    to_remove.append(idx)
        for idx in reversed(to_remove):
            st.session_state["po_items"].pop(idx)
        if to_remove:
            st.rerun()

    # --- Delivery date/time ---
    st.write("### 📅 Delivery Info")
    date_col, time_col = st.columns(2)
    delivery_date = date_col.date_input("Delivery Date", value=datetime.date.today(), min_value=datetime.date.today())
    delivery_time = time_col.time_input("Delivery Time", value=datetime.time(9,0))

    # --- Generate POs button ---
    if st.button("🧾 Generate Purchase Orders"):
        if not po_items:
            st.error("Please add at least one item before generating purchase orders.")
        else:
            # Group by supplier
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

    # --- Result tab (second page) ---
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
