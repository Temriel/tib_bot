import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
from PIL import Image, ImageDraw, ImageFont
import io
import re

database = sqlite3.connect('database.db')
cursor = database.cursor()
database.execute('CREATE TABLE IF NOT EXISTS points(user STR, canvas STR, pixels INT, PRIMARY KEY (user, canvas))')

class db(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print('Main DB cog loaded.')
    
    @app_commands.command(name='add-pixels', description='Add pixels to a user.')
    @app_commands.describe(user='The user to add pixels to.', canvas='Canvas number (no c).', pixels='Amount placed.')
    async def pixels_db_add(self, interaction: discord.Interaction, user: str, canvas: str, pixels: int):
        query = "INSERT OR REPLACE INTO points VALUES (?, ?, ?)" # the three question marks represents the above "user", "canvas", and "pixels"
        try:
            if interaction.user.id == 313264660826685440:
                if not isinstance(canvas, str):
                    canvas = str(canvas)
                if not re.fullmatch(r'^(?![cC])[a-z0-9]{1,4}+$', canvas):
                    await interaction.response.send_message('Invalid format! A canvas code can only contain a-z and 0-9.', ephemeral=True)
                    return
                cursor.execute(query, (str(user), canvas, pixels)) # the reason we define query is to make sure cursor.execute isn't Huge
                database.commit()
                await interaction.response.send_message("Added!")
            else:
                await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message('Error! Something went wrong, ping Temriel.', ephemeral=True)
            print(f'An error occurred: {e}')

    @app_commands.command(name='lookup', description='See how many pixels a certain user has placed for us.')
    @app_commands.describe(profile='Who do you want to look up?')
    async def pixels_db_lookup(self, interaction: discord.Interaction, profile: str):
        get_users = "SELECT SUM(pixels) FROM points WHERE user=?"
        cursor.execute(get_users, (profile,))
        total = cursor.fetchone()[0]
        if total is None:
            total = 0
        await interaction.response.send_message(f"**{profile}** has placed **{total}** pixels for us. They have the rank of **placeholder**.")
        # the placeholder above will be calculated to look at a users role eventually, yes this will probably be TPE specific at first :3

    @app_commands.command(name='list', description='See how much people have placed for us.')
    async def pixels_db_list(self, interaction: discord.Interaction):
        get_users_all = "SELECT user, SUM(pixels) as total_all FROM points GROUP BY user ORDER BY total_all DESC" # in short, selects the "points" table, gets the users on that table, sums up all "pixels" associated with each user, and orders them by pixels
        cursor.execute(get_users_all) # does the above
        all_pixels = cursor.fetchall() # defines all_pixels to be the thing we got from the database
        if not all_pixels:
            await interaction.response.send_message('No pixels or users found.')
            return # self explanatory but if "all_pixels" is empty it returns this. I love error handling :3  

        font_path = "font.ttf" # can be any font, though you might have to change around the font sizes for this to make sense
        font_size = 24
        font = ImageFont.truetype(font_path, font_size)
        spacing = 30
        max_image_width = 800
        min_username_x = 36

        all_pixels = [(str(user), total_all) for user, total_all in all_pixels]
        max_username_length = max(len(user) for user, _ in all_pixels)
        max_pixels_length = max(len(str(total_all)) for _, total_all in all_pixels)

        username_spacing = max_username_length * font_size + 10
        pixels_spacing = max_pixels_length * font_size + 6

        image_width = max(200, min(max_image_width, username_spacing + pixels_spacing - 30))
        image_height = spacing * (len(all_pixels) + 3)
        image = Image.new("RGB", (image_width, image_height), color=(24, 4, 53))
        draw = ImageDraw.Draw(image)

        headers = ["Rank", "Username", "Pixels"]
        header_positions = [50, min_username_x + username_spacing // 2, username_spacing + pixels_spacing // 2 - min_username_x] # decides spacing for the headers, kinda needs to be manually adjusted
        for header, pos in zip(headers, header_positions):
            header_bbox = draw.textbbox((0, 0), header, font=font)
            header_width = header_bbox[2] - header_bbox[0]
            draw.text((pos - header_width / 2, 10), header, fill="white", font=font)

        y_text = 50
        for rank, (user, total_all) in enumerate(all_pixels, start=1):
            rank_text = str(rank)
            rank_bbox = draw.textbbox((0, 0), rank_text, font=font)
            rank_width = rank_bbox[2] - rank_bbox[0]
            draw.text((header_positions[0] - rank_width / 2, y_text), rank_text, fill="white", font=font)

            user_bbox = draw.textbbox((0, 0), user, font=font)
            user_width = user_bbox[2] - user_bbox[0]
            draw.text((header_positions[1] - user_width / 2, y_text), user, fill="white", font=font)
            
            pixels_text = str(total_all)
            pixels_bbox = draw.textbbox((0, 0), pixels_text, font=font)
            pixels_width = pixels_bbox[2] - pixels_bbox[0]
            draw.text((header_positions[2] - pixels_width / 2, y_text), pixels_text, fill="white", font=font)
            y_text += spacing

        with io.BytesIO() as image_binary: # below sends the embed w/ the image
            image.save(image_binary, 'PNG')
            image_binary.seek(0)
            file = discord.File(fp=image_binary, filename='leaderboard.png')
            embed = discord.Embed(color=discord.Color.purple())
            embed.set_image(url="attachment://leaderboard.png")
            await interaction.response.send_message(embed=embed, file=file)

async def setup(client):
    await client.add_cog(db(client))