import discord
from discord import app_commands
from discord.ext import commands
import tib_utility.config as config
import sqlite3
import time
import re
import tib_utility.db_utils as db_utils
from tib_utility.db_utils import cursor, database, get_stats, generate_placemap, tpe_pixels_count_user, \
    find_pxls_username, tpe_pixels_count_canvas, description_format, CANVAS_REGEX, KEY_REGEX, resolve_name


async def is_owner_check(interaction: discord.Interaction) -> bool:
    """Check if the user is the owner of the bot. Is usually used to return a function immediately."""
    return interaction.user.id == config.owner()

class PlacemapDBAddAdmin(discord.ui.Modal, title='Force add a logkey'):
    user_canvas = discord.ui.TextInput(label='userID/name, canvas', placeholder='uID,28,30a,59 OR 56a,uID1,uID2,uID3', style=discord.TextStyle.short, max_length=200)
    key = discord.ui.TextInput(label='Log keys (512 char each)', placeholder='key1,key2,key3,key4,key5,key6', style=discord.TextStyle.paragraph, max_length=4000)

    async def on_submit(self, interaction: discord.Interaction):
        query_logkey = "INSERT OR REPLACE INTO logkey VALUES (?, ?, ?)"
        query_user = "INSERT OR IGNORE INTO users (user_id) VALUES (?)"
        try:
            if not await is_owner_check(interaction):
                await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)
                return

            user_canvases = [x.strip() for x in self.user_canvas.value.split(',')]
            keys = [x.strip() for x in self.key.value.split(',')]
            if len(user_canvases) < 2:
                await interaction.response.send_message('You must provide a user ID and at least one canvas.', ephemeral=True)
                return

            first_item = user_canvases[0]
            is_canvas_many = not CANVAS_REGEX.fullmatch(first_item)
            
            if is_canvas_many: # one user, multiple canvases
                user_input = user_canvases[0]
                canvases = user_canvases[1:]
                user_id = resolve_name(user_input)
                if not user_id:
                    await interaction.response.send_message(f'Could not find a linked name for {user_input}. Are you sure you typed it correctly or that they\'re linked?', ephemeral=True)
                if len(keys) != len(canvases):
                    await interaction.response.send_message('The number of keys must match the number of canvases.', ephemeral=True)
                    return
                success = []
                fail = []
                for canvas, key in zip(canvases, keys):
                    if not CANVAS_REGEX.fullmatch(canvas):
                        fail.append(f'c{canvas}, Invalid canvas format')
                        continue
                    if not KEY_REGEX.fullmatch(key):
                        fail.append(f'c{canvas}, Invalid key format')
                        continue
                    try:
                        cursor.execute(query_logkey, (user_id, canvas, key))
                        cursor.execute(query_user, (user_id,))
                        database.commit()
                        success.append(f'c{canvas}')
                    except sqlite3.OperationalError as e:
                        fail.append(f'c{canvas}, SQLite error: {e}')
                    except Exception as e:
                        fail.append(f'c{canvas}, Error: {e}')
                message = f'<@{user_id}> ({user_id}) now has keys for canvases: {', '.join(success)}'
                if fail:
                    message += f'\nFailed for canvases: {', '.join(fail)}'
                await interaction.response.send_message(message, ephemeral=True)
                
            else: # one canvas, multiple users
                canvas = user_canvases[0]
                user_inputs = user_canvases[1:]
                if len(keys) != len(user_inputs):
                    await interaction.response.send_message('The number of keys must match the number of canvases.', ephemeral=True)
                    return
                success = []
                fail = []
                for user_input, key in zip(user_inputs, keys):
                    user_id = await resolve_name(user_input)
                    if not user_id:
                        fail.append(f'<@{user_id}> ({user_id}), Invalid user ID format')
                        continue
                    if not KEY_REGEX.fullmatch(key):
                        fail.append(f'<@{user_id}> ({user_id}), Invalid key format')
                        continue
                    try:
                        cursor.execute(query_logkey, (int(user_id), canvas, key))
                        cursor.execute(query_user, (user_id,))
                        database.commit()
                        success.append(f'<@{user_id}> ({user_id})')
                    except sqlite3.OperationalError as e:
                        fail.append(f'{user_input}, SQLite error: {e}')
                    except Exception as e:
                        fail.append(f'{user_input}, Error: {e}')
                message = f'c{canvas} now has logkeys for: {', '.join(success)}'
                if fail:
                    message += f'\nFailed for users: {', '.join(fail)}'
                await interaction.response.send_message(message, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message('Error! Something went wrong, check the console.', ephemeral=True)
            print(f'An error occurred: {e}')


class Admin(commands.Cog): # this is for the actual Discord commands part
    def __init__(self, client):
        self.client = client
        self.owner_id = config.owner()
        self.update_channel_id = config.update_channel()
        self.hidden = True

    @commands.Cog.listener()
    async def on_ready(self):
        print('Admin cog loaded.')

    group = app_commands.Group(name="admin", description="Admin only commands :3")
    @group.command(name='link', description='Link a Pxls username with a Discord user (ADMIN ONLY).')
    @app_commands.describe(userid='The Discord user to link to.', username='The Pxls username to link.')
    async def pixels_db_link(self, interaction: discord.Interaction, userid: discord.User, username: str):
        """Link a Pxls username to a Discord user."""
        query = "INSERT OR REPLACE INTO users VALUES (?, ?)"
        try:
            if not await is_owner_check(interaction):
                await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)
                return
            cursor.execute(query, (userid.id, username))
            database.commit()
            await interaction.response.send_message(f'Successfully linked **{username}** to **{userid}**!')
        except sqlite3.IntegrityError:
            await interaction.response.send_message(f'Error! The username **{username}** is already linked to another user.', ephemeral=True)
        except Exception as e:
            await interaction.response.send_message('Error! Something went wrong, check the console.', ephemeral=True)
            print(f'An error occurred: {e}')

    @group.command(name='unlink', description='Unink a Pxls username from a Discord user (ADMIN ONLY).')
    @app_commands.describe(username='The Pxls username to unlink.')
    async def pixels_db_unlink(self, interaction: discord.Interaction, username: str):
        """Unink a Pxls username from a Discord user."""
        query = "UPDATE users SET username = NULL WHERE username = ?"
        if not re.fullmatch(r'^[a-zA-Z0-9_-]{1,32}$', username):
            await interaction.response.send_message('Invalid username', ephemeral=True)
            return
        try:
            if not await is_owner_check(interaction):
                await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)
                return
            cursor.execute(query, (username,))
            database.commit()
            if cursor.rowcount > 0:
                await interaction.response.send_message(f'Successfully unlinked **{username}**!')
            else:
                await interaction.response.send_message(f'No linked user found for **{username}**.', ephemeral=True)
        except Exception as e:
            await interaction.response.send_message('Error! Something went wrong, check the console.', ephemeral=True)
            print(f'An error occurred: {e}')

    # Pxls related logic
    @group.command(name='add-pixels', description='Add pixels to a user (ADMIN ONLY)')
    @app_commands.describe(user='The user to add pixels to.', canvas='Canvas number (no c).', pixels='Amount placed.')
    async def pixels_db_add(self, interaction: discord.Interaction, user: str, canvas: str, pixels: int):
        """Add pixels to a user in the database. Needed values are user, canvas & pixels."""
        query = "INSERT OR REPLACE INTO points VALUES (?, ?, ?)" # the reason we define query is to make sure cursor.execute isn't Huge
        try:
            if not await is_owner_check(interaction):
                await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)
                return
            if not isinstance(canvas, str):
                canvas = str(canvas)
            if not CANVAS_REGEX.fullmatch(canvas):
                await interaction.response.send_message("Invalid format! A canvas code can only contain a-z and 0-9.", ephemeral=True)
                return
            prev_stats = get_stats(user) # so we can check for rank changes
            prev_rank = prev_stats['rank']
            cursor.execute(query, (str(user), canvas, pixels))
            database.commit()
            new_stats = get_stats(user)
            new_total = new_stats['total']
            new_rank = new_stats['rank']
            if prev_rank != new_rank:
                if new_rank == "griefer":
                    new_rank = "a griefer" # so the update_channel message makes more sense 
                update_channel = interaction.client.get_channel(self.update_channel_id)
                if isinstance(update_channel, discord.TextChannel) or isinstance(update_channel, discord.Thread):
                    await update_channel.send(f'**{user}** should now be **{new_rank}**. They have **{new_total}** pixels placed.')
                else:
                    print(f'Does not work for {type(update_channel)}. If this error still persists, double check the channel ID in config.py, and that the bot has access to it')
            if pixels >= 0:
                status = "Added"
            else:
                status = "Removed"
            await interaction.response.send_message(f"{status} {pixels} pixels for {user} on c{canvas}!")
            print (f"{status} {pixels} pixels for {user} on canvas {canvas}")
        except Exception as e:
            await interaction.response.send_message('Error! Something went wrong, check the console.', ephemeral=True)
            print(f'An error occurred: {e}')

    @group.command(name='notfy-users', description='Notify all users who signed up for notifications about a new canvas (ADMIN ONLY).')
    async def notifications_admin(self, interaction: discord.Interaction):
        """Notify all users who signed up for notifications about a new canvas (ADMIN ONLY)."""
        if not await is_owner_check(interaction):
            await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=False,thinking=True)
        cursor.execute('SELECT user_id FROM notif WHERE status = 1')
        users_to_notify = cursor.fetchall()
        notified_count = 0
        for (user_id,) in users_to_notify:
            user = self.client.get_user(user_id)
            if user is None:
                try:
                    user = await self.client.fetch_user(user_id)
                except Exception as e:
                    print(f'Failed to fetch user {user_id}: {e}')
                    continue
            if user:
                try:
                    await user.send('Tib now has the latest canvas in its DB, you can now create placemaps as you wish.')
                    notified_count += 1
                except Exception as e:
                    print(f'Failed to notify user {user_id}: {e}')
        await interaction.followup.send(f'Notified {notified_count} users.', ephemeral=True)

    @group.command(name='force-add', description='Force add a logkey for a user (ADMIN ONLY).') 
    async def placemap_db_add_admin(self, interaction: discord.Interaction):
        """Add a logkey forcefully"""
        try:
            if not await is_owner_check(interaction):
                await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)
                return
            modal = PlacemapDBAddAdmin()
            await interaction.response.send_modal(modal)

        except Exception as e:
            await interaction.response.send_message('Error! Something went wrong, check the console.', ephemeral=True)
            print(f'An error occurred: {e}')

    @group.command(name='force-generate', description='Forcefully generate a placemap for a user (ADMIN ONLY).')
    @app_commands.describe(user='The user to generate the placemap for.', canvas='What canvas to generate the placemap for.')
    async def placemap_db_generate_admin(self, interaction: discord.Interaction, user: discord.User, canvas: str):
        """Forcefully generate a placemap by piping the necessary arguments to pxlslog-explorer."""
        if not await is_owner_check(interaction):
            await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)
            return
        update_channel_id = config.update_channel()
        update_channel = interaction.client.get_channel(update_channel_id)
        start_time = time.time()
        await interaction.response.defer(ephemeral=False,thinking=True)
        state, results = await generate_placemap(user, canvas)

        if state:
            constructed_desc = await description_format(canvas, results)
            mode = results.get("mode", "0")
            user_log_file = results.get("user_log_file", "0")
        else:
            await interaction.followup.send(results['error'])
            return
        pxls_username = await find_pxls_username(user)
        if isinstance(update_channel, discord.TextChannel) or isinstance(update_channel, discord.Thread):
            embed = discord.Embed(
            title=f'{pxls_username} on c{canvas}', 
            description=f'**User ID:** {user.id}\n{constructed_desc}',
            color=discord.Color.red()
            )
            embed.set_author(
                name=user.name, 
                icon_url=user.avatar.url if user.avatar else user.default_avatar.url
                )
            await update_channel.send(embed=embed)

        try: 
            end_time = time.time()
            elapsed_time = end_time - start_time
            print(f'/admin force-generate took {elapsed_time:.2f}s')
            file = discord.File(results["output_path"], filename=results["filename"])
            description=constructed_desc
            embed = discord.Embed(
                title=f'Your Placemap for Canvas {canvas}', 
                description=description,
                color=discord.Color.red()
                )
            embed.set_author(
                name=user.global_name or user.name, 
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
    
    @group.command(name='force-check-user', description='Forcefully check how many pixels a user has placed on all recorded canvases (ADMIN ONLY).')
    @app_commands.describe(user='The user to check (user ID works too).')
    async def placemap_db_force_check_user(self, interaction: discord.Interaction, user: discord.User):
        """Checks how many pixels a user has placed for TPE using logkeys - going past the limit of /logkey generate only checking after the feature was implemented."""
        try:
            if not await is_owner_check(interaction):
                await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True, thinking=True)
            progress = await interaction.followup.send(f'Checking how many pixels <@{user.id}> has placed on all recorded canvases...', ephemeral=True, wait=True)
            
            async def callback(used_canvas, idx, total):
                """Update the message so you can see THINGS are HAPPENING."""
                await progress.edit(content=f'Checking how many pixels <@{user.id}> has placed on all recorded TPE canvases... (c{used_canvas} {idx}/{total})')
                print(f'Processing c{used_canvas} ({idx}/{total}) for user {user.id}')
            results = await tpe_pixels_count_user(user.id, callback=callback)
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
                stats = results.get(canvas, {})
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
                    title=f'Stats for {user.global_name} ({user.name})',
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
            await interaction.followup.send('Error! Something went wrong, check the console.', ephemeral=True)
            print(f'An error occurred: {e}')
            return

    @group.command(name='force-check-canvas', description='Forcefully check how many pixels all users have placed on a specific canvas (ADMIN ONLY).')
    @app_commands.describe(canvas='What canvas to check (no c).')
    async def placemap_db_force_check_canvas(self, interaction: discord.Interaction, canvas: str):
        """Checks how many pixels all users have placed for TPE on a specific canvas using logkeys - going past the limit of /logkey generate only checking after the feature was implemented."""
        try:
            if not await is_owner_check(interaction):
                await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True, thinking=True)
            progress = await interaction.followup.send(f'Checking how many pixels have been placed on canvas {canvas}...', ephemeral=True, wait=True)
            async def callback(user_id, idx, total):
                """Update the message so you can see THINGS are HAPPENING."""
                await progress.edit(content=f'Checking how many pixels have been placed on canvas {canvas}... (user {user_id} {idx}/{total})')
                print(f'Processing user {user_id} ({idx}/{total}) for c{canvas}')
            results = await tpe_pixels_count_canvas(canvas, callback=callback)
            if not results:
                await progress.edit(content=f'No logs found for c{canvas}, or there\'s no user data present.')
                return
            cursor.execute('SELECT user_id, username FROM users WHERE username IS NOT NULL')
            linked_users = dict(cursor.fetchall())
            cleaned_results = sorted(results.keys(), key=lambda user_id: results[user_id].get('tpe_pixels', 0), reverse=True)
            header2 = f"{'User':<20} | {'Placed':>7} | {'For TPE':>7} | {'Griefed':>7}"
            header_seperator = f"{'-'*20}-+-{'-'*7}-+-{'-'*7}-+-{'-'*7}"
            pixels_total = sum(stats.get('total_pixels', 0) for stats in results.values())
            tpe_total = sum(stats.get('tpe_pixels', 0) for stats in results.values())
            grief_total = sum(stats.get('tpe_griefs', 0) for stats in results.values())
            lines = []
            for user_id in cleaned_results:
                stats = results.get(user_id, {})
                total_pixels = stats.get('total_pixels', 0)
                tpe_pixels = stats.get('tpe_pixels', 0)
                tpe_griefs = stats.get('tpe_griefs', 0)
                name = linked_users.get(user_id, str(user_id))
                line = f"{name:<20} | {total_pixels:>7} | {tpe_pixels:>7} | {tpe_griefs:>7}"
                lines.append(line)
            summary = f"{'-'*20}-+-{'-'*7}-+-{'-'*7}-+-{'-'*7}\n{'Total':<20} | {pixels_total:>7} | {tpe_total:>7} | {grief_total:>7}"
            chunks = []
            current_chunk = f'```{header2}\n{header_seperator}'
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
                    title=f'Logfile-based leaderboard for c{canvas}',
                    description=chunks[0],
                    color=discord.Color.purple()
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
            await interaction.followup.send('Error! Something went wrong, check the console.', ephemeral=True)
            print(f'An error occurred: {e}')

async def setup(client):
    admin_guild = discord.Object(id=config.admin_server())
    dev_guild = discord.Object(id=config.dev_server())
    await client.add_cog(Admin(client), guilds=[admin_guild, dev_guild])