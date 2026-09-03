---
name: kitty
description: Instructions for using kitty remote control to spawn windows/tabs, send text, inspect output, and manage processes. Useful for running servers or long-running tasks in the background.
allowed-tools:
  - Bash(kitten @ *)
  - Bash(echo *)
---

# Kitty Remote Control Skill

This skill empowers you to manage multiple concurrent processes (like servers, watchers, or long builds) using kitty's remote control feature directly from the `Bash` tool.

Since you are running inside a kitty terminal, you can spawn new windows or tabs to handle these tasks without blocking your main communication channel.

## 1. Verify Environment & Check Status

First, verify you are running inside kitty with remote control enabled. You can try listing windows:

```bash
kitten @ ls
```

If this fails with `open /dev/tty: device not configured`, kitty is only reachable over the escape-code channel, which requires a controlling terminal. Agent `Bash` tools normally run with their output piped, so there is no TTY and that channel is unavailable. The fix is to have kitty listen on a socket as well:

```bash
echo $KITTY_LISTEN_ON
```

If this is empty, the user needs *both* of these settings in their `kitty.conf`. `allow_remote_control` on its own does not open a socket, and kitty has no default socket path:

```conf
allow_remote_control yes
listen_on unix:/tmp/kitty-{kitty_pid}
```

`listen_on` is not applied by a config reload, so kitty has to be restarted. After that, kitty exports `KITTY_LISTEN_ON` to every child process and `kitten @` reads it automatically, so no `--to` argument is ever needed.

The `{kitty_pid}` placeholder keeps concurrent kitty instances from fighting over the same path. A fixed path is claimed by whichever instance binds it first, and the rest are left without remote control.

For a tighter setup, `allow_remote_control socket-only` also works, and additionally disables the escape-code channel — which any program writing to the terminal can otherwise trigger.

## 2. Spawn a Background Process

To run a command (e.g., a dev server) in a way that persists and can be inspected:

1. **Create a new window in the SAME tab as the agent** (recommended):
   Use `$KITTY_WINDOW_ID` to ensure the new window stays with you. Note that the `--match` of `launch` matches *tabs*, so `window_id:` is the field that resolves a window id to its containing tab. A plain `id:` looks for a tab with that id first and only falls back to windows, which silently puts the new window in the wrong tab whenever a tab id happens to collide.

   ```bash
   WID=$(kitten @ launch --match "window_id:$KITTY_WINDOW_ID" --title "server-log" --keep-focus)
   echo "Created window with ID: $WID"
   ```

2. **Or create a new tab:**

   ```bash
   kitten @ launch --type=tab --title "server-log" --keep-focus
   ```

3. **Launch with a command directly:**
   (Use `--hold` if you want the window to stay open after the command finishes)

   ```bash
   kitten @ launch --title "server-log" --keep-focus --hold npm start
   ```

## 3. Send Text/Commands to a Window

Send keystrokes to a specific window. Use the window ID for precision, or matching for convenience.

**Using ID (Reliable):**

```bash
kitten @ send-text --match "id:$WID" "npm start\n"
```

**Using Matching (Title):**

Note: Use `\n` for Enter. In some shells, you may need to use `$'...'` or pipe to ensure the newline is interpreted correctly.

```bash
kitten @ send-text --match "title:server-log" "npm start
"
# OR
echo "npm start" | kitten @ send-text --match "title:server-log" --stdin
```

Or send to all windows:

```bash
kitten @ send-text --all "echo hello\n"
```

## 4. Inspect Output (Get Text from Window)

Get the current visible text from a window:

```bash
kitten @ get-text --match "id:$WID"
```

Get text including scrollback buffer:

```bash
kitten @ get-text --match "title:server-log" --extent=all
```

Get only the last command output (requires shell integration):

```bash
kitten @ get-text --match "title:server-log" --extent=last_cmd_output
```

## 5. Focus or Bring Window to Front

Focus a specific window:

```bash
kitten @ focus-window --match "id:$WID"
```

Focus a specific tab:

```bash
kitten @ focus-tab --match "title:server-log"
```

## 6. Interact with Processes

**Send Ctrl+C (Interrupt):**

```bash
kitten @ send-text --match "id:$WID" "\x03"
```

**Close a window:**

```bash
kitten @ close-window --match "id:$WID"
```

**Close a tab:**
(Note: You can close a tab by matching its title or any window ID inside it)

```bash
# By ID of a window inside the tab
kitten @ close-tab --match "id:$WID"

# By tab title
kitten @ close-tab --match "title:server-log"
```

## 7. Advanced: Window Matching

Kitty supports powerful matching expressions:

- `title:pattern` - Match by window title
- `id:number` - Match by window ID
- `pid:number` - Match by process ID
- `cwd:path` - Match by current working directory
- `cmdline:pattern` - Match by command line
- `state:focused` - Match the focused window
- `state:active` - Match the active window

Combine with `and`, `or`, `not`:

```bash
kitten @ focus-window --match "title:server and state:active"
```

## 8. Get Window/Tab Information

List all OS windows, tabs, and windows as JSON:

```bash
kitten @ ls
```

**Get current focused window ID:**

```bash
kitten @ ls | jq -r '.[].tabs[] | select(.is_focused) | .windows[] | select(.is_focused) | .id'
```

**Parse for specific info:**

```bash
kitten @ ls | jq '.[].tabs[].windows[] | {id, title, cmdline}'
```

## Summary of Pattern

1. `WID=$(kitten @ launch --title "NAME" --keep-focus [CMD])` - Create window and save ID
2. `kitten @ send-text --match "id:$WID" "CMD\n"` - Send command reliably
3. `kitten @ get-text --match "id:$WID"` - Read output
4. `kitten @ close-window --match "id:$WID"` - Cleanup

## Common Remote Control Commands

| Command | Description |
| ------- | ----------- |
| `kitten @ ls` | List all windows/tabs |
| `kitten @ launch` | Create new window/tab |
| `kitten @ send-text` | Send text to window |
| `kitten @ get-text` | Get text from window |
| `kitten @ focus-window` | Focus a window |
| `kitten @ focus-tab` | Focus a tab |
| `kitten @ close-window` | Close a window |
| `kitten @ close-tab` | Close a tab |
| `kitten @ signal-child` | Send signal to process |
| `kitten @ set-tab-title` | Change tab title |
| `kitten @ set-colors` | Change terminal colors |
