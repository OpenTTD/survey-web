import glob
import os
import yaml

BANANAS_CACHE = {
    "ai": {},
    "newgrf": {},
    "game-script": {},
}
BANANAS_LOOKUP = {}


def _count(summary, content_data, seconds, name):
    if content_data["version"] == "(unknown)":
        # For "unknown", only record the highest value.
        summary[name][content_data["version"]] = max(summary[name][content_data["version"]], seconds)
    else:
        summary[name][content_data["version"]] += seconds


def analyse_ais(companies, summary, seconds):
    if companies is None:
        return

    for company in companies.values():
        if company["type"] != "ai":
            continue

        ai_name, _, ai_version = company["script"].partition(".")

        # DummyAI isn't an actual AI. It's a placeholder for when no AI is available.
        if ai_name == "DummyAI":
            continue

        # We only show popularity of content that are uploaded to BaNaNaS, as those are public content.
        # Anything not on BaNaNaS is either private or not yet released. It would be wrong for a survey
        # to leak information about such content.
        content_id = lookup_bananas_id("ai", ai_name)
        if content_id is None:
            # For some reason it is not uncommon for AIs to be named without "AI" in-game, but with "AI" on BaNaNaS.
            content_id = lookup_bananas_id("ai", f"{ai_name} AI")
        if content_id is None:
            content_id = "(other)"
            ai_version = "(unknown)"

        _count(summary, {"version": ai_version}, seconds, f"game.ai.{content_id}")


def analyse_gamescripts(game_script, summary, seconds):
    if game_script is None:
        return

    game_script_name, _, game_script_version = game_script.partition(".")

    # We only show popularity of content that are uploaded to BaNaNaS, as those are public content.
    # Anything not on BaNaNaS is either private or not yet released. It would be wrong for a survey
    # to leak information about such content.
    content_id = lookup_bananas_id("game-script", game_script_name)
    if content_id is None:
        content_id = "(other)"
        game_script_version = "(unknown)"

    _count(summary, {"version": game_script_version}, seconds, f"game.game_script.{content_id}")


def analyse_grfs(grfs, summary, seconds):
    if grfs is None:
        return

    for grf_id, params in grfs.items():
        if params["status"] != "activated":
            continue

        content_data = get_bananas_data("newgrf", grf_id, params["md5sum"])
        # We only show popularity of content that are uploaded to BaNaNaS, as those are public content.
        # Anything not on BaNaNaS is either private or not yet released. It would be wrong for a survey
        # to leak information about such content.
        if content_data is None:
            grf_id = "(other)"
            content_data = {
                "version": "(unknown)",
                "classification": {
                    "set": "unknown",
                },
            }

        set = content_data.get("classification", {}).get("set", "unknown")
        _count(summary, content_data, seconds, f"game.grf.{set}.{grf_id}")


def get_bananas_data(content_type, content_id, md5sum):
    if content_id not in BANANAS_CACHE[content_type]:
        load_bananas_data(content_type, content_id)

    if not BANANAS_CACHE[content_type][content_id]:
        return None

    BANANAS_CACHE[content_type][content_id]["used"] = True

    md5sum_partial = md5sum[:8].lower()
    return BANANAS_CACHE[content_type][content_id]["versions"].get(md5sum_partial)


def lookup_bananas_id(content_type, name):
    def fix_name(name):
        # Replace some common words.
        name = name.replace("&", "and")

        # Remove all non-alpha characters and make it lowercase.
        name = "".join([c for c in name if c.isalpha()]).lower()

        return name

    if content_type not in BANANAS_LOOKUP:
        BANANAS_LOOKUP[content_type] = {}

        for content in glob.glob(f"BaNaNaS/{content_type}/*/global.yaml"):
            content_id = os.path.basename(os.path.dirname(content))
            data = load_bananas_data(content_type, content_id)
            BANANAS_LOOKUP[content_type][fix_name(data["general"]["name"])] = content_id

    content_id = BANANAS_LOOKUP[content_type].get(fix_name(name))
    if content_id is None:
        return None

    BANANAS_CACHE[content_type][content_id]["used"] = True
    return content_id


def load_bananas_data(content_type, content_id):
    BANANAS_CACHE[content_type][content_id] = {}

    if os.path.exists(f"BaNaNaS/{content_type}/{content_id}/authors.yaml") is False:
        return None

    with open(f"BaNaNaS/{content_type}/{content_id}/global.yaml") as f:
        BANANAS_CACHE[content_type][content_id]["general"] = yaml.load(f.read(), Loader=yaml.CSafeLoader)

    with open(f"BaNaNaS/{content_type}/{content_id}/authors.yaml") as f:
        BANANAS_CACHE[content_type][content_id]["authors"] = yaml.load(f.read(), Loader=yaml.CSafeLoader)

    BANANAS_CACHE[content_type][content_id]["versions"] = {}

    for versions in glob.glob(f"BaNaNaS/{content_type}/{content_id}/versions/*.yaml"):
        with open(versions) as f:
            version = yaml.load(f.read(), Loader=yaml.CSafeLoader)
            BANANAS_CACHE[content_type][content_id]["versions"][version["md5sum-partial"]] = version

    return BANANAS_CACHE[content_type][content_id]


def export_bananas_data():
    content = {}

    for content_type, cache in BANANAS_CACHE.items():
        if content_type == "game-script":
            content_type = "game_script"

        content[content_type] = {}

        for content_id, data in cache.items():
            if "used" not in data:
                continue

            content[content_type][content_id] = {
                "name": data["general"]["name"],
            }

    return content
