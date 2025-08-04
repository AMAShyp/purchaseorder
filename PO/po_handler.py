import pandas as pd
from datetime import datetime
from db_handler import DatabaseManager
from psycopg2.extras import execute_values

class POHandler(DatabaseManager):
    """
    Handles all database interactions related to purchase orders.
    Extends DatabaseManager for DB connection, queries, and commands.
    """

    # ===================== PO Retrieval =======================

    def get_all_purchase_orders(self):
        """
        Return all active purchase orders (not archived/declined/completed) with joined supplier/item info.
        """
        query = """
        SELECT 
            po.POID AS poid,
            po.SupplierID AS supplierid,
            po.OrderDate AS orderdate,
            po.ExpectedDelivery AS expecteddelivery,
            po.Status AS status,
            po.RespondedAt AS respondedat,
            po.ActualDelivery AS actualdelivery,
            po.CreatedBy AS createdby,
            po.supproposeddeliver AS sup_proposeddeliver,
            po.SupplierNote AS suppliernote,
            po.OriginalPOID AS originalpoid,
            po.Approval AS po_approval,
            s.SupplierName AS suppliername,

            poi.ItemID AS itemid,
            poi.OrderedQuantity AS orderedquantity,
            poi.EstimatedPrice AS estimatedprice,
            poi.ReceivedQuantity AS receivedquantity,
            poi.SupProposedQuantity AS supproposedquantity,
            poi.SupProposedPrice AS supproposedprice,
            poi.Approval AS item_approval,

            i.ItemNameEnglish AS itemnameenglish,
            i.ItemPicture AS itempicture
        FROM PurchaseOrders po
        JOIN Supplier s ON po.SupplierID = s.SupplierID
        JOIN PurchaseOrderItems poi ON po.POID = poi.POID
        JOIN Item i ON poi.ItemID = i.ItemID
        WHERE po.Status NOT IN (
            'Completed', 
            'Declined', 
            'Declined by AMAS',
            'Declined by Supplier'
        )
        ORDER BY po.OrderDate DESC
        """
        return self.fetch_data(query)

    def get_archived_purchase_orders(self):
        """
        Return all archived/declined/completed purchase orders.
        """
        query = """
        SELECT 
            po.POID AS poid,
            po.SupplierID AS supplierid,
            po.OrderDate AS orderdate,
            po.ExpectedDelivery AS expecteddelivery,
            po.Status AS status,
            po.RespondedAt AS respondedat,
            po.ActualDelivery AS actualdelivery,
            po.CreatedBy AS createdby,
            po.SupplierNote AS suppliernote,
            po.Approval AS po_approval,
            s.SupplierName AS suppliername,

            poi.ItemID AS itemid,
            poi.OrderedQuantity AS orderedquantity,
            poi.EstimatedPrice AS estimatedprice,
            poi.ReceivedQuantity AS receivedquantity,
            poi.Approval AS item_approval,

            i.ItemNameEnglish AS itemnameenglish,
            i.ItemPicture AS itempicture
        FROM PurchaseOrders po
        JOIN Supplier s ON po.SupplierID = s.SupplierID
        JOIN PurchaseOrderItems poi ON po.POID = poi.POID
        JOIN Item i ON poi.ItemID = i.ItemID
        WHERE po.Status IN (
            'Completed',
            'Declined',
            'Declined by AMAS',
            'Declined by Supplier'
        )
        ORDER BY po.OrderDate DESC
        """
        return self.fetch_data(query)

    def get_items(self):
        """Return all item information."""
        query = """
        SELECT 
            ItemID AS itemid,
            ItemNameEnglish AS itemnameenglish,
            ItemPicture AS itempicture,
            AverageRequired AS averagerequired
        FROM Item
        """
        return self.fetch_data(query)

    def get_item_supplier_mapping(self):
        """Return mapping between items and suppliers."""
        query = "SELECT ItemID AS itemid, SupplierID AS supplierid FROM ItemSupplier"
        return self.fetch_data(query)

    def get_suppliers(self):
        """Return supplier IDs and names."""
        query = "SELECT SupplierID AS supplierid, SupplierName AS suppliername FROM Supplier"
        return self.fetch_data(query)

    # ============= PO Creation and Updates ====================

    def create_manual_po(self, supplier_id, expected_delivery, items: list, created_by: str, original_poid=None, approval='pending'):
        """
        Create a new purchase order with multiple items (line items).
        Each item dict must include: item_id, quantity, estimated_price, [item_approval].
        """
        supplier_id = int(supplier_id) if supplier_id is not None else None
        original_poid = int(original_poid) if original_poid else None
        if pd.notnull(expected_delivery) and not isinstance(expected_delivery, datetime):
            expected_delivery = pd.to_datetime(expected_delivery).to_pydatetime()

        self._ensure_live_conn()
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO purchaseorders
                          (supplierid, expecteddelivery, createdby, originalpoid, approval)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING poid;
                    """,
                    (supplier_id, expected_delivery, created_by, original_poid, approval),
                )
                po_id = cur.fetchone()[0]

                # Build line items rows for execute_values
                rows = [
                    (
                        po_id,
                        int(item["item_id"]),
                        int(item["quantity"]),
                        item.get("estimated_price"),
                        0,  # receivedquantity (default 0)
                        item.get("item_approval", "pending")
                    )
                    for item in items
                ]

                execute_values(
                    cur,
                    """
                    INSERT INTO purchaseorderitems
                          (poid, itemid, orderedquantity, estimatedprice, receivedquantity, approval)
                    VALUES %s
                    """,
                    rows,
                )
        return po_id

    def update_po_status_to_received(self, poid):
        """Set PO status to 'Received' and update ActualDelivery timestamp."""
        poid = int(poid)
        query = """
        UPDATE PurchaseOrders
        SET Status = 'Received', ActualDelivery = CURRENT_TIMESTAMP
        WHERE POID = %s
        """
        self.execute_command(query, (poid,))

    def update_received_quantity(self, poid, item_id, received_quantity):
        """Update the received quantity for an item in a PO."""
        poid = int(poid)
        item_id = int(item_id)
        received_quantity = int(received_quantity)
        query = """
        UPDATE PurchaseOrderItems
        SET ReceivedQuantity = %s
        WHERE POID = %s AND ItemID = %s
        """
        self.execute_command(query, (received_quantity, poid, item_id))

    # ===== Approval workflow =====
    def update_po_approval(self, poid, approval):
        """Update the approval status of a purchase order."""
        poid = int(poid)
        assert approval in ['pending', 'approved', 'rejected']
        query = """
        UPDATE PurchaseOrders
        SET approval = %s
        WHERE POID = %s
        """
        self.execute_command(query, (approval, poid))

    def update_poitem_approval(self, poid, item_id, approval):
        """Update the approval status of an individual PO item."""
        poid = int(poid)
        item_id = int(item_id)
        assert approval in ['pending', 'approved', 'rejected']
        query = """
        UPDATE PurchaseOrderItems
        SET approval = %s
        WHERE POID = %s AND ItemID = %s
        """
        self.execute_command(query, (approval, poid, item_id))

    # ============= PO Acceptance / Modification ==============

    def accept_proposed_po(self, proposed_po_id: int):
        """
        Accept a proposed purchase order (clone with accepted quantities/prices and set as accepted).
        """
        proposed_po_id = int(proposed_po_id)
        po_info_df = self.fetch_data(
            "SELECT * FROM PurchaseOrders WHERE POID = %s",
            (proposed_po_id,)
        ).rename(columns=str.lower)
        if po_info_df.empty:
            return None
        po_info = po_info_df.iloc[0]

        items_info = self.fetch_data(
            "SELECT * FROM PurchaseOrderItems WHERE POID = %s",
            (proposed_po_id,)
        ).rename(columns=str.lower)

        supplier_id = po_info.get("supplierid")
        if pd.notnull(supplier_id):
            supplier_id = int(supplier_id)

        sup_proposed_date = None
        if pd.notnull(po_info.get("supproposeddeliver")):
            sup_proposed_date = pd.to_datetime(po_info["supproposeddeliver"]).to_pydatetime()

        new_items = []
        for _, row in items_info.iterrows():
            qty = (
                int(row["supproposedquantity"])
                if pd.notnull(row.get("supproposedquantity"))
                else int(row.get("orderedquantity") or 1)
            )
            price = (
                float(row["supproposedprice"])
                if pd.notnull(row.get("supproposedprice"))
                else float(row.get("estimatedprice") or 0.0)
            )
            item_approval = row.get("approval", "pending")
            new_items.append({
                "item_id": int(row["itemid"]),
                "quantity": qty,
                "estimated_price": price,
                "item_approval": item_approval
            })

        created_by = po_info.get("createdby", "Unknown")
        po_approval = po_info.get("approval", "pending")

        new_poid = self.create_manual_po(
            supplier_id=supplier_id,
            expected_delivery=sup_proposed_date,
            items=new_items,
            created_by=created_by,
            original_poid=proposed_po_id,
            approval=po_approval
        )

        self.execute_command(
            "UPDATE PurchaseOrders SET Status = 'Accepted by AMAS' WHERE POID = %s",
            (proposed_po_id,),
        )
        return new_poid

    def decline_proposed_po(self, proposed_po_id):
        """Mark a proposed PO as 'Declined by AMAS'."""
        proposed_po_id = int(proposed_po_id)
        self.execute_command(
            "UPDATE PurchaseOrders SET Status = 'Declined by AMAS' WHERE POID = %s",
            (proposed_po_id,)
        )

    def modify_proposed_po(self, proposed_po_id, new_delivery_date, new_items, user_email):
        """
        Clone a proposed PO with new delivery date and new line items, mark original as modified.
        """
        proposed_po_id = int(proposed_po_id)
        po_info_df = self.fetch_data("SELECT * FROM PurchaseOrders WHERE POID = %s", (proposed_po_id,))
        if po_info_df.empty:
            return None
        po_info = po_info_df.iloc[0]

        supplier_id = po_info.get("supplierid", None)
        if pd.notnull(supplier_id):
            supplier_id = int(supplier_id)
        po_approval = po_info.get("approval", "pending")

        new_poid = self.create_manual_po(
            supplier_id=supplier_id,
            expected_delivery=new_delivery_date,
            items=new_items,
            created_by=user_email,
            original_poid=proposed_po_id,
            approval=po_approval
        )

        self.execute_command(
            "UPDATE PurchaseOrders SET Status = 'Modified by AMAS' WHERE POID = %s",
            (proposed_po_id,)
        )
        return new_poid
