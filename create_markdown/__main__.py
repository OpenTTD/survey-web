import json
import os
import sys

def create_summary(year, week, start_date, end_date):
    output = f"_summaries/{year}/wk{week}.md"
    os.makedirs(os.path.dirname(output), exist_ok=True)

    with open(output, "w") as file:
        file.write(f"""---
title: {year} - Week {week}
active_nav: summaries
year: "{year}"
week: "wk{week}"
start_date: "{start_date}"
end_date: "{end_date}"
---
""")

def create_version(year, week, start_date, end_date, version):
    output = f"_summaries/{year}/wk{week}/{version}.md"
    os.makedirs(os.path.dirname(output), exist_ok=True)

    with open(output, "w") as file:
        file.write(f"""---
title: {year} - Week {week} - {version}
active_nav: summaries
year: "{year}"
week: "wk{week}"
version: "{version}"
start_date: "{start_date}"
end_date: "{end_date}"
layout: "summary"
---
""")

def main():
    year = sys.argv[1]
    week = sys.argv[2]
    start_date = sys.argv[3]
    end_date = sys.argv[4]

    create_summary(year, week, start_date, end_date)
    with open(f"_data/summaries/{year}/wk{week}.json", "r") as file:
        data = json.load(file)
        for version, content in data.items():
            if content:
                create_version(year, week, start_date, end_date, version)

if __name__ == "__main__":
    main()
