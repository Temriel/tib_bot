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
# from PIL import image 

database = sqlite3.connect('database.db')
cursor = database.cursor()
database.execute('CREATE TABLE IF NOT EXISTS logkey(user INT, canvas STR, key STR, PRIMARY KEY (user, canvas))')

semaphore = asyncio.Semaphore(3)

async def render(user: Union[discord.User, discord.Member], canvas: str, mode: str, user_log_file: str) -> tuple[asyncio.subprocess.Process, str, str]:
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

class placemap(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print('Key DB cog loaded')

    group = app_commands.Group(name="logkey", description="Add your log key or make a placemap from it :3")

    @group.command(name='add', description='Add a log key.') # adds a log key to the database using a fancy ass modal
    async def placemap_db_add(self, interaction: discord.Interaction):
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
        modal = self.placemap_db_add_modal()
        await interaction.response.send_modal(modal)

    class placemap_db_add_modal(discord.ui.Modal, title='Add your log key.'):
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

    @group.command(name='generate', description='Generate a placemap from a log key.')
    async def placemap_db_generate(self, interaction: discord.Interaction, canvas: str):
        await interaction.response.defer(ephemeral=False,thinking=True)
        async with semaphore:
            start_time = time.time()
            get_key = "SELECT key FROM logkey WHERE canvas=? AND user=?"
            user = interaction.user
            ple_dir = config.pxlslog_explorer_dir
            cursor.execute(get_key, (canvas, user.id)) # does the above
            user_key = cursor.fetchone()
            mode = 'normal'

            if not user_key:
                await interaction.followup.send(f'No log key found for this canvas.')
                return
            if not re.fullmatch(r'^(?![cC])[a-z0-9]{1,4}+$', canvas):
                await interaction.followup.send('Invalid format! A canvas code may not begin with a c, and can only contain a-z and 0-9.', ephemeral=True)
                return
            user_key = user_key[0]
            if not re.fullmatch(r'[a-z0-9]{512}', user_key):
                await interaction.followup.send('Invalid format! A log key can only contain a-z, and 0-9.', ephemeral=True)
                return

            try:
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
                    await interaction.followup.send(f'Something went wrong when generating the log file! Ping Temriel.')
                    return
            
                place = 0
                undo = 0
                mod = 0
                with open(user_log_file, 'r') as log_file:
                    for line in log_file:
                        if 'user place' in line:
                            place += 1
                        elif 'user undo' in line:
                            undo += 1
                        elif 'mod overwrite' in line:
                            mod += 1
                total_pixels = place - undo
                print(f'{total_pixels} pixels placed')
                print(f'{undo} pixels undone')
                print(f'{mod} mod overwrites')

                render_result, filename, output_path = await render(user, canvas, mode, user_log_file)
                # function that checks if pixel matches tpe

                if render_result.returncode == 0:
                    end_time = time.time()
                    elapsed_time = end_time - start_time
                    file = discord.File(output_path, filename=filename)
                    (active_x, active_y), active_count = await most_active(user_log_file)
                    description=f'**Pixels Placed:** {total_pixels}\n**Undos:** {undo}\n**Most Active:** ({active_x}, {active_y}) with {active_count} pixels'
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
                else:
                    await interaction.followup.send(f'An error occurred! Ping Temriel.')
            except Exception as e:
                await interaction.followup.send(f'An error occurred! Check the logs.')
                print(f'An error occurred: {e}')

async def setup(client):
    await client.add_cog(placemap(client))