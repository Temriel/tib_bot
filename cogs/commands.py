import discord
from discord import app_commands
import os
from dotenv import load_dotenv

load_dotenv()

class commandcog(app_commands.Cog):
    def __init__(self, client):
        self.client = client

# async def setup(client):
    # await client.add_cog(commandcog(client))

@app_commands.command()
async def hello(interaction: discord.Interaction):
    """Say hi!"""
    await interaction.response.send_message(f'Hello, {interaction.user.mention}.')

@app_commands.command()
async def ping(interaction: discord.Interaction):
    """See the ping."""
    await interaction.response.send_message(f'Pong! Current ping is {round(client.latency * 1000)}ms.')