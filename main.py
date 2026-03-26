import logging
from pathlib import Path
import asyncio
import aiohttp
import re
import sys

from config import (
    PACKAGE_SYSTEM,
    TARGET_PACKAGE,
    TARGET_VERSION,
    API_BASE,
    CHECK_LIST,
    MAX_CONCURRENT_REQUESTS,
)

from rich.console import Console
from rich.progress import Progress
from rich.live import Live
from rich.text import Text
from rich.console import Group


# --- logging setup ---
def write_log(path: Path, packages: dict[str, str]) -> None:
    with open(path, "w") as f:
        for package, version in packages.items():
            f.write(f"{package}=={version}\n")


output_dir = Path("logs")
output_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.FileHandler(output_dir / "run_output.log", mode="w"),
        # logging.StreamHandler()  # keep printing to console too
    ],
)
log = logging.getLogger(__name__)

# --- progress bar setup ---
console = Console()
progress = Progress()
task = progress.add_task("", total=len(CHECK_LIST))
current = Text()
header = Text(
    f"Running Dependency Checker for {PACKAGE_SYSTEM} {TARGET_PACKAGE}=={TARGET_VERSION}"
)
display = Group(header, current, progress)


# --- helpers ---
async def get_default_version_async(
    session: aiohttp.ClientSession, package: str
) -> str | None:
    """Get the default/latest version of a package. (None if not found)"""
    async with session.get(f"{API_BASE}/{package}") as r:
        if not r.ok:
            return None

        data = await r.json()
        for v in data.get("versions", []):
            if v.get("isDefault"):
                return v["versionKey"]["version"]

        # fallback: last in list
        versions = data.get("versions", [])
        return versions[-1]["versionKey"]["version"] if versions else None


async def get_transitive_deps_async(
    session: aiohttp.ClientSession, package: str, version: str
) -> list[tuple[str, str]] | None:
    """Get all resolved transitive dependencies as (name, version) tuples. (None if deps not found i.e. in 404/50X situations)"""
    async with session.get(
        f"{API_BASE}/{package}/versions/{version}:dependencies"
    ) as r:
        if not r.ok:
            return None

        data = await r.json()
        return [
            (node["versionKey"]["name"].lower(), node["versionKey"]["version"])
            for node in data.get("nodes", [])
        ]


async def check_package_async(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    package: str,
    pinned_version: str | None,
) -> tuple[str, str, bool | None]:
    """Returns (package, version, result) where result is True/False/None."""
    async with sem:
        if pinned_version:
            version = pinned_version
        else:
            version = await get_default_version_async(session, package)

        if version is None:
            return package, "unknown", None

        deps = await get_transitive_deps_async(session, package, version)
        if deps is None:
            return package, version, None

        banned = any(
            name == TARGET_PACKAGE and ver == TARGET_VERSION for name, ver in deps
        )
        return package, version, banned


# may the lord have mercy on my insatiable greed
CHECKLIST_PATTERN = re.compile(
    r"^([a-zA-Z0-9][a-zA-Z0-9\-]*)==([a-zA-Z0-9][a-zA-Z0-9\.\-]*)$|^([a-zA-Z0-9][a-zA-Z0-9\-]*)$"
)

def parse_checklist(checklist: list[str]) -> list[tuple[str, str | None]]:
    """Returns (package, version) tuples. Version is None if not specified."""
    result = []
    for entry in checklist:
        # strip extras like [hf]
        match = CHECKLIST_PATTERN.match(entry)
        if not match:
            # NOTE: fstrings are insecure here? can a malicious entry cause execution here?
            print(
                f"INVALID CHECKLIST ENTRY: {entry} - must be <package> or <package>==<version>"
            )
            sys.exit(1)
        if match.group(1):  # version matched
            result.append((match.group(1), match.group(2)))
        else:
            result.append((match.group(3), None))

    return result


# --- main ---
async def main_async():
    clean = {}
    violations = {}
    errors = {}

    checklist = parse_checklist(CHECK_LIST)

    async with aiohttp.ClientSession() as session:
        with Live(display, console=console, refresh_per_second=10):
            sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)  # max requests
            tasks = [
                check_package_async(session, sem, pkg, ver) for pkg, ver in checklist
            ]

            for coro in asyncio.as_completed(tasks):
                package, version, result = await coro
                current.plain = f"Checking {package}=={version}"

                if result is None:
                    errors[package] = version
                    log.error(f"ERROR: Could not fetch deps for {package}=={version}")
                elif result:
                    violations[package] = version
                    log.warning(
                        f"VIOLATION: {package}=={version} depends on {TARGET_PACKAGE}=={TARGET_VERSION}"
                    )
                else:
                    clean[package] = version
                    log.info(f"CLEAN: {package}=={version}")
                progress.advance(task)

    # summary that prints to run_output.log
    log.info(f"\n--- SUMMARY ---")
    log.info(f"TOTAL PACKAGES: {len(CHECK_LIST)}")
    if clean:
        log.info(f"CLEAN: {len(clean)} packages")
    if violations:
        log.info(f"VIOLATIONS: {len(violations)} packages")
    if violations:
        log.info(f"ERRORS: {len(errors)} packages")
    log.info("See /logs/ for package lists for each")

    # gotta duplicate for rich console printing the same info
    console.print(f"\n--- SUMMARY ---")
    console.print(f"TOTAL PACKAGES: {len(CHECK_LIST)}")
    if clean:
        console.print(f"CLEAN: {len(clean)} packages")
    if violations:
        console.print(f"VIOLATIONS: {len(violations)} packages")
    if violations:
        console.print(f"ERRORS: {len(errors)} packages")
    console.print("See /logs/ for package lists for each")

    # after summary logging
    write_log(output_dir / "clean.log", clean)
    write_log(output_dir / "violations.log", violations)
    write_log(output_dir / "errors.log", errors)


if __name__ == "__main__":
    asyncio.run(main_async())
