---
name: kitty
description: Instructions for using kitty remote control to spawn windows/tabs, send text, inspect output, and manage processes. Useful for running servers or long-running tasks in the background.
allowed-tools:
  - Bash(kitten @ *)
  - Bash(echo *)
  - Bash(jq *)
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
   kitten @ launch --match "window_id:$KITTY_WINDOW_ID" --title "server-log" --keep-focus
   ```

   Give every window a unique `--title` and use that as the handle from then on, rather than capturing the id `launch` prints into a shell variable. Two reasons, both specific to being driven by an agent:

   - Agent `Bash` tools normally run each command in a fresh shell, so a variable set by one call is gone by the next. `WID=$(kitten @ launch ...)` followed by a separate `kitten @ get-text --match "id:$WID"` call matches nothing.
   - The `allowed-tools` entry above is `Bash(kitten @ *)`, and an allow rule does not match past an assignment of a variable that is not a known-safe environment variable. A command written as `WID=$(kitten @ ...)` is not covered by it and prompts for approval.

   Capturing the id is still fine within a single command, where both parts run in the same shell.

   **Keep the title free of spaces.** A match specification is parsed as a boolean expression, with `and`, `or` and `not` as operators, so a space splits it into two terms. `--match "title:nvim: agents"` fails with `Error: No location specified before agents`. Use `nvim-agents`, or match a space-free prefix, since the query is a regular expression: `--match "title:^nvim"`.

2. **Or create a new tab:**

   ```bash
   kitten @ launch --type=tab --title "server-log" --keep-focus
   ```

3. **Launch with a command directly:**
   (Use `--hold` if you want the window to stay open after the command finishes)

   ```bash
   kitten @ launch --title "server-log" --keep-focus --hold npm start
   ```

   **The command runs in kitty's environment, not the user's shell environment.** `launch` execs the command directly: no shell profile is read, and the `PATH` is whatever kitty itself was started with. A kitty started from Finder or the Dock on macOS passes something like `/Applications/kitty.app/Contents/MacOS:/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin` — with no `/opt/homebrew/bin`, so nothing installed by Homebrew on Apple Silicon is found. The `shell` setting in `kitty.conf` does not help here; it applies to windows that start a shell, not to a launched command.

   Run the program through a login shell, which also gives it the environment it would have had if the user had started it:

   ```bash
   kitten @ launch --title "editor" --cwd /path/to/repo zsh -lc 'nvim .'
   ```

   An absolute path such as `/opt/homebrew/bin/nvim` also works, but does not fix anything the program itself looks up in `PATH` later.

## 3. Send Text/Commands to a Window

Send keystrokes to a specific window. Match by title across separate commands; match by id only within a single command, where the variable is still in scope.

**Using Title (Reliable across calls):**

```bash
kitten @ send-text --match "title:server-log" "npm start\n"
```

**Using ID (same command only):**

The id has to be captured and used in one command, since the next call gets a fresh shell:

```bash
WID=$(kitten @ launch --title "server-log" --keep-focus) && kitten @ send-text --match "id:$WID" "npm start\n"
```

Note that this form is not covered by `Bash(kitten @ *)` and will ask for approval.

**Newline handling:**

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

Read the window back after launching anything, not only to follow a long-running process. A `launch` whose command fails to start still returns a window id, and the window still appears in `kitten @ ls` with the title and working directory that were asked for. kitty holds it open so the error stays visible — even without `--hold` — so `ls` reports the holding process rather than the command that was wanted. From the outside the launch is indistinguishable from a successful one; the error text exists only inside the window:

```
Failed to launch child: nvim
With error: No such file or directory
```

Get the current visible text from a window:

```bash
kitten @ get-text --match "title:server-log"
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
kitten @ focus-window --match "title:server-log"
```

Focus a specific tab:

```bash
kitten @ focus-tab --match "title:server-log"
```

## 6. Interact with Processes

**Send Ctrl+C (Interrupt):**

```bash
kitten @ send-text --match "title:server-log" "\x03"
```

**Close a window:**

```bash
kitten @ close-window --match "title:server-log"
```

**Close a tab:**
(Note: You can close a tab by matching its title or any window ID inside it)

```bash
# By id of a window inside the tab
kitten @ close-tab --match "window_id:$WID"

# By tab title
kitten @ close-tab --match "title:server-log"
```

## 7. Advanced: Window Matching

Kitty supports powerful matching expressions:

- `title:pattern` - Match by window title
- `id:number` - Match by window ID, or by tab ID for the tab-level commands below
- `pid:number` - Match by process ID
- `cwd:path` - Match by current working directory
- `cmdline:pattern` - Match by command line
- `state:focused` - Match the focused window
- `state:active` - Match the active window

Combine with `and`, `or`, `not`:

```bash
kitten @ focus-window --match "title:server and state:active"
```

**Tabs vs. windows:** `--match` selects *tabs* for the tab-level commands — `launch`, `close-tab` and `focus-tab` — and *windows* for everything else. Each command's `--help` says which of the two it matches. Inside a tab-level match, `id:` is a tab id and `title:` a tab title, so use `window_id:` and `window_title:` to select the tab that contains a given window. Getting this wrong rarely errors: kitty falls back to looking for a window when a tab match fails, so the command works until the two id spaces collide.

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

1. `kitten @ launch --title "NAME" --keep-focus [CMD]` - Create window under a unique title
2. `kitten @ send-text --match "title:NAME" "CMD\n"` - Send command
3. `kitten @ get-text --match "title:NAME"` - Read output
4. `kitten @ close-window --match "title:NAME"` - Cleanup

The title is the handle that survives between separate commands; see section 2 for why a captured window id does not.

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
