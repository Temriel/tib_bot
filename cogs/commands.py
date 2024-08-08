import discord
from discord import app_commands
from discord.ext import commands

class commands(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print('Command cog loaded.')

    @app_commands.command(name='hello', description='Say hi!')
    async def hello(self, interaction: discord.Interaction):
        await interaction.response.send_message(f'Hello, {interaction.user.mention}.')
    
    @app_commands.command(name='ping', description='See the ping.')
    async def ping(self, interaction: discord.Interaction):
        bot_latency = round(self.client.latency * 1000)
        await interaction.response.send_message(f'Pong! Current ping is {bot_latency}ms.')

async def setup(client):
    await client.add_cog(commands(client))