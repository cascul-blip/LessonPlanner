# Lesson Planner

Weekly lesson planner for Math 87, Algebra 1, Algebra 2, Consumer Math, Science 8,
Biology and Physics. Each class has **Lesson**, **Special** (quizzes, tests, labs,
anything out of the ordinary; highlighted when filled) and **Homework** for every school day.

- The data is one SQLite file (`lessonplanner.db`) in a folder you choose, meant to be in Nextcloud.
- The lock file `lessonplanner.lock` stops two computers from editing at once. The second
  computer opens **read-only**, and switches to editable when the first one closes.
- A daily backup `lessons_MMDDYYYY.db` is saved in the same folder. The last 30 days are
  kept; you can change that in Options.
- Read-only PDFs of every week are kept up to date in `<folder>/Tablet/` so you can view
  them on the Android tablet with the Nextcloud app.
- The app follows the system light/dark mode.

## Install and run (Linux or Windows)

Requires Python 3.10+.

```sh
python -m venv .venv
# Linux:   .venv/bin/pip install -e .
# Windows: .venv\Scripts\pip install -e .
.venv/bin/lessonplanner          # Windows: .venv\Scripts\lessonplanner.exe
```

On first run the app asks for the database folder, e.g. `~/Nextcloud/Documents/School`.
This choice is saved per computer (File → Options).

### Import the old spreadsheet

Use File → Import from Excel… (or `lessonplanner-import LessonPlan.xlsx`). Sheets named "Week N"
are placed using the "Monday of Week 1" setting (default Sep 7, 2026). Each cell is split
into Lesson / Special / Homework. Cells that already have data are never overwritten.

## Using it

- Tabs are weeks, newest on the left. The current week opens at startup. Use **+** (Ctrl+N)
  to add the next week, and Ctrl+T to jump back to this week.
- Edits save automatically.
- Right-click a class/day:
  - **Insert lesson here**: that class's lessons from this day on move one school day later.
  - **Remove this lesson**: deletes it and pulls that class's later lessons one school day earlier.
  - **Mark day as No School**: every class shifts one day later. Right-click the
    No School row to undo it.
- File → Print week / Export week to PDF prints one landscape page per week.

## AI agent (MCP)

`lessonplanner-mcp` is a stdio MCP server that uses the same database and shifting rules.
It reads the database folder from the app's settings (or `LESSONPLANNER_DB_FOLDER`), and
refuses to write while another computer holds the lock.

Claude Code:

```sh
claude mcp add lesson-planner -- /path/to/LessonPlanner/.venv/bin/lessonplanner-mcp
```

Claude Desktop (`claude_desktop_config.json`):

```json
{ "mcpServers": { "lesson-planner": {
    "command": "C:\\path\\to\\LessonPlanner\\.venv\\Scripts\\lessonplanner-mcp.exe" } } }
```

Tools: `current_week`, `list_classes`, `get_week`, `get_entry`, `set_entry`,
`insert_lesson`, `remove_lesson`, `mark_no_school`, `unmark_no_school`,
`list_no_school_days`, `find_lessons`.
Examples: "Physics got pushed back a day on Thursday", "snow day tomorrow",
"what's the Biology homework this week?".

## Standalone Windows build (optional)

Build on Windows so the school computer doesn't need Python:

```bat
.venv\Scripts\pip install -e .[dev]
.venv\Scripts\pyinstaller --windowed --name LessonPlanner packaging\launch_app.py
.venv\Scripts\pyinstaller --console --name lessonplanner-mcp packaging\launch_mcp.py
```

## Development

```sh
.venv/bin/pip install -e .[dev]
.venv/bin/pytest
```
