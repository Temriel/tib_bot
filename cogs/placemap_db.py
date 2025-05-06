import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import config
import subprocess
import re
import time
import asyncio
# from collections import defaultdict
# from PIL import image

database = sqlite3.connect('database.db')
cursor = database.cursor()
database.execute('CREATE TABLE IF NOT EXISTS logkey(user INT, canvas STR, key STR, PRIMARY KEY (user, canvas))')

semaphore = asyncio.Semaphore(3)

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
            bg, palette_path, output_path = config.paths(canvas, user.id)
            ple_dir = config.pxlslog_explorer_dir
            cursor.execute(get_key, (canvas, user.id)) # does the above
            user_key = cursor.fetchone()

            if not re.fullmatch(r'^(?![cC])[a-z0-9]{1,4}+$', canvas):
                await interaction.followup.send('Invalid format! A canvas code may not begin with a c, and can only contain a-z and 0-9.', ephemeral=True)
                return
            user_key = user_key[0]
            if not re.fullmatch(r'[a-z0-9]{512}', user_key):
                await interaction.followup.send('Invalid format! A log key can only contain a-z, and 0-9.', ephemeral=True)
                return
            if not user_key:
                await interaction.followup.send(f'No log key found for this canvas.')
                return

            try:
                user_log_file = f'{ple_dir}/pxls-userlogs-tib/{user.id}_pixels_c{canvas}.log'
                filter_cli = [f'{ple_dir}/filter.exe', '--user', user_key, '--log', f'{ple_dir}/pxls-logs/pixels_c{canvas}.sanit.log', '--output', user_log_file]
                filter_result = await asyncio.create_subprocess_exec(
                    *filter_cli, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                print(f'Filtering {user_key} for {user} on canvas {canvas}.')
                stdout, stderr = await filter_result.communicate()
                print(f'Subprocess output: {stdout}')
                print(f'Subprocess error: {stderr}')
                if filter_result.returncode != 0:
                    await interaction.followup.send(f'Something went wrong when generating the log file! Ping Temriel.')
                    return
            
                place = 0
                undo = 0
                with open(user_log_file, 'r') as log_file:
                    for line in log_file:
                        if 'user place' in line:
                            place += 1
                        elif 'user undo' in line:
                            undo += 1

                total_pixels = place - undo
                print(f'{total_pixels} pixels placed')
                print(f'{undo} pixels undone')

                render_cli = [f'{ple_dir}/render.exe', '--log', user_log_file, '--bg', bg, '--palette', palette_path, '--screenshot', '--output', output_path, 'normal']
                # render_result = subprocess.run(render_cli, capture_output=True, text=True) # use for error handling
                render_result = await asyncio.create_subprocess_exec(
                    *render_cli, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                print(f'Generating placemap for {user} on canvas {canvas}')
                stdout, stderr = await render_result.communicate()
                print(f'Subprocess output: {stdout}')
                print(f'Subprocess error: {stderr}')
                # print(f'Final command list: {render_cli}') # use for error handling
                filename = f'c{canvas}_normal_{user.id}.png'
                path = output_path

                # function that checks if pixel matches tpe

                if render_result.returncode == 0:
                    end_time = time.time()
                    elapsed_time = end_time - start_time
                    file = discord.File(path, filename=filename)
                    embed = discord.Embed(
                        title=f'Your Placemap for Canvas {canvas}', 
                        description=f"**Pixels placed:** {total_pixels}\n**Undos:** {undo}", 
                        color=discord.Color.purple()
                        )
                    embed.set_author(name=user.global_name, icon_url=user.avatar.url)
                    embed.set_image(url=f'attachment://{filename}')
                    embed.set_footer(text=f'Generated in {elapsed_time:.2f}s')
                    await interaction.followup.send(embed=embed, file=file)
                else:
                    await interaction.followup.send(f'An error occurred! Ping Temriel.')
            except Exception as e:
                await interaction.followup.send(f'An error occurred! Check the logs.')
                print(f'An error occurred: {e}')

async def setup(client):
    await client.add_cog(placemap(client))