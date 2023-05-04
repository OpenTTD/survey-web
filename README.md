# OpenTTD's Survey website

[![GitHub License](https://img.shields.io/github/license/OpenTTD/survey-web)](https://github.com/OpenTTD/survey-web/blob/main/LICENSE)
[![GitHub Tag](https://img.shields.io/github/v/tag/OpenTTD/survey-web?include_prereleases&label=stable)](https://github.com/OpenTTD/survey-web/releases)
[![GitHub commits since latest release](https://img.shields.io/github/commits-since/OpenTTD/survey-web/latest/main)](https://github.com/OpenTTD/survey-web/commits/main)

This is the [website](https://survey.openttd.org) to show the results of the survey analysis and the information and privacy statement of the participation.

This is a [Jekyll](https://jekyllrb.com/) website, and is served by nginx as a static site.

## Development

### Running a local server

If you do not want to run a server, but just build the current site, replace `serve` with `build` in the examples below.

Under `_site` Jekyll will put the compiled result in both `serve` and `build`.

- Follow [jekyll installation](https://jekyllrb.com/docs/installation/)
- Run `bundle install`
- Run `JEKYLL_ENV=production jekyll serve`
