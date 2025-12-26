import os
import sys
import sqlite3


CUR_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(CUR_DIR)
sys.path.append(SRC_DIR)


from tib_utility.db_utils import cursor, database, get_all_users, get_linked_pxls_username, get_linked_discord_username, CANVAS_REGEX, KEY_REGEX
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
    
    # links all usernames w/ each-other (case-sensitive)
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


def resolve_user_gui(identifier: str):
    identifier = identifier.strip()
    if identifier.isdigit() and len(identifier) > 16:
        return int(identifier)

    linked_id = get_linked_pxls_username(identifier)
    if linked_id:
        return int(linked_id)
    return None


def logkey_add(): # /admin force-add but GUI form!
    top = tkinter.Toplevel(root)
    top.title("Add logkeys")
    top.geometry("600x450")

    tkinter.Label(top, text="Format 1: User(linked name or Discord ID),53,88a,94\nFormat 2: 56a,User1,User2,User3", justify="left").pack(pady=5)
    tkinter.Label(top, text="User/Canvas List(CSV style):").pack(anchor='w', padx=10)
    entry_targets = tkinter.Entry(top, width=80)
    entry_targets.pack(padx=10, pady=5)

    tkinter.Label(top, text="Keys (CSV style)").pack(anchor='w', padx=10)
    text_keys = tkinter.Text(top, height=10, width=60)
    text_keys.pack(padx=10, pady=5)

    def submit_key():
        raw_target = entry_targets.get()
        raw_key = text_keys.get("1.0", "end-1c")
        if not raw_target or not raw_key:
            messagebox.showwarning("Error", "Fill both fields!")
            return
        user_canvases = [x.strip() for x in raw_target.split(",") if x.strip()]
        keys = [x.strip() for x in raw_key.split(",") if x.strip()]
        if len(user_canvases) < 2:
            messagebox.showwarning("Error", "You must provide at least one user and canvas.")
            return

        query_logkey = "INSERT OR REPLACE INTO logkey VALUES (?, ?, ?)"
        query_user = "INSERT OR IGNORE INTO users (user_id) VALUES (?)"
        try:
            first_item = user_canvases[0]
            is_canvas_many = not CANVAS_REGEX.fullmatch(first_item)

            if is_canvas_many:  # one user, multiple canvases
                user_input = user_canvases[0]
                canvases = user_canvases[1:]
                user_id = resolve_user_gui(user_input)
                if not user_id:
                    messagebox.showerror("Error", f"Could not find a linked name for {user_input}. Are you sure you typed it correctly or that they\'re linked?")
                    return
                if len(keys) != len(canvases):
                    messagebox.showerror("Error", "The number of keys must match the number of canvases.")
                    return
                success = []
                fail = []
                for canvas, key in zip(canvases, keys):
                    if not CANVAS_REGEX.fullmatch(canvas):
                        fail.append(f"c{canvas}, Invalid canvas format")
                        continue
                    if not KEY_REGEX.fullmatch(key):
                        fail.append(f"c{canvas}, Invalid key format")
                        continue
                    try:
                        cursor.execute(query_logkey, (user_id, canvas, key))
                        cursor.execute(query_user, (user_id,))
                        database.commit()
                        success.append(f"c{canvas}")
                    except sqlite3.OperationalError as e:
                        fail.append(f"c{canvas}, SQLite error: {e}")
                    except Exception as e:
                        fail.append(f"c{canvas}, Error: {e}")
                find_username = get_linked_discord_username(user_id)
                message = f"{find_username} ({user_id}) now has keys for canvases: {', '.join(success)}"
                if fail:
                    message += f"\nFailed for canvases: {', '.join(fail)}"
                messagebox.showinfo("Result", message)
                print(message)

            else: # one canvas, multiple users
                canvas = user_canvases[0]
                user_inputs = user_canvases[1:]
                if len(keys) != len(user_inputs):
                    messagebox.showerror("Error", "The number of keys must match the number of canvases.")
                    return
                success = []
                fail = []
                for user_input, key in zip(user_inputs, keys):
                    user_id = resolve_user_gui(user_input)
                    if not user_id:
                        fail.append(f"{user_input}, Invalid user format")
                    if not KEY_REGEX.fullmatch(key):
                        fail.append(f"c{user_input}, Invalid key format")
                        continue
                    try:
                        cursor.execute(query_logkey, (user_id, canvas, key))
                        cursor.execute(query_user, (user_id,))
                        database.commit()
                        success.append(f"c{canvas}")
                    except sqlite3.OperationalError as e:
                        fail.append(f"c{canvas}, SQLite error: {e}")
                    except Exception as e:
                        fail.append(f"c{canvas}, Error: {e}")
                message = f"c{canvas} now has logkeys for: {', '.join(success)}"
                if fail:
                    message += f"\nFailed for canvases: {', '.join(fail)}"
                messagebox.showinfo("Result", message)
                print(message)
        except Exception as e:
            messagebox.showerror("Error", "Something went wrong, check the console.")
            print(f'An error occurred: {e}')
    submit_btn = tkinter.Button(top, text="Submit Logkeys", command=submit_key, bg="#dddddd")
    submit_btn.pack(pady=15)


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

button_frame = tkinter.Frame(outer_frame)
button_frame.pack(pady=10)

refresh_button = tkinter.Button(button_frame, text="Refresh Data", command=refresh_data)
refresh_button.pack(side='left', pady=10)

add_key_button = tkinter.Button(button_frame, text="Add Logkeys", command=logkey_add)
add_key_button.pack(side='left', pady=10)
refresh_data()

root.mainloop()