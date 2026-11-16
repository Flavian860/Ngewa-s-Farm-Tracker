from datetime import datetime
import pandas as pd
import streamlit as st

# --- CONFIG & DATABASE CONNECTION ---
st.set_page_config(
    page_title="Multi-Farm Tracker (Live)", page_icon="🌾", layout="wide"
)


@st.cache_resource
def get_cloud_connection():
  """Connects to a shared cloud database (or falls back to local SQLite)"""
  db_url = st.secrets.get("DATABASE_URL", "sqlite:///farm_tracker.db")

  if db_url.startswith("sqlite"):
    import sqlite3

    return sqlite3.connect("farm_tracker.db", check_same_thread=False)
  else:
    import psycopg2

    return psycopg2.connect(db_url)


def initialize_database():
  """Sets up database tables and seeds initial data if they don't exist."""
  conn = get_cloud_connection()
  cursor = conn.cursor()

  is_postgres = not hasattr(conn, "isolation_level")

  if is_postgres:
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS farms (
                farm_id SERIAL PRIMARY KEY,
                farm_name TEXT UNIQUE NOT NULL,
                location TEXT
            )
        """)
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                category_id SERIAL PRIMARY KEY,
                category_name TEXT NOT NULL,
                type TEXT CHECK(type IN ('Income', 'Expenditure')) NOT NULL,
                sector TEXT CHECK(sector IN ('Crops', 'Livestock', 'General')) NOT NULL
            )
        """)
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id SERIAL PRIMARY KEY,
                farm_id INTEGER REFERENCES farms(farm_id),
                category_id INTEGER REFERENCES categories(category_id),
                amount REAL NOT NULL,
                date TEXT NOT NULL,
                description TEXT
            )
        """)
  else:
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

  # Seed initial farms
  farms = [
      ("Mavui", "Location 1"),
      ("Kasong'e", "Location 2"),
      ("Kithambioni", "Location 3"),
      ("TT", "Location 4"),
      ("Kairungu", "Location 5"),
  ]
  for f_name, f_loc in farms:
    if is_postgres:
      cursor.execute(
          "INSERT INTO farms (farm_name, location) VALUES (%s, %s) ON CONFLICT"
          " (farm_name) DO NOTHING",
          (f_name, f_loc),
      )
    else:
      cursor.execute(
          "INSERT OR IGNORE INTO farms (farm_name, location) VALUES (?, ?)",
          (f_name, f_loc),
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
  for c_name, c_type, c_sec in categories:
    if is_postgres:
      cursor.execute(
          "INSERT INTO categories (category_name, type, sector) VALUES (%s,"
          " %s, %s) ON CONFLICT DO NOTHING",
          (c_name, c_type, c_sec),
      )
    else:
      cursor.execute(
          "INSERT OR IGNORE INTO categories (category_name, type, sector)"
          " VALUES (?, ?, ?)",
          (c_name, c_type, c_sec),
      )

  conn.commit()
  cursor.close()


initialize_database()

# --- STREAMLIT UI ---
st.title("🌾 Multi-Farm Management Dashboard (Live Sync)")
st.write(
    "Any updates made by any team member instantly reflect here for everyone."
)

menu = st.sidebar.selectbox(
    "Navigation", ["Dashboard & Reports", "Add Transaction", "Manage Data"]
)
conn = get_cloud_connection()

farms_df = pd.read_sql("SELECT farm_name FROM farms", conn)

if menu == "Dashboard & Reports":
  st.header("📊 Live Financial Summary")

  query = """
        SELECT f.farm_name, c.type, c.sector, t.amount, t.date, c.category_name, t.description 
        FROM transactions t 
        JOIN farms f ON t.farm_id = f.farm_id 
        JOIN categories c ON t.category_id = c.category_id
    """
  df = pd.read_sql(query, conn)

  if df.empty:
    st.info(
        "No transactions recorded yet. Go to 'Add Transaction' to log an entry."
    )
  else:
    total_income = df[df["type"] == "Income"]["amount"].sum()
    total_exp = df[df["type"] == "Expenditure"]["amount"].sum()
    net_profit = total_income - total_exp

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Income", f"KSH{total_income:,.2f}")
    col2.metric("Total Expenditure", f"KSH{total_exp:,.2f}")
    col3.metric("Net Profit", f"KSH{net_profit:,.2f}")

    st.markdown("---")
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

    st.dataframe(
        pivot.style.format({
            "Income": "KSH{:,.2f}",
            "Expenditure": "KSH{:,.2f}",
            "Net Profit": "KSH{:,.2f}",
        }),
        use_container_width=True,
    )

    st.subheader("Recent Transactions Log")
    st.dataframe(
        df.sort_values(by="date", ascending=False), use_container_width=True
    )

elif menu == "Add Transaction":
  st.header("➕ Record Income or Expenditure")

  selected_farm = st.selectbox(
      "Select Farm Location", farms_df["farm_name"].tolist()
  )
  transaction_type = st.radio("Transaction Type", ["Income", "Expenditure"])

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
      ph = "%s" if not hasattr(conn, "isolation_level") else "?"

      cursor.execute(
          f"SELECT farm_id FROM farms WHERE farm_name = {ph}", (selected_farm,)
      )
      f_id = cursor.fetchone()[0]

      cursor.execute(
          f"SELECT category_id FROM categories WHERE category_name = {ph}",
          (selected_category,),
      )
      c_id = cursor.fetchone()[0]

      insert_query = f"""
                INSERT INTO transactions (farm_id, category_id, amount, date, description) 
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
            """
      cursor.execute(
          insert_query, (f_id, c_id, amount, str(date), description)
      )
      conn.commit()
      cursor.close()
      st.success(
          f"Successfully recorded amount {amount:,.2f} under"
          f" {selected_category} for {selected_farm}!"
      )
      st.rerun()

elif menu == "Manage Data":
  st.header("⚙️ Farm & Data Management")
  st.subheader("Your Farm Locations")
  farms_full = pd.read_sql("SELECT * FROM farms", conn)
  st.dataframe(farms_full, use_container_width=True)

  st.markdown("---")
  st.subheader("🗑️ Delete a Transaction")

  query = """
        SELECT t.transaction_id, f.farm_name, c.type, c.category_name, t.amount, t.date 
        FROM transactions t 
        JOIN farms f ON t.farm_id = f.farm_id 
        JOIN categories c ON t.category_id = c.category_id 
        ORDER BY t.date DESC
    """
  records_df = pd.read_sql(query, conn)

  if not records_df.empty:
    options = {
        f"ID {r.transaction_id} | {r.farm_name} | {r.type} - {r.category_name} | KSH {r.amount:,.2f} ({r.date})": r.transaction_id
        for _, r in records_df.iterrows()
    }
    selected_record = st.selectbox(
        "Select a transaction to delete", options=list(options.keys())
    )

    if st.button("Delete Transaction", type="primary"):
      record_id = options[selected_record]
      cursor = conn.cursor()
      ph = "%s" if not hasattr(conn, "isolation_level") else "?"
      cursor.execute(
          f"DELETE FROM transactions WHERE transaction_id = {ph}", (record_id,)
      )
      conn.commit()
      cursor.close()
      st.success(f"Successfully deleted transaction ID {record_id}!")
      st.rerun()
  else:
    st.info("No transactions available to delete.")
