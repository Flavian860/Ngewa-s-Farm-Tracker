from datetime import datetime
import sqlite3
import pandas as pd
import streamlit as st

DB_NAME = "farm_tracker.db"


def get_connection():
  return sqlite3.connect(DB_NAME, check_same_thread=False)


def initialize_database():
  """Sets up the SQLite database and populates initial farms and categories."""
  conn = get_connection()
  cursor = conn.cursor()

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS farms (
            farm_id INTEGER PRIMARY KEY AUTOINCREMENT,
            farm_name TEXT UNIQUE NOT NULL,
            location TEXT
        )
    """)

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            category_id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name TEXT NOT NULL,
            type TEXT CHECK(type IN ('Income', 'Expenditure')) NOT NULL,
            sector TEXT CHECK(sector IN ('Crops', 'Livestock', 'General')) NOT NULL
        )
    """)

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            farm_id INTEGER,
            category_id INTEGER,
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            description TEXT,
            FOREIGN KEY (farm_id) REFERENCES farms (farm_id),
            FOREIGN KEY (category_id) REFERENCES categories (category_id)
        )
    """)

  # Seed your 5 specific farms
  farms = [
      ("Mavui", "Location 1"),
      ("Kasong'e", "Location 2"),
      ("Kithambioni", "Location 3"),
      ("TT", "Location 4"),
      ("Kairungu", "Location 5"),
  ]
  cursor.executemany(
      """
        INSERT OR IGNORE INTO farms (farm_name, location) VALUES (?, ?)
    """,
      farms,
  )

  # Seed categories
  categories = [
      ("Crop Sales", "Income", "Crops"),
      ("Livestock & Produce Sales", "Income", "Livestock"),
      ("Seeds & Seedlings", "Expenditure", "Crops"),
      ("Fertilizers & Chemicals", "Expenditure", "Crops"),
      ("Crop Labor", "Expenditure", "Crops"),
      ("Animal Feed", "Expenditure", "Livestock"),
      ("Veterinary & Medicine", "Expenditure", "Livestock"),
      ("Livestock Labor", "Expenditure", "Livestock"),
      ("Equipment & Maintenance", "Expenditure", "General"),
      ("Utilities (Water/Power)", "Expenditure", "General"),
  ]
  cursor.executemany(
      """
        INSERT OR IGNORE INTO categories (category_name, type, sector) VALUES (?, ?, ?)
    """,
      categories,
  )

  conn.commit()
  conn.close()


# Initialize DB on load
initialize_database()

# --- STREAMLIT UI ---
st.set_page_config(
    page_title="Multi-Farm Tracker", page_icon="🌾", layout="wide"
)

st.title("🌾 Multi-Farm Management Dashboard")
st.markdown(
    "Track expenditures, incomes, and net profits across Mavui, Kasong'e,"
    " Kithambioni, TT, and Kairungu."
)

# Sidebar Navigation
menu = st.sidebar.selectbox(
    "Navigation", ["Dashboard & Reports", "Add Transaction", "Manage Data"]
)

conn = get_connection()

# Fetch dropdown options for farms
farms_df = pd.read_sql("SELECT farm_name FROM farms", conn)

if menu == "Dashboard & Reports":
  st.header("📊 Financial Summary")

  # Fetch transactions with joined data
  query = """
        SELECT 
            f.farm_name,
            c.type,
            c.sector,
            t.amount,
            t.date,
            c.category_name,
            t.description
        FROM transactions t
        JOIN farms f ON t.farm_id = f.farm_id
        JOIN categories c ON t.category_id = c.category_id
    """
  df = pd.read_sql(query, conn)

  if df.empty:
    st.info(
        "No transactions recorded yet. Go to 'Add Transaction' to log your first"
        " entry."
    )
  else:
    # High-level metrics
    total_income = df[df["type"] == "Income"]["amount"].sum()
    total_exp = df[df["type"] == "Expenditure"]["amount"].sum()
    net_profit = total_income - total_exp

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Income", f"KSH{total_income:,.2f}")
    col2.metric("Total Expenditure", f"KSH{total_exp:,.2f}")
    col3.metric("Net Profit", f"KSH{net_profit:,.2f}")

    st.markdown("---")

    # Pivot table breakdown by Farm
    st.subheader("Performance by Farm Location")
    pivot = (
        df.pivot_table(
            index="farm_name", columns="type", values="amount", aggfunc="sum"
        )
        .fillna(0)
        .reset_index()
    )

    if "Income" not in pivot.columns:
      pivot["Income"] = 0
    if "Expenditure" not in pivot.columns:
      pivot["Expenditure"] = 0

    pivot["Net Profit"] = pivot["Income"] - pivot["Expenditure"]

    # Display as a formatted table
    st.dataframe(pivot.style.format({"Income": "KSH{:,.2f}", "Expenditure": "KSH{:,.2f}", "Net Profit": "KSH{:,.2f}"}), use_container_width=True)

    # Detailed logs
    st.subheader("Recent Transactions Log")
    st.dataframe(df.sort_values(by="date", ascending=False), use_container_width=True)

elif menu == "Add Transaction":
  st.header("➕ Record Income or Expenditure")

  # Let's keep transaction type outside the form so it refreshes instantly when clicked
  selected_farm = st.selectbox(
      "Select Farm Location", farms_df["farm_name"].tolist()
  )
  transaction_type = st.radio("Transaction Type", ["Income", "Expenditure"])

  # Strict separation of categories based on selection
  if transaction_type == "Income":
    filtered_cats = ["Crop Sales", "Livestock & Produce Sales"]
  else:
    filtered_cats = [
        "Seeds & Seedlings",
        "Fertilizers & Chemicals",
        "Crop Labor",
        "Animal Feed",
        "Veterinary & Medicine",
        "Livestock Labor",
        "Equipment & Maintenance",
        "Utilities (Water/Power)",
    ]

  with st.form("transaction_form"):
    selected_category = st.selectbox("Category", filtered_cats)
    amount = st.number_input("Amount", min_value=0.0, step=10.0)
    date = st.date_input("Date", datetime.today())
    description = st.text_area(
        "Description / Notes (Optional)",
        placeholder="e.g., Bought fertilizer for Mavui",
    )

    submit = st.form_submit_button("Save Transaction")

    if submit:
      cursor = conn.cursor()
      f_id = cursor.execute(
          "SELECT farm_id FROM farms WHERE farm_name = ?", (selected_farm,)
      ).fetchone()[0]
      c_id = cursor.execute(
          "SELECT category_id FROM categories WHERE category_name = ?",
          (selected_category,),
      ).fetchone()[0]

      cursor.execute(
          """
                INSERT INTO transactions (farm_id, category_id, amount, date, description)
                VALUES (?, ?, ?, ?, ?)
            """,
          (f_id, c_id, amount, str(date), description),
      )
      conn.commit()
      st.success(
          f"Successfully recorded amount {amount:,.2f} under"
          f" {selected_category} for {selected_farm}!"
      )

elif menu == "Manage Data":
  st.header("⚙️ Farm & Data Management")
  st.subheader("Your Farm Locations")
  farms_full = pd.read_sql("SELECT * FROM farms", conn)
  st.dataframe(farms_full, use_container_width=True)

  st.markdown("### Update Farm Details")
  with st.form("update_farm"):
    f_to_update = st.selectbox(
        "Choose Farm to Update", farms_full["farm_name"].tolist()
    )
    new_name = st.text_input("New Farm Name")
    new_loc = st.text_input("New Location/Region")
    update_btn = st.form_submit_button("Update Details")

    if update_btn and new_name:
      cursor = conn.cursor()
      cursor.execute(
          "UPDATE farms SET farm_name = ?, location = ? WHERE farm_name = ?",
          (new_name, new_loc, f_to_update),
      )
      conn.commit()
      st.success("Farm details updated successfully! Please refresh.")

conn.close()
# --- DELETE TRANSACTION SECTION ---
st.markdown("---")
st.subheader("🗑️ Delete a Transaction")

# Connect to database
conn = get_connection()
cursor = conn.cursor()

# Fetch transactions with proper table joins matching your database
query = """
    SELECT t.transaction_id, f.farm_name, c.type, c.category_name, t.amount, t.date 
    FROM transactions t 
    JOIN farms f ON t.farm_id = f.farm_id 
    JOIN categories c ON t.category_id = c.category_id
    ORDER BY t.date DESC
"""
cursor.execute(query)
records = cursor.fetchall()

if records:
  # Create a clean dropdown list mapping transaction details to their unique ID
  options = {
      f"ID {r[0]} | {r[1]} | {r[2]} - {r[3]} | ${r[4]:,.2f} ({r[5]})": r[0]
      for r in records
  }
  selected_record = st.selectbox(
      "Select a transaction to delete", options=list(options.keys())
  )

  if st.button("Delete Transaction", type="primary"):
    record_id = options[selected_record]
    cursor.execute(
        "DELETE FROM transactions WHERE transaction_id = ?", (record_id,)
    )
    conn.commit()
    st.success(f"Successfully deleted transaction ID {record_id}!")
    st.rerun()
else:
  st.info("No transactions available to delete.")

conn.close()
