"""Check every trusted channel in data/youtube_channels.json against the YouTube Data API: the id must
exist and its title should match the name in the file. Uses the real API (1 quota unit per 50 channels),
so it is not part of pytest.

    cd backend && python scripts/check_youtube_channels.py

Exits 1 if an id does not exist or YOUTUBE_API_KEY is not set.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.agents.course_search.youtube import YouTubeDataAPI, YouTubeError, trusted_channels  # noqa: E402
from core.config import YOUTUBE_API_KEY  # noqa: E402


def main() -> int:
    if not YOUTUBE_API_KEY:
        print("YOUTUBE_API_KEY is not set in backend/.env.")
        return 1
    channels = trusted_channels()
    api = YouTubeDataAPI(YOUTUBE_API_KEY)
    ids = list(channels)
    found: dict[str, str] = {}
    try:
        for start in range(0, len(ids), 50):
            data = api._get("channels", 1, part="snippet", id=",".join(ids[start:start + 50]))
            found |= {c["id"]: c["snippet"]["title"] for c in data.get("items", [])}
    except YouTubeError as e:
        print(e)
        return 1
    missing = 0
    for cid, name in channels.items():
        if cid not in found:
            missing += 1
            print(f"MISSING   {cid}  {name}")
        elif found[cid].casefold() != name.casefold():
            print(f"RENAMED   {cid}  file: {name!r}  YouTube: {found[cid]!r}")
    print(f"{len(channels)} channels: {len(channels) - missing} found, {missing} missing ({api.units} quota units)")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
