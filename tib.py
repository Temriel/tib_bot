from typing import Optional
import discord
from discord.ext import commands
from discord import app_commands
import os
import sys
from dotenv import load_dotenv
import logging

load_dotenv()

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')

MY_GUILD = discord.Object(id=991132678202085446)

class MyClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.tree.copy_global_to(guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)

intents = discord.Intents.default()
client = MyClient(intents=intents)

def restart_bot():
    os.execv(sys.executable, ['python'] + sys.argv)

@client.event
async def on_ready():
    print(f'Started. Logged in as {client.user}.')

@client.tree.command(name='shutdown', description='Shut down the bot.')
async def shutdown(interaction: discord.Interaction):
    if interaction.user.id == 313264660826685440:
        await interaction.response.send_message("Shutting down...")
        await client.close()
    else:
        await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)

#@client.tree.command(name='restart', description='Restart the bot.')
#async def restart(interaction:discord.Interaction):
#    if interaction.user.id == 313264660826685440:
#        await interaction.response.send_message("Restarting bot...")
#    else:
#        await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)
#
### I might re-implement this if I can get it to work. 

@client.tree.command(name='hello', description='Say hi!')
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message(f'Hello, {interaction.user.mention}.')

@client.tree.command(name='ping', description='See the ping.')
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f'Pong! Current ping is {round(client.latency * 1000)}ms.')

client.run(os.getenv("BOT_TOKEN"), log_handler=handler, log_level=logging.DEBUG)