import discord
from discord.ext import commands
from discord import app_commands

class CommandCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tree = bot.tree

    @app_commands.command()
    async def hello(self, interaction: discord.Interaction):
        """Say hi!"""
        await interaction.response.send_message(f'Hello, {interaction.user.mention}.')

    @app_commands.command()
    async def ping(self, interaction: discord.Interaction):
        """See the ping."""
        await interaction.response.send_message(f'Pong! Current ping is {round(self.bot.latency * 1000)}ms.')

async def setup(bot):
    await bot.add_cog(CommandCog(bot))