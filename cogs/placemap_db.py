import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
from PIL import Image, ImageDraw, ImageFont
import io
import os
import subprocess
import re

database = sqlite3.connect('database.db')
cursor = database.cursor()
database.execute('CREATE TABLE IF NOT EXISTS logkey(user INT, canvas STR, key STR, PRIMARY KEY (user, canvas))')

class placemap(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print('Key DB cog loaded.')

    group = app_commands.Group(name="logkey", description="Add your log key or make a placemap from it :3")

    @group.command(name='add', description='Add a log key.') # adds a log key to the database using a fancy ass modal
    async def placemap_db_add(self, interaction: discord.Interaction):
        modal = self.placemap_db_add_modal()
        await interaction.response.send_modal(modal)
    class placemap_db_add_modal(discord.ui.Modal, title='Add your log key.'):
        canvas = discord.ui.TextInput(label='Canvas Number', placeholder='Add canvas number (eg, 28 or 56a).')
        key = discord.ui.TextInput(label='Log key (512 char)', style=discord.TextStyle.paragraph, max_length=512, min_length=512)
        
        async def on_submit(self, interaction: discord.Interaction):
            if not re.fullmatch(r'^(?![cC])[a-z0-9]+$', self.canvas.value):
                await interaction.response.send_message('Invalid format! A canvas code can only contain a-z and 0-9.', ephemeral=True)
                return
            if not re.fullmatch(r'[a-z0-9]{512}', self.key.value):
                await interaction.response.send_message('Invalid format! A log key can only contain a-z, A-Z and 0-9.', ephemeral=True)
                return
            
            user = interaction.user
            query = "INSERT OR REPLACE INTO logkey VALUES (?, ?, ?)" # the three question marks represents the above "user", "canvas", and "logkey"
            try:
                cursor.execute(query, (user.id, self.canvas.value, self.key.value)) # we use user.id to store the ID instead of the user string - das bad
                database.commit()
                print(f'Log key added for {user.id} on canvas {self.canvas.value}.')
                await interaction.response.send_message("Added key!")
            except sqlite3.OperationalError as e:
                await interaction.response.send_message('Error! Something went wrong, ping Temriel.', ephemeral=True)
                print(f'An SQLite3 error occurred: {e}')
            except Exception as e:
                await interaction.response.send_message('Error! Something went wrong, ping Temriel.', ephemeral=True)
                print(f'An error occurred: {e}')

    @group.command(name='generate', description='Generate a placemap from a log key.')
    async def placemap_db_generate(self, interaction: discord.Interaction, canvas: str):
        await interaction.response.defer()
        get_key = "SELECT key FROM logkey WHERE canvas=? AND user=?"
        user = interaction.user
        cursor.execute(get_key, (canvas, user.id)) # does the above
        user_key = cursor.fetchone()
        if not user_key:
            await interaction.followup.send("No log key found for this canvas.")
            return

        if not re.fullmatch(r'^(?![cC])[a-z0-9]+$', canvas):
            await interaction.followup.send('Invalid format! A canvas code may not begin with a c, and can only contain a-z and 0-9.', ephemeral=True)
            return
        user_key = user_key[0]
        if not re.fullmatch(r'[a-z0-9]{512}', user_key):
            await interaction.followup.send('Invalid format! A log key can only contain a-z, and 0-9.', ephemeral=True)
            return

        try:
            if not os.path.isfile('./generate.sh'):
                raise FileNotFoundError(f'Generative script not found.')
            if not os.access('./generate.sh', os.X_OK):
                os.chmod('./generate.sh', 0o755) 
            command = list(map(str, ['C:/Program Files/Git/bin/bash.exe', './generate.sh', str(canvas), str(user.id), str(user_key)])) # change depending on path (or if you actually get a not-absolute path to work then please do tell xD)
#            print(f'Final command list: {command}') # these are for error handling
#            print(f'Command element types: {[type(arg) for arg in command]}') #this one too
            result = subprocess.run(command, capture_output=True, text=True)
            print(f'Subprocess output: {result.stdout}')
            print(f'Subprocess error: {result.stderr}')
            output = f'D:/pxlslog-explorer/target/release/pxls-out-tib' # change depending on path
            filename = f'c{canvas}_normal_{user.id}.png'
            path = os.path.join(output, filename)

            if result.returncode == 0:
                file = discord.File(path, filename=filename)
                embed = discord.Embed(title='Your placemap', color=discord.Color.purple())
                embed.set_image(url=f'attachment://{filename}')
                await interaction.followup.send(embed=embed, file=file)
            else:
                await interaction.followup.send(f'An error occurred! Ping Temriel.')
        except Exception as e:
            await interaction.followup.send(f'An error occurred! Check the logs.')
            print(f'An error occurred: {e}')

async def setup(client):
    await client.add_cog(placemap(client))