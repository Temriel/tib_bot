import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
from PIL import Image, ImageDraw, ImageFont
import time
import io
import re
import config
from typing import Union, Optional

database = sqlite3.connect('database.db')
cursor = database.cursor()
database.execute('CREATE TABLE IF NOT EXISTS points(user STR, canvas STR, pixels INT, PRIMARY KEY (user, canvas))')
database.execute('CREATE TABLE IF NOT EXISTS users (user_id INT, username STR UNIQUE, PRIMARY KEY (user_id))')

owner_id = config.owner()
update_channel_id = config.update_channel()

def create_pages(items: list, page: int, page_size: int = 30):
    """Function to determine the amount of pages & what goes where."""
    total_pages = (len(items) + page_size - 1) // page_size
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    return items[start:start + page_size], total_pages

class LeaderboardView(discord.ui.View):
    def __init__(self, all_pixels: list, font_path: str, font_size: int, page_size: int = 30, timeout: Optional[float] = 60, canvas: Optional[str] = None):
        super().__init__(timeout=timeout)
        self.all_pixels = all_pixels
        self.font_path = font_path
        self.font_size = font_size
        self.page_size = page_size
        self.canvas = canvas
        self.current_page = 1
        self.total_pages = (len(all_pixels) + page_size - 1) // page_size
        self.spacing = 18
    
    def generate_embed(self):
        """Generate an embed for /list, applies to pages too."""
        # getting page function, font, and headers
        page_pixels, _ = create_pages(self.all_pixels, self.current_page, self.page_size)
        font = ImageFont.truetype(self.font_path, self.font_size)
        spacing = self.spacing
        top_adjustment = 2
        bottom_adjustment = 3

        bg_color = (24, 4, 53)
        header_color = (75, 0, 130)
        even_row_color = (34, 11, 76)
        odd_row_color = (29, 8, 65)
        border_color = (138, 43, 226)
        text_color = (255, 255, 255)

        headers = ["Rank", "Username", "Pixels"]
        temp_image = Image.new("RGB", (1, 1))
        temp_draw = ImageDraw.Draw(temp_image)

        ranks_value = [
            str(rank) for rank in range(1 + (self.current_page - 1) * self.page_size,
                                        1 + (self.current_page - 1) * self.page_size + len(page_pixels))
                                        ]
        ranks_width = max(temp_draw.textbbox((0, 0), text, font=font)[2] for text in (headers[0], *ranks_value)) + 10

        usernames = [user for user, _ in page_pixels]
        usernames_width = max(temp_draw.textbbox((0, 0), text, font=font)[2] for text in (headers[1], *usernames)) + 10

        pixels = [str(total) for _, total in page_pixels]
        pixels_width = max(temp_draw.textbbox((0, 0), text, font=font)[2] for text in (headers[2], *pixels)) + 10

        ranks_start = spacing
        usernames_start = ranks_start + ranks_width + spacing
        pixels_start = usernames_start + usernames_width + spacing

        ascent, descent = font.getmetrics()
        headers_height = ascent + descent + 10
        rows_height = headers_height
        image_width = pixels_start + pixels_width + spacing
        image_height = headers_height + (rows_height * len(page_pixels)) + bottom_adjustment
        image = Image.new("RGB", (image_width, image_height), color=bg_color)
        draw = ImageDraw.Draw(image)
        # header colour
        draw.rectangle([0, 0, image_width, spacing + top_adjustment + headers_height], fill=header_color)

        # headers
        for idx, text in enumerate(headers):
            if idx == 0:
                start = ranks_start
                width = ranks_width
            elif idx == 1:
                start = usernames_start
                width = usernames_width
            else:
                start = pixels_start
                width = pixels_width
            pos_x = start + (width / 2)
            pos_y = top_adjustment + headers_height / 2 - 1
            draw.text((pos_x, pos_y), text, fill=text_color, font=font, anchor="mm")

        # rows
        y = headers_height
        for i, (user, total_all) in enumerate(page_pixels):
            row_color = even_row_color if i % 2 == 0 else odd_row_color
            draw.rectangle([0, y, image_width, y + rows_height], fill=row_color)

            for idx, (text, start, width) in enumerate([
                (str(i + 1 + (self.current_page - 1) * self.page_size), ranks_start, ranks_width),
                (user, usernames_start, usernames_width),
                (str(total_all), pixels_start, pixels_width)
            ]):
                pos_x = start + (width / 2)
                pos_y = y + (rows_height) / 2 - 1
                draw.text((pos_x, pos_y), text, fill="white", font=font, anchor="mm")
            y += rows_height

        # draw border (last)
        draw.rectangle([0, 0, image_width - 1, image_height - 1], outline=border_color, width=2)

        with io.BytesIO() as image_binary: # below sends the embed w/ the image
            image.save(image_binary, 'PNG')
            image_binary.seek(0)
            file = discord.File(fp=image_binary, filename='leaderboard.png')

        embed = discord.Embed(color=discord.Color.purple())
        if self.canvas:
            embed.title = f"TPE Leaderboard, c{self.canvas}"
        else:
            embed.title = "TPE Leaderboard"
        embed.description = f'Total pixels recorded: **{sum(total for _, total in self.all_pixels)}**'
        embed.set_image(url="attachment://leaderboard.png")
        return embed, file
    
    @discord.ui.button(label='Prev', style=discord.ButtonStyle.primary, custom_id='ldb_previous')
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        start_time = time.time()
        if self.current_page > 1:
            self.current_page -= 1
        else: 
            self.current_page = 1
        embed, file = self.generate_embed()
        end_time = time.time()
        elapsed_time = end_time - start_time
        embed.set_footer(text=f'Generated in {elapsed_time:.2f}s\nPage {self.current_page}/{self.total_pages}')
        await interaction.response.edit_message(embed=embed, attachments=[file], view=self)

    @discord.ui.button(label='Next', style=discord.ButtonStyle.primary, custom_id='ldb_next')
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        start_time = time.time()
        if self.current_page < self.total_pages:
            self.current_page += 1
        else: 
            self.current_page = 1
        embed, file = self.generate_embed()
        end_time = time.time()
        elapsed_time = end_time - start_time
        embed.set_footer(text=f'Generated in {elapsed_time:.2f}s\nPage {self.current_page}/{self.total_pages}')
        await interaction.response.edit_message(embed=embed, attachments=[file], view=self)

def get_linked_discord_username(user_id: int) -> Optional[str]:
    """Get the linked Pxls username for a given Discord user ID."""
    query = "SELECT username FROM users WHERE user_id = ?"
    cursor.execute(query, (user_id,))
    result = cursor.fetchone()
    return result[0] if result else None

def get_linked_pxls_username(pxls_username: str) -> Optional[int]:
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

class db(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print('Main DB cog loaded.')

    @app_commands.command(name='lookup', description='See how many pixels a certain user has placed for us.')
    @app_commands.describe(pxls_username='Pxls username to look up.')
    @app_commands.describe(discord_user='Discord username to look up.')
    async def pixels_db_lookup(self, interaction: discord.Interaction, pxls_username: Optional[str] = None, discord_user: Optional[discord.User] = None):
        """Find the total pixel count for a user & their rank (defined in config.py)"""
        internal_pxls_username: Optional[str] = None # what exists in the db
        internal_discord_user: Optional[Union[discord.User, discord.Member]] = None # same here
        # both provided 
        if pxls_username and discord_user:
            await interaction.response.send_message('Please provide either a Pxls username or a Discord user, not both.', ephemeral=True)
            return
        # only pxls username, finds discord if any 
        elif pxls_username:
            if not re.fullmatch(r'^[a-zA-Z0-9_-]{1,32}$', pxls_username):
                await interaction.response.send_message('Invalid username', ephemeral=True)
                return
            internal_pxls_username = pxls_username
            linked_discord = get_linked_pxls_username(internal_pxls_username)
            if not linked_discord:
                internal_discord_user = None
            else: 
                internal_discord_user = await interaction.client.fetch_user(linked_discord)
        # only discord user, errors if no pxls username
        elif discord_user:
            internal_pxls_username = get_linked_discord_username(discord_user.id)
            internal_discord_user = discord_user
            if not internal_pxls_username:
                await interaction.response.send_message(f'{discord_user} does not have a linked Pxls username (yet)', ephemeral=True)
                return
        # no arguments provided, uses interaction user (errors again if no pxls username)
        else:
            internal_discord_user = interaction.user
            internal_pxls_username = get_linked_discord_username(internal_discord_user.id)
            if not internal_pxls_username:
                await interaction.response.send_message(f'You do not have a linked Pxls username (yet).', ephemeral=True)
                return
        stats = get_stats(internal_pxls_username)
        total = stats['total']
        rank = stats['rank']
        if internal_discord_user:
            await interaction.response.send_message(f"**{internal_discord_user}** (Pxls username: **{internal_pxls_username}**) has placed **{total}** pixels for us. They have the rank of **{rank}**.")
        else:
            await interaction.response.send_message(f"**{internal_pxls_username}** has placed **{total}** pixels for us. They have the rank of **{rank}**.")

    @app_commands.command(name='list', description='See how much people have placed for us.')
    @app_commands.describe(canvas='Canvas code to filter by (no c).')
    async def pixels_db_list(self, interaction: discord.Interaction, canvas: Optional[str] = None):
        """Create a user leaderboard."""
        start_time = time.time()
        if canvas:
            if not re.fullmatch(r'^(?![cC])[a-z0-9]{1,4}+$', canvas):
                await interaction.response.send_message('Invalid format! A canvas code can only contain a-z and 0-9.', ephemeral=True)
                return
            get_users_all = ("SELECT user, SUM(pixels) as total_all FROM points WHERE canvas=? GROUP BY user ORDER BY total_all DESC")
            cursor.execute(get_users_all, (canvas,)) # does the above
        else: 
            get_users_all = "SELECT user, SUM(pixels) as total_all FROM points GROUP BY user ORDER BY total_all DESC"
            cursor.execute(get_users_all) # does the above
        all_pixels = cursor.fetchall() # defines all_pixels to be the thing we got from the database
        if not all_pixels:
            await interaction.response.send_message('No pixels or users found.')
            return # self explanatory but if "all_pixels" is empty it returns this. I love error handling :3  
        all_pixels = [(str(user), total_all) for user, total_all in all_pixels]

        font_path = "font.ttf" # can be any, as long as it's in the main folder 
        font_size = 24
        page_size = 30

        view = LeaderboardView(all_pixels, font_path, font_size, page_size, canvas=canvas)
        embed, file = view.generate_embed()
        end_time = time.time()
        elapsed_time = end_time - start_time
        embed.set_footer(text=f'Generated in {elapsed_time:.2f}s\nPage {view.current_page}/{view.total_pages}')
        await interaction.response.send_message(embed=embed, file=file, view=view)
        
    # Discord user related logic
    @app_commands.command(name='link', description='Link a Pxls username with a Discord user (ADMIN ONLY).')
    @app_commands.describe(userid='The Discord user to link to.', username='The Pxls username to link.')
    async def pixels_db_link(self, interaction: discord.Interaction, userid: discord.User, username: str):
        """Link a Pxls username to a Discord user."""
        query = "INSERT OR REPLACE INTO users VALUES (?, ?)"
        try:
            if interaction.user.id != owner_id:
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

    @app_commands.command(name='unlink', description='Unink a Pxls username from a Discord user (ADMIN ONLY).')
    @app_commands.describe(username='The Pxls username to unlink.')
    async def pixels_db_unlink(self, interaction: discord.Interaction, username: str):
        """Unink a Pxls username from a Discord user."""
        query = "UPDATE users SET username = NULL WHERE username = ?"
        if not re.fullmatch(r'^[a-zA-Z0-9_-]{1,32}$', username):
            await interaction.response.send_message('Invalid username', ephemeral=True)
            return
        try:
            if interaction.user.id != owner_id:
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
    @app_commands.command(name='add-pixels', description='Add pixels to a user (ADMIN ONLY)')
    @app_commands.describe(user='The user to add pixels to.', canvas='Canvas number (no c).', pixels='Amount placed.')
    async def pixels_db_add(self, interaction: discord.Interaction, user: str, canvas: str, pixels: int):
        """Add pixels to a user in the database. Needed values are user, canvas & pixels."""
        query = "INSERT OR REPLACE INTO points VALUES (?, ?, ?)"
        try:
            if interaction.user.id != owner_id:
                await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)
                return
            if not isinstance(canvas, str):
                canvas = str(canvas)
            if not re.fullmatch(r'^(?![cC])[a-z0-9]{1,4}+$', canvas):
                await interaction.response.send_message("Invalid format! A canvas code can only contain a-z and 0-9.", ephemeral=True)
                return
            prev_stats = get_stats(user)
            prev_rank = prev_stats['rank']
            cursor.execute(query, (str(user), canvas, pixels)) # the reason we define query is to make sure cursor.execute isn't Huge
            database.commit()
            new_stats = get_stats(user)
            new_total = new_stats['total']
            new_rank = new_stats['rank']
            if prev_rank != new_rank:
                update_channel = interaction.client.get_channel(update_channel_id)
                if isinstance(update_channel, discord.TextChannel) or isinstance(update_channel, discord.Thread):
                    await update_channel.send(f'**{user}** should now be **{new_rank}**. They have **{new_total}** pixels placed.')
                else:
                    print(f'Does not work for {type(update_channel)}. If this error still peresists, double check the channel ID in config.py, and that the bot has access to it')
            await interaction.response.send_message(f"Added {pixels} pixels for {user} on c{canvas}!")
            print (f"Added {pixels} pixels for {user} on canvas {canvas}")
        except Exception as e:
            await interaction.response.send_message('Error! Something went wrong, check the console.', ephemeral=True)
            print(f'An error occurred: {e}')

async def setup(client):
    await client.add_cog(db(client))