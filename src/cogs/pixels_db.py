import discord
from discord import app_commands, Interaction
from discord.ext import commands
import os
from PIL import Image, ImageDraw, ImageFont
import time
import io
from tib_utility.db_utils import cursor, get_linked_discord_username, get_linked_pxls_username, get_stats, CANVAS_REGEX, USERNAME_REGEX
from typing import Optional

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
                pos_y = y + rows_height / 2 - 1
                draw.text((pos_x, pos_y), text, fill="white", font=font, anchor="mm")
            y += rows_height

        # draw border (last)
        draw.rectangle([0, 0, image_width - 1, image_height - 1], outline=border_color, width=2)

        embed = discord.Embed(color=discord.Color.purple()) # moved here so the canvas check is only done once
        with io.BytesIO() as image_binary: # below sends the embed w/ the image
            image.save(image_binary, 'PNG')
            image_binary.seek(0)
            
            if self.canvas:
                file = discord.File(fp=image_binary, filename=f'c{self.canvas}_leaderboard.png')
                embed.set_image(url=f"attachment://c{self.canvas}_leaderboard.png")
                embed.title = f"TPE c{self.canvas} Leaderboard"
            else:
                file = discord.File(fp=image_binary, filename='alltime_leaderboard.png')
                embed.set_image(url="attachment://alltime_leaderboard.png")
                embed.title = "TPE all-time Leaderboard"
                
        embed.description = f"Total pixels recorded: **{sum(total for _, total in self.all_pixels)}**\n"
        embed.description += f"Total users recorded: **{len(self.all_pixels)}**"
        return embed, file


    async def pages_embed(self, interaction: Interaction, start_time: float):
        embed, file = self.generate_embed()
        end_time = time.time()
        elapsed_time = end_time - start_time
        embed.set_footer(text=f'Generated in {elapsed_time:.2f}s\nPage {self.current_page}/{self.total_pages}')
        await interaction.response.edit_message(embed=embed, attachments=[file], view=self)


    @discord.ui.button(label='Prev', style=discord.ButtonStyle.primary, custom_id='ldb_previous')
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        start_time = time.time()
        if self.current_page > 1:
            self.current_page -= 1
        else: 
            self.current_page = self.total_pages
        await self.pages_embed(interaction, start_time)


    @discord.ui.button(label='Next', style=discord.ButtonStyle.primary, custom_id='ldb_next')
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        start_time = time.time()
        if self.current_page < self.total_pages:
            self.current_page += 1
        else: 
            self.current_page = 1
        await self.pages_embed(interaction, start_time)


class Database(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print('Pixels cog loaded.')

    @app_commands.command(name='lookup', description='See how many pixels a certain user has placed for us.')
    @app_commands.describe(pxlsuser='Pxls username to look up.', discorduser='Discord username to look up.')
    async def pixels_db_lookup(self, interaction: discord.Interaction, pxlsuser: Optional[str] = None, discorduser: Optional[discord.User] = None):
        """Find the total pixel count for a user & their rank (defined in config.py)"""
        # both provided, treat like only pxlsuser
        if pxlsuser and discorduser or pxlsuser:
            if not USERNAME_REGEX.fullmatch(pxlsuser):
                await interaction.response.send_message('Invalid username', ephemeral=True)
                return
            internal_pxls_username = pxlsuser
            linked_discord = get_linked_pxls_username(internal_pxls_username)
            if not linked_discord:
                internal_discord_user = None
            else: 
                internal_discord_user = await interaction.client.fetch_user(linked_discord)
        # only discord user, errors if no pxls username
        elif discorduser:
            internal_pxls_username = get_linked_discord_username(discorduser.id)
            internal_discord_user = discorduser
            if not internal_pxls_username:
                await interaction.response.send_message(f'{discorduser} does not have a linked Pxls username (yet)', ephemeral=True)
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
    @app_commands.describe(canvas='Canvas code to filter by (no leading c).')
    async def pixels_db_list(self, interaction: discord.Interaction, canvas: Optional[str] = None):
        """Create a user leaderboard."""
        start_time = time.time()
        if canvas:
            if not CANVAS_REGEX.fullmatch(canvas):
                await interaction.response.send_message('Invalid format! A canvas code can only contain a-z and 0-9.', ephemeral=True)
                return
            get_users_canvas = "SELECT user, SUM(pixels) as total_all FROM points WHERE canvas=? GROUP BY user ORDER BY total_all DESC"
            cursor.execute(get_users_canvas, (canvas,)) # does the above
        else: 
            get_users_all = "SELECT user, SUM(pixels) as total_all FROM points GROUP BY user ORDER BY total_all DESC"
            cursor.execute(get_users_all) # does the above
        all_pixels = cursor.fetchall() # defines all_pixels to be the thing we got from the database
        if not all_pixels:
            await interaction.response.send_message('No pixels or users found.')
            return # self-explanatory but if "all_pixels" is empty it returns this. I love error handling :3
        all_pixels = [(str(user), total_all) for user, total_all in all_pixels]

        cog_dir = os.path.dirname(os.path.abspath(__file__))
        src_dir = os.path.dirname(cog_dir)
        font_path = os.path.join(src_dir, "font.ttf") # can be any, as long as it's in the main folder
        font_size = 24
        page_size = 30

        view = LeaderboardView(all_pixels, font_path, font_size, page_size, canvas=canvas)
        embed, file = view.generate_embed()
        end_time = time.time()
        elapsed_time = end_time - start_time
        embed.set_footer(text=f'Generated in {elapsed_time:.2f}s\nPage {view.current_page}/{view.total_pages}')
        await interaction.response.send_message(embed=embed, file=file, view=view)

async def setup(client):
    await client.add_cog(Database(client))