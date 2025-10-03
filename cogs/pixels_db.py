import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
from PIL import Image, ImageDraw, ImageFont
import time
import io
import re
import config
from typing import Optional

database = sqlite3.connect('database.db')
cursor = database.cursor()
database.execute('CREATE TABLE IF NOT EXISTS points(user STR, canvas STR, pixels INT, PRIMARY KEY (user, canvas))')

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
        headers = ["Rank", "Username", "Pixels"]
        temp_image = Image.new("RGB", (1, 1))
        temp_draw = ImageDraw.Draw(temp_image)

        # header pos
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
        
        # image gen
        headers_height = temp_draw.textbbox((0, 0), "Ag", font=font)[3]
        rows_height = headers_height + 3
        image_width = pixels_start + pixels_width + spacing
        image_height = spacing + rows_height * (len(page_pixels) + 1) + spacing
        image = Image.new("RGB", (image_width, image_height), color=(24, 4, 53))
        draw = ImageDraw.Draw(image)

        y = spacing
        text = headers[0]
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        pos_x = ranks_start + (ranks_width - text_width) / 2
        draw.text((pos_x, y), text, fill="white", font=font)

        text = headers[1]
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        pos_x = usernames_start + (usernames_width - text_width) / 2
        draw.text((pos_x, y), text, fill="white", font=font)

        text = headers[2]
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        pos_x = pixels_start + (pixels_width - text_width) / 2
        draw.text((pos_x, y), text, fill="white", font=font)

        y += rows_height
        for i, (user, total_all) in enumerate(page_pixels):
            rank_text = str(i + 1 + (self.current_page - 1) * self.page_size)
            bbox = draw.textbbox((0, 0), rank_text, font=font)
            text_width = bbox[2] - bbox[0]
            pos_x = ranks_start + (ranks_width - text_width) / 2
            draw.text((pos_x, y), rank_text, fill="white", font=font)

            bbox = draw.textbbox((0, 0), user, font=font)
            text_width = bbox[2] - bbox[0]
            pos_x = usernames_start + (usernames_width - text_width) / 2
            draw.text((pos_x, y), user, fill="white", font=font)
            
            pixels_text = str(total_all)
            bbox = draw.textbbox((0, 0), pixels_text, font=font)
            text_width = bbox[2] - bbox[0]
            pos_x = pixels_start + (pixels_width - text_width) / 2
            draw.text((pos_x, y), pixels_text, fill="white", font=font)
            y += rows_height

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

class db(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print('Main DB cog loaded.')
    
    @app_commands.command(name='add-pixels', description='Add pixels to a user (ADMIN ONLY)')
    @app_commands.describe(user='The user to add pixels to.', canvas='Canvas number (no c).', pixels='Amount placed.')
    async def pixels_db_add(self, interaction: discord.Interaction, user: str, canvas: str, pixels: int):
        """Add pixels to a user in the database. Needed values are user, canvas & pixels."""
        query = "INSERT OR REPLACE INTO points VALUES (?, ?, ?)"
        try:
            if interaction.user.id == owner_id:
                if not isinstance(canvas, str):
                    canvas = str(canvas)
                if not re.fullmatch(r'^(?![cC])[a-z0-9]{1,4}+$', canvas):
                    await interaction.response.send_message("Invalid format! A canvas code can only contain a-z and 0-9.", ephemeral=True)
                    return
                cursor.execute("SELECT SUM(pixels) FROM points WHERE user=?", (user,))
                prev_total = cursor.fetchone()[0] or 0
                prev_rank = "nothing"
                ranks = config.ranks()
                for threshold, name in ranks:
                    if prev_total >= threshold:
                        prev_rank = name
                        break
                if prev_total < 0:
                    prev_rank = "griefer"
                cursor.execute(query, (str(user), canvas, pixels)) # the reason we define query is to make sure cursor.execute isn't Huge
                database.commit()
                cursor.execute("SELECT SUM(pixels) FROM points WHERE user=?", (user,))
                new_total = cursor.fetchone()[0] or 0
                new_rank = "nothing"
                for threshold, name in ranks:
                    if new_total >= threshold:
                        new_rank = name
                        break
                if new_total < 0:
                    new_rank = "griefer"
                if prev_rank != new_rank:
                    update_channel = interaction.client.get_channel(update_channel_id)
                    if isinstance(update_channel, discord.TextChannel) or isinstance(update_channel, discord.Thread):
                        await update_channel.send(f'**{user}** should now be **{new_rank}**. They have **{new_total}** pixels placed.')
                    else:
                        print(f'Does not work for {type(update_channel)}. If this error still peresists, double check the channel ID in config.py, and that the bot has access to it')
                await interaction.response.send_message(f"Added {pixels} pixels for {user} on c{canvas}!")
                print (f"Added {pixels} pixels for {user} on canvas {canvas}")
            else:
                await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message('Error! Something went wrong, check the console.', ephemeral=True)
            print(f'An error occurred: {e}')

    @app_commands.command(name='lookup', description='See how many pixels a certain user has placed for us.')
    @app_commands.describe(profile='Who do you want to look up?')
    async def pixels_db_lookup(self, interaction: discord.Interaction, profile: str):
        """Find the total pixel count for a user & their rank (defined in config.py)"""
        if not re.fullmatch(r'^[a-zA-Z0-9_-]{1,32}$', profile):
            await interaction.response.send_message('Invalid username', ephemeral=True)
            return
        get_users = "SELECT SUM(pixels) FROM points WHERE user=?"
        cursor.execute(get_users, (profile,))
        total = cursor.fetchone()[0]
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
        await interaction.response.send_message(f"**{profile}** has placed **{total}** pixels for us. They have the rank of **{rank}**.")

    @app_commands.command(name='list', description='See how much people have placed for us.')
    async def pixels_db_list(self, interaction: discord.Interaction, canvas: Optional[str] = None):
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

async def setup(client):
    await client.add_cog(db(client))