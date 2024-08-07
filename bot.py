import discord
from discord import app_commands

BOT_TOKEN = "MTI3MDc1ODUyMTg2ODEyODM1OA.GJ4eZD.fEtj21FXAiLOqgtXIJZnAoZ6mZsmhvYdUmOFIU"
CHANNEL_ID = "1250950564460757102"

intents = discord.Intents.bot()
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

@client.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=991132678202085446))
    print("Started.")

@tree.command(
    name="test",
    description="test command",
)
async def first_command(interaction):
    await interaction.response.send_message("Testing complete.")

client.run(BOT_TOKEN)