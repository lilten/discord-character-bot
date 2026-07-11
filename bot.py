async def setup_menu_auto():
    """Автоматически создает меню в канале создать-лобби при запуске бота"""
    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name="создать-лобби")
        if not channel:
            print(f"⚠️ Канал «создать-лобби» не найден на сервере {guild.name}")
            continue

        # Удаляем старые сообщения бота
        try:
            async for message in channel.history(limit=20):
                if message.author == bot.user:
                    await message.delete()
                    await asyncio.sleep(0.3)
        except:
            pass

        # Создаем ОДНО компактное меню
        embed = discord.Embed(
            title="",
            description="Выберите рейд для создания лобби:",
            color=discord.Color.gold()
        )
        
        view = CompactMenuView()
        
        await channel.send(embed=embed, view=view)
        print(f"✅ Меню создано в канале «создать-лобби» на сервере {guild.name}")
