import discord
from discord import app_commands
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.none()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

async def load_cogs():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py') and filename != '__init__.py':
            client.load_cogs(f'cogs.{filename[:-3]}')

@client.event
async def on_ready():
    print("Started.")
    guild_id = 991132678202085446    
    
@client.event
async def on_error(error):
    print("Error detected.")

client.run(os.getenv("BOT_TOKEN"))