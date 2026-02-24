import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
# import subprocess # for error handling
import time
from typing import Optional
# from collections import defaultdict # used previously, cannot remember if this was for error handling or not
import tib_utility.config as config
import tib_utility.db_utils as db_utils
from tib_utility.db_utils import cursor, database, generate_placemap, get_linked_pxls_username, description_format, CANVAS_REGEX, KEY_REGEX

owner_id = config.owner()


# noinspection PyTypeChecker
class PlacemapDBAdd(discord.ui.Modal, title='Add your log key.'):
    canvas = discord.ui.TextInput(label='Canvas Number', placeholder='Add canvas number (eg, 28 or 56a).', max_length=4, min_length=1)
    key = discord.ui.TextInput(label='Log key (512 char)', style=discord.TextStyle.paragraph, max_length=512, min_length=512)
    
    async def on_submit(self, interaction: discord.Interaction):
        if not CANVAS_REGEX.fullmatch(self.canvas.value):
            await interaction.response.send_message('Invalid format! A canvas code can only contain a-z and 0-9.', ephemeral=True)
            return
        if not KEY_REGEX.fullmatch(self.key.value):
            await interaction.response.send_message('Invalid format! A log key can only contain a-z and 0-9.', ephemeral=True)
            return
        
        user = interaction.user
        query = "INSERT OR REPLACE INTO logkey VALUES (?, ?, ?)" # the three question marks represents the above "user", "canvas", and "logkey"
        query_user = "INSERT OR IGNORE INTO users (user_id) VALUES (?)"
        try:
            cursor.execute(query, (user.id, self.canvas.value, self.key.value)) # we use user.id to store the ID instead of the user string - das bad
            cursor.execute(query_user, (user.id,))
            database.commit()
            print(f'Log key added for {user} ({user.id}) on canvas {self.canvas.value}.')
            await interaction.response.send_message(f'Added key for canvas {self.canvas.value}!', ephemeral=True)
            return
        except sqlite3.OperationalError as e:
            await interaction.response.send_message('Error! Something with the DB went wrong, ping Temriel.', ephemeral=True)
            print(f'An SQLite3 error occurred: {e}')
            return
        except Exception as e:
            await interaction.response.send_message('Error! Something went wrong, ping Temriel.', ephemeral=True)
            print(f'An error occurred: {e}')
            return

##############################
### DISCORD COMMANDS BELOW ###
##############################

async def open_modal(interaction: discord.Interaction):
    modal = PlacemapDBAdd()
    await interaction.response.send_modal(modal)


class Placemap(commands.Cog):
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
        # noinspection PyTypeChecker
        button = discord.ui.Button(label='Add Log Key', style=discord.ButtonStyle.primary)
        button.callback = open_modal
        view = discord.ui.View()
        view.add_item(button)
        await interaction.response.send_message(embed=embed, view=view)

    @group.command(name='generate', description='Generate a placemap from a log key.')
    @app_commands.describe(canvas='What canvas to generate the placemap for.', nofilter='Skip filtering (only for repeat pladcemaps, much faster but returns if no logkey)')
    async def placemap_db_generate(self, interaction: discord.Interaction, canvas: str, nofilter: Optional[bool] = False):
        """Generate a placemap by piping the necessary arguments to pxlslog-explorer."""
        user = interaction.user
        update_channel_id = config.update_channel()
        update_channel = interaction.client.get_channel(update_channel_id)
        start_time = time.time()
        if nofilter is not None:
            nofilter = nofilter
        await interaction.response.defer(ephemeral=False,thinking=True)
        state, results = await generate_placemap(user, canvas, nofilter)

        if state:
            constructed_desc = await description_format(canvas, results)
            mode = results.get("mode", "0")
            user_log_file = results.get("user_log_file", "0")
        else:
            await interaction.followup.send(results['error'])
            return
        pxls_username = await get_linked_pxls_username(user.id)
        if not pxls_username:
            pxls_username = user.global_name or user.name

        if isinstance(update_channel, discord.TextChannel) or isinstance(update_channel, discord.Thread):
            embed = discord.Embed(
            title=f'{pxls_username} on c{canvas}', 
            description=f'**User ID:** {user.id}\n{constructed_desc}',
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
            print(f'/logkey generate took {elapsed_time:.2f}s')
            file = discord.File(results["output_path"], filename=results["filename"])
            description=constructed_desc
            embed = discord.Embed(
                title=f'Your Placemap for Canvas {canvas}', 
                description=description,
                color=discord.Color.purple()
                )
            embed.set_author(
                name=user.name, 
                icon_url=user.avatar.url if user.avatar else user.default_avatar.url
                )
            embed.set_image(url=f'attachment://{results["filename"]}')
            embed.set_footer(text=f'Generated in {elapsed_time:.2f}s')
            view = db_utils.PlacemapAltView(user, canvas, mode, user_log_file)
            await interaction.followup.send(embed=embed, file=file, view=view)
        except Exception as e:
            await interaction.response.send_message('Error! Something went wrong, check the console.', ephemeral=True)
            print(f'An error occurred: {e}')
            return
    
    @group.command(name='view', description='View your stored log keys.')
    async def placemap_db_view(self, interaction: discord.Interaction):
        """View stored logkeys"""
        user = interaction.user
        query = "SELECT canvas FROM logkey WHERE user = ? ORDER BY CAST(canvas AS INTEGER) DESC, canvas DESC"
        try:
            cursor.execute(query, (user.id,))
            results = cursor.fetchall()
            if not results:
                await interaction.response.send_message('No log keys found for your user!', ephemeral=True)
                return
            canvases = [str(row[0]) for row in results]
            cols = 4
            rows_count = (len(canvases) + cols - 1) // cols
            rows = []
            for r in range(rows_count):
                row = []
                for c in range(cols):
                    idx = r * cols + c
                    row.append(canvases[idx] if idx < len(canvases) else '')
                rows.append(row)
            width = 16
            lines = []
            for row in rows:
                cells = []
                for entry in row:
                    if not entry:
                        cells.append(''.ljust(width))
                        continue
                    display = f'c{entry}'
                    if not entry[-1].isalpha():
                        display += ' '
                    marker = ':purple_heart:' if config.tpe(entry) else ':black_heart:'
                    cells.append(f'{marker}`{display}`'.ljust(width))
                lines.append(''.join(cells))
            found_keys = "\n".join(lines)
            embed = discord.Embed(
                title=f'Your added log keys', 
                description=found_keys,
                color=discord.Color.purple()
                )
            embed.set_author(
                name=user.name, 
                icon_url=user.avatar.url if user.avatar else user.default_avatar.url
                )
            await interaction.response.send_message(embed=embed)
            
        except sqlite3.OperationalError as e:
            await interaction.response.send_message('Error! Something with the DB went wrong, ping Temriel.', ephemeral=True)
            print(f'An SQLite3 error occurred: {e}')
            return
        except Exception as e:
            await interaction.response.send_message('Error! Something went wrong, ping Temriel.', ephemeral=True)
            print(f'An error occurred: {e}')
            return

async def setup(client):
    await client.add_cog(Placemap(client))