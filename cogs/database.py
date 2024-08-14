import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
from PIL import Image, ImageDraw, ImageFont
import io

database = sqlite3.connect('database.db')
cursor = database.cursor()
database.execute('CREATE TABLE IF NOT EXISTS points(user STRING, canvas INT, pixels INT)')

class db(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print('Database cog loaded.')
    
    @app_commands.command(name='add-pixels', description='Add pixels to a user.')
    @app_commands.describe(user='The user to add pixels to.', canvas='Canvas number (no c).', pixels='Amount placed.')
    async def database_add(self, interaction: discord.Interaction, user: str, canvas: int, pixels: int):
        if interaction.user.id == 313264660826685440:
            query = "INSERT INTO points VALUES (?, ?, ?)"
            cursor.execute(query, (user, canvas, pixels))
            database.commit()
            await interaction.response.send_message("Added!")
        else:
            await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)

    @app_commands.command(name='lookup', description='See how many pixels a certain user has placed for us.')
    @app_commands.describe(profile='Who do you want to look up?')
    async def database_lookup(self, interaction: discord.Interaction, profile: str):
        get_users = "SELECT SUM(pixels) FROM points WHERE user=?"
        cursor.execute(get_users, (profile,))
        total = cursor.fetchone()[0]
        if total is None:
            total = 0
        await interaction.response.send_message(f"**{profile}** has placed **{total}** pixels for us. They have the rank of **placeholder**.")

    @app_commands.command(name='list', description='See how much people have placed for us.')
    async def database_list(self, interaction: discord.Interaction):
        get_users_all = "SELECT user, SUM(pixels) as total_all FROM points GROUP BY user ORDER BY total_all DESC"
        cursor.execute(get_users_all)
        all_pixels = cursor.fetchall()
        if not all_pixels:
            await interaction.response.send_message("No pixels or users found.")
            return

        font_path = "font.ttf"
        font_size = 24
        font = ImageFont.truetype(font_path, font_size)
        spacing = 30
        max_username_lenth = max(len(user) for user, _ in all_pixels)
        username_spacing = max_username_lenth * font_size
        
        image_width = 486
        image_height = spacing * (len(all_pixels) + 3)
        image = Image.new("RGB", (image_width, image_height), color=(24, 4, 53))
        draw = ImageDraw.Draw(image)

        headers = ["Rank", "Username", "Pixels"]
        header_positions = [50, 30 + username_spacing // 2, 30 + username_spacing]
        for header, pos in zip(headers, header_positions):
            header_bbox = draw.textbbox((0, 0), header, font=font)
            header_width = header_bbox[2] - header_bbox[0]
            draw.text((pos - header_width / 2, 10), header, fill="white", font=font)

        y_text = 50
        for rank, (user, total_all) in enumerate(all_pixels, start=1):
            rank_text = str(rank)
            rank_bbox = draw.textbbox((0, 0), rank_text, font=font)
            rank_width = rank_bbox[2] - rank_bbox[0]
            draw.text((50 - rank_width / 2, y_text), rank_text, fill="white", font=font)

            user_bbox = draw.textbbox((0, 0), user, font=font)
            user_width = user_bbox[2] - user_bbox[0]
            draw.text((30 + username_spacing // 2 - user_width / 2, y_text), user, fill="white", font=font)
            
            pixels_text = str(total_all)
            pixels_bbox = draw.textbbox((0, 0), pixels_text, font=font)
            pixels_width = pixels_bbox[2] - pixels_bbox[0]
            draw.text((30 + username_spacing - pixels_width / 2, y_text), pixels_text, fill="white", font=font)
            y_text += spacing

        with io.BytesIO() as image_binary:
            image.save(image_binary, 'PNG')
            image_binary.seek(0)
            file = discord.File(fp=image_binary, filename='leaderboard.png')
            embed = discord.Embed(color=discord.Color.purple())
            embed.set_image(url="attachment://leaderboard.png")
            await interaction.response.send_message(embed=embed, file=file)

async def setup(client):
    await client.add_cog(db(client))