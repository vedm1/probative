---
description: Get Probative ready to run: check the configuration and guide the user through the one thing that is missing
allowed-tools: mcp__plugin_probative_probative__doctor
---

Call the Probative `doctor` tool and show the text it returns verbatim. Then act only on what
it reports as missing.

**Everything ready.** Say so in one line and suggest `/probative:critique <path>`. Nothing more.

**A provider key is missing or a placeholder.** The key is a secret, so it must never pass
through this conversation.

- Never ask for the key in chat. Do not accept it, repeat it, or use it if the user pastes it.
- Tell the user to run `/plugin configure probative@probative` themselves. Claude Code asks
  for the key itself and treats it as a sensitive option, so it never enters this chat.
- The alternative is to export `ANTHROPIC_API_KEY` in the shell profile before starting Claude.
- If a key does appear in the conversation anyway, say plainly that it is now in the
  transcript and the user should rotate it.

**A root is missing, too broad, or does not contain the user's documents.** Explain that the
tool only reads inside the allowed roots and that `PROBATIVE_MCP_ROOTS` names them (folders
separated by the platform's path separator). Starting Claude inside the folder that holds the
documents also works, because the working directory is the default root.

**The model has no provider prefix, or `.env` is unreadable.** Quote the line `doctor` printed.
The fix is in the user's own `MODEL` setting or `.env` file; do not edit either yourself.

When the user says they have made a change, call `doctor` again and show it verbatim. Do not
claim the setup works until `doctor` says it is ready.
