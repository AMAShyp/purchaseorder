import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
import datetime

# Barcode scanner (optional dependency)
try:
    from streamlit_qrcode_scanner import qrcode_scanner
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

from PO.po_handler import POHandler

BARCODE_COLUMN = "barcode"

# --------------------------- Helpers: shelves + deck.gl ---------------------------

def to_float(x):
    try:
        return float(x)
    except:
        return 0.0

def shelves_are_adjacent(a, b, tol=1e-7):
    ax1, ay1, aw, ah = map(to_float, (a['x_pct'], a['y_pct'], a['w_pct'], a['h_pct']))
    bx1, by1, bw, bh = map(to_float, (b['x_pct'], b['y_pct'], b['w_pct'], b['h_pct']))
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    return not (ax2 < bx1 - tol or bx2 < ax1 - tol or ay2 < by1 - tol or by2 < ay1 - tol)

def build_clusters(locs_df):
    # locs_df: DataFrame with rows of shelves
    locs = locs_df.to_dict("records")
    n = len(locs)
    visited = [False] * n
    clusters = []
    for i in range(n):
        if not visited[i]:
            cluster = []
            queue = [i]
            visited[i] = True
            while queue:
                curr = queue.pop(0)
                cluster.append(curr)
                for j in range(n):
                    if not visited[j] and shelves_are_adjacent(locs[curr], locs[j]):
                        visited[j] = True
                        queue.append(j)
            clusters.append(cluster)
    return clusters

def color_for_idx(idx):
    COLORS = [
        "#dc3545", "#0275d8", "#5cb85c", "#f0ad4e", "#9b59b6", "#333333", "#800080", "#008080",
        "#FFD700", "#E67E22", "#C0392B", "#16A085", "#7B241C", "#1ABC9C",
    ]
    hexcol = COLORS[idx % len(COLORS)]
    rgb = tuple(int(hexcol[i:i+2], 16) for i in (1, 3, 5))
    return rgb, hexcol

def make_rectangle(x, y, w, h, deg):
    """
    Return rectangle corners (counterclockwise) in normalized 0..1 space.
    Deck.gl expects [lng, lat] -> we use x as lng, y as lat.
    """
    cx = x + w / 2.0
    cy = y + h / 2.0
    rad = np.deg2rad(deg)
    cos, sin = np.cos(rad), np.sin(rad)
    # corners relative to center
    corners = np.array([
        [-w/2, -h/2],
        [ w/2, -h/2],
        [ w/2,  h/2],
        [-w/2,  h/2]
    ])
    rotated = np.dot(corners, np.array([[cos, -sin],[sin, cos]]))
    abs_pts = rotated + [cx, cy]
    # close polygon by repeating the first point
    return abs_pts.tolist() + [abs_pts[0].tolist()]

def build_deck_from_locs(locs_df, highlight_locids=None):
    """
    Build a Deck.gl (pydeck) object:
      - All shelves as polygons
      - Highlight shelves whose locid is in highlight_locids
      - Labels shown only on hover via tooltip
    """
    if highlight_locids is None:
        highlight_locids = set()

    # Build cluster coloring once
    clusters = build_clusters(locs_df)
    index_to_cluster = {}
    cluster_color_map = {}
    for ci, clist in enumerate(clusters):
        rgb, _ = color_for_idx(ci)
        cluster_color_map[ci] = rgb
        for idx in clist:
            index_to_cluster[idx] = ci

    polygons = []
    for idx, row in locs_df.reset_index(drop=True).iterrows():
        x = to_float(row["x_pct"]); y = to_float(row["y_pct"])
        w = to_float(row["w_pct"]);  h = to_float(row["h_pct"])
        deg = to_float(row.get("rotation_deg", 0))
        coords = make_rectangle(x, y, w, h, deg)

        label = str(row.get('label') or row.get('locid') or idx)
        locid = str(row.get('locid') or label)

        ci = index_to_cluster.get(idx, 0)
        base_rgb = cluster_color_map[ci]

        # Highlight if selected
        if locid in highlight_locids:
            fill_color = list(base_rgb) + [190]
            line_color = [0, 0, 0, 255]
            line_width = 2
        else:
            fill_color = list(base_rgb) + [110]
            line_color = list(base_rgb) + [220]
            line_width = 1

        polygons.append({
            "polygon": coords,
            "label": label,
            "locid": locid,
            "fill_color": fill_color,
            "line_color": line_color,
            "line_width": line_width,
        })

    poly_df = pd.DataFrame(polygons)

    polygon_layer = pdk.Layer(
        "PolygonLayer",
        data=poly_df,
        get_polygon="polygon",
        get_fill_color="fill_color",
        get_line_color="line_color",
        get_line_width="line_width",
        pickable=True,
        auto_highlight=True,
    )

    view_state = pdk.ViewState(
        longitude=0.5, latitude=0.5, zoom=6, min_zoom=4, max_zoom=20, pitch=0, bearing=0
    )

    deck = pdk.Deck(
        layers=[polygon_layer],
        initial_view_state=view_state,
        map_provider=None,  # no basemap
        tooltip={
            "html": "<b>{label}</b><br/><span style='color:#777'>({locid})</span>",
            "style": {"backgroundColor": "white", "color": "#222", "fontSize": "14px"},
        },
        height=480,
    )
    return deck

# --------------------------- Caching + data access ---------------------------

@st.cache_data
def load_locids():
    LOCID_CSV_PATH = "assets/locid_list.csv"
    df = pd.read_csv(LOCID_CSV_PATH)
    # Ensure required columns exist
    required = {"locid","label","x_pct","y_pct","w_pct","h_pct","rotation_deg"}
    missing = required - set(df.columns)
    if missing:
        st.error(f"locid_list.csv missing columns: {missing}")
        st.stop()
    # Clean + ensure strings
    df["locid"] = df["locid"].astype(str).str.strip()
    df["label"] = df["label"].astype(str).str.strip()
    filtered = set(df["locid"].dropna().unique().tolist())
    return df, filtered

@st.cache_resource
def get_po_handler():
    return POHandler()

@st.cache_data
def get_latest_estimated_price(item_id):
    po_handler = get_po_handler()
    price_df = po_handler.fetch_data("""
        SELECT estimatedprice FROM purchaseorderitems
        WHERE itemid = %s AND estimatedprice IS NOT NULL AND estimatedprice > 0
        ORDER BY poitemid DESC LIMIT 1
    """, (int(item_id),))
    if not price_df.empty and pd.notnull(price_df.iloc[0]["estimatedprice"]):
        return float(price_df.iloc[0]["estimatedprice"])
    return 0.0

# --------------------------- The Manual PO Page ---------------------------

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

    # Load shelf locations for Deck.gl view
    locs_df, all_locids = load_locids()

    # Initialize session state
    defaults = {
        "po_items": [],              # list of dicts
        "confirm_feedback": "",
        "clear_after_confirm": False,
        "just_confirmed": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # Check for barcode column
    if BARCODE_COLUMN not in items_df.columns:
        st.error(f"'{BARCODE_COLUMN}' column NOT FOUND in your item table!")
        st.stop()

    # Barcode index
    barcode_to_item = {
        str(row[BARCODE_COLUMN]).strip(): row
        for _, row in items_df.iterrows()
        if pd.notnull(row[BARCODE_COLUMN]) and str(row[BARCODE_COLUMN]).strip()
    }

    # If just confirmed, clear items and stop here
    if st.session_state["clear_after_confirm"]:
        st.session_state["po_items"] = []
        st.session_state["clear_after_confirm"] = False
        st.session_state["just_confirmed"] = True
        st.success("✅ All items confirmed and purchase orders created!")
        st.stop()
    else:
        st.session_state["just_confirmed"] = False

    # Feedback
    if st.session_state["confirm_feedback"]:
        msg = st.session_state["confirm_feedback"]
        if msg.startswith("❌"):
            st.error(msg)
        elif msg.startswith("✅"):
            st.success(msg)
        st.session_state["confirm_feedback"] = ""

    # ---------- Deck.gl map up top: highlights selected locids ----------
    selected_locids = {po.get("locid") for po in st.session_state["po_items"] if po.get("locid")}
    st.subheader("🗺️ Shelf Map (Deck.gl)")
    st.pydeck_chart(build_deck_from_locs(locs_df, selected_locids))

    # ---------- Add item via barcode ----------
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
                "locid": "",  # NEW: user can assign a shelf later
            })
            st.success(f"Added: {found_row['itemnameenglish']}")
            st.rerun()
        else:
            st.info(f"Item '{found_row['itemnameenglish']}' (Supplier: {suppliername}) already added.")

    with tab1:
        st.markdown("**Scan barcode with your webcam**")
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

    # ---------- Current items with per-item shelf (locid) assignment ----------
    st.write("### Current Items")
    po_items = st.session_state["po_items"]
    if not po_items:
        st.info("No items added yet. Scan a barcode to begin.")
    else:
        to_remove = []
        for idx, po in enumerate(po_items):
            cols = st.columns([7, 3, 1])
            with cols[0]:
                st.markdown(
                    f"<div style='font-size:18px;font-weight:700;color:#174e89;margin-bottom:2px;'>🛒 {po['itemname']}</div>"
                    f"<div style='font-size:14px;color:#086b37;margin-bottom:3px;'>Barcode: <code>{po['barcode']}</code></div>"
                    f"<div style='font-size:13px;color:#098A23;margin-bottom:2px;'>Supplier: {po['suppliername']}</div>",
                    unsafe_allow_html=True,
                )
                # Tags
                tags = [
                    f"<span style='background:#fff3e0;color:#C61C1C;border-radius:7px;padding:3px 12px 3px 12px;font-size:13.5px;margin-right:6px;'><b>Class:</b> {po.get('classcat','')}</span>",
                    f"<span style='background:#e3f2fd;color:#004CBB;border-radius:7px;padding:3px 12px;font-size:13.5px;margin-right:6px;'><b>Department:</b> {po.get('departmentcat','')}</span>",
                    f"<span style='background:#eafaf1;color:#098A23;border-radius:7px;padding:3px 12px;font-size:13.5px;margin-right:6px;'><b>Section:</b> {po.get('sectioncat','')}</span>",
                    f"<span style='background:#fff8e1;color:#FF8800;border-radius:7px;padding:3px 12px;font-size:13.5px;'><b>Family:</b> {po.get('familycat','')}</span>",
                ]
                st.markdown(f"<div style='margin-bottom:4px;'>{''.join(tags)}</div>", unsafe_allow_html=True)

            with cols[1]:
                # NEW: assign shelf (locid) for better visualization + routing
                current_locid = po.get("locid", "")
                new_locid = st.selectbox(
                    "Shelf (locid)",
                    options=[""] + sorted(all_locids),
                    index=([""] + sorted(all_locids)).index(current_locid) if current_locid in all_locids else 0,
                    key=f"locid_select_{idx}",
                    help="Assign the shelf where this item belongs."
                )
                if new_locid != current_locid:
                    st.session_state["po_items"][idx]["locid"] = new_locid
                    # Update the Deck.gl highlight live
                    st.experimental_rerun()

            with cols[2]:
                if st.button("❌", key=f"rm_{idx}"):
                    to_remove.append(idx)

            st.markdown("---")

        if to_remove:
            for idx in reversed(to_remove):
                st.session_state["po_items"].pop(idx)
            st.rerun()

    # ---------- Confirm button to create PO(s) ----------
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
                    "barcode": po["barcode"],
                    # Optional: include chosen locid in the PO payload if your backend supports it
                    "locid": po.get("locid", "")
                }
                po_by_supplier[supid]["items"].append(item_dict)

            expected_dt = datetime.datetime.now()
            created_by = st.session_state.get("user_email", "ManualUser")
            any_success = False
            for supid, supinfo in po_by_supplier.items():
                try:
                    _poid = po_handler.create_manual_po(
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

# --------------------------- Run page ---------------------------
manual_po_page()
