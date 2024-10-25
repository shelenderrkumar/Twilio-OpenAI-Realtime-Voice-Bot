import sqlite3

# Create or connect to a SQLite database
def connect_db(db_name='tracking.db'):
    conn = sqlite3.connect(db_name)
    return conn

# Check if the table exists
def table_exists(cursor, table_name):
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return cursor.fetchone() is not None

# Create a table in the database if it does not exist
def create_table():
    conn = connect_db()
    cursor = conn.cursor()
    
    if not table_exists(cursor, 'tracking'):
        cursor.execute('''
            CREATE TABLE tracking (
                tracking_number TEXT PRIMARY KEY,
                status TEXT NOT NULL
            )
        ''')
        print("Table 'tracking' created.")
    else:
        print("Table 'tracking' already exists.")
        
    conn.commit()
    conn.close()

# Function to insert tracking number and status
def insert_tracking(tracking_number, status):
    # Ensure the table exists before inserting
    create_table()
    
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO tracking (tracking_number, status)
        VALUES (?, ?)
    ''', (tracking_number, status))
    conn.commit()
    conn.close()

# Function to fetch status by tracking number
def fetch_status(tracking_number):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT status FROM tracking WHERE tracking_number = ?
    ''', (tracking_number,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return result[0]
    else:
        return 'Tracking number not found.'
