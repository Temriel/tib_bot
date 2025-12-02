import sqlite3
import asyncio
import csv
import glob
import os
import re
import time
from typing import Union, Optional
import discord
from PIL import Image
import utils.config as config

CUR_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(CUR_DIR)
ROOT_DIR = os.path.dirname(SRC_DIR)
DB_PATH = os.path.join(SRC_DIR, 'database.db')

database = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = database.cursor()
database.execute('CREATE TABLE IF NOT EXISTS notif (user_id INT PRIMARY KEY, status BOOLEAN, FOREIGN KEY (user_id) REFERENCES users(user_id))')
database.execute('CREATE TABLE IF NOT EXISTS points(user STR, canvas STR, pixels INT, PRIMARY KEY (user, canvas))')
database.execute('CREATE TABLE IF NOT EXISTS users (user_id INT, username STR UNIQUE, PRIMARY KEY (user_id))')
database.execute('CREATE TABLE IF NOT EXISTS logkey(user INT, canvas STR, key STR, PRIMARY KEY (user, canvas))')

semaphore = asyncio.Semaphore(3)

def get_linked_discord_username(user_id: int):
    """Get the linked Pxls username for a given Discord user ID."""
    query = "SELECT username FROM users WHERE user_id = ?"
    cursor.execute(query, (user_id,))
    result = cursor.fetchone()
    return result[0] if result else None

def get_linked_pxls_username(pxls_username: str):
    """Get the linked Discord user for a given Pxls username."""
    query = "SELECT user_id FROM users WHERE username = ?"
    cursor.execute(query, (pxls_username,))
    result = cursor.fetchone()
    return result [0] if result else None

def get_stats(pxls_username: str) -> dict:
    """Get pixel stats for a given Pxls username."""
    query = "SELECT SUM(pixels) FROM points WHERE user = ?"
    cursor.execute(query, (pxls_username,))
    total = cursor.fetchone()[0] or 0
    rank = "nothing"
    if total is None:
        total = 0
    if total < 0:
        rank = "griefer"
    ranks = config.ranks()
    for threshold, name in ranks:
        if total >= threshold:
            rank = name
            break
    return {'total': total, 'rank': rank}

async def render(user: Union[discord.User, discord.Member], canvas: str, mode: str, user_log_file: str) -> tuple[asyncio.subprocess.Process, str, str]:
    """Render a placemap from a log file. Uses pxlslog-explorer render.exe."""
    bg, palette_path, output_path = config.paths(canvas, user.id, mode)
    ple_dir = config.pxlslog_explorer_dir
    render_cli = [f'{ple_dir}/render.exe', '--log', user_log_file, '--bg', bg, '--palette', palette_path, '--screenshot', '--output', output_path, mode]
    # render_result = subprocess.run(render_cli, capture_output=True, text=True) # use for error handling
    render_result = await asyncio.create_subprocess_exec(
        *render_cli, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    print(f'Generating {mode} placemap for {user} on canvas {canvas}')
    stdout, stderr = await render_result.communicate()
    stdout_str = stdout.decode('utf-8').strip()
    stderr_str = stderr.decode('utf-8').strip()
    print(f'Subprocess output: {stdout_str}')
    print(f'Subprocess error: {stderr_str}')
    # print(f'Final command list: {render_cli}') # use for error handling
    filename = f'c{canvas}_{mode}_{user.id}.png'
    return render_result, filename, output_path

async def gpl_palette(palette_path: str) -> list[tuple[int, int, int]]:
    """Find palette RGB from a .gpl file."""
    palette = []
    with open(palette_path, 'r') as f:
        for line in f:
            if line.startswith(('GIMP', 'Name', 'Columns', '#')):
                continue
            parts = line.split()
            if len(parts) >= 3:
                try:
                    r = int(parts[0])
                    g = int(parts[1])
                    b = int(parts[2])
                    palette.append((r, g, b))
                except ValueError:
                    continue
    return palette

# Placemap handling

async def most_active(user_log_file: str) -> tuple[tuple[int, int], int]:
    """Find the most active pixel using a user log file."""
    pixel_counts = {}
    with open (user_log_file, newline='') as csvfile:
        reader = csv.reader(csvfile, delimiter='\t')
        for row in reader:
            if len(row) >=6:
                x = row[2].strip()
                y = row[3].strip()
                key = (x, y)
                pixel_counts[key] = pixel_counts.get(key, 0) + 1
    if pixel_counts:
        most_active, count = max(pixel_counts.items(), key=lambda item: item[1])
        return most_active, count
    else: 
        return (0, 0), 0

async def pixel_counting(user_log_file: str, canvas: str):
    """Find placement amounts on a canvas"""
    place, undo, mod = 0, 0, 0
    with open(user_log_file, 'r') as log_key:
        for line in log_key:
            if 'user place' in line:
                place += 1
            elif 'user undo' in line:
                undo += 1  
            elif 'mod overwrite' in line:
                mod += 1
    total_pixels = place - undo
    return total_pixels, undo, mod

async def survival(user_log_file: str, final_canvas_path: str, palette: list[tuple[int, int, int]]):
    """Find survival stats on a canvas"""
    def process_stats():
        final_state = {}
        replaced_user = 0
        try:
            with open (user_log_file, newline='') as csvfile:
                reader = csv.reader(csvfile, delimiter='\t')
                for row in reader:
                    if len(row) >=6:
                        x, y, index, action = int(row[2].strip()), int(row[3].strip()), int(row[4].strip()), row[5].strip()
                        coord = (x, y)
                        if action == 'user place':
                            if (x, y) in final_state:
                                replaced_user += 1
                            final_state[coord] = index
                        elif action == 'user undo':
                            final_state.pop(coord, None)
        except FileNotFoundError as e:
            print(f'{e}')
            return 0
        
        survived = 0
        try:
            with Image.open(final_canvas_path).convert('RGB') as final_canvas_image:
                width, height = final_canvas_image.size
                for coord, index in final_state.items():
                    x, y = coord
                    if x >= width or y >= height:
                        continue
                    if index >= len(palette):
                        continue
                    placed_pixel = palette[index]
                    final_pixel = final_canvas_image.getpixel(coord) # error here
                    if final_pixel == placed_pixel:
                        survived += 1
        except FileNotFoundError as e:
            print(f'{e}')
            return 0
        return survived
    return await asyncio.to_thread(process_stats)

async def tpe_pixels_count(user_log_file: str, temp_pattern: str, palette_path: str, initial_canvas_path) -> tuple [int, int]:
    """Find the amount of pixels placed for TPE on a specified canvas using template images. Handles virgin pixels."""
    palette_rgb = await gpl_palette(palette_path)
    if not palette_rgb:
        return 0, 0
    template_images = []
    template_map = []
    try:
        initial_canvas_image = Image.open(initial_canvas_path).convert('RGB')
        initial_canvas = initial_canvas_image.load()
        for path in glob.glob(temp_pattern):
            img = Image.open(path).convert('RGBA')
            template_images.append(img)
            template_map.append(img.load())
    except FileNotFoundError as e:
        print(f'{e}')
        return 0, 0
    if initial_canvas == None:
        return 0, 0
    tpe_place = {}
    tpe_grief = {}
    with open (user_log_file, newline='') as csvfile:
        reader = csv.reader(csvfile, delimiter='\t')
        for row in reader:
            if len(row) < 6:    
                continue
            try:
                x = int(row[2].strip())
                y = int(row[3].strip())
                coord = (x, y)
                index = int(row[4].strip())
                placed_rgb = palette_rgb[index]
                action = row[5].strip()
            except (ValueError, IndexError):
                continue
            if action == 'user undo':
                if coord in tpe_place:
                    tpe_place[coord] -= 1
                    if tpe_place[coord] <= 0:
                        del tpe_place[coord]
                if coord in tpe_grief:
                    tpe_grief[coord] -= 1
                    if tpe_grief[coord] <= 0:
                        del tpe_grief[coord]
            if action != 'user place':
                continue
            is_correct = False
            is_virgin = False
            present = False
            try:
                initial_canvas_rgb = initial_canvas[x, y]
            except IndexError:
                continue
            for tpe_image in template_map:
                try:
                    tpe_image_rgb = tpe_image[x, y]
                except IndexError:
                    continue
                # palette check
                if not isinstance(tpe_image_rgb, (tuple, list)) or len(tpe_image_rgb) < 4:
                    continue
                r, g, b, a = tpe_image_rgb
                if a == 0:
                    continue
                present = True
                target_rgb = (r, g, b)
                if placed_rgb == target_rgb: # correct pixel
                    is_correct = True
                    break
                if target_rgb == initial_canvas_rgb: # virgin pixel
                    is_virgin = True
            if is_correct or is_virgin:
                tpe_place[coord] = tpe_place.get(coord, 0) + 1
                tpe_grief.pop(coord, None)
            elif present and not is_correct:
                tpe_grief[coord] = tpe_grief.get(coord, 0) + 1
                tpe_place.pop(coord, None)
    tpe_pixels = sum(tpe_place.values())
    tpe_griefs = sum(tpe_grief.values())
    return tpe_pixels - tpe_griefs, tpe_griefs

async def tpe_pixels_count_user(user_id: int, callback = None) -> dict:
    """Finds how many pixels a user has placed on all recorded TPE canvases using user logfiles."""
    ple_dir = config.pxlslog_explorer_dir
    user_log_file_pattern = f'{ple_dir}/pxls-userlogs-tib/{user_id}_pixels_c*.log'
    found_user_logs = glob.glob(user_log_file_pattern)
    canvases = []
    for path in found_user_logs:
        match = re.search(r'_c(.+?)\.log$', path)
        if match:
            canvas_id = match.group(1)
            if config.tpe(canvas_id):
                canvases.append(canvas_id)
    results = {}
    total = len(canvases)
    for idx, canvas in enumerate(canvases):
        if callback and ((idx + 1) % 10 == 0 or (idx + 1) == total):
            await callback(canvas, idx + 1, total)
        else:
            print(f'Processing c{canvas} ({idx + 1}/{total}) for user {user_id}')
        user_log_file = f'{ple_dir}/pxls-userlogs-tib/{user_id}_pixels_c{canvas}.log'
        _, palette_path, _ = config.paths(canvas, user_id, 'normal')
        temp_pattern = os.path.join(ROOT_DIR, 'template', f'c{canvas}', '*.png')
        initial_canvas_path = f"{ple_dir}/pxls-canvas/canvas-{canvas}-initial.png"
        try:
            # even though we don't use mod, it throws an error if we only define 2 variables
            total_pixels, undo, mod = await pixel_counting(user_log_file, canvas)
            tpe_pixels, tpe_griefs = await tpe_pixels_count(user_log_file, temp_pattern, palette_path, initial_canvas_path)
            results[canvas] = {
                'total_pixels': total_pixels,
                'undo': undo,
                'tpe_pixels': tpe_pixels,
                'tpe_griefs': tpe_griefs,
                }
        except Exception as e:
            print(f'An error occurred while processing canvas {canvas} for user {user_id}: {e}')
            results[canvas] = (0, 0, 0, 0)
    return results

async def tpe_pixels_count_canvas(canvas: str, callback = None) -> dict:
    """Find how many pixels have been placed on a specific canvas by all registered users. Those with no data are ignored."""
    if not config.tpe(canvas):
        print(f'Canvas c{canvas} is not a TPE canvas.')
        return {}
    ple_dir = config.pxlslog_explorer_dir
    user_log_file_pattern = f'{ple_dir}/pxls-userlogs-tib/*_pixels_c{canvas}.log'
    found_user_logs = glob.glob(user_log_file_pattern)
    results = {}
    total = len(found_user_logs)
    for idx, user_log_file in enumerate(found_user_logs):
        user_id = -1
        basename = os.path.basename(user_log_file)
        match = re.match(r'(\d+)_pixels_c', basename)
        if not match:
            print(f'Could not extract user ID from filename: {basename}')
            continue
        user_id = int(match.group(1))
        if callback and ((idx + 1) % 10 == 0 or (idx + 1) == total):
            await callback(user_id, idx + 1, total)
        else:
            print(f'Processing user {user_id} ({idx + 1}/{total}) for c{canvas}')
        _, palette_path, _ = config.paths(canvas, user_id, 'normal')
        temp_pattern = os.path.join(ROOT_DIR, 'template', f'c{canvas}', '*.png')
        initial_canvas_path = f"{ple_dir}/pxls-canvas/canvas-{canvas}-initial.png"
        try:
            total_pixels, undo, mod = await pixel_counting(user_log_file, canvas)
            tpe_pixels, tpe_griefs = await tpe_pixels_count(user_log_file, temp_pattern, palette_path, initial_canvas_path)
            results[user_id] = {
                'total_pixels': total_pixels,
                'undo': undo,
                'tpe_pixels': tpe_pixels,
                'tpe_griefs': tpe_griefs,
                }
        except Exception as e:
            print(f'An error occurred while processing canvas {canvas} for user {user_id}: {e}')
            results[user_id] = (0, 0, 0, 0)
    return results

async def generate_placemap(user: Union[discord.User, discord.Member], canvas: str) -> tuple[bool, dict]:
    """Helper function to generate a placemap. Returns various other user logkey stats as well."""
    async with semaphore:
        filter_start_time = time.time()
        get_key = "SELECT key FROM logkey WHERE canvas=? AND user=?"
        ple_dir = config.pxlslog_explorer_dir
        cursor.execute(get_key, (canvas, user.id)) # does the above
        user_key = cursor.fetchone()
        mode = 'normal'
        _, palette_path, _ = config.paths(canvas, user.id, mode)

        if not re.fullmatch(r'^(?![cC])[a-z0-9]{1,4}+$', canvas):
            return False, {'error': f'Invalid format! A canvas code may not begin with a c, and can only contain a-z and 0-9.'}
            
        if not user_key:
            return False, {'error': f'No log key found for this canvas.'}
        
        user_key = user_key[0]
        if isinstance(user_key, int):
            return False, {'error': f'Your key is just a bunch of numbers smh.'}
        
        user_key = str(user_key)
        if not re.fullmatch(r'(?=.*[a-z])[a-z0-9]{512}', user_key):
            return False, {'error': f'Invalid format! A log key can only contain a-z, and 0-9.'}

        user_log_file = f'{ple_dir}/pxls-userlogs-tib/{user.id}_pixels_c{canvas}.log'
        filter_cli = [f'{ple_dir}/filter.exe', '--user', user_key, '--log', f'{ple_dir}/pxls-logs/pixels_c{canvas}.sanit.log', '--output', user_log_file]
        filter_result = await asyncio.create_subprocess_exec(
            *filter_cli, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        print(f'Filtering {user_key} for {user} on canvas {canvas}.')
        stdout, stderr = await filter_result.communicate()
        stdout_str = stdout.decode('utf-8').strip()
        stderr_str = stderr.decode('utf-8').strip()
        print(f'Subprocess output: {stdout_str}')
        print(f'Subprocess error: {stderr_str}')
        if filter_result.returncode != 0:
            return False, {'error': f'Something went wrong when filtering the log file! Ping Temriel.'}
        try:
            if os.path.getsize(user_log_file) == 0:
                return False, {'error': f'Invalid log key for c{canvas}. Wrong key?'}
        except FileNotFoundError:
            return False, {'error': f'Log file not found after filtering. Ping Temriel.'}
        except Exception as e:
            return False, {'error': f'An error occurred while accessing the log file: {e}'}
        filter_end_time = time.time()
        print(f'filter.exe took {filter_end_time - filter_start_time:.2f}s')
        total_pixels, undo, mod = await pixel_counting(user_log_file, canvas)
        survive_start_time = time.time()
        survived = await survival(user_log_file, f'{ple_dir}/pxls-final-canvas/canvas-{canvas}-final.png', await gpl_palette(palette_path))
        survived_perc = (survived / total_pixels * 100) if total_pixels > 0 else 0
        survived_perc = f'{survived_perc:.2f}'
        survive_end_time = time.time()
        print(f'{total_pixels} pixels placed')
        print(f'{undo} pixels undone')
        print(f'{mod} mod overwrites')
        print(f'{survived} ({survived_perc}%) pixels survived ({survive_end_time - survive_start_time:.2f}s)')
        tpe_pixels = 0
        tpe_griefs = 0
        if config.tpe(canvas):
            tpe_start_time = time.time()
            temp_pattern = os.path.join(ROOT_DIR, 'template', f'c{canvas}', '*.png')
            initial_canvas_path=f"{ple_dir}/pxls-canvas/canvas-{canvas}-initial.png"
            tpe_pixels, tpe_griefs = await tpe_pixels_count(user_log_file, temp_pattern, palette_path, initial_canvas_path)
            tpe_end_time = time.time()
            print(f'{tpe_pixels} pixels placed for TPE (took {tpe_end_time - tpe_start_time:.2f}s)')
            print(f'{tpe_griefs} pixels griefed')

        render_start_time = time.time()
        render_result, filename, output_path = await render(user, canvas, mode, user_log_file)
        render_end_time = time.time()
        print(f'render.exe took {render_end_time - render_start_time:.2f}s')
        if render_result.returncode != 0:
            return False, {'error': f'Something went wrong when generating the placemap! Ping Temriel.'}
        return True, {
            'total_pixels': total_pixels, # placed - undo
            'undo': undo,
            'mod': mod,
            'survived': survived, # pixels that are the same as the "final" state of the canvas
            'survived_perc': survived_perc, # above but % form
            'tpe_pixels': tpe_pixels, # for tpe - griefs
            'tpe_griefs': tpe_griefs,
            'filename': filename,
            'output_path': output_path,
            'user_log_file': user_log_file,
            'mode': mode # defaults to normal
        }
        
async def find_pxls_username(user: Union[discord.User, discord.Member]) -> str:
    """Find the pxls.space username linked to a Discord user ID."""
    query = "SELECT username FROM users WHERE user_id = ?"
    cursor.execute(query, (user.id,))
    found_user = cursor.fetchone()
    if found_user and found_user[0]:
        pxls_username = found_user[0]
        return pxls_username
    else:
        pxls_username = user.global_name or user.name
        return pxls_username
    
class PlacemapAltView(discord.ui.View):
    def __init__(self, user: Union[discord.User, discord.Member], canvas: str, mode: str, user_log_file: str, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.user = user
        self.canvas = canvas
        self.mode = mode
        self.user_log_file = user_log_file
        self.pressed = False
    
    def disable_button(self, custom_id: str):
        new_view = PlacemapAltView(
            user=self.user, 
            canvas=self.canvas, 
            mode=self.mode, 
            user_log_file=self.user_log_file, 
            timeout=self.timeout or 300.0
        )
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                new_button = discord.ui.Button(
                    label=item.label, 
                    style=item.style, 
                    custom_id=item.custom_id,
                    disabled=(item.custom_id == custom_id)
                )
        return new_view

    @discord.ui.button(label='Activity', style=discord.ButtonStyle.primary, custom_id='activity')
    async def activity_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled = True
        await interaction.response.defer()
        await interaction.edit_original_response(view=self)
        embed, file = await self.generate_alt(interaction, mode='activity')
        if file:
            await interaction.followup.send(embed=embed, file=file)
        else:
            await interaction.followup.send(embed=embed)

    @discord.ui.button(label='Age', style=discord.ButtonStyle.primary, custom_id='age')
    async def age_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled = True
        await interaction.response.defer()
        await interaction.edit_original_response(view=self)
        embed, file = await self.generate_alt(interaction, mode='age')
        if file:
            await interaction.followup.send(embed=embed, file=file)
        else:
            await interaction.followup.send(embed=embed)

    async def generate_alt(self, interaction: discord.Interaction, mode: str) -> tuple[discord.Embed, Optional[discord.File]]:
        """Function to generate "age" and "activity" placemaps."""
        start_time = time.time()
        render_result, filename, output_path = await render(self.user, self.canvas, mode, self.user_log_file)
        if mode == 'activity':
            (active_x, active_y), active_count = await most_active(self.user_log_file)
            description = f'**Most Active:** ({active_x}, {active_y}) with {active_count} pixels'
            embed = discord.Embed(
            title=f'Canvas {self.canvas} ({mode})',
            description=description,
            color=discord.Color.purple()
            )
        else:
            embed = discord.Embed(
                title=f'Canvas {self.canvas} ({mode})',
                color=discord.Color.purple()
            )
        if render_result.returncode == 0:
            end_time = time.time()
            elapsed_time = end_time - start_time
            file = discord.File(output_path, filename=filename)
            embed.set_author(
                name=self.user.global_name or self.user.name, 
                icon_url=self.user.avatar.url if self.user.avatar else self.user.default_avatar.url
                )
            embed.set_image(url=f'attachment://{filename}')
            embed.set_footer(text=f'Generated in {elapsed_time:.2f}s')
            return embed, file
        else:
            embed = discord.Embed(
            title='Error',
            description='An error occured! Ping Temriel.',
            color=discord.Color.red()
            )
            return embed, None