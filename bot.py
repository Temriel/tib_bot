from typing import Optional
import discord
from discord import app_commands

BOT_TOKEN = "MTI3MDc1ODUyMTg2ODEyODM1OA.GJ4eZD.fEtj21FXAiLOqgtXIJZnAoZ6mZsmhvYdUmOFIU"

MY_GUILD = discord.Object(id=991132678202085446)

class MyClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.tree.copy_global_to(guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)

intents = discord.Intents.none()
client = MyClient(intents=intents)

@client.event
async def on_ready():
    print("Started.")

@client.tree.command()
async def test(interaction: discord.Interaction):
    """Testing."""
    await interaction.response.send_message(f'Hello, {interaction.user.mention}.')

client.run(BOT_TOKEN)