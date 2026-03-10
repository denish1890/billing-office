import streamlit as st
import mysql.connector
import pandas as pd
import firebase_admin
from firebase_admin import credentials, auth
from datetime import datetime
import matplotlib.pyplot as plt
import urllib
from streamlit_autorefresh import st_autorefresh

# ==========================
# 🔹 Initialize Firebase
# ==========================
cred = credentials.Certificate(st.secrets["firebase"])
firebase_admin.initialize_app(cred)
    

# ==========================
# 🔹 MySQL Connection Function
# ==========================

def get_db_connection():
    return mysql.connector.connect(
        host="gateway01.ap-southeast-1.prod.aws.tidbcloud.com",
        user="4Er7E7yAa5CmneH.root",
        password="4Er7E7yAa5CmneH.root",
        database="cafe",
        autocommit=True
    )

# ==========================
# 🔹 Fetch Admin Requests
# ==========================
def fetch_admin_requests():
    query = """
        SELECT *
        FROM admin_requests
        ORDER BY created_at DESC
    """
    db = get_db_connection()
    return pd.read_sql(query, db)

def update_admin_status(request_id, new_status):
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("""
        UPDATE admin_requests
        SET status = %s, updated_at = NOW()
        WHERE id = %s
    """, (new_status, request_id))
    db.commit()
    cursor.close()
    db.close()

def get_admin_stats(df):
    return {
        "total": len(df),
        "approved": len(df[df['status'] == "Approved"]),
        "paused": len(df[df['status'] == "Paused"])
    }

def fetch_admin_full_details():
    query = """
        SELECT 
            email,
            status,
            created_at,
            updated_at,
            company_name,
            gst_number,
            mobile,
            company_address AS address,
            upi_id,
            total_tables
        FROM admin_requests
        ORDER BY created_at DESC
    """
    db = get_db_connection()
    return pd.read_sql(query, db)



# 🔄 Auto refresh every 5 seconds
st_autorefresh(interval=5000, key="global_refresh")

# ==========================
# 🔹 Streamlit Tabs
# ==========================
st.title("Cafe Admin Dashboard")

tabs = st.tabs(["✏️ Dashboard", "📝 Admin Requests", "👤 Data", "🧾 Admin Details", "🆙 Bank Details"])

# --------------------------
# Dashboard Tab (enhanced)
# --------------------------
with tabs[0]:
    st.header("Dashboard")

    df_requests = fetch_admin_requests()

    if df_requests.empty:
        st.info("No admin data available.")
    else:
        # Normalize status
        df_requests['status'] = df_requests['status'].str.capitalize()

        stats = get_admin_stats(df_requests)
        col1, col2, col3 = st.columns(3)
        col1.metric(label="👥 Total Admin Requests", value=stats["total"])
        col2.metric(label="✅ Approved Admins", value=stats["approved"])
        col3.metric(label="⏸ Paused Admins", value=stats["paused"])

        st.markdown("---")
        st.subheader("Top Admin Performance")

        # Aggregate admin data
        if 'total_amount' in df_requests.columns:
            admin_summary = df_requests.groupby(['company_name', 'email']).agg(
                total_bills=pd.NamedAgg(column='id', aggfunc='count'),
                total_earning=pd.NamedAgg(column='total_amount', aggfunc='sum')
            ).sort_values('total_bills', ascending=False).reset_index()
        else:
            admin_summary = df_requests.groupby(['company_name', 'email']).agg(
                total_bills=pd.NamedAgg(column='id', aggfunc='count'),
                total_earning=pd.NamedAgg(column='id', aggfunc=lambda x: 0)
            ).sort_values('total_bills', ascending=False).reset_index()

        col1, col2 = st.columns(2)
     
        with col1:
           # Select the most used admin
           top_admin = admin_summary.iloc[0]
           st.markdown(
               f"**🌟 Top Admin: {top_admin['company_name']} ({top_admin['email']})**\n\n"
               f"**Total Bills:** {top_admin['total_bills']} | **Total Earnings:** ₹{top_admin['total_earning']}"
           )
   
           # Filter only top admin's requests
           top_admin_requests = df_requests[df_requests['company_name'] == top_admin['company_name']]
           top_admin_requests['created_date'] = top_admin_requests['created_at'].dt.date
   
           today = datetime.now().date()
           yesterday = today - pd.Timedelta(days=1)
   
           # Count bills and earnings
           bills_today = top_admin_requests[top_admin_requests['created_date'] == today].shape[0]
           earning_today = top_admin_requests[top_admin_requests['created_date'] == today]['total_amount'].sum() if 'total_amount' in top_admin_requests.columns else 0
   
           bills_yesterday = top_admin_requests[top_admin_requests['created_date'] == yesterday].shape[0]
           earning_yesterday = top_admin_requests[top_admin_requests['created_date'] == yesterday]['total_amount'].sum() if 'total_amount' in top_admin_requests.columns else 0
        with col2:
        # Plot chart
           fig, ax = plt.subplots(figsize=(6,4))
           ax.bar(['Yesterday', 'Today'], [bills_yesterday, bills_today], color=['skyblue','lightgreen'])
   
           # Show earnings on top
           ax.text(0, bills_yesterday + 0.05, f"₹{int(earning_yesterday)}", ha='center', va='bottom', fontsize=10)
           ax.text(1, bills_today + 0.05, f"₹{int(earning_today)}", ha='center', va='bottom', fontsize=10)
   
           ax.set_ylabel("Number of Bills")
           ax.set_title(f"{top_admin['company_name']}'s Requests: Yesterday vs Today")
           st.pyplot(fig)

   

# --------------------------
# Admin Requests Tab
# --------------------------
with tabs[1]:
    st.subheader("Admin Requests")

    df_requests = fetch_admin_requests()

    if df_requests.empty:
        st.info("No admin requests found.")
    else:
        # Normalize status just in case
        df_requests['status'] = df_requests['status'].str.capitalize()

        sub_tabs = st.tabs(["📝Pending", "✔️Approved", "⏸️Paused", "❌Cancelled"])

        # ---------------- Pending ----------------
        with sub_tabs[0]:
            st.subheader("📝Pending Requests")
        
            # 🔹 Search bar for Pending
            search_pending = st.text_input(
                "Search Pending Admin",
                placeholder="Enter name or email",
                key="search_pending"
            )
        
            pending_df = df_requests[df_requests['status'] == "Pending"]
        
            if search_pending.strip():
                pending_df = pending_df[
                    pending_df['company_name'].str.contains(search_pending, case=False, na=False) |
                    pending_df['email'].str.contains(search_pending, case=False, na=False)
                ]
        
            if pending_df.empty:
                st.info("No pending admin requests.")
            else:
                for _, row in pending_df.iterrows():
                    col1, col2, col3, col4, col5, col6 = st.columns([3,3,2,2,2,2])
        
                    col1.write(row['company_name'])
                    col2.write(row['email'])
        
                    # ✅ Approve
                    if col3.button("✅ Approve", key=f"approve_{row['id']}"):
                        update_admin_status(row['id'], "Approved")
                        st.success(f"{row['company_name']} approved")
                        st.rerun()
        
                    # ⏸ Pause Subscription
                    if col4.button("⏸ Pause", key=f"pause_{row['id']}"):
                        update_admin_status(row['id'], "Paused")
                        st.warning(f"{row['company_name']} paused")
                        st.rerun()
        
                    # ❌ Reject Request
                    if col5.button("❌ Reject", key=f"reject_{row['id']}"):
                        update_admin_status(row['id'], "Rejected")
                        st.error(f"{row['company_name']} rejected")
                        st.rerun()
        
                    # 🚫 Cancel Membership
                    if col6.button("🚫 Cancel", key=f"cancel_{row['id']}"):
                        update_admin_status(row['id'], "Cancelled")
                        st.error(f"{row['company_name']} membership cancelled")
                        st.rerun()
        
        

        # ---------------- Approved ----------------
        with sub_tabs[1]:
            st.subheader("✔️Approved Admins")
            # 🔹 Search bar for Approved Admins
            search_approved = st.text_input(
                "Search Approved Admin",
                placeholder="Enter name or email",
                key="search_approved"
            )
            approved_df = df_requests[df_requests['status'] == "Approved"]
            
            if search_approved.strip():
                approved_df = approved_df[
                    approved_df['company_name'].str.contains(search_approved, case=False) |
                    approved_df['email'].str.contains(search_approved, case=False)
                ]
        
            approved_df = df_requests[df_requests['status'] == "Approved"]
        
            if approved_df.empty:
                st.info("No approved admins.")
            else:
                for _, row in approved_df.iterrows():
                    col1, col2, col3, col4 = st.columns([3,3,2,2])
        
                    col1.write(row['company_name'])
                    col2.write(row['email'])
        
                    # ⏸ Pause
                    if col3.button("⏸ Pause", key=f"pause2_{row['id']}"):
                        update_admin_status(row['id'], "Paused")
                        st.warning(f"{row['company_name']} paused")
                        st.rerun()
        
                    # 🚫 Cancel
                    if col4.button("🚫 Cancel", key=f"cancel2_{row['id']}"):
                        update_admin_status(row['id'], "Cancelled")
                        st.error(f"{row['company_name']} cancelled")
                        st.rerun()
        
        

        # ---------------- Paused ----------------
        with sub_tabs[2]:
            st.subheader("⏸️Paused Admins")
            # 🔹 Search bar for Paused Admins
            search_paused = st.text_input(
                "Search Paused Admin",
                placeholder="Enter name or email",
                key="search_paused"
            )
            paused_df = df_requests[df_requests['status'] == "Paused"]
            
            if search_paused.strip():
                paused_df = paused_df[
                    paused_df['company_name'].str.contains(search_paused, case=False) |
                    paused_df['email'].str.contains(search_paused, case=False)
                ]
            paused_df = df_requests[df_requests['status'] == "Paused"]
        
            if paused_df.empty:
                st.info("No paused admins.")
            else:
                for _, row in paused_df.iterrows():
                    col1, col2, col3, col4 = st.columns([3,3,2,2])
        
                    col1.write(row['company_name'])
                    col2.write(row['email'])
        
                    # ▶ Resume
                    if col3.button("▶ Resume", key=f"resume_{row['id']}"):
                        update_admin_status(row['id'], "Approved")
                        st.success(f"{row['company_name']} resumed")
                        st.rerun()
        
                    # 🚫 Cancel
                    if col4.button("🚫 Cancel", key=f"final_cancel_{row['id']}"):
                        update_admin_status(row['id'], "Cancelled")
                        st.error(f"{row['company_name']} cancelled permanently")
                        st.rerun()
         
        # ---------------- Cancelled ----------------
        with sub_tabs[3]:
            st.subheader("❌Cancelled Admins")
        
            # 🔹 Search bar for Cancelled
            search_cancelled = st.text_input(
                "Search Cancelled Admin",
                placeholder="Enter name or email",
                key="search_cancelled"
            )
        
            cancelled_df = df_requests[df_requests['status'] == "Cancelled"]
        
            if search_cancelled.strip():
                cancelled_df = cancelled_df[
                    cancelled_df['company_name'].str.contains(search_cancelled, case=False, na=False) |
                    cancelled_df['email'].str.contains(search_cancelled, case=False, na=False)
                ]
        
            if cancelled_df.empty:
                st.info("No cancelled admins.")
            else:
                for _, row in cancelled_df.iterrows():
                    col1, col2, col3 = st.columns([3,3,2])
        
                    col1.write(row['company_name'])
                    col2.write(row['email'])
        
                    # ▶ Recover / Restore
                    if col3.button("▶ Recover", key=f"recover_{row['id']}"):
                        update_admin_status(row['id'], "Approved")
                        st.success(f"{row['company_name']} recovered and now Approved")
                        st.rerun()


# --------------------------
# Admin Details Tab
# --------------------------
with tabs[2]:
    st.header("👤 Admin Full Details")

    df_admins = fetch_admin_full_details()

    if df_admins.empty:
        st.info("No admin data found.")

    else: 
        # Search box
        search = st.text_input(
            "Search Admin (Name / Email / Company / GST / Mobile)",
            placeholder="Type to search..."
        )

        if search.strip():
            df_admins = df_admins[
                df_admins['company_name'].str.contains(search, case=False, na=False) |
                df_admins['email'].str.contains(search, case=False, na=False) |
                df_admins['gst_number'].str.contains(search, case=False, na=False) |
                df_admins['mobile'].astype(str).str.contains(search, na=False)
            ]

        # Display final table
        st.dataframe(
            df_admins[['email','mobile','company_name','total_tables','gst_number','address','status','created_at','updated_at']],
            use_container_width=True,
            hide_index=True
        )

# --------------------------
# Company Dashboard Tab
# --------------------------
with tabs[3]:
    st.header("🏢 Company Dashboard")
    
    # Fetch all admins
    df_admins = fetch_admin_full_details()
    
    if df_admins.empty:
        st.info("No companies found.")
    else:
        # Search
        search = st.text_input("Search Company / Email", placeholder="Type to search...", key="search_company_dashboard")
        if search.strip():
            df_admins = df_admins[
                df_admins['company_name'].str.contains(search, case=False, na=False) |
                df_admins['email'].str.contains(search, case=False, na=False)
            ]
        
        # Loop through companies
        for _, row in df_admins.iterrows():
            company_name = row['company_name']
            email = row['email']

            # Expandable section per company
            with st.expander(f"{company_name} ({email})"):

                # Create sub-tabs inside expander
                company_subtabs = st.tabs(["📋 Menu", "🧾 Orders", "🏢 Company Details"])
                
                db = get_db_connection()
                cursor = db.cursor(dictionary=True)

                # ---------------- Menu ----------------
                with company_subtabs[0]:
                    cursor.execute("""
                        SELECT id, name, price
                        FROM menu_items
                        WHERE email=%s
                    """, (email,))
                    menu_items = cursor.fetchall()
                    menu_df = pd.DataFrame(menu_items)
                    
                    if menu_df.empty:
                        st.info("No menu items found.")
                    else:
                        st.write(f"Total Items: {len(menu_df)}")
                        st.dataframe(menu_df[['name','price']], use_container_width=True)

                # ---------------- Orders ----------------
                with company_subtabs[1]:
                    order_statuses = ["PENDING", "COMPLETED", "CANCELLED"]
                    order_labels = ["Pending", "Completed", "Cancelled"]
                    orders_tabs = st.tabs(order_labels)
                    
                    for idx, status in enumerate(order_statuses):
                        with orders_tabs[idx]:
                            cursor.execute("""
                                SELECT o.id AS order_id, o.customer_name, o.total_amount, o.status, o.order_time
                                FROM orders o
                                JOIN order_items oi ON o.id = oi.order_id
                                JOIN menu_items m ON oi.menu_id = m.id
                                WHERE m.email=%s AND o.status=%s
                                ORDER BY o.order_time DESC
                            """, (email, status))
                            orders = cursor.fetchall()
                            orders_df = pd.DataFrame(orders)

                            if orders_df.empty:
                                st.info(f"No {status.lower()} orders.")
                            else:
                                st.write(f"Total Orders: {len(orders_df)}")
                                st.write(f"Total Earnings: ₹{orders_df['total_amount'].sum()}")
                                st.dataframe(
                                    orders_df[['order_id','customer_name','total_amount','status','order_time']],
                                    use_container_width=True
                                )

                # ---------------- Company Details ----------------
                with company_subtabs[2]:
                    st.write(f"**Company Name:** {company_name}")
                    st.write(f"**Email:** {email}")
                    st.write(f"**GST Number:** {row['gst_number']}")
                    st.write(f"**Mobile:** {row['mobile']}")
                    st.write(f"**Address:** {row['address']}")
                    st.write(f"**UPI ID:** {row.get('upi_id','Not Configured')}")

                    # Optional: Generate UPI QR Code
                    if row.get('upi_id'):
                        import qrcode, io
                        upi_url = f"upi://pay?pa={row['upi_id']}&pn={urllib.parse.quote(company_name)}&cu=INR"
                        qr = qrcode.QRCode(version=1, box_size=6, border=2)
                        qr.add_data(upi_url)
                        qr.make(fit=True)
                        img = qr.make_image(fill_color="black", back_color="white")
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        st.image(buf.getvalue(), caption="UPI QR Code", width=150)

                cursor.close()
                db.close()

# --------------------------
# 5️⃣ Founder UPI Tab
# --------------------------
with tabs[4]:
    st.header("🆙 Founder UPI")

    # Fetch the first (or only) admin record to store UPI info
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, upi_id_founder, upi_qr_image_founder FROM admin_requests LIMIT 1")
    row = cursor.fetchone()
    cursor.close()
    db.close()

    # UPI ID input
    upi_input = st.text_input(
        "Founder UPI ID",
        value=row['upi_id_founder'] if row else "",
        key="upi_input"
    )

    # UPI QR upload
    qr_upload = st.file_uploader(
        "Upload Founder UPI QR",
        type=['png', 'jpg', 'jpeg'],
        key="upi_qr_upload"
    )

    # Save button
    if st.button("💾 Save UPI"):
        db = get_db_connection()
        cursor = db.cursor()
        qr_bytes = qr_upload.read() if qr_upload else None
        cursor.execute("""
            UPDATE admin_requests
            SET upi_id_founder=%s, upi_qr_image_founder=%s, updated_at=NOW()
            WHERE id=%s
        """, (upi_input, qr_bytes, row['id']))
        db.commit()
        cursor.close()
        db.close()
        st.success("Founder UPI saved!")
        st.experimental_rerun()

    # Display saved QR
    if row and row['upi_qr_image_founder']:
        st.image(row['upi_qr_image_founder'], caption="Saved Founder UPI QR", width=150)



