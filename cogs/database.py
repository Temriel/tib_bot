import discord
from discord import app_commands
from discord.ext import commands
import sqlite3

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
            await interaction.response.send_message("Added!")
            query = "INSERT INTO points VALUES (?, ?, ?)"
            cursor.execute(query, (user, canvas, pixels))
            database.commit()
        else:
            await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)

async def setup(client):
    await client.add_cog(db(client))