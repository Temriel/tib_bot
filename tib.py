import asyncio
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import logging

load_dotenv()

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')

intents = discord.Intents.none()
bot = commands.Bot(command_prefix='>', intents=intents)
tree = bot.tree

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

@tree.command(name='shutdown', description='Shut down the bot.')
async def shutdown(interaction: discord.Interaction):
    if interaction.user.id == 313264660826685440:
        await interaction.response.send_message("Shutting down...")
        await bot.close()
    else:
        await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)

@tree.command(name='sync', description='Sync.')
async def sync(interaction: discord.Interaction):
    if interaction.user.id == 313264660826685440:
        fmt = await tree.sync()
        await interaction.response.send_message('Synced commands.', ephemeral=True)
        print(f'Synced {len(fmt)} commands globally.')
    else:
        await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)

@tree.command(name='reload-cogs', description='Reload the cogs.')
async def reload_cogs(interaction: discord.Interaction):
    if interaction.user.id == 313264660826685440:
        reload = []
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await bot.reload_extension(f'cogs.{filename[:-3]}')
                    print(f'{filename[:-3]} successfully re-loaded.')
                    reload.append(f'{filename[:-3]} successfully re-loaded.')
                except Exception as e:
                    print(f'Failed to reload {filename[:-3]}: {e}')
                    reload.append(f'Failed to reload {filename[:-3]}, check terminal.')
        if reload:
            await interaction.response.send_message('\n'.join(reload), ephemeral=True)
        else:
            await interaction.response.send_message('No cogs found.', ephemeral=True)
    else:
        await interaction.response.send_message("You do not have permission to use this command :3", ephemeral=True)

async def main():
    await load()

asyncio.run(main())
bot.run(os.getenv("BOT_TOKEN"), log_handler=handler)