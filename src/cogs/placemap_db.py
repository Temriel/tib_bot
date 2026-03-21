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
from tib_utility.db_utils import cursor, database, generate_placemap, get_linked_pxls_username, description_format, filter, CANVAS_REGEX, KEY_REGEX, ROOT_DIR, pixel_counting
import tempfile
import os
import shutil
from pathlib import Path

owner_id = config.owner()


# noinspection PyTypeChecker
class PlacemapDBAdd(discord.ui.Modal, title='Add your log key.'):
    """Modal to add log keys to the database, with necessary error handling.

    Args:
        discord (_type_): Since it's a modal, it inherits from discord.ui.Modal. This is also where the input fields are defined.
        title (str): The title of the modal, set to "Add your log key." It *can* be anything.
    """
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


class PlacemapDBCheckKeysFromUser(discord.ui.Modal, title='Input desired logkeys here.'):
    # this is gonna be used for adding the keys ONLY, similar to the above (but moreso the admin version)
    def __init__(self, canvas: str, template_paths: list[str], temp_dir: str):
        super().__init__()
        self.canvas = canvas
        self.template_paths = template_paths
        self.temp_dir = temp_dir
        self.logkeys = discord.ui.TextInput(
            label='Log keys, seperated by commas',
            style=discord.TextStyle.paragraph,
            placeholder='log1,log2,log3,...',
            min_length=512,
            max_length=4000,
        )
        self.add_item(self.logkeys)
    
    async def on_submit(self, interaction: discord.Interaction): 
        await interaction.response.send_message('Processing log keys, this may take a while...', ephemeral=True)
        logkeys = [k.strip() for k in self.logkeys.value.strip().split(',') if k.strip()]
        if not logkeys:
            await interaction.edit_original_response(content='No logkeys provided.')
            return
        
        ple_dir = config.pxlslog_explorer_dir
        logfile = f'{ple_dir}/pxls-logs/pixels_c{self.canvas}.sanit.log'
        if not os.path.exists(logfile):
            await interaction.edit_original_response(content='No log file available for this canvas.')
            return
        palette_path, initial_canvas_path = config.palette_initial_paths(self.canvas)
        
        results = {}
        errors = []
        
        for idx, user_key in enumerate(logkeys, start=1):
            users = f'User {idx}'
            if not KEY_REGEX.fullmatch(user_key):
                errors.append(f'Invalid format for log key {idx}! A logkey can only contain a-z and 0-9.')
                continue
            with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.log') as temp_log:
                user_log_file = temp_log.name
            success = await filter(self.canvas, user_key, logfile, user_log_file)
            if not success:
                errors.append(f'Filtering failed for log key {idx}.')
                if os.path.exists(user_log_file):
                    os.unlink(user_log_file)
                continue
            try:
                correct_pixels, grief_pxiels = await db_utils.tpe_pixels_count(
                    user_log_file,
                    temp_pattern='',
                    palette_path=palette_path,
                    initial_canvas_path=initial_canvas_path,
                    logkey_check_from_user=True,
                    template_from_user=self.template_paths
                )
                total_pixels, undo, mod = await pixel_counting(user_log_file)
                results[users] = {
                    'total': total_pixels,
                    'correct': correct_pixels,
                    'grief': grief_pxiels
                }
            except Exception as e:
                errors.append(f'An error occurred while counting pixels for log key {idx}')
                print(f'An error occurred while counting pixels for log key {idx}: {e}')
            finally:
                if os.path.exists(user_log_file):
                    os.unlink(user_log_file)
        if not results:
            if not errors:
                errors.append('No log keys were processed.')
            await interaction.edit_original_response(content=f'All log keys failed to process. Errors: (if any)\n' + '\n'.join(errors))
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
            return
        
        cleaned_results = sorted(results.keys(), key=lambda name: results[name].get('correct', 0), reverse=True)
        header2 = f"{'User':<6} | {'Placed':>7} | {'Correct':>7} | {'Griefed':>7}"
        header_seperator = f"{'-'*6}-+-{'-'*7}-+-{'-'*7}-+-{'-'*7}"
        
        total_pixels = sum(stats.get('total', 0) for stats in results.values())
        # yeah tpe. right
        tpe_total = sum(stats.get('correct', 0) for stats in results.values())
        grief_total = sum(stats.get('grief', 0) for stats in results.values())
        
        lines = []
        for name in cleaned_results:
            stats = results[name]
            line = f"{name:<6} | {stats.get('total', 0):>7} | {stats.get('correct', 0):>7} | {stats.get('grief', 0):>7}"
            lines.append(line)
        summary = f"{'Total':<6} | {total_pixels:>7} | {tpe_total:>7} | {grief_total:>7}"
        description = f"```\n{header2}\n{header_seperator}\n" + "\n".join(lines) + f"\n{header_seperator}\n{summary}\n```" # AHH BACKTICKS
        embed = discord.Embed(
            title=f'Results for c{self.canvas}', 
            description=description,
            color=discord.Color.purple()
        )
        await interaction.edit_original_response(content=None, embed=embed)
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

async def open_add_modal(interaction: discord.Interaction):
    """Open the modal to add a log key.

    Args:
        interaction (discord.Interaction): Discord user.
    """
    modal = PlacemapDBAdd()
    await interaction.response.send_modal(modal)
    
    
async def open_check_modal(interaction: discord.Interaction, canvas: str, template_paths: list[str], temp_dir: str):
    """Open the modal to check log keys against user-provided templates.

    Args:
        interaction (discord.Interaction): Discord user.
        canvas (str): The canvas code to check.
        template_paths (list[str]): List of paths to the user-provided template images.
        temp_dir (str): Path to the temporary directory where the templates are stored.
    """
    modal = PlacemapDBCheckKeysFromUser(canvas, template_paths, temp_dir)
    await interaction.response.send_modal(modal)    
    
##############################
### DISCORD COMMANDS BELOW ###
##############################


class Placemap(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print('Key DB cog loaded')

    group = app_commands.Group(name="logkey", description="Add your log key or make a placemap from it :3")

    @group.command(name='add', description='Add a log key.') # adds a log key to the database using a fancy ass modal
    async def placemap_db_add(self, interaction: discord.Interaction):
        """Command to add a log key to the database. Opens a modal

        Args:
            interaction (discord.Interaction): Discord user.
        """
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
        button.callback = open_add_modal
        view = discord.ui.View()
        view.add_item(button)
        await interaction.response.send_message(embed=embed, view=view)

    @group.command(name='generate', description='Generate a placemap from a log key.')
    @app_commands.describe(canvas='What canvas to generate the placemap for.', nofilter='Skip filtering (only for repeat pladcemaps)')
    async def placemap_db_generate(self, interaction: discord.Interaction, canvas: str, nofilter: Optional[bool] = False):
        """Generate a placemap by piping the necessary arguments to pxlslog-explorer.

        Args:
            interaction (discord.Interaction): The Discord user who uses the command.
            canvas (str): The canvas to use.
            nofilter (Optional[bool], optional): Whether to skip filtering since it's faster. If it fails while True, attempt to generate one anyway. Defaults to False.
        """
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
        """View added logkeys to the bot. Shows if a canvas is considered TPE or not.
        
        Args:
            interaction (discord.Interaction): Who to generate it for (Discord user).
        """
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
    
    @group.command(name='check-template', description='Upload several logkeys and templates to use Tib\'s checking feature')
    async def placemap_db_check_user_template(
        self,
        interaction: discord.Interaction,
        canvas: str,
        image_1: Optional[discord.Attachment] = None,
        image_2: Optional[discord.Attachment] = None,
        image_3: Optional[discord.Attachment] = None,
        image_4: Optional[discord.Attachment] = None,
        image_5: Optional[discord.Attachment] = None,
        image_6: Optional[discord.Attachment] = None,
        image_7: Optional[discord.Attachment] = None,
        image_8: Optional[discord.Attachment] = None,
        image_9: Optional[discord.Attachment] = None,
        image_10: Optional[discord.Attachment] = None,
    ):
        await interaction.response.defer(thinking=True, ephemeral=True)
        images = [img for img in (
            image_1, image_2, image_3, image_4, image_5, 
            image_6, image_7, image_8, image_9, image_10
        ) if img]
        if not CANVAS_REGEX.fullmatch(canvas):
            await interaction.followup.send('Invalid format! A canvas code can only contain a-z and 0-9.', ephemeral=True)
            return
        if not images:
            await interaction.followup.send('Please upload at least one template image.', ephemeral=True)
            return
        print(f'User {interaction.user} is checking templates for canvas {canvas} with {len(images)} images.')
        
        temp_dir = tempfile.mkdtemp()
        template_paths = []
        for idx, img in enumerate(images, start=1):
            out_path = Path(temp_dir) / f'template_{idx}.png'
            await img.save(out_path)
            template_paths.append(out_path)
        embed = discord.Embed(
            title='Template Pixel Checker:tm:', 
            description=f'Canvas: `{canvas}`\nNumber of template images: {len(template_paths)}\nYou can input the logkeys by using the button below.',
            color=discord.Color.purple()
        )
        async def button_callback(interaction: discord.Interaction):
            await open_check_modal(interaction, canvas, template_paths, temp_dir)
        button = discord.ui.Button(label='Input Log Keys', style=discord.ButtonStyle.primary)
        button.callback = button_callback
        view = discord.ui.View()
        view.add_item(button)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

async def setup(client):
    await client.add_cog(Placemap(client))