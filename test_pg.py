import psycopg2

try:
    print("Testing Azure PostgreSQL connection...")
    conn = psycopg2.connect(
        host="matchmaticaldb.postgres.database.azure.com",
        database="postgres",
        user="mmadmin",  # Try without @server suffix first
        password="matches1234!!",
        port=5432,
        sslmode="require"
    )
    print("✅ Connection successful!")
    conn.close()
except Exception as e:
    print("❌ Connection failed:", e)
    
    # Try with @server suffix
    try:
        print("Trying with @server suffix...")
        conn = psycopg2.connect(
            host="matchmaticaldb.postgres.database.azure.com",
            database="postgres",
            user="mmadmin@matchmaticaldb",
            password="matches1234!!",
            port=5432,
            sslmode="require"
        )
        print("✅ Connection successful with @server suffix!")
        conn.close()
    except Exception as e2:
        print("❌ Also failed with @server suffix:", e2)