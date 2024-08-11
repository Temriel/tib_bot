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
            query = "INSERT INTO points VALUES (?, ?, ?)"
            cursor.execute(query, (user, canvas, pixels))
            database.commit()
            await interaction.response.send_message("Added!")
        else:
            await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)

#    @app_commands.command(name='list', description='See all users in the database')
#    async def database_list(self, interaction: discord.Interaction):
#        cursor.execute("SELECT pixels FROM points")
#        re = cursor.fetchall()
#
#        if re == []: # no data
#            return await interaction.response.send_message('No users in database. ')
        
#        embed = discord.Embed(colour=discord.Colour.purple(), title='Added users and their pixel counts.')

#        await interaction.response.send_modal(embed=embed)

    @app_commands.command(name='lookup', description='See how many pixels a certain user has placed for us.')
    @app_commands.describe(profile='Who do you want to look up?')
    async def database_lookup(self, interaction: discord.Interaction, profile: str):
        get_users = "SELECT SUM(pixels) FROM points WHERE user=?"
        cursor.execute(get_users, (profile,))
        total = cursor.fetchone()[0]
        if total is None:
            total = 0
        await interaction.response.send_message(f"**{profile}** has placed **{total}** pixels for us. They have the rank of **placeholder**.")
        
async def setup(client):
    await client.add_cog(db(client))