import json
import sys
import tarfile

from collections import defaultdict

from .content import analyse_ais, analyse_gamescripts, analyse_grfs, export_bananas_data
from .windows_name import WINDOWS_BUILD_NUMBER_TO_NAME

# Ensure the summary is always based on a good amount of surveys.
# Otherwise it is very easy for one user to be visible in the results.
THRESHOLD_DIFFERENT_SAVEGAMES = 150
THRESHOLD_DIFFERENT_SURVEYS = 300
# Ensure games were actually played, and not just opened/closed.
# Otherwise it is very easy to bring your settings to the top.
THRESHOLD_GAME_SECONDS = 60
THRESHOLD_GAME_TICKS = 100

# These versions report the "seconds" wrong for network client games.
VERSION_BROKEN_NETWORK_CLIENT = [
    "14.0-beta1",
    "14.0-beta2",
    "14.0-beta3",
    "jgrpp-0.56.2",
    "jgrpp-0.57.0",
    "jgrpp-0.57.1",
]
VERSION_BROKEN_NETWORK_CLIENT_MASTER = 20240213

BLACKLIST_PATHS = [
    "date",  # Not interesting.
    "game.companies",  # Processed differently.
    "game.game_script",  # Processed differently.
    "game.grfs",  # Processed differently.
    "game.settings.game_creation.generation_seed",  # Too many results.
    "game.settings.game_creation.generation_unique_id",  # Too many results.
    "game.settings.large_font",  # Might expose user information, and is already covered by info.font.large.
    "game.settings.last_newgrf_count",  # Not interesting.
    "game.settings.medium_font",  # Might expose user information, and is already covered by info.font.medium.
    "game.settings.mono_font",  # Might expose user information, and is already covered by info.font.mono.
    "game.settings.music.custom_1",  # Not interesting.
    "game.settings.music.custom_2",  # Not interesting.
    "game.settings.music.effect_vol",  # Not interesting.
    "game.settings.music.music_vol",  # Not interesting.
    "game.settings.musicset",  # Already in "info.configuration.music_set".
    "game.settings.player_face",  # Not interesting.
    "game.settings.small_font",  # Might expose user information, and is already covered by info.font.small.
    "game.settings.soundsset",  # Already in "info.configuration.sound_set".
    "game.timers",  # Not interesting.
    "id",  # Not interesting.
    "info.compiler",  # Not interesting.
    "info.configuration.graphics_set_parameters",  # Processed differently.
    "info.libraries",  # Not interesting.
    "info.openttd.build_date",  # Not interesting.
    "info.openttd.version",  # Not interesting.
    "info.os.machine",  # OS specific setting, not interesting.
    "info.os.max_ver",  # OS specific setting, Not interesting.
    "info.os.min_ver",  # OS specific setting, Not interesting.
    "info.os.release",  # Combined with "info.os.os".
    "info.os.version",  # OS specific setting, Not interesting.
    "key",  # Not interesting.
    "schema",  # Not interesting.
    "session",  # Processed differently.
]

# In what percentile to report savegame sizes.
SAVEGAME_SIZE_PERCENTILE = [50, 90, 95, 99, 99.9]


def summarize_setting(summary, version, seconds, path, data):
    if path in BLACKLIST_PATHS:
        return

    if type(data) is dict:
        for key, value in data.items():
            # Combine info.os.os with info.os.release, as their whole is the OS version.
            if path == "info.os" and key == "os":
                summarize_setting(summary, version, seconds, f"{path}.vendor", value)
                value = f"{value} {data['release']}".replace(" ()", "").split("-")[0]

            summarize_setting(summary, version, seconds, f"{path}.{key}", value)

        return

    # Broken data from the early days.
    if path == "info.plugins":
        return

    # Only track plugins if they are running.
    if path.startswith("info.plugins"):
        for entry in data:
            if entry["state"] == "running":
                data = entry["version"]
                break
        else:
            data = "(not running)"

    if type(data) is list:
        raise Exception("Lists are not implemented yet")

    if path in ("game.settings.display_opt", "game.settings.extra_display_opt"):
        if not data:
            return

        for option in data.split("|"):
            summarize_setting(summary, version, seconds, f"{path}.{option}", "true")
        return

    if path == "info.configuration.video_info":
        if "(" not in data or data.startswith("sdl "):
            data = "(no hardware acceleration)"
            summarize_setting(summary, version, seconds, f"{path}.brand", data)
        else:
            driver = data.split("(")[0].strip()

            # SDL reports slightly different from the rest.
            if driver == "sdl-opengl":
                data = data.split("(", 2)[2]
            else:
                data = data.split("(", 1)[1]

            # Only keep the graphics driver name; remove all versions etc.
            data = data.replace("(TM)", "@TM@").replace("(R)", "@R@").replace("(C)", "@C@")
            data = data.split(",")[0].split("(")[0].strip()
            data = data.replace("@TM@", "(TM)").replace("@R@", "(R)").replace("@C@", "(C)")

            if "nvidia" in data.lower() or "geforce" in data.lower() or "quadro" in data.lower():
                brand = "NVIDIA"
            elif "intel" in data.lower():
                brand = "Intel"
            elif "amd " in data.lower() or "radeon" in data.lower():
                brand = "AMD"
            elif "apple" in data.lower():
                brand = "Apple"
            else:
                brand = "(other)"

            summarize_setting(summary, version, seconds, f"{path}.brand", brand)

    if path == "game.settings.resolution":
        width, _, height = data.partition(",")
        if width and height and width.isdigit() and height.isdigit():
            summarize_setting(summary, version, seconds, f"{path}.width", int(width))
            summarize_setting(summary, version, seconds, f"{path}.height", int(height))
        else:
            # We failed to split in width/height, so record unknowns.
            summarize_setting(summary, version, seconds, f"{path}.width", "(unknown)")
            summarize_setting(summary, version, seconds, f"{path}.height", "(unknown)")

    if path == "info.os.os":
        if data.startswith("Windows"):
            major, minor, buildnumber = data.split(" ")[1].split(".")
            os_version = WINDOWS_BUILD_NUMBER_TO_NAME.get(f"{major}.{minor}", data)
            if major == "10" and buildnumber.isdigit() and int(buildnumber) >= 22000:
                os_version = WINDOWS_BUILD_NUMBER_TO_NAME.get(f"{major}.{minor}.22000", os_version)
        elif data.startswith("MacOS"):
            major, minor, patch = data.split(" ", 1)[1].split(".")
            if major.isdigit() and int(major) <= 10:
                os_version = f"MacOS {major}.{minor}"
            else:
                os_version = f"MacOS {major}"
        elif data.startswith("Linux"):
            os_version = "Linux"
        else:
            os_version = data

        summarize_setting(summary, version, seconds, f"{path}.version", os_version)

    if path in ("info.configuration.graphics_set", "info.configuration.music_set", "info.configuration.sound_set"):
        content, _, content_version = data.partition(".")
        path = f"{path}.{content}"
        data = content_version

    if type(data) is str:
        if data.startswith('"') and data.endswith('"'):
            data = data[1:-1]
        if not data:
            data = "(empty)"

    summary[version][path][data] += seconds


def summarize_result(summary, timeframe, fp):
    data = json.loads(fp.read())
    schema = data["schema"]

    try:
        if schema == 1:
            seconds = data["game"]["timers"]["seconds"]
        else:
            seconds = data["session"]["seconds"]

        ticks = data["game"]["timers"]["ticks"]
    except KeyError:
        # Invalid (or very old) survey result.
        return

    # Surveys results that were either mostly paused or really short are skipped
    # to avoid people gaming the system.
    if seconds < THRESHOLD_GAME_SECONDS or ticks < THRESHOLD_GAME_TICKS:
        return

    version = data["info"]["openttd"]["version"]["revision"]

    if "-" in version and version[0:8].isdigit():
        branch = version.split("-")[1]
        # Only track the nightlies.
        if branch == "master":
            date = int(version[0:8])
            version = "vanilla-master"
        else:
            return

    # Due to a bug in older OpenTTD clients, results with network=client report a broken "seconds".
    if version in VERSION_BROKEN_NETWORK_CLIENT or (
        version == "vanilla-master" and date < VERSION_BROKEN_NETWORK_CLIENT_MASTER
    ):
        if data["info"]["configuration"]["network"] == "client":
            return
        # Due to another bug, the game sometimes doesn't report it was a network=client.
        # The biggest impact with these games is that they can contain the unixtimestamp
        # as "seconds". Ignore only this situation here.
        if seconds > 1000000000:
            return

    if timeframe == "wk":
        pass
    elif timeframe == "q":
        original_version = version

        # For quarterly summaries, we only report "14" or "jgrpp" for versions.
        version = version.rsplit(".")[0]
        version = version.split("-")[0]
    else:
        raise Exception(f"Unknown timeframe: {timeframe}")

    for key, value in data.items():
        summarize_setting(summary, version, seconds, key, value)

    analyse_ais(data["game"]["companies"], summary[version], seconds)
    analyse_gamescripts(data["game"]["game_script"], summary[version], seconds)
    analyse_grfs(data["game"]["grfs"], summary[version], seconds)

    # Count how many NewGRFs are active.
    newgrf_count = (
        sum(1 for grf in data["game"]["grfs"].values() if grf["status"] == "activated") if data["game"]["grfs"] else 0
    )
    summary[version]["game.newgrf_count"][newgrf_count] += seconds
    # Count how many AIs are active.
    ai_count = (
        sum(
            1
            for company in data["game"]["companies"].values()
            if company["type"] == "ai" and company["script"] != "DummyAI"
        )
        if data["game"]["companies"]
        else 0
    )
    summary[version]["game.ai_count"][ai_count] += seconds
    # Mention whether a GameScript was used.
    summary[version]["game.game_script_used"][True if data["game"]["game_script"] else False] += seconds

    summary[version]["summary"]["count"] += 1
    summary[version]["summary"]["seconds"] += seconds

    # Quarterly reports are combined per major version; also show the relative usage of versions.
    if timeframe == "q":
        summary[version]["info.openttd.version"][original_version] += seconds

    # Depending whether the game was saved, we see a savegame-size or not.
    if schema >= 2 and "savegame_size" in data["session"]:
        summary[version]["savegame_size"][(data["session"]["savegame_size"] // 10000) * 10000] += 1

    if "ids" not in summary[version]["summary"]:
        summary[version]["summary"]["ids"] = set()
    if schema == 1:
        summary[version]["summary"]["ids"].add(data["id"])
    else:
        summary[version]["summary"]["ids"].add(data["session"]["id"])


def summarize_archive(summary, timeframe, filename):
    if filename.endswith(".json"):
        if not filename.endswith("verified.json"):
            return

        with open(filename) as fp:
            summarize_result(summary, timeframe, fp)
            return

    with tarfile.open(filename) as archive:
        for member in archive:
            if not member.isfile():
                continue

            # If the filename doesn't end with "verified.json", the survey result
            # wasn't created by an official client. For now, we skip those results.
            if not member.name.endswith("verified.json"):
                continue

            with archive.extractfile(member) as fp:
                summarize_result(summary, timeframe, fp)


def get_percentile(data, percentile):
    total = sum(data.values())
    target = total * percentile / 100
    current = 0
    for key, value in data.items():
        current += value
        if current >= target:
            return key
    return None


def main():
    timeframe = sys.argv[1]

    summary = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    for filename in sys.argv[2:]:
        summarize_archive(summary, timeframe, filename)

    remove_version = []

    # Calculate the "false" condition of each display option, assuming that if you didn't have it on, it was off.
    for version, version_summary in summary.items():
        for path, data in version_summary.items():
            if path == "summary":
                data["ids"] = len(data["ids"])

                if data["ids"] < THRESHOLD_DIFFERENT_SAVEGAMES or data["count"] < THRESHOLD_DIFFERENT_SURVEYS:
                    remove_version.append(version)
                    break

            if path == "savegame_size":
                buckets = dict(sorted(data.items()))
                data = {}
                for percentile in SAVEGAME_SIZE_PERCENTILE:
                    data[f"Percentile ({percentile}%)"] = get_percentile(buckets, percentile)
                data["Average size"] = sum(key * value for key, value in buckets.items()) // sum(buckets.values())
                version_summary[path] = data

            if path.startswith("game.settings.display_opt.") or path.startswith("game.settings.extra_display_opt."):
                data["false"] = version_summary["summary"]["seconds"] - data["true"]

            total = sum(data.values())

            if (
                path.startswith("game.grf.")
                or path.startswith("game.ai.")
                or path.startswith("game.game_script.")
                or path.startswith("info.configuration.graphics_set.")
                or path.startswith("info.configuration.music_set.")
                or path.startswith("info.configuration.sound_set.")
            ):
                # Content entries follow special rules (see below).
                pass
            else:
                # Check if it adds up to the total; if not, it is (most likely) an OS specific setting.
                if path not in ("summary", "savegame_size") and total != version_summary["summary"]["seconds"]:
                    data["(not reported)"] = version_summary["summary"]["seconds"] - total

                # Collapse entries below 0.1% to a single (other) entry, and not true/false.
                if path not in ("summary", "reason", "savegame_size"):
                    collapse = []
                    for key, value in data.items():
                        if value / total < 0.001 and key not in ("true", "false", "(not reported)"):
                            collapse.append(key)
                    for key in collapse:
                        data["(other)"] += data[key]
                        del data[key]

        # We iterate again, this time to collapse GRF / AI / GS.
        for path, data in list(version_summary.items()):
            total = sum(data.values())

            if path.startswith("game.grf."):
                set = path.split(".")[2]
                if total / version_summary["summary"]["seconds"] < 0.001:
                    version_summary[f"game.grf.{set}.(other)"]["(other)"] += total
                    del version_summary[path]
            elif path.startswith("game.ai.") or path.startswith("game.game_script."):
                prefix = ".".join(path.split(".")[:2])
                if total / version_summary["summary"]["seconds"] < 0.001:
                    version_summary[f"{prefix}.(other)"]["(other)"] += total
                    del version_summary[path]
            elif (
                path.startswith("info.configuration.graphics_set.")
                or path.startswith("info.configuration.music_set.")
                or path.startswith("info.configuration.sound_set.")
            ):
                prefix = ".".join(path.split(".")[:3])
                if total / version_summary["summary"]["seconds"] < 0.001:
                    version_summary[f"{prefix}.(other)"]["(other)"] += total
                    del version_summary[path]

        for path, data in version_summary.items():
            # Sort the data based on the value.
            version_summary[path] = dict(sorted(data.items(), key=lambda item: item[1], reverse=True))

        def sort_results(item):
            # Sort based on popularity.
            for key in (
                "game.grf.",
                "game.ai.",
                "game.game_script.",
                "info.configuration.graphics_set.",
                "info.configuration.music_set.",
                "info.configuration.sound_set.",
            ):
                if item[0].startswith(key):
                    return (key, -sum(item[1].values()))

            # Sort the data based on the path.
            return (item[0], 0)

        summary[version] = dict(sorted(summary[version].items(), key=sort_results))

    # Remove versions that didn't reach the threshold.
    for version in remove_version:
        del summary[version]

    summary = {
        "survey": dict(sorted(summary.items(), key=lambda item: item[0])),
        "content": export_bananas_data(),
    }

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
