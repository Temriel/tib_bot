import sqlite3
import asyncio
import csv
import os
import re
import io
import time
from typing import Union, Optional
import discord
from PIL import Image
import tib_utility.config as config
from functools import lru_cache
from pathlib import Path
from collections import Counter
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import StrMethodFormatter

CANVAS_REGEX = re.compile(r'^(?![cC])[a-z0-9]{1,4}$')
KEY_REGEX = re.compile(r'(?=.*[a-z])[a-z0-9]{512}$')
USERNAME_REGEX = re.compile(r'^[a-zA-Z0-9_-]{1,32}$')

CUR_DIR = Path(__file__).resolve()
SRC_DIR = CUR_DIR.parents[1]
ROOT_DIR = CUR_DIR.parents[2]
DB_PATH = SRC_DIR / 'database.db'

database = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = database.cursor()
cursor.execute('PRAGMA journal_mode=WAL;')
cursor.execute('PRAGMA synchronous=NORMAL;')
cursor.execute('PRAGMA temp_store=MEMORY;')
database.execute('CREATE TABLE IF NOT EXISTS points(user STR, canvas STR, pixels INT, PRIMARY KEY (user, canvas))')
database.execute('CREATE TABLE IF NOT EXISTS users (user_id INT, username STR UNIQUE, notif_status BOOLEAN DEFAULT 0, PRIMARY KEY (user_id))')
database.execute('CREATE TABLE IF NOT EXISTS logkey(user INT, canvas STR, key STR, PRIMARY KEY (user, canvas))')

semaphore = asyncio.Semaphore(3)


def db_shutdown():
    try:
        cursor.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        database.commit()
        database.close()
        print('DB synced. Goodbye')
    except Exception as e:
        print(f'Error during DB shutdown: {e}')


async def get_linked_pxls_username(user_id: int):
    """Get the linked Pxls username for a given Discord user ID."""
    query = "SELECT username FROM users WHERE user_id = ?"
    cursor.execute(query, (user_id,))
    result = cursor.fetchone()
    return result[0] if result else None


async def get_linked_discord_username(pxls_username: str):
    """Get the linked Discord user for a given Pxls username."""
    query = "SELECT user_id FROM users WHERE username = ?"
    cursor.execute(query, (pxls_username,))
    result = cursor.fetchone()
    return result[0] if result else None


async def resolve_name(identifier: str) -> int | None:
    if identifier.isdigit() and len(identifier) > 16:
        return int(identifier)
    linked_id = await get_linked_discord_username(identifier)
    if linked_id:
        return int(linked_id)
    return None


def get_stats(pxls_username: str) -> dict:
    """Get pixel stats for a given Pxls username."""
    query = "SELECT SUM(pixels) FROM points WHERE user = ?"
    cursor.execute(query, (pxls_username,))
    total = cursor.fetchone()[0] or 0
    rank = "nothing"
    group = "nothing"
    if total is None:
        total = 0
    if total < 0:
        rank = "griefer"
    ranks = config.ranks()
    for threshold, name in ranks:
        if total >= threshold:
            rank = name
            break
    groups = config.rank_group()
    for threshold, name in groups:
        if total >= threshold:
            group = name
            break
    return {'total': total, 'rank': rank, 'group': group}


def get_all_users() -> list[tuple[int, str]]:
    """Get all linked Discord user IDs."""
    query = "SELECT user_id, username FROM users"
    cursor.execute(query)
    results = cursor.fetchall()
    return results


async def render(user: Union[discord.User, discord.Member], canvas: str, mode: str, user_log_file: str) -> tuple[
    asyncio.subprocess.Process, str, str]:
    """Render a placemap from a log file. Uses pxlslog-explorer render.exe."""
    bg, palette_path, output_path = config.paths(canvas, user.id, mode)
    ple_dir = config.pxlslog_explorer_dir
    render_cli = [f'{ple_dir}/render.exe', '--log', user_log_file, '--bg', bg, '--palette', palette_path,
                  '--screenshot', '--output', output_path, mode]
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
    return await asyncio.to_thread(read_gpl_palette, palette_path)


@lru_cache(maxsize=128)
def read_gpl_palette(palette_path: str):
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
    return await asyncio.to_thread(read_most_active, user_log_file)


def read_most_active(user_log_file: str):
    coords = []
    with open(user_log_file, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.split('\t')
            if len(parts) >= 6:
                coords.append((parts[2].strip(), parts[3].strip()))
    if not coords:
        return (0, 0), 0
    (found_most_active, count), = Counter(coords).most_common(1)
    return found_most_active, count


async def pixel_counting(user_log_file: str):
    return await asyncio.to_thread(read_pixel_counting, user_log_file)


def read_pixel_counting(user_log_file: str):
    """Find placement amounts on a canvas"""
    with open(user_log_file, 'r') as log_key:
        data = log_key.read()
    place = data.count('user place')
    undo = data.count('undo')
    mod = data.count('mod')
    total_pixels = place - undo
    return total_pixels, undo, mod


async def survival(user_log_file: str, final_canvas_path: str, palette: list[tuple[int, int, int]]):
    """Find survival stats on a canvas"""

    def process_stats():
        final_state = {}
        replaced_user = 0  # UNUSED
        try:
            with open(user_log_file, newline='') as csvfile:
                reader = csv.reader(csvfile, delimiter='\t')
                for row in reader:
                    if len(row) >= 6:
                        x, y, index, action = int(row[2].strip()), int(row[3].strip()), int(row[4].strip()), row[
                            5].strip()
                        coord = (x, y)
                        if action == 'user place':
                            if (x, y) in final_state:
                                replaced_user += 1
                            final_state[coord] = index
                        elif action == 'user undo':
                            final_state.pop(coord, None)
        except FileNotFoundError as e:
            print(f'{e}')
            return 0, 0, 0

        replaced_other = 0  # UNUSED
        survived = 0
        try:
            with Image.open(final_canvas_path).convert('RGB') as final_canvas_image:
                width, height = final_canvas_image.size
                final_canvas_data = final_canvas_image.load()
                if final_canvas_data is None:
                    print('Failed to load final canvas image.')
                    return 0, 0, 0
                for coord, index in final_state.items():
                    x, y = coord
                    if x >= width or y >= height:
                        continue
                    if index >= len(palette):
                        continue
                    placed_pixel = palette[index]
                    final_pixel = final_canvas_data[coord]
                    if final_pixel == placed_pixel:
                        survived += 1
                    else:
                        replaced_other += 1
        except FileNotFoundError as e:
            print(f'{e}')
            return 0, 0, 0
        return replaced_user, replaced_other, survived

    return await asyncio.to_thread(process_stats)


async def tpe_pixels_count(user_log_file: str, temp_pattern: str, palette_path: str, initial_canvas_path) -> tuple[
    int, int]:
    """Find the amount of pixels placed for TPE on a specified canvas using template images."""
    palette_rgb = [tuple(c) for c in await gpl_palette(palette_path)]
    if not palette_rgb:
        return 0, 0

    template_images = []
    template_map = []
    try:
        initial_canvas_image = Image.open(initial_canvas_path).convert('RGB')
        initial_canvas = initial_canvas_image.load()
        template_dir = os.path.dirname(temp_pattern)
        if os.path.isdir(template_dir):
            with os.scandir(template_dir) as entries:
                for entry in entries:
                    if not entry.is_file():
                        continue
                    if not entry.name.lower().endswith('.png'):
                        continue
                    path = os.path.join(template_dir, entry.name)
                    try:
                        img = Image.open(path).convert('RGBA')
                        template_images.append(img)
                        template_map.append(img.load())
                    except Exception as e:
                        print(f'Error loading template image {path}: {e}')
    except FileNotFoundError as e:
        print(f'{e}')
        return 0, 0

    if initial_canvas is None:
        print("No initial canvas found.")
        return 0, 0

    tpe_place = {}
    tpe_grief = {}
    template_cache = {}

    with open(user_log_file, newline='') as csvfile:
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
                initial_canvas_rgb = initial_canvas[x, y] # for virgin
            except IndexError:
                continue
            if coord not in template_cache:
                correct_colour = set()
                has_virgin = False
                for tpe_image in template_map:
                    try:
                        tpe_image_rgb = tpe_image[x, y] # for tpe check
                        if isinstance(tpe_image_rgb, (tuple, list)) and len(tpe_image_rgb) >= 4:
                            r, g, b, a = tpe_image_rgb
                            if a > 0:
                                target_rgb = (r, g, b)
                                correct_colour.add(target_rgb)
                                if target_rgb == initial_canvas_rgb:
                                    has_virgin = True
                    except IndexError:
                        continue
                template_cache[coord] = (correct_colour, has_virgin)
            correct_colour, has_virgin = template_cache[coord]

            if correct_colour:
                present = True
                if placed_rgb in correct_colour:
                    is_correct = True
                elif has_virgin:
                    is_virgin = True
            if is_correct or is_virgin: # since it passed the for loop, add as correct
                tpe_place[coord] = tpe_place.get(coord, 0) + 1
                tpe_grief.pop(coord, None)
            elif present and not is_correct: # fails is_correct check, fails is_virgin check, but is present, thus it's a grief
                tpe_grief[coord] = tpe_grief.get(coord, 0) + 1
                tpe_place.pop(coord, None)
    tpe_pixels = sum(tpe_place.values())
    tpe_griefs = sum(tpe_grief.values())
    return tpe_pixels - tpe_griefs, tpe_griefs # I return tpe_pixels - tpe_griefs, so I don't have to do that math everywhere else lol


async def tpe_pixels_count_user(user_id: int, callback=None) -> dict:
    return await tpe_pixels_count_user_canvas(user_id=user_id, callback=callback)


async def tpe_pixels_count_canvas(canvas: str, callback=None) -> dict:
    return await tpe_pixels_count_user_canvas(canvas=canvas, callback=callback)


async def tpe_pixels_count_user_canvas(user_id: Optional[int] = None, canvas: Optional[str] = None, callback=None) -> dict:
    ple_dir = config.pxlslog_explorer_dir
    if not ple_dir:
        print('pxlslog-explorer directory is not configured.')
        return {}
    user_logs_dir = os.path.join(ple_dir, 'pxls-userlogs-tib')
    found_user_logs = []
    if os.path.isdir(user_logs_dir):
        with os.scandir(user_logs_dir) as entries:
            for entry in entries:
                if not entry.is_file():
                    continue
                if user_id is not None:
                    if entry.name.startswith(f'{user_id}_pixels_c') and entry.name.endswith('.log'):
                        found_user_logs.append(entry.name)
                else:
                    if entry.name.lower().endswith(f'_pixels_c{canvas}.log'):
                        found_user_logs.append(entry.name)

    results: dict[Union[int, str], dict] = {}
    total = len(found_user_logs)
    file_regex = re.compile(r'^(\d+)_pixels_c(.+)\.log$', flags=re.IGNORECASE)

    for idx, filename in enumerate(found_user_logs):
        match = file_regex.match(filename)
        if not match:
            print('Regex failed, continuing')
            continue
        found_user_id = int(match.group(1))
        found_canvas = match.group(2)
        user_log_file = os.path.join(user_logs_dir, filename)

        if user_id is not None:
            result_key = found_canvas
            to_print = f'Processing c{found_canvas} ({idx + 1}/{total}) for user {user_id}'
        else:
            result_key = found_user_id
            to_print = f'Processing user {found_user_id} ({idx + 1}/{total}) for c{canvas}'

        if callback and ((idx + 1) % 10 == 0 or (idx + 1) == total):
            await callback(result_key, idx + 1, total)
        else:
            print(to_print)

        await find_tpe_stats(canvas=found_canvas, ple_dir=ple_dir, results=results, user_id=found_user_id, user_log_file=user_log_file, result_key=result_key)
    return results


async def find_tpe_stats(canvas: str, ple_dir, results: dict[Union[int, str], dict], user_id: int, user_log_file, result_key: Optional[Union[int, str]] = None):
    """Thank you PyCharm for just Making This Work lol"""
    _, palette_path, _ = config.paths(canvas, user_id, 'normal')
    temp_pattern = os.path.join(ROOT_DIR, 'template', f'c{canvas}', '*.png')
    initial_canvas_path = f"{ple_dir}/pxls-canvas/canvas-{canvas}-initial.png"
    try:
        total_pixels, undo, mod = await pixel_counting(user_log_file)
        tpe_pixels, tpe_griefs = await tpe_pixels_count(user_log_file, temp_pattern, palette_path,
                                                        initial_canvas_path)
        key = result_key if result_key is not None else user_id # to make it work for both functions
        results[key] = {
            'total_pixels': total_pixels,
            'undo': undo,
            'tpe_pixels': tpe_pixels,
            'tpe_griefs': tpe_griefs,
        }
    except Exception as e:
        print(f'An error occurred while processing canvas {canvas} for user {user_id}: {e}')
        key = result_key if result_key is not None else user_id
        results[key] = {'total_pixels': 0, 'undo': 0, 'tpe_pixels': 0, 'tpe_griefs': 0}


async def generate_placemap(user: Union[discord.User, discord.Member], canvas: str) -> tuple[bool, dict]:
    """Helper function to generate a placemap. Returns various other user logkey stats as well."""
    async with semaphore:
        filter_start_time = time.time()
        get_key = "SELECT key FROM logkey WHERE canvas=? AND user=?"
        ple_dir = config.pxlslog_explorer_dir
        logfile = f'{ple_dir}/pxls-logs/pixels_c{canvas}.sanit.log'
        cursor.execute(get_key, (canvas, user.id))  # does the above
        user_key = cursor.fetchone()
        mode = 'normal'
        _, palette_path, _ = config.paths(canvas, user.id, mode)

        if not CANVAS_REGEX.fullmatch(canvas):
            return False, {'error': f'Invalid format! A canvas code may not begin with a c, and can only contain a-z and 0-9.'}

        if not os.path.exists(logfile): 
            return False, {'error': f'No log file found. Either invalid canvas or the logs haven\'t been added yet.'}

        if not user_key:
            return False, {'error': f'No log key found for this canvas.'}

        user_key = user_key[0]
        if isinstance(user_key, int):
            return False, {'error': f'Your key is just a bunch of numbers smh.'}

        user_key = str(user_key)
        if not KEY_REGEX.fullmatch(user_key):
            return False, {'error': f'Invalid format! A log key can only contain a-z, and 0-9.'}

        user_log_file = f'{ple_dir}/pxls-userlogs-tib/{user.id}_pixels_c{canvas}.log'
        filter_cli = [f'{ple_dir}/filter.exe', '--user', user_key, '--log', logfile,
                      '--output', user_log_file]
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
        total_pixels, undo, mod = await pixel_counting(user_log_file)

        survive_start_time = time.time()
        replaced_user, replaced_other, survived = await survival(user_log_file,
                                                                 f'{ple_dir}/pxls-final-canvas/canvas-{canvas}-final.png',
                                                                 await gpl_palette(palette_path))
        survived_perc = (survived / total_pixels * 100) if total_pixels > 0 else 0
        survived_perc = f'{survived_perc:.2f}'
        survive_end_time = time.time()

        active_start_time = time.time()
        (active_x, active_y), active_count = await most_active(user_log_file)
        active_end_time = time.time()

        print(f'{total_pixels} pixels placed')
        print(f'{undo} pixels undone')
        print(f'{active_x, active_y} with {active_count} pixels (took {active_end_time - active_start_time:.2f}s)')
        print(f'{mod} mod overwrites')
        print(f'{survived} ({survived_perc}%) pixels survived (took {survive_end_time - survive_start_time:.2f}s)')
        print(f'{replaced_user} pixels replaced by self')
        print(f'{replaced_other} pixels replaced by others')

        tpe_pixels = 0
        tpe_griefs = 0
        if config.tpe(canvas):
            tpe_start_time = time.time()
            temp_pattern = os.path.join(ROOT_DIR, 'template', f'c{canvas}', '*.png')
            initial_canvas_path = f"{ple_dir}/pxls-canvas/canvas-{canvas}-initial.png"
            tpe_pixels, tpe_griefs = await tpe_pixels_count(user_log_file, temp_pattern, palette_path,
                                                            initial_canvas_path)
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
            'total_pixels': total_pixels,  # placed - undo
            'undo': undo,  # reverses a pixel
            'mod': mod,  # mod overwrites, not included in total_pixels & is almost always 0
            'active_x': active_x,
            'active_y': active_y,
            'active_count': active_count, # most active pixel (& num placements there)
            'survived': survived,  # pixels that are the same as the "final" state of the canvas
            'survived_perc': survived_perc,  # above but % form
            'replaced_user': replaced_user,  # pixels replaced by self
            'replaced_other': replaced_other,  # pixels replaced by others
            'tpe_pixels': tpe_pixels,  # for tpe - griefs
            'tpe_griefs': tpe_griefs,  # just griefs. not always accurate
            'filename': filename,
            'output_path': output_path,
            'user_log_file': user_log_file,
            'mode': mode  # defaults to normal
        }


async def description_format(canvas: str, results: dict) -> str:
    """Generate description string for placemap embed."""
    total_pixels = results.get("total_pixels", 0)
    undo = results.get("undo", 0)
    mod = results.get("mod", 0)
    active_x = results.get("active_x", 0)
    active_y = results.get("active_y", 0)
    active_count = results.get("active_count", 0)
    survived = results.get("survived", 0)
    survived_perc = results.get("survived_perc", 0)
    replaced_user = results.get("replaced_user", 0)
    replaced_other = results.get("replaced_other", 0)
    tpe_pixels = results.get("tpe_pixels", 0)
    tpe_griefs = results.get("tpe_griefs", 0)
    constructed_desc = (
        f'**Pixels Placed:** {total_pixels}\n'
        f'**Undos:** {undo}\n'
        f'**Surviving Pixels:** {survived} ({survived_perc}%)\n'
        # f'**Replaced by Self:** {replaced_user}\n'    # Not used due to faulty math, since this only uses the userlog file instead of the full canvas log
        # f'**Replaced by Others:** {replaced_other}\n' # which means grief defence counts towards replaced by others. Esp since "replaced by others" is only compared against final canvas state
        f'**Most Active:** ({active_x}, {active_y}) with {active_count} pixels'
    )
    if config.tpe(canvas):
        constructed_desc += f'\n**Pixels for TPE:** {tpe_pixels}'
        constructed_desc += f'\n**Pixels Griefed:** {tpe_griefs}'
    if mod > 0:
        constructed_desc += f'\n**Mod Overwrites:** {mod}'
    return constructed_desc


class PlacemapAltView(discord.ui.View):
    def __init__(self, user: Union[discord.User, discord.Member], canvas: str, mode: str, user_log_file: str,
                 timeout: float = 300):
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

    # noinspection PyTypeChecker
    @discord.ui.button(label='Activity', style=discord.ButtonStyle.primary, custom_id='activity')
    async def activity_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled = True
        await interaction.response.defer()
        await interaction.edit_original_response(view=self)
        embed, file = await self.generate_alt(mode='activity')
        if file:
            await interaction.followup.send(embed=embed, file=file)
        else:
            await interaction.followup.send(embed=embed)

    # noinspection PyTypeChecker
    @discord.ui.button(label='Age', style=discord.ButtonStyle.primary, custom_id='age')
    async def age_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled = True
        await interaction.response.defer()
        await interaction.edit_original_response(view=self)
        embed, file = await self.generate_alt(mode='age')
        if file:
            await interaction.followup.send(embed=embed, file=file)
        else:
            await interaction.followup.send(embed=embed)

    async def generate_alt(self, mode: str) -> tuple[
        discord.Embed, Optional[discord.File]]:
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
                description='An error occurred! Ping Temriel.',
                color=discord.Color.red()
            )
            return embed, None


def create_graph(canvases: list[str], pixels: list[int]) -> io.BytesIO:
    """Generic function to create graphs."""
    cumulative = []
    current_total = 0
    for pixel in pixels:
        current_total += pixel
        cumulative.append(current_total)
        
    plt.style.use('dark_background')
    fig, ax1 = plt.subplots(figsize=(10, 5))

    per_canvas = ax1.plot(canvases, pixels, marker='o', linestyle='-', color='purple', linewidth=2, markersize=6, label='Pixels for TPE')
    ax1.set_title(f"TPE pixels per canvas", fontsize=14, pad=15)
    ax1.set_xlabel('Canvas', fontsize=12)
    ax1.set_ylabel('Pixels for TPE', color='purple', fontsize=12)
    ax1.tick_params(axis='y', labelcolor='purple') 
    ax1.grid(True, linestyle='--', alpha=0.3)
    ax1.tick_params(axis='x', rotation=45)
    ax1.yaxis.set_major_formatter(StrMethodFormatter('{x:,.0f}'))
    
    ax2 = ax1.twinx()
    cumulative_line = ax2.plot(canvases, cumulative, marker='s', linestyle='--', color='cyan', linewidth=2, markersize=6, label='Cumulative')
    ax2.set_ylabel('Cumulative', color='cyan', fontsize=12)
    ax2.tick_params(axis='y', labelcolor='cyan')
    ax2.yaxis.set_major_formatter(StrMethodFormatter('{x:,.0f}'))
    
    lines = per_canvas + cumulative_line
    labels = [str(line.get_label()) for line in lines]
    ax1.legend(lines, labels, loc='upper left')
    plt.tight_layout()

    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', dpi=150)
    buffer.seek(0)
    plt.close(fig)
    
    return buffer
