import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import os
from dotenv import load_dotenv
import logging

load_dotenv()

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')

intents = discord.Intents.none()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
bot = commands.Bot(command_prefix='>', intents=intents)

@client.event
async def on_ready():
    print(f'Started. Logged in as {client.user}.')

async def load():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            await bot.load_extension(f'cogs.{filename[:-3]}')
            print(f'{filename[:-3]} successfully loaded.')


@tree.command(name='shutdown', description='Shut down the bot.')
async def slash_command(interaction: discord.Interaction):
    if interaction.user.id == 313264660826685440:
        await interaction.response.send_message("Shutting down...")
        await client.close()
    else:
        await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)

@tree.command(name='sync', description='Sync.')
async def slash_command(interaction: discord.Interaction):
    if interaction.user.id == 313264660826685440:
        fmt = await tree.sync()
        await interaction.response.send_message('Synced commands.', ephemeral=True)
        print(f'Synced {len(fmt)} commands to the current guild.')
    else:
        await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)

@tree.command(name='reload-cogs', description='Reload the cogs.')
async def slash_command(interaction: discord.Interaction):
    if interaction.user.id == 313264660826685440:
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                await bot.reload_extension(f'cogs.{filename[:-3]}')
                print(f'{filename[:-3]} successfully re-loaded.')
                await interaction.response.send_message('Re-loaded cogs.', ephemeral=True)
    else:
        await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)

async def main():
    await load()
#    await client.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="The Purple Empire"))

asyncio.run(main())
client.run(os.getenv("BOT_TOKEN"), log_handler=handler)