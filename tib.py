import asyncio
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import logging
import config
import importlib

load_dotenv()

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')

intents = discord.Intents.none()
intents.guilds = True
bot = commands.Bot(command_prefix='>', intents=intents)
tree = bot.tree

owner_id = config.owner()

@bot.event
async def on_ready():
    print(f'Started. Logged in as {bot.user}.')

async def load():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
            except Exception as e:
                print(f'Failed to load {filename[:-3]}: {e}')
# all commands in this file are just for making sure the bot Actually Works
@tree.command(name='shutdown', description='Shut down the bot (ADMIN ONLY)')
async def shutdown(interaction: discord.Interaction):
    """Goodnight, sweet prince."""
    if interaction.user.id != owner_id:
        await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)
        return
    await interaction.response.send_message("Shutting down...")
    await bot.close()

@tree.command(name='sync', description='Sync (ADMIN ONLY)')
async def sync(interaction: discord.Interaction):
    """Sync commands to Discord (DO NOT SPAM)"""
    if interaction.user.id != owner_id:
        await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)
        return
    fmt = await tree.sync()
    await interaction.response.send_message('Synced commands.', ephemeral=True)
    print(f'Synced {len(fmt)} commands globally.')

@tree.command(name='reload-cogs', description='Reload the cogs (ADMIN ONLY)')
async def reload_cogs(interaction: discord.Interaction):
    """Reload all cogs present within the bot. They can't be used otherwise (esp if you add new code)"""
    if interaction.user.id != owner_id:
        await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)
        return
    reload = []
    importlib.reload(config)
    # reload.append(f'Config successfully reloaded.') # doesn't seem to work
    print('config successfully reloaded.')
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                await bot.reload_extension(f'cogs.{filename[:-3]}')
                print(f'{filename[:-3]} successfully reloaded.')
                reload.append(f'{filename[:-3]} successfully reloaded.')
            except Exception as e:
                print(f'Failed to reload {filename[:-3]}: {e}')
                reload.append(f'Failed to reload {filename[:-3]}, check terminal.')
    if reload:
        message = '\n'.join(reload)
    else:
        message = 'No cogs found.'
    await interaction.response.send_message(message, ephemeral=True)

async def main():
    await load()

asyncio.run(main())
token = os.getenv("bot_token")
if not token:
    raise ValueError("No token found in .env file.")
bot.run(token, log_handler=handler)