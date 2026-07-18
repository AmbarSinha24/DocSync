import re

# Matches:
#   https://github.com/owner/repo
#   https://github.com/owner/repo.git
#   https://github.com/owner/repo/
#   git@github.com:owner/repo.git
#   owner/repo  (shorthand)
_PATTERNS = [
    re.compile(r"^https?://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(\.git)?/?$"),
    re.compile(r"^git@github\.com:(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(\.git)?$"),
    re.compile(r"^(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)$"),
]


class InvalidGitHubUrlError(ValueError):
    pass


def parse_github_url(raw: str) -> tuple[str, str]:
    """Parses a GitHub URL or owner/repo shorthand into (owner, repo). Rejects
    anything that isn't recognizably GitHub -- other hosts, malformed input."""
    candidate = raw.strip()
    for pattern in _PATTERNS:
        match = pattern.match(candidate)
        if match:
            return match.group("owner"), match.group("repo")
    raise InvalidGitHubUrlError(f"'{raw}' is not a recognizable GitHub repository URL")
