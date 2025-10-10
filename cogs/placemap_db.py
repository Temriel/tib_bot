import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import config
# import subprocess # for error handling
import re
import time
import asyncio
from typing import Union, Optional
import csv
# from collections import defaultdict
from PIL import Image 
import glob

owner_id = config.owner()

database = sqlite3.connect('database.db')
cursor = database.cursor()
database.execute('CREATE TABLE IF NOT EXISTS logkey(user INT, canvas STR, key STR, PRIMARY KEY (user, canvas))')

semaphore = asyncio.Semaphore(3)

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

async def tpe_pixels_count(user_log_file: str, temp_pattern: str, palette_path: str, initial_canvas_path) -> tuple [int, int]:
    """Find the amount of pixels placed for TPE on a specified canvas using template images. Handles virgin pixels."""
    palette_rgb = await gpl_palette(palette_path)
    template_path = glob.glob(temp_pattern)
    try:
        template_images = [Image.open(path).convert('RGBA') for path in template_path]
        initial_canvas_image = Image.open(initial_canvas_path).convert('RGB')
    except FileNotFoundError as e:
        print(f'{e}')
        return 0, 0
    tpe_place = {}
    tpe_grief = {}
    with open (user_log_file, newline='') as csvfile:
        reader = csv.reader(csvfile, delimiter='\t')
        for row in reader:
            try:
                if len(row) < 6:
                    continue
                x = int(row[2].strip())
                y = int(row[3].strip())
                index = int(row[4].strip())
                action = row[5].strip()
                coord = (x, y)

                if action == 'user place':
                    placed_rgb = palette_rgb[index]
                    is_correct = False
                    is_virgin = False
                    present = False
                    for tpe_image in template_images:
                        value = tpe_image.getpixel(coord)
                        if isinstance(value, tuple) and len(value) == 4:
                            r, g, b, a = value
                        else:
                            continue
                        if a == 0:
                            continue
                        present = True
                        target_rgb = (r, g, b)
                        initial_canvas_rgb = initial_canvas_image.getpixel(coord)
                        if placed_rgb == target_rgb:
                            is_correct = True
                            break
                        if target_rgb == initial_canvas_rgb:
                            is_virgin = True
                    if is_correct or is_virgin:
                        tpe_place[coord] = tpe_place.get(coord, 0) + 1
                        tpe_grief.pop(coord, None)
                    elif present and not is_correct:
                        tpe_grief[coord] = tpe_grief.get(coord, 0) + 1
                        tpe_place.pop(coord, None)
                elif action == 'user undo':
                    tpe_place.pop(coord, None)
                    tpe_grief.pop(coord, None)
            except (ValueError, IndexError, OSError):
                continue
    tpe_pixels = sum(tpe_place.values())
    tpe_griefs = sum(tpe_grief.values())
    return tpe_pixels - tpe_griefs, tpe_griefs

async def tpe_pixels_count_older(user_id: int, callback=None,) -> dict:
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
        temp_pattern = f'template/c{canvas}/*.png'
        initial_canvas_path = f"{ple_dir}/pxls-canvas/canvas-{canvas}-initial.png"
        place = 0
        undo = 0
        try:
            with open(user_log_file, 'r') as log_key:
                for line in log_key:
                    if 'user place' in line:
                        place += 1
                    elif 'user undo' in line:
                        undo += 1  
            total_pixels = place - undo
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

async def generate_placemap(user: Union[discord.User, discord.Member], canvas: str) -> tuple[bool, dict]:
    """Helper function to generate a placemap"""
    async with semaphore:
        get_key = "SELECT key FROM logkey WHERE canvas=? AND user=?"
        ple_dir = config.pxlslog_explorer_dir
        cursor.execute(get_key, (canvas, user.id)) # does the above
        user_key = cursor.fetchone()
        mode = 'normal'

        if not re.fullmatch(r'^(?![cC])[a-z0-9]{1,4}+$', canvas):
            return False, {'error': f'Invalid format! A canvas code may not begin with a c, and can only contain a-z and 0-9.'}
            
        if not user_key:
            return False, {'error': f'No log key found for this canvas.'}
        
        user_key = user_key[0]
        if not re.fullmatch(r'[a-z0-9]{512}', user_key):
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
            return False, {'error': f'Something went wrong when generating the log file! Ping Temriel.'}
    
        place = 0
        undo = 0
        mod = 0
        tpe_pixels = 0
        tpe_griefs = 0
        with open(user_log_file, 'r') as log_file:
            for line in log_file:
                if 'user place' in line:
                    place += 1
                elif 'user undo' in line:
                    undo += 1
                elif 'mod overwrite' in line:
                    mod += 1
        total_pixels = place - undo
        if config.tpe(canvas):
            _, palette_path, _ = config.paths(canvas, user.id, mode)
            temp_pattern = f'template/c{canvas}/*.png' # in tib directory
            initial_canvas_path=f"{ple_dir}/pxls-canvas/canvas-{canvas}-initial.png"
            tpe_pixels, tpe_griefs = await tpe_pixels_count(user_log_file, temp_pattern, palette_path, initial_canvas_path)
        print(f'{total_pixels} pixels placed')
        print(f'{undo} pixels undone')
        if config.tpe(canvas):
            print(f'{tpe_pixels} pixels placed for TPE')
            print(f'{tpe_griefs} pixels griefed')
        print(f'{mod} mod overwrites')

        render_result, filename, output_path = await render(user, canvas, mode, user_log_file)

        if render_result.returncode != 0:
            return False, {'error': f'Something went wrong when generating the placemap! Ping Temriel.'}
        return True, {
            'total_pixels': total_pixels,
            'undo': undo,
            'mod': mod,
            'tpe_pixels': tpe_pixels,
            'tpe_griefs': tpe_griefs,
            'filename': filename,
            'output_path': output_path,
            'user_log_file': user_log_file,
            'mode': mode
        }
    
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
        
class placemapDBAdd(discord.ui.Modal, title='Add your log key.'):
    canvas = discord.ui.TextInput(label='Canvas Number', placeholder='Add canvas number (eg, 28 or 56a).', max_length=4, min_length=1)
    key = discord.ui.TextInput(label='Log key (512 char)', style=discord.TextStyle.paragraph, max_length=512, min_length=512)
    
    async def on_submit(self, interaction: discord.Interaction):
        if not re.fullmatch(r'^(?![cC])[a-z0-9]{1,4}+$', self.canvas.value):
            await interaction.response.send_message('Invalid format! A canvas code can only contain a-z and 0-9.', ephemeral=True)
            return
        if not re.fullmatch(r'[a-z0-9]{512}', self.key.value):
            await interaction.response.send_message('Invalid format! A log key can only contain a-z and 0-9.', ephemeral=True)
            return
        
        user = interaction.user
        query = "INSERT OR REPLACE INTO logkey VALUES (?, ?, ?)" # the three question marks represents the above "user", "canvas", and "logkey"
        try:
            cursor.execute(query, (user.id, self.canvas.value, self.key.value)) # we use user.id to store the ID instead of the user string - das bad
            database.commit()
            print(f'Log key added for {user} ({user.id}) on canvas {self.canvas.value}.')
            await interaction.response.send_message(f'Added key for canvas {self.canvas.value}!', ephemeral=True)
            return
        except sqlite3.OperationalError as e:
            await interaction.response.send_message('Error! Something went wrong, ping Temriel.', ephemeral=True)
            print(f'An SQLite3 error occurred: {e}')
            return
        except Exception as e:
            await interaction.response.send_message('Error! Something went wrong, ping Temriel.', ephemeral=True)
            print(f'An error occurred: {e}')
            return

class placemapDBAddAdmin(discord.ui.Modal, title='Force add a logkey'):
    user_canvas = discord.ui.TextInput(label='userID, canvas', placeholder='uID,28,30a,59 OR 56a,uID1,uID2,uID3', style=discord.TextStyle.short, max_length=200)
    key = discord.ui.TextInput(label='Log keys (512 char each)', placeholder='key1,key2,key3,key4,key5,key6', style=discord.TextStyle.paragraph, max_length=4000)

    async def on_submit(self, interaction: discord.Interaction):
        query = "INSERT OR REPLACE INTO logkey VALUES (?, ?, ?)"
        try:
            if interaction.user.id == owner_id:
                user_canvases = [x.strip() for x in self.user_canvas.value.split(',')]
                keys = [x.strip() for x in self.key.value.split(',')]
                if len(user_canvases) < 2:
                    await interaction.response.send_message('You must provide a user ID and at least one canvas.', ephemeral=True)
                    return
                
                if len(user_canvases[0]) > 4: # one user, multiple canvases
                    user_id = int(user_canvases[0])
                    canvases = user_canvases[1:]
                    if len(keys) != len(canvases):
                        await interaction.response.send_message('The number of keys must match the number of canvases.', ephemeral=True)
                        return
                    success = []
                    fail = []
                    for canvas, key in zip(canvases, keys):
                        if not re.fullmatch(r'^(?![cC])[a-z0-9]{1,4}+$', canvas):
                            fail.append((f'c{canvas}, Invalid canvas format'))
                            continue
                        if not re.fullmatch(r'[a-z0-9]{512}', key):
                            fail.append((f'c{canvas}, Invalid key format'))
                            continue
                        try:
                            cursor.execute(query, (user_id, canvas, key))
                            database.commit()
                            success.append(f'c{canvas}')
                        except sqlite3.OperationalError as e:
                            fail.append((f'c{canvas}, SQLite error: {e}'))
                        except Exception as e:
                            fail.append((f'c{canvas}, Error: {e}'))
                    message = f'<@{user_id}> ({user_id}) now has keys for canvases: {', '.join(success)}'
                    if fail:
                        message += f'\nFailed for canvases: {', '.join(fail)}'
                    await interaction.response.send_message(message, ephemeral=True)
                else:
                    canvas = user_canvases[0]
                    user_ids = user_canvases[1:]
                    if len(keys) != len(user_ids):
                        await interaction.response.send_message('The number of keys must match the number of canvases.', ephemeral=True)
                        return
                    success = []
                    fail = []
                    for user_id, key in zip(user_ids, keys):
                        if not re.fullmatch(r'\d{17,}', user_id):
                            fail.append((f'<@{user_id}> ({user_id}), Invalid user ID format'))
                            continue
                        if not re.fullmatch(r'[a-z0-9]{512}', key):
                            fail.append((f'<@{user_id}> ({user_id}), Invalid key format'))
                            continue
                        try:
                            cursor.execute(query, (int(user_id), canvas, key))
                            database.commit()
                            success.append(f'<@{user_id}> ({user_id})')
                        except sqlite3.OperationalError as e:
                            fail.append((f'{user_id}, SQLite error: {e}'))
                        except Exception as e:
                            fail.append((f'{user_id}, Error: {e}'))
                    message = f'c{canvas} now has logkeys for: {', '.join(success)}'
                    if fail:
                        message += f'\nFailed for users: {', '.join(fail)}'
                    await interaction.response.send_message(message, ephemeral=True)
            else:
                await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message('Error! Something went wrong, check the console.', ephemeral=True)
            print(f'An error occurred: {e}')

# DISCORD COMMANDS BELOW
class placemap(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print('Key DB cog loaded')

    group = app_commands.Group(name="logkey", description="Add your log key or make a placemap from it :3")

    @group.command(name='add', description='Add a log key.') # adds a log key to the database using a fancy ass modal
    async def placemap_db_add(self, interaction: discord.Interaction):
        """Add a logkey to Tib's internal database."""
        embed = discord.Embed(
            title='Add your log key', 
            description='''
            Here you can easily add your log key to the bot for placemap processing.
            You can find your log keys here: https://pxls.space/profile?action=data
            Once the log keys have been added to the bot, you can run `/logkey generate` to make your placemaps!
            ''',
            color=discord.Color.purple()
            )
        button = discord.ui.Button(label='Add Log Key', style=discord.ButtonStyle.primary)
        button.callback = self.open_modal
        view = discord.ui.View()
        view.add_item(button)
        await interaction.response.send_message(embed=embed, view=view)
    async def open_modal(self, interaction: discord.Interaction):
        modal = placemapDBAdd()
        await interaction.response.send_modal(modal)

    @group.command(name='generate', description='Generate a placemap from a log key.')
    async def placemap_db_generate(self, interaction: discord.Interaction, canvas: str):
        """Generate a placemap by piping the necessary arguments to pxlslog-explorer."""
        user = interaction.user
        update_channel_id = config.update_channel()
        update_channel = interaction.client.get_channel(update_channel_id)
        start_time = time.time()
        await interaction.response.defer(ephemeral=False,thinking=True)
        state, results = await generate_placemap(user, canvas)

        if state:
            total_pixels = results.get("total_pixels", 0)
            undo = results.get("undo", 0)
            mod = results.get("mod", 0)
            tpe_pixels = results.get("tpe_pixels", 0)
            tpe_griefs = results.get("tpe_griefs", 0)
            filename = results.get("filename", 0)
            user_log_file = results.get("user_log_file", 0)
            mode = results.get("mode", 0)
        else:
            await interaction.followup.send(results['error'])
            return
        if isinstance(update_channel, discord.TextChannel) or isinstance(update_channel, discord.Thread):
            embed = discord.Embed(
            title=f'{user} on c{canvas}', 
            description=f'**User ID:** {user.id}\n**Pixels placed:** {total_pixels}\n**Undos:** {undo}\n**For TPE:** {tpe_pixels}\n**TPE griefed:** {tpe_griefs}\n**Mod overwrites:** {mod}',
            color=discord.Color.purple()
            )
            embed.set_author(
                name=user.global_name or user.name, 
                icon_url=user.avatar.url if user.avatar else user.default_avatar.url
                )
            await update_channel.send(embed=embed)

        try: 
            end_time = time.time()
            elapsed_time = end_time - start_time
            file = discord.File(results["output_path"], filename=results["filename"])
            (active_x, active_y), active_count = await most_active(results["user_log_file"])
            description=f'**Pixels Placed:** {results["total_pixels"]}\n**Undos:** {undo}\n**Most Active:** ({active_x}, {active_y}) with {active_count} pixels'
            if config.tpe(canvas):
                description += f'\n**Pixels for TPE:** {results["tpe_pixels"]}'
                description += f'\n**Pixels griefed:** {results["tpe_griefs"]}'
            if mod > 0:
                description += f'\n**Mod Overwrites:** {mod}'
            embed = discord.Embed(
                title=f'Your Placemap for Canvas {canvas}', 
                description=description,
                color=discord.Color.purple()
                )
            embed.set_author(
                name=user.global_name or user.name, 
                icon_url=user.avatar.url if user.avatar else user.default_avatar.url
                )
            embed.set_image(url=f'attachment://{filename}')
            embed.set_footer(text=f'Generated in {elapsed_time:.2f}s')
            view = PlacemapAltView(user, canvas, mode, user_log_file)
            await interaction.followup.send(embed=embed, file=file, view=view)
        except Exception as e:
            await interaction.response.send_message('Error! Something went wrong, check the console.', ephemeral=True)
            print(f'An error occurred: {e}')
            return

    @group.command(name='force-add', description='Force add a logkey for a user (ADMIN ONLY).') 
    async def placemap_db_add_admin(self, interaction: discord.Interaction):
        """Add a logkey forcefully"""
        try:
            if interaction.user.id != owner_id:
                await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)
                return
            modal = placemapDBAddAdmin()
            await interaction.response.send_modal(modal)

        except Exception as e:
            await interaction.response.send_message('Error! Something went wrong, check the console.', ephemeral=True)
            print(f'An error occurred: {e}')

    @group.command(name='force-generate', description='Forcefully generate a placemap for a user (ADMIN ONLY).')
    async def placemap_db_generate_admin(self, interaction: discord.Interaction, user: discord.User, canvas: str):
        """Forcefully generate a placemap by piping the necessary arguments to pxlslog-explorer."""
        if interaction.user.id != owner_id:
            await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)
            return
        update_channel_id = config.update_channel()
        update_channel = interaction.client.get_channel(update_channel_id)
        start_time = time.time()
        await interaction.response.defer(ephemeral=False,thinking=True)
        state, results = await generate_placemap(user, canvas)

        if state:
            total_pixels = results.get("total_pixels", 0)
            undo = results.get("undo", 0)
            mod = results.get("mod", 0)
            tpe_pixels = results.get("tpe_pixels", 0)
            tpe_griefs = results.get("tpe_griefs", 0)
            filename = results.get("filename", 0)
            user_log_file = results.get("user_log_file", 0)
            mode = results.get("mode", 0)
        else:
            await interaction.followup.send(results['error'])
            return
        if isinstance(update_channel, discord.TextChannel) or isinstance(update_channel, discord.Thread):
            embed = discord.Embed(
            title=f'{user} on c{canvas}', 
            description=f'**User ID:** {user.id}\n**Pixels Placed:** {total_pixels}\n**Undos:** {undo}\n**For TPE:** {tpe_pixels}\n**TPE Griefed:** {tpe_griefs}\n**Mod Overwrites:** {mod}',
            color=discord.Color.red()
            )
            embed.set_author(
                name=user.global_name or user.name, 
                icon_url=user.avatar.url if user.avatar else user.default_avatar.url
                )
            await update_channel.send(embed=embed)

        try: 
            end_time = time.time()
            elapsed_time = end_time - start_time
            file = discord.File(results["output_path"], filename=results["filename"])
            (active_x, active_y), active_count = await most_active(results["user_log_file"])
            description=f'**Pixels Placed:** {results["total_pixels"]}\n**Undos:** {undo}\n**Most Active:** ({active_x}, {active_y}) with {active_count} pixels'
            if config.tpe(canvas):
                description += f'\n**Pixels for TPE:** {results["tpe_pixels"]}'
                description += f'\n**Pixels Griefed:** {results["tpe_griefs"]}'
            if mod > 0:
                description += f'\n**Mod Overwrites:** {mod}'
            embed = discord.Embed(
                title=f'Your Placemap for Canvas {canvas}', 
                description=description,
                color=discord.Color.red()
                )
            embed.set_author(
                name=user.global_name or user.name, 
                icon_url=user.avatar.url if user.avatar else user.default_avatar.url
                )
            embed.set_image(url=f'attachment://{filename}')
            embed.set_footer(text=f'Generated in {elapsed_time:.2f}s')
            view = PlacemapAltView(user, canvas, mode, user_log_file)
            await interaction.followup.send(embed=embed, file=file, view=view)
        except Exception as e:
            await interaction.response.send_message('Error! Something went wrong, check the console.', ephemeral=True)
            print(f'An error occurred: {e}')
            return
    
    @group.command(name='force-check', description='Forcefully check how many pixels a user has placed on all recorded canvases (ADMIN ONLY).')
    async def placemap_db_force_check(self, interaction: discord.Interaction, user: discord.User):
        """Checks how many pixels a user has placed for TPE using logkeys - going past the limit of /logkey generate only checking after the feature was implemented."""
        try:
            if interaction.user.id != owner_id:
                await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True,thinking=True)
            progress = await interaction.followup.send(f'Checking how many pixels <@{user.id}> has placed on all recorded TPE canvases...', ephemeral=True, wait=True)
            async def callback(canvas, idx, total):
                """Update the message so you can see THINGS are HAPPENING."""
                await progress.edit(content=f'Checking how many pixels <@{user.id}> has placed on all recorded TPE canvases... (c{canvas} {idx}/{total})')
                print(f'Processing c{canvas} ({idx}/{total}) for user {user.id}')
            results = await tpe_pixels_count_older(user.id, callback=callback)
            if not results:
                await progress.edit(content=f'No logs found for <@{user.id}>')
                return
            cleaned_results = sorted(results.keys(), key=lambda c: (int(re.sub(r'\D', '', c)), re.sub(r'\d', '', c)))
            header = f'<@{user.id}> ({user.id})'
            header2 = f"{'Canvas':<6} | {'Placed':>7} | {'For TPE':>7} | {'Griefed':>7}"
            header_seperator = f"{'-'*6}-+-{'-'*7}-+-{'-'*7}-+-{'-'*7}"
            pixels_total = sum(stats.get('total_pixels', 0) for stats in results.values())
            tpe_total = sum(stats.get('tpe_pixels', 0) for stats in results.values())
            grief_total = sum(stats.get('tpe_griefs', 0) for stats in results.values())
            lines = []
            for canvas in cleaned_results:
                stats = results[canvas]
                total_pixels = stats.get('total_pixels', 0)
                tpe_pixels = stats.get('tpe_pixels', 0)
                tpe_griefs = stats.get('tpe_griefs', 0)
                line = f"{'c'+canvas:<6} | {total_pixels:>7} | {tpe_pixels:>7} | {tpe_griefs:>7}"
                lines.append(line)
            summary = f"{'-'*6}-+-{'-'*7}-+-{'-'*7}-+-{'-'*7}\n{'Total':<6} | {pixels_total:>7} | {tpe_total:>7} | {grief_total:>7}"
            chunks = []
            current_chunk = f'{header}\n```{header2}\n{header_seperator}'
            for line in lines:
                if len(current_chunk) + len(line) + 50 > 4000:
                    current_chunk = f'\n```' # THIS IS A BACKTICK
                    chunks.append(current_chunk)
                    current_chunk = f'{header2}\n{header_seperator}\n' + line
                else:
                    current_chunk += '\n' + line
            current_chunk += f'\n{summary}\n```' # THIS IS A BACKTICK
            if current_chunk:
                chunks.append(current_chunk)
            if chunks:
                first_embed = discord.Embed(
                    title=f'{user.global_name} ({user.name})',
                    description=chunks[0],
                    color=discord.Color.purple()
                    )
                first_embed.set_author(
                    name=user.global_name or user.name, 
                    icon_url=user.avatar.url if user.avatar else user.default_avatar.url
                    )    
                await progress.edit(content=None, embed=first_embed)
                if len(chunks) > 1:
                    for chunk in chunks[1:]:
                        embed = discord.Embed(
                            description=chunk,
                            color=discord.Color.purple()
                            )
                        await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message('Error! Something went wrong, check the console.', ephemeral=True)
            print(f'An error occurred: {e}')
            return

async def setup(client):
    await client.add_cog(placemap(client))