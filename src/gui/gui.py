import os
import sys
CUR_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(CUR_DIR)
sys.path.append(SRC_DIR)

from utils.db_utils import cursor, database, get_all_users
import tkinter
from tkinter import messagebox, ttk


def find_data():
    """Find all userdata in the DB."""
    users = get_all_users()
    users_db_data = {str(row[1]): row[0] for row in users} # since this returns (user_id, username)
    
    pixel_query = "SELECT user, SUM(pixels) as total_all FROM points GROUP BY user"
    cursor.execute(pixel_query)
    pixels_db_data = {str(row[0]): row[1] for row in cursor.fetchall()} # since this returns (user, pixels)
    
    all_pixels = set(users_db_data.keys()) | set(pixels_db_data.keys())
    
    results = []
    
    # links all usernames w/ eachother (case sensitive)
    # if there's no associated user_id, it shows as 'Unknown'
    for name in all_pixels:
        found_user_id = users_db_data.get(name, 'Unknown')
        found_pixels = pixels_db_data.get(name, 0)
        results.append((found_user_id, name, found_pixels))
    results.sort(key=lambda x: x[2], reverse=True)
    return results

def refresh_data():
    """Query the DB to refresh stats."""
    data = find_data()
    for row in tree.get_children():
        tree.delete(row)
    for row in data:
        tree.insert('', 'end', values=row)

root = tkinter.Tk()
root.title("Tib Admin Panel")
root.geometry("500x400")

label = tkinter.Label(root, text="Welcome to Tib's Admin Panel, free from the clasps of Discord!")
label.pack(pady=20)

# table + button
outer_frame = tkinter.Frame(root)
outer_frame.pack(side='left', anchor='n', padx=10, pady=10)

# just table
table_frame = tkinter.Frame(outer_frame)
table_frame.pack()

# needs to be defined otherwise the tree def gets mad
scrollbar = tkinter.Scrollbar(table_frame)

# creates the table
columns = ('user_id', 'username', 'pixels')
tree = ttk.Treeview(table_frame, columns=columns, show='headings', yscrollcommand=scrollbar.set)

tree.heading('user_id', text='User ID')
tree.column('user_id', width=130)
tree.heading('username', text='Username')
tree.column('username', width=130)
tree.heading('pixels', text='Total Pixels')
tree.column('pixels', width=100)
tree.pack(side='left', fill='y')

# done last so the scrollbar lands correctly
scrollbar.config(command=tree.yview)
scrollbar.pack(side='left', fill='y')

refresh_button = tkinter.Button(outer_frame, text="Refresh Data", command=refresh_data)
refresh_button.pack(pady=10)
refresh_data()

root.mainloop()