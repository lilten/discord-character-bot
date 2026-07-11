class CreateLobbyModal(ui.Modal):
    def __init__(self, raid_key: str, difficulty: str, channel: discord.TextChannel, role: discord.Role):
        raid_config = RAID_CONFIG[raid_key]
        title = f"{raid_config['emoji']} {raid_config['name']} - {difficulty}"
        super().__init__(title=title[:45])
        self.raid_key = raid_key
        self.difficulty = difficulty
        self.target_channel = channel
        self.role = role

    screenshot_url = ui.TextInput(
        label="🖼️ Ссылка на скриншот лобби",
        placeholder="https://i.imgur.com/пример.png или https://cdn.discordapp.com/...",
        max_length=500,
        required=True
    )

    description_input = ui.TextInput(
        label="📝 Описание",
        placeholder="прим: 4-4 +дд +сап",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        creator_id = str(interaction.user.id)

        if creator_id in active_rooms:
            existing_room = active_rooms[creator_id]
            await interaction.response.send_message(
                f"❌ У вас уже есть активное лобби!\n"
                f"📁 Канал: {existing_room.channel.mention}\n"
                f"📋 Название: **{existing_room.title}**\n\n"
                f"Закройте его перед созданием нового.",
                ephemeral=True
            )
            return

        raid_config = RAID_CONFIG[self.raid_key]
        diff_config = DIFFICULTY_CONFIG[self.difficulty]

        room = CharacterRoom(
            creator=interaction.user,
            channel=self.target_channel,
            role=self.role,
            title=f"{raid_config['emoji']} {raid_config['name']} - {diff_config['emoji']} {self.difficulty}",
            description=self.description_input.value,
            raid_name=self.raid_key,
            difficulty=self.difficulty,
            screenshot_url=self.screenshot_url.value
        )

        active_rooms[creator_id] = room

        await room.create_room_message()

        await interaction.response.send_message(
            f"✅ Лобби создано в канале {self.target_channel.mention}!\n"
            f"🎯 {raid_config['emoji']} **{raid_config['name']}** — {diff_config['emoji']} **{self.difficulty}**",
            ephemeral=True
        )
