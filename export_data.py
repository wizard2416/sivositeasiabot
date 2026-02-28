import os
import psycopg2
from datetime import datetime

DATABASE_URL = os.environ.get('DATABASE_URL')

def export_table(cursor, table_name, output_file):
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()
    
    if not rows:
        output_file.write(f"-- No data in {table_name}\n\n")
        return
    
    cursor.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}' ORDER BY ordinal_position")
    columns = [row[0] for row in cursor.fetchall()]
    
    output_file.write(f"-- {table_name}: {len(rows)} rows\n")
    
    for row in rows:
        values = []
        for val in row:
            if val is None:
                values.append('NULL')
            elif isinstance(val, str):
                escaped = val.replace("'", "''")
                values.append(f"'{escaped}'")
            elif isinstance(val, bool):
                values.append('TRUE' if val else 'FALSE')
            elif isinstance(val, datetime):
                values.append(f"'{val.isoformat()}'")
            else:
                values.append(str(val))
        
        cols_str = ', '.join(columns)
        vals_str = ', '.join(values)
        output_file.write(f"INSERT INTO {table_name} ({cols_str}) VALUES ({vals_str}) ON CONFLICT DO NOTHING;\n")
    
    output_file.write("\n")

def main():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    tables = ['users', 'cards', 'xena_orders', 'payment_requests', 'phones', 'coin_rates', 'settings', 'balance_transactions']
    
    with open('production_data_export.sql', 'w', encoding='utf-8') as f:
        f.write(f"-- Data Export from Development Database\n")
        f.write(f"-- Generated: {datetime.now().isoformat()}\n")
        f.write("-- Run this in your PRODUCTION database after publishing\n\n")
        
        for table in tables:
            try:
                export_table(cursor, table, f)
                print(f"Exported {table}")
            except Exception as e:
                print(f"Error exporting {table}: {e}")
    
    conn.close()
    print("\nExport complete: production_data_export.sql")

if __name__ == "__main__":
    main()
