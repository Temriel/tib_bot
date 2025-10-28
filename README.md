# funny discord bot
This is my first proper attempt in making a discord bot, it'll just focus on making a database to record some numbers for now.

Currently, it can write to a database and retrieve information about 1 user at a time, and generate a (semi-dynamic) image for a list! One day I'll fix this and make it fully dynamic.

Additionally, as an admin only command, you can look through all canvases for one user to see their placements per canvas, or how much ALL users have placed on a single canvas (both ran against tib_bot/template/c\*\*/\*.png).
To make the above command easier to use, it will optionally retrieve Pxls usernames (linked using a manual admin-only linking system) to show instead of Discord's User ID's. This doesn't change functionality but makes administrative jobs so much easier when you don't have to go through User ID's manually. 

If you want to use this bot, you can find us [here](https://discord.gg/vzB8DZAkpA). For a full list of commands, you can run /help in the bot channel.

The entirety of the placemap utility is currently run using the pxlslog-explorer, made by Etos2. You can find it [here](https://github.com/Etos2/pxlslog-explorer). This bot runs using [this version](https://github.com/Etos2/pxlslog-explorer/tree/6deef7cf38498da3a13095b8eb873938a294b202).