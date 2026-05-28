#!/usr/bin/env python
"""Walk a company's blog archive, enumerate postmortem URLs, fetch each verbatim.

Per-company configurations describe how to enumerate and filter posts.
Output:
  data/raw_html/<company>/_urls.txt   — list of canonical URLs found
  data/raw_html/<company>/<slug>.md   — verbatim extracted text per post

Usage:
  python tools/walk_archive.py <company>
  python tools/walk_archive.py --list
  python tools/walk_archive.py --all
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

import requests
import trafilatura

UA = "Mozilla/5.0"
UA_FULL = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
ROOT = Path(__file__).resolve().parent.parent.parent
RAW = ROOT / "data" / "raw_html"


@dataclass
class CompanyConfig:
    name: str
    archive_urls: list[str]
    # Regex to extract post URLs from index pages.
    post_url_pattern: str
    # Optional whitelist/blacklist substrings applied to URL.
    must_contain: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    # Explicit URLs to always include (in addition to enumerated ones).
    extra_urls: list[str] = field(default_factory=list)


CONFIGS: dict[str, CompanyConfig] = {
    "cloudflare": CompanyConfig(
        name="cloudflare",
        archive_urls=[
            "https://blog.cloudflare.com/tag/post-mortem/",
            "https://blog.cloudflare.com/tag/post-mortem/page/2/",
            "https://blog.cloudflare.com/tag/post-mortem/page/3/",
            "https://blog.cloudflare.com/tag/post-mortem/page/4/",
        ],
        post_url_pattern=r"https://blog\.cloudflare\.com/[a-z0-9][a-z0-9-]+/?",
        must_not_contain=[
            "/tag/", "/author/", "/cdn-cgi/", "/page/",
            "/ar-ar/", "/de-de/", "/es-es/", "/fr-fr/", "/it-it/", "/ja-jp/",
            "/ko-kr/", "/nl-nl/", "/pl-pl/", "/pt-br/", "/ru-ru/", "/sv-se/",
            "/th-th/", "/tr-tr/", "/vi-vn/", "/zh-cn/", "/zh-tw/", "/zh-hans-cn/",
            "/help-center/", "/contact-us/", "/about/", "/careers/", "/press/",
            "/products/", "/learning/", "/security/", "/privacy/", "/terms/",
        ],
    ),
    "aws": CompanyConfig(
        name="aws",
        archive_urls=["https://aws.amazon.com/premiumsupport/technology/pes/"],
        post_url_pattern=r"https://aws\.amazon\.com/(?:message|premiumsupport)/[a-zA-Z0-9/_-]+/?",
        must_contain=["/message/"],
    ),
    "github": CompanyConfig(
        name="github",
        archive_urls=[
            "https://github.blog/tag/post-incident/",
            "https://github.blog/tag/post-incident/page/2/",
            "https://github.blog/news-insights/company-news/",
            "https://github.blog/news-insights/company-news/page/2/",
            "https://github.blog/news-insights/company-news/page/3/",
        ],
        # Match blog post slugs only — must be inside /news-insights/<section>/<slug>/ or YYYY-MM-DD-<slug>
        post_url_pattern=r"https://github\.blog/(?:[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9][a-z0-9-]+|news-insights/(?:company-news|engineering|the-library)/[a-z0-9][a-z0-9-]+)/?",
        must_not_contain=["/tag/", "/author/", "/category/", "/page/", "/wp-content/", "/wp-includes/"],
        extra_urls=[
            "https://github.blog/2018-10-30-oct21-post-incident-analysis/",
            "https://github.blog/news-insights/company-news/february-service-disruptions-post-incident-analysis/",
            "https://github.blog/news-insights/company-news/oct21-post-incident-analysis/",
            "https://github.blog/news-insights/the-library/dns-outage-post-mortem/",
            "https://github.blog/news-insights/the-library/downtime-last-saturday/",
            "https://github.blog/news-insights/the-library/github-availability-this-week/",
            "https://github.com/blog/2106-january-28th-incident-report",
            "https://github.blog/news-insights/company-news/github-availability-report-october-2020/",
            "https://github.blog/news-insights/company-news/github-availability-report-may-2021/",
            "https://github.blog/news-insights/company-news/github-availability-report-august-2024/",
        ],
    ),
    "slack": CompanyConfig(
        name="slack",
        archive_urls=["https://slack.engineering/"],
        post_url_pattern=r"https://slack\.engineering/[a-z0-9-]+/?",
        must_not_contain=["/tag/", "/category/", "/author/"],
        # Slack has no postmortem tag, so we rely on extra_urls for known incidents:
        extra_urls=[
            "https://slack.engineering/a-terrible-horrible-no-good-very-bad-day-at-slack/",
            "https://slack.engineering/slacks-outage-on-january-4th-2021/",
            "https://slack.engineering/slacks-dnssec-rollout-and-its-effects/",
            "https://slack.engineering/slacks-incident-on-2-22-22/",
            "https://slack.engineering/query-strikes-again-using-our-incident-response-process-to-debug-a-pesky-bug/",
            "https://slack.engineering/jenkins-pipelines-postmortem/",
        ],
    ),
    "circleci": CompanyConfig(
        name="circleci",
        archive_urls=[
            "https://discuss.circleci.com/c/announcements/incident-reports/13.json",
            "https://discuss.circleci.com/c/announcements/incident-reports/13.json?page=1",
            "https://discuss.circleci.com/c/announcements/incident-reports/13.json?page=2",
        ],
        post_url_pattern=r"\"slug\"\s*:\s*\"([a-z0-9-]+)\".*?\"id\"\s*:\s*(\d+)",
        # JSON pattern won't work with simple regex extraction; use extras + manual fetch
        extra_urls=[
            "https://discuss.circleci.com/t/incident-report-november-8-2021-jobs-stuck-in-a-not-running-state/41890",
            "https://discuss.circleci.com/t/post-incident-report-april-4-2025-circleci-ui-loading-build-triggering-issues/53208",
            "https://discuss.circleci.com/t/post-incident-report-april-4-2025-delays-in-starting-workflows/53113",
            "https://discuss.circleci.com/t/postmortem-march-26-april-10-workflow-delay-incidents/30060",
            "https://discuss.circleci.com/t/postmortem-may-21-2021-delay-in-starting-docker-jobs-machine-remote-docker-environments-blocked/40274",
            "https://circleci.com/blog/jan-4-2023-incident-report/",
            "https://circleci.com/blog/circleci-security-incident-jan-2023/",
            "https://discuss.circleci.com/t/post-incident-report-january-2-2025-self-hosted-machine-runner-failures/49855",
            "https://discuss.circleci.com/t/post-incident-report-october-21-2024-deploy-related-failures/48015",
            "https://discuss.circleci.com/t/post-incident-report-april-29-2024-cloud-platform-impact/45148",
        ],
    ),
    "heroku": CompanyConfig(
        name="heroku",
        archive_urls=[
            "https://blog.heroku.com/archives",
            "https://www.heroku.com/blog/",
        ],
        post_url_pattern=r"https://(?:blog\.heroku\.com|www\.heroku\.com/blog)/[a-z0-9-]+/?",
        extra_urls=[
            "https://blog.heroku.com/april-2022-incident-review",
            "https://blog.heroku.com/how-i-broke-git-push-heroku-main",
            "https://blog.heroku.com/summary-of-june-10-outage",
            "https://blog.heroku.com/summary-of-june-15-2022-outage",
            "https://blog.heroku.com/tuesday_postmortem",
            "https://engineering.heroku.com/blogs/2017-02-15-filesystem-corruption-on-heroku-dynos/",
            "https://status.heroku.com/incidents/2558",
            "https://status.heroku.com/incidents/1091",
            "https://status.heroku.com/incidents/642?postmortem",
            "https://status.heroku.com/incidents/2451",
        ],
    ),
    "incident_io": CompanyConfig(
        name="incident_io",
        archive_urls=["https://incident.io/blog"],
        post_url_pattern=r"https://incident\.io/blog/[a-z0-9-]+/?",
        extra_urls=[
            "https://incident.io/blog/one-two-skip-a-few",
            "https://incident.io/blog/database-performance",
            "https://status.incident.io/incidents/01JRDFKAGE07YYDY0KZR137BX3/write-up",
        ],
    ),
    "honeycomb": CompanyConfig(
        name="honeycomb",
        archive_urls=[
            "https://www.honeycomb.io/blog/category/incident-response",
            "https://www.honeycomb.io/blog/category/incident-response/page/2",
        ],
        post_url_pattern=r"https://www\.honeycomb\.io/blog/(?:incident-(?:report|review)|postmortem)[a-z0-9-]+",
        extra_urls=[
            "https://www.honeycomb.io/blog/incident-report-missing-trigger-notification-emails",
            "https://www.honeycomb.io/blog/incident-report-running-dry-on-memory-without-noticing",
            "https://www.honeycomb.io/blog/incident-report-exercises-cleanups-and-evacuations",
            "https://www.honeycomb.io/blog/incident-review-what-comes-up-must-first-go-down",
        ],
    ),
    "gitlab": CompanyConfig(
        name="gitlab",
        archive_urls=["https://about.gitlab.com/blog/categories/incidents/"],
        post_url_pattern=r"https://about\.gitlab\.com/blog/[0-9]{4}/[0-9]{2}/[0-9]{2}/[a-z0-9-]+/?",
        extra_urls=[
            "https://about.gitlab.com/blog/2017/02/01/gitlab-dot-com-database-incident/",
            "https://about.gitlab.com/blog/2017/02/10/postmortem-of-database-outage-of-january-31/",
        ],
    ),
    "twilio": CompanyConfig(
        name="twilio",
        archive_urls=["https://www.twilio.com/en-us/blog/archive"],
        post_url_pattern=r"https://www\.twilio\.com/en-us/blog/[a-z0-9-]+/?",
        extra_urls=[
            "https://www.twilio.com/en-us/blog/billing-incident-post-mortem-breakdown-analysis-and-root-cause",
            "https://www.twilio.com/en-us/blog/february-26-service-disruption-update",
            "https://www.twilio.com/en-us/blog/engineering-improvements-for-service-disruption-prevention",
        ],
    ),
    "discord": CompanyConfig(
        name="discord",
        archive_urls=["https://discord.com/blog"],
        post_url_pattern=r"https://discord\.com/blog/[a-z0-9-]+/?",
        extra_urls=[
            "https://discord.com/blog/authentication-outage",
            "https://discord.com/blog/behind-the-scenes-of-the-3-25-26-voice-outage",
            "https://discord.com/blog/how-discord-stores-trillions-of-messages",  # not pm but technical context
        ],
    ),
    "datadog": CompanyConfig(
        name="datadog",
        archive_urls=["https://www.datadoghq.com/blog/engineering/"],
        post_url_pattern=r"https://www\.datadoghq\.com/blog/[a-z0-9-]+/?",
        extra_urls=[
            "https://www.datadoghq.com/blog/engineering/2023-03-08-deep-dive-into-incident-response/",
            "https://www.datadoghq.com/blog/engineering/2023-03-08-deep-dive-into-platform-level-impact/",
            "https://www.datadoghq.com/blog/engineering/2023-03-08-deep-dive-into-platform-level-recovery/",
            "https://www.datadoghq.com/blog/2023-03-08-multiregion-infrastructure-connectivity-issue/",
        ],
    ),
    "roblox": CompanyConfig(
        name="roblox",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://corp.roblox.com/newsroom/2022/01/roblox-return-to-service-10-28-10-31-2021",
            "https://blog.roblox.com/2022/01/roblox-return-to-service-10-28-10-31-2021/",
        ],
    ),
    # Single-incident historical cases:
    "openai": CompanyConfig(
        name="openai",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://openai.com/index/march-20-chatgpt-outage/",
            "https://web.archive.org/web/20240426015133/https://openai.com/blog/march-20-chatgpt-outage",
        ],
    ),
    "crowdstrike": CompanyConfig(
        name="crowdstrike",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://www.crowdstrike.com/falcon-content-update-remediation-and-guidance-hub/",
            "https://www.crowdstrike.com/wp-content/uploads/2024/08/Channel-File-291-Incident-Root-Cause-Analysis-08.06.2024.pdf",
            "https://www.crowdstrike.com/en-us/blog/falcon-content-update-preliminary-post-incident-report/",
        ],
    ),
    "atlassian": CompanyConfig(
        name="atlassian",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://www.atlassian.com/engineering/post-incident-review-april-2022-outage",
        ],
    ),
    "stripe": CompanyConfig(
        name="stripe",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://support.stripe.com/questions/outage-postmortem-2015-10-08-utc",
        ],
    ),
    "netflix": CompanyConfig(
        name="netflix",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://netflixtechblog.com/post-mortem-of-october-22-2012-aws-degradation-efcee3ab40d5",
        ],
    ),
    "knight_capital": CompanyConfig(
        name="knight_capital",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://www.sec.gov/litigation/admin/2013/34-70694.pdf",
            "https://dougseven.com/2014/04/17/knightmare-a-devops-cautionary-tale/",
        ],
    ),
    "azure": CompanyConfig(
        name="azure",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://azure.microsoft.com/en-us/blog/update-on-azure-storage-service-interruption/",
            "https://azure.microsoft.com/en-us/blog/summary-of-windows-azure-service-disruption-on-feb-29th-2012/",
            "https://azure.status.microsoft/en-us/status/history/",
        ],
    ),
    "gcp": CompanyConfig(
        name="gcp",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://cloud.google.com/blog/products/infrastructure/details-of-google-cloud-gcve-incident",
            "https://status.cloud.google.com/incident/compute/16007",
            "https://status.cloud.google.com/incident/compute/17007",
            "https://status.cloud.google.com/incident/storage/19002",
            "https://status.cloud.google.com/incident/cloud-networking/19009",
            "https://status.cloud.google.com/incidents/ow5i3PPK96RduMcb1SsW",
            "https://status.cloud.google.com/incidents/1xkAB1KmLrh5g3v9ZEZ7",
            "https://status.cloud.google.com/incidents/6PM5mNd43NbMqjCZ5REh",
        ],
    ),
    "travisci": CompanyConfig(
        name="travisci",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://www.traviscistatus.com/incidents/r9n3v5gv3sxz",
            "https://www.traviscistatus.com/incidents/9k9rzhrbm6tn",
            "https://web.archive.org/web/20180816225828/https://blog.travis-ci.com/2017-08-01-incident-post-mortem",
        ],
    ),
    "stackexchange": CompanyConfig(
        name="stackexchange",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://stackstatus.tumblr.com/post/96025967369/outage-post-mortem-august-25th-2014",
            "https://stackstatus.tumblr.com/post/126892152906/outage-post-mortem-august-25-2015",
            "https://web.archive.org/web/20201020103424/https://stackstatus.net/post/96025967369/outage-post-mortem-august-25th-2014",
        ],
    ),
    "wikimedia": CompanyConfig(
        name="wikimedia",
        archive_urls=["https://wikitech.wikimedia.org/wiki/Incident_documentation"],
        post_url_pattern=r"/wiki/Incidents?/[^\s\"<>?#]+",
    ),
    "stripe": CompanyConfig(
        name="stripe",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://support.stripe.com/questions/outage-postmortem-2015-10-08-utc",
        ],
    ),
    "netflix": CompanyConfig(
        name="netflix",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://netflixtechblog.com/post-mortem-of-october-22-2012-aws-degradation-efcee3ab40d5",
        ],
    ),
    "stackexchange": CompanyConfig(
        name="stackexchange",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://stackstatus.tumblr.com/post/96025967369/outage-post-mortem-august-25th-2014",
            "https://stackstatus.tumblr.com/post/126892152906/outage-post-mortem-august-25-2015",
        ],
    ),
    "travisci": CompanyConfig(
        name="travisci",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://blog.travis-ci.com/2017-08-01-incident-post-mortem",
            "https://www.traviscistatus.com/incidents/r9n3v5gv3sxz",
            "https://www.traviscistatus.com/incidents/9k9rzhrbm6tn",
        ],
    ),
    "knight_capital": CompanyConfig(
        name="knight_capital",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://dougseven.com/2014/04/17/knightmare-a-devops-cautionary-tale/",
            "https://www.henricodolfing.com/2019/06/project-failure-case-study-knight-capital.html",
        ],
    ),
    # Historical / canonical case studies (Tier C single-incident)
    "healthcare_gov": CompanyConfig(
        name="healthcare_gov",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://en.wikipedia.org/wiki/HealthCare.gov",
            "https://www.govexec.com/management/2014/02/its-not-all-bad-news-about-healthcaregov/79002/",
            "https://hbr.org/2014/02/the-real-lessons-from-healthcare-gov",
        ],
    ),
    "therac25": CompanyConfig(
        name="therac25",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://en.wikipedia.org/wiki/Therac-25",
        ],
    ),
    "arpanet1980": CompanyConfig(
        name="arpanet1980",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://datatracker.ietf.org/doc/html/rfc789",
        ],
    ),
    "northeast_blackout": CompanyConfig(
        name="northeast_blackout",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://en.wikipedia.org/wiki/Northeast_blackout_of_2003",
        ],
    ),
    "indian_grid": CompanyConfig(
        name="indian_grid",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://en.wikipedia.org/wiki/2012_India_blackouts",
        ],
    ),
    "npm2014": CompanyConfig(
        name="npm2014",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://blog.npmjs.org/post/74949623024/2014-01-28-outage-postmortem.html",
        ],
    ),
    "mozilla_addons": CompanyConfig(
        name="mozilla_addons",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://hacks.mozilla.org/2019/07/add-ons-outage-post-mortem-result/",
            "https://hacks.mozilla.org/2022/02/retrospective-and-technical-details-on-the-recent-firefox-outage/",
        ],
    ),
    "wikimedia_wiki": CompanyConfig(
        name="wikimedia_wiki",
        archive_urls=["https://wikitech.wikimedia.org/wiki/Incident_documentation"],
        post_url_pattern=r"/wiki/Incidents?/[^\s\"<>?#]+",
    ),
    "ovhcloud": CompanyConfig(
        name="ovhcloud",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://www.ovhcloud.com/en/abuse-incident-strasbourg-2021/",
            "https://en.wikipedia.org/wiki/2021_OVH_data_center_fire",
        ],
    ),
    "facebook_meta": CompanyConfig(
        name="facebook_meta",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://engineering.fb.com/2021/10/04/networking-traffic/outage/",
            "https://engineering.fb.com/2021/10/05/networking-traffic/outage-details/",
            "https://engineering.fb.com/2024/03/05/data-infrastructure/server-performance-llm-mtia-aws-meta/",
        ],
    ),
    "linkedin": CompanyConfig(
        name="linkedin",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://engineering.linkedin.com/blog/2020/learnings-from-a-major-outage",
        ],
    ),
    "etsy": CompanyConfig(
        name="etsy",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://www.etsy.com/codeascraft/blameless-postmortems",
            "https://www.etsy.com/codeascraft/learning-from-failure",
        ],
    ),
    "bitly": CompanyConfig(
        name="bitly",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://bitly.com/blog/2014/05/the-data-incident-may-2014/",
        ],
    ),
    "browserstack": CompanyConfig(
        name="browserstack",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://www.browserstack.com/attack-and-downtime-on-9-November",
        ],
    ),
    "buildkite": CompanyConfig(
        name="buildkite",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://buildkite.com/blog/postmortem-for-rds-upgrade-causing-database-outage-on-25-may-2023",
            "https://buildkite.com/blog/outage-postmortem-9-october-2024",
            "https://buildkite.com/blog/incident-postmortem-7-january-2020",
        ],
    ),
    "okta": CompanyConfig(
        name="okta",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://sec.okta.com/articles/2022/03/oktas-investigation-of-the-january-2022-compromise",
        ],
    ),
    "robinhood": CompanyConfig(
        name="robinhood",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://newsroom.aboutrobinhood.com/an-update-on-yesterdays-outage/",
        ],
    ),
    # === Scrum / large software-PROJECT failures (Scrum's domain: product/project delivery) ===
    # These are documented via public inquiry reports, audits, court filings, Wikipedia.
    "tsb_migration": CompanyConfig(
        name="tsb_migration",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://en.wikipedia.org/wiki/TSB_Bank_(United_Kingdom)",
        ],
    ),
    "queensland_health": CompanyConfig(
        name="queensland_health",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://en.wikipedia.org/wiki/Queensland_Health_Payroll_System_Commission_of_Inquiry",
        ],
    ),
    "universal_credit": CompanyConfig(
        name="universal_credit",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://en.wikipedia.org/wiki/Universal_Credit",
        ],
    ),
    "phoenix_pay": CompanyConfig(
        name="phoenix_pay",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://en.wikipedia.org/wiki/Phoenix_pay_system",
        ],
    ),
    "boeing_737max": CompanyConfig(
        name="boeing_737max",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://en.wikipedia.org/wiki/Maneuvering_Characteristics_Augmentation_System",
        ],
    ),
    "ariane5": CompanyConfig(
        name="ariane5",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://en.wikipedia.org/wiki/Cluster_(spacecraft)",
            "http://sunnyday.mit.edu/nasa-class/Ariane5-report.html",
        ],
    ),
    "mars_climate_orbiter": CompanyConfig(
        name="mars_climate_orbiter",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://en.wikipedia.org/wiki/Mars_Climate_Orbiter",
        ],
    ),
    "london_ambulance": CompanyConfig(
        name="london_ambulance",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://en.wikipedia.org/wiki/London_Ambulance_Service#Computer-aided_despatch_failures",
        ],
    ),
    "denver_airport": CompanyConfig(
        name="denver_airport",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://en.wikipedia.org/wiki/Denver_International_Airport#Automated_baggage_system",
        ],
    ),
    "foxmeyer": CompanyConfig(
        name="foxmeyer",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://en.wikipedia.org/wiki/FoxMeyer",
        ],
    ),
    "nike_i2": CompanyConfig(
        name="nike_i2",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://en.wikipedia.org/wiki/I2_Technologies",
        ],
    ),
    "hertz_accenture": CompanyConfig(
        name="hertz_accenture",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://en.wikipedia.org/wiki/Hertz",
        ],
    ),
    # === Accessible Tier-C single incidents from danluu (engineering blogs, not bot-blocked) ===
    "spotify": CompanyConfig(
        name="spotify",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://engineering.atspotify.com/2013/06/incident-management-at-spotify",
        ],
    ),
    "kickstarter": CompanyConfig(
        name="kickstarter",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://kickstarter.engineering/the-day-the-replication-died-e543ba45f262",
        ],
    ),
    "dropbox": CompanyConfig(
        name="dropbox",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://dropbox.tech/infrastructure/outage-post-mortem",
        ],
    ),
    "gocardless": CompanyConfig(
        name="gocardless",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://gocardless.com/blog/incident-review-api-and-dashboard-outage-on-10th-october/",
        ],
    ),
    "sentry": CompanyConfig(
        name="sentry",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://blog.sentry.io/a-post-mortem-on-our-recent-outage/",
            "https://blog.sentry.io/sentry-outage-jan-21-2024/",
        ],
    ),
    "fastly": CompanyConfig(
        name="fastly",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://www.fastly.com/blog/summary-of-june-8-outage",
        ],
    ),
    "cockroachlabs": CompanyConfig(
        name="cockroachlabs",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://www.cockroachlabs.com/blog/cockroach-cloud-outage-postmortem/",
        ],
    ),
    "monzo": CompanyConfig(
        name="monzo",
        archive_urls=[],
        post_url_pattern=r"",
        extra_urls=[
            "https://monzo.com/blog/2019/09/08/why-monzo-wasnt-working-on-july-29th",
        ],
    ),
}

# wikitech URLs are relative; need to prefix
def _post_process_wikimedia():
    pass


def fetch(url: str, timeout: float = 30.0) -> str:
    # Try simple UA first (more permissive). Fall back to full UA.
    for ua in (UA, UA_FULL):
        for u in (url, url + "/" if not url.endswith("/") else None):
            if u is None:
                continue
            try:
                r = requests.get(
                    u,
                    headers={"User-Agent": ua, "Accept": "text/html,application/xhtml+xml,*/*"},
                    timeout=timeout,
                    allow_redirects=True,
                    verify=False,  # netflixtechblog.com cert chain issue with anaconda
                )
                r.raise_for_status()
                return r.text
            except (requests.HTTPError, requests.exceptions.SSLError):
                continue
    raise RuntimeError(f"all fetch variants failed: {url}")


def filter_url(url: str, cfg: CompanyConfig) -> str | None:
    url = url.split("#")[0].split("?")[0]
    # Check substrings on the *unstripped* form so /xxx/ markers still match
    if cfg.must_contain and not any(s in url for s in cfg.must_contain):
        return None
    if cfg.must_not_contain and any(s in url for s in cfg.must_not_contain):
        return None
    # Also check stripped trailing-slash form
    url_stripped = url.rstrip("/")
    if cfg.must_not_contain and any(s.rstrip("/") in url_stripped for s in cfg.must_not_contain if not s.endswith("/wp-content/") and s not in ("/page/",)):
        # Skip purely terminal locale-style endings: /ar-ar, /de-de etc
        for s in cfg.must_not_contain:
            core = s.strip("/")
            if url_stripped.endswith("/" + core):
                return None
    return url_stripped


def enumerate_urls(cfg: CompanyConfig) -> list[str]:
    found: set[str] = set()
    for arch in cfg.archive_urls:
        try:
            html = fetch(arch)
        except Exception as e:
            print(f"  archive fetch failed {arch}: {e}", file=sys.stderr)
            continue
        if cfg.post_url_pattern:
            for m in re.findall(cfg.post_url_pattern, html):
                if isinstance(m, tuple):
                    m = m[0]
                # Make relative URLs absolute against archive URL
                if m.startswith("/"):
                    parsed = urllib.parse.urlparse(arch)
                    m = f"{parsed.scheme}://{parsed.netloc}{m}"
                u = filter_url(m, cfg)
                if u:
                    found.add(u)
    for u in cfg.extra_urls:
        cleaned = filter_url(u, cfg)
        if cleaned:
            found.add(cleaned)
        else:
            found.add(u.rstrip("/").split("#")[0])
    return sorted(found)


def slugify(url: str) -> str:
    """Use the last URL path segment as slug, or a hash if not feasible."""
    parsed = urllib.parse.urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if parts:
        slug = parts[-1]
    else:
        slug = "index"
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", slug)[:100]
    return slug or "index"


def fetch_post(url: str) -> tuple[str, int]:
    """Return (markdown_text, char_count). Empty string + 0 if failed."""
    try:
        html = fetch(url)
    except Exception as e:
        return f"FETCH_ERROR: {e}", 0
    text = trafilatura.extract(
        html,
        url=url,
        include_links=True,
        include_tables=True,
        include_formatting=True,
        output_format="markdown",
    )
    if not text or not text.strip():
        # Fallback: BS4 minimal strip
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
                tag.decompose()
            main = soup.find("article") or soup.find("main") or soup.body or soup
            text = main.get_text("\n", strip=True)
        except Exception:
            text = ""
    return (text or "EXTRACT_ERROR: no content extracted"), len(text or "")


def walk_company(name: str, force: bool = False) -> dict:
    cfg = CONFIGS.get(name)
    if not cfg:
        raise SystemExit(f"unknown company: {name}. Run --list to see configs.")
    outdir = RAW / name
    outdir.mkdir(parents=True, exist_ok=True)
    urls = enumerate_urls(cfg)
    (outdir / "_urls.txt").write_text("\n".join(urls) + "\n", encoding="utf-8")
    stats = {"company": name, "urls_found": len(urls), "fetched_ok": 0, "fetched_fail": 0, "fetched_empty": 0, "skipped_existing": 0}
    for url in urls:
        slug = slugify(url)
        out = outdir / f"{slug}.md"
        if out.exists() and out.stat().st_size > 500 and not force:
            stats["skipped_existing"] += 1
            continue
        text, n = fetch_post(url)
        header = f"# Source: {url}\n# Length: {n} chars\n\n"
        out.write_text(header + text, encoding="utf-8")
        if text.startswith("FETCH_ERROR") or text.startswith("EXTRACT_ERROR"):
            stats["fetched_fail"] += 1
        elif n < 500:
            stats["fetched_empty"] += 1
        else:
            stats["fetched_ok"] += 1
        time.sleep(0.5)
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("company", nargs="?", default=None)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if args.list:
        for name in sorted(CONFIGS):
            cfg = CONFIGS[name]
            extras = len(cfg.extra_urls)
            archs = len(cfg.archive_urls)
            print(f"  {name:20s}  archives={archs}  extras={extras}")
        return 0
    if args.all:
        all_stats = []
        for name in CONFIGS:
            print(f"[{name}] walking...")
            stats = walk_company(name, force=args.force)
            print(f"  {stats}")
            all_stats.append(stats)
        (RAW / "_walk_stats.json").write_text(json.dumps(all_stats, indent=2), encoding="utf-8")
        return 0
    if not args.company:
        ap.error("specify a company or --all or --list")
    stats = walk_company(args.company, force=args.force)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
