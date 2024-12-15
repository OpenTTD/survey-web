import json
import os
import sys

def create_summary(timeframe, year, quarter_or_week, start_date, end_date):
    output = f"_summaries/{year}/{timeframe}{quarter_or_week}.md"
    os.makedirs(os.path.dirname(output), exist_ok=True)

    with open(output, "w") as file:
        if timeframe == "wk":
            file.write(f"""---
title: {year} - Week {quarter_or_week}
active_nav: summaries
year: "{year}"
type: week
filename: "wk{quarter_or_week}"
start_date: "{start_date}"
end_date: "{end_date}"
---
""")
        else:
            file.write(f"""---
title: {year} - Quarter {quarter_or_week}
active_nav: summaries
year: "{year}"
type: quarter
filename: "q{quarter_or_week}"
start_date: "{start_date}"
end_date: "{end_date}"
---
""")


def create_version(timeframe, year, quarter_or_week, start_date, end_date, version):
    output = f"_summaries/{year}/{timeframe}{quarter_or_week}/{version}.md"
    os.makedirs(os.path.dirname(output), exist_ok=True)

    with open(output, "w") as file:
        if timeframe == "wk":
            file.write(f"""---
title: {year} - Week {quarter_or_week} - {version}
active_nav: summaries
year: "{year}"
filename: "wk{quarter_or_week}"
version: "{version}"
start_date: "{start_date}"
end_date: "{end_date}"
layout: "summary"
---
""")
        else:
            file.write(f"""---
title: {year} - Quarter {quarter_or_week} - {version}
active_nav: summaries
year: "{year}"
filename: "q{quarter_or_week}"
version: "{version}"
start_date: "{start_date}"
end_date: "{end_date}"
layout: "summary"
---
""")

    output = f"_summaries/{year}/{timeframe}{quarter_or_week}/{version}/content.md"
    os.makedirs(os.path.dirname(output), exist_ok=True)

    with open(output, "w") as file:
        if timeframe == "wk":
            file.write(f"""---
title: {year} - Week {quarter_or_week} - {version} - 3rd Party Content
active_nav: summaries
year: "{year}"
filename: "wk{quarter_or_week}"
version: "{version}"
start_date: "{start_date}"
end_date: "{end_date}"
layout: "summary_content"
---
""")
        else:
            file.write(f"""---
title: {year} - Quarter {quarter_or_week} - {version} - 3rd Party Content
active_nav: summaries
year: "{year}"
filename: "q{quarter_or_week}"
version: "{version}"
start_date: "{start_date}"
end_date: "{end_date}"
layout: "summary_content"
---
""")

def main():
    timeframe = sys.argv[1]
    year = sys.argv[2]
    week = sys.argv[3]
    start_date = sys.argv[4]
    end_date = sys.argv[5]

    if timeframe != "q" and timeframe != "wk":
        raise ValueError("Timeframe must be 'q' or 'wk'")

    create_summary(timeframe, year, week, start_date, end_date)
    with open(f"_data/summaries/{year}/{timeframe}{week}.json", "r") as file:
        data = json.load(file)
        for version, content in data["survey"].items():
            if content:
                create_version(timeframe, year, week, start_date, end_date, version)

if __name__ == "__main__":
    main()
