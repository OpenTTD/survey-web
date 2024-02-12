import json
import sys
import tarfile

from collections import defaultdict

from .windows_name import WINDOWS_BUILD_NUMBER_TO_NAME

# Ensure the summary is always based on a good amount of surveys.
# Otherwise it is very easy for one user to be visible in the results.
THRESHOLD_DIFFERENT_SAVEGAMES = 150
THRESHOLD_DIFFERENT_SURVEYS = 300

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
    "info.configuration.graphics_set",  # Processed differently.
    "info.configuration.graphics_set_parameters",  # Processed differently.
    "info.configuration.music_set",  # Processed differently.
    "info.configuration.sound_set",  # Processed differently.
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
]


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
            major, minor, buildnumber = data.split(" ", 1)[1].split(".")
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

    if type(data) is str:
        if data.startswith('"') and data.endswith('"'):
            data = data[1:-1]
        if not data:
            data = "(empty)"

    summary[version][path][data] += seconds


def summarize_result(summary, fp):
    data = json.loads(fp.read())

    try:
        seconds = data["game"]["timers"]["seconds"]
        ticks = data["game"]["timers"]["ticks"]
    except KeyError:
        # Invalid (or very old) survey result.
        return

    # Due to a bug in OpenTTD, clients report a broken "seconds".
    if data["info"]["configuration"]["network"] == "client":
        return

    # Surveys results that were either mostly paused or really short are skipped
    # to avoid people gaming the system.
    if seconds < 60 or ticks < 100:
        return

    version = data["info"]["openttd"]["version"]["revision"]

    if "-" in version and version[0:8].isdigit():
        branch = version.split("-")[1]
        # Only track the nightlies.
        if branch == "master":
            version = "vanilla-master"
        else:
            return

    for key, value in data.items():
        summarize_setting(summary, version, seconds, key, value)

    summary[version]["summary"]["count"] += 1
    summary[version]["summary"]["seconds"] += seconds

    if "ids" not in summary[version]["summary"]:
        summary[version]["summary"]["ids"] = set()
    summary[version]["summary"]["ids"].add(data["id"])


def summarize_archive(summary, filename):
    if filename.endswith(".json"):
        if not filename.endswith("verified.json"):
            return

        with open(filename) as fp:
            summarize_result(summary, fp)
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
                summarize_result(summary, fp)


def main():
    summary = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    for filename in sys.argv[1:]:
        summarize_archive(summary, filename)

    # Calculate the "false" condition of each display option, assuming that if you didn't have it on, it was off.
    for version, version_summary in summary.items():
        # Sort the data based on the path.
        summary[version] = dict(sorted(summary[version].items(), key=lambda item: item[0]))

        for path, data in version_summary.items():
            if path == "summary":
                data["ids"] = len(data["ids"])

                if data["ids"] < THRESHOLD_DIFFERENT_SAVEGAMES or data["count"] < THRESHOLD_DIFFERENT_SURVEYS:
                    summary[version] = None
                    break

            if path.startswith("game.settings.display_opt.") or path.startswith("game.settings.extra_display_opt."):
                data["false"] = version_summary["summary"]["seconds"] - data["true"]

            total = sum(data.values())

            # Check if it adds up to the total; if not, it is (most likely) an OS specific setting.
            if path != "summary" and total != version_summary["summary"]["seconds"]:
                data["(not reported)"] = version_summary["summary"]["seconds"] - total

            # Collapse entries below 0.1% to a single (other) entry, and not true/false.
            if path != "summary":
                collapse = []
                for key, value in data.items():
                    if value / total < 0.001 and key not in ("true", "false", "(not reported)"):
                        collapse.append(key)
                for key in collapse:
                    data["(other)"] += data[key]
                    del data[key]

            # Sort the data based on the value.
            summary[version][path] = dict(sorted(data.items(), key=lambda item: item[1], reverse=True))

    print(json.dumps(dict(sorted(summary.items(), key=lambda item: item[0])), indent=4))


if __name__ == "__main__":
    main()
