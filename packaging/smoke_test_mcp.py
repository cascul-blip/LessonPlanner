"""Start a built lessonplanner-mcp executable and check that its tools work.

Usage: python packaging/smoke_test_mcp.py path/to/lessonplanner-mcp[.exe]
"""

import asyncio
import os
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from lessonplanner.db import Database


async def check(exe: str, folder: str) -> None:
    env = {**os.environ, "LESSONPLANNER_DB_FOLDER": folder}
    async with stdio_client(StdioServerParameters(command=exe, env=env)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            assert {"get_week", "insert_lesson", "mark_no_school"} <= tools, tools
            result = await session.call_tool(
                "set_entry", {"class_name": "Biology", "day": "2026-10-01", "lesson": "Lesson 1"})
            assert not result.is_error, result.content
            result = await session.call_tool("get_entry",
                                             {"class_name": "Biology", "day": "2026-10-01"})
            assert "Lesson 1" in result.content[0].text, result.content
    print(f"OK: {len(tools)} tools")


def main() -> None:
    with tempfile.TemporaryDirectory() as folder:
        Database(os.path.join(folder, "lessonplanner.db")).close()
        asyncio.run(check(os.path.abspath(sys.argv[1]), folder))


if __name__ == "__main__":
    main()
