import discord
from discord import app_commands
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()

intents = discord.Intents.none()
bot = commands.Bot(intents=intents, command_prefix=">")
tree = bot.tree
GUILD_ID = 991132678202085446

async def load_cogs():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py') and filename != '__init__.py':
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                print(f'Loaded {filename}')
            except Exception as e:
                print(f'Failed to load: {e}')

@bot.event # startup + shutdown command
async def on_ready():
    print("Started.")
    try: 
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            await tree.sync(guild=guild)
            print('Application commands synced for the guild {GUILD_ID}')
        else:
            await tree.sync()
            print('Application commands synced globally.')
        
        print("Registered Commands:")
        for command in await tree.fetch_commands():
            print(f'{command.name}: {command.description}')

        @tree.command()
        async def shutdown(interaction: discord.Interaction):
            """Shuts down the bot."""
            if interaction.user.id == 313264660826685440:
                await interaction.response.send_message("Shutting down...")
                await bot.close()
            else:
                await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
    except Exception as e:
        print(f'Failed to sync: {e}')

@bot.event
async def on_error(event, *args, **kwargs):
    print("Error detected: {event}")

async def main():
    async with bot:
        await load_cogs()
        await bot.start(os.getenv("BOT_TOKEN"))

if __name__ == '__main__':
    asyncio.run(main())