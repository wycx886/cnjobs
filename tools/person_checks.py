"""Validate public person-profile shapes; identity still needs actual source verification."""
import ipaddress
import re
from urllib.parse import parse_qs, urlencode, unquote, urlsplit, urlunsplit


RESERVED_GITHUB = {'about', 'collections', 'contact', 'enterprise', 'events', 'explore', 'features', 'issues', 'join', 'login', 'marketplace', 'new', 'notifications', 'orgs', 'pricing', 'pulls', 'search', 'settings', 'signup', 'sponsors', 'topics', 'trending', 'users'}
RESERVED_X = {'about', 'compose', 'explore', 'home', 'i', 'intent', 'login', 'messages', 'notifications', 'privacy', 'search', 'settings', 'share', 'signup', 'tos'}


def public_url(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or not host or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Use a public HTTPS URL without credentials or custom ports')
    if host == 'localhost' or host.endswith(('.localhost', '.local')):
        raise ValueError('A public source cannot use a local host')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError('A public source cannot use a private network address')
    if any(part in {'.', '..'} for part in unquote(parsed.path).split('/')):
        raise ValueError('Invalid public URL path')
    return parsed


PHOTO_PATH = re.compile(r'assets/people/[a-z0-9-]+\.(?:jpg|jpeg|png|webp)')


def validate_person_photo(photo, sources, latest):
    """Check portrait provenance; the stored file itself is checked against data/views by validate.py."""
    from datetime import date
    if not PHOTO_PATH.fullmatch(photo['path']):
        raise ValueError('Person photo must be stored under assets/people/ with a lowercase image name')
    for field in ('source_url', 'page_url'):
        public_url(photo[field])
    refs = set(photo['source_ids'])
    if not refs <= sources.keys() or any(sources[s].get('scope', 'organization') == 'channel' for s in refs):
        raise ValueError('Person photo requires existing person or organization evidence, not institution-channel sources')
    checked = date.fromisoformat(photo['checked_at'])
    if checked > latest or any(checked > date.fromisoformat(sources[s]['checked_at']) for s in refs):
        raise ValueError('Person photo check lacks evidence at the claimed date')
    return refs


def person_profile_url(url, platform):
    parsed = public_url(url)
    host = (parsed.hostname or '').lower()
    parts = unquote(parsed.path).strip('/').split('/')
    if platform == 'linkedin':
        if not (host == 'linkedin.com' or host.endswith('.linkedin.com')) or len(parts) != 2 or parts[0] != 'in' or not parts[1]:
            raise ValueError('LinkedIn person profiles must use /in/<person>, not company pages')
        return 'https://www.linkedin.com/in/' + parts[1].lower() + '/'
    if platform == 'x':
        if host not in {'x.com', 'www.x.com', 'twitter.com', 'www.twitter.com', 'mobile.twitter.com'} or len(parts) != 1 or not re.fullmatch(r'[A-Za-z0-9_]{1,15}', parts[0]) or parts[0].lower() in RESERVED_X:
            raise ValueError('X profiles require a specific account handle')
        return 'https://x.com/' + parts[0].lower()
    if platform == 'github':
        if host not in {'github.com', 'www.github.com'} or len(parts) != 1 or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?', parts[0]) or parts[0].lower() in RESERVED_GITHUB:
            raise ValueError('GitHub person profiles require an account root, not a repository or organization route')
        return 'https://github.com/' + parts[0].lower()
    if platform == 'scholar':
        user = parse_qs(parsed.query).get('user', [])
        if host != 'scholar.google.com' or parsed.path.rstrip('/') != '/citations' or len(user) != 1 or not user[0].strip():
            raise ValueError('Scholar profiles require a specific citations user ID')
        return 'https://scholar.google.com/citations?' + urlencode({'user': user[0]})
    if platform == 'jike':
        if host != 'web.okjike.com' or len(parts) != 2 or parts[0] != 'u' or not parts[1]:
            raise ValueError('Jike person profiles require /u/<person>')
        return 'https://web.okjike.com/u/' + parts[1]
    if platform == 'zhihu':
        if host not in {'zhihu.com', 'www.zhihu.com'} or len(parts) != 2 or parts[0] != 'people' or not parts[1]:
            raise ValueError('Zhihu person profiles require /people/<person>')
        return 'https://www.zhihu.com/people/' + parts[1]
    if platform not in {'personal_site', 'other'}:
        raise ValueError('Unknown person-profile platform')
    known = ('linkedin.com', 'github.com', 'x.com', 'twitter.com', 'okjike.com', 'zhihu.com', 'zhipin.com', 'liepin.com', 'maimai.cn')
    if host == 'scholar.google.com' or any(host == domain or host.endswith('.' + domain) for domain in known):
        raise ValueError('Use the actual platform label; recruitment company pages are not personal sites')
    return urlunsplit(('https', host, parsed.path or '/', parsed.query, ''))


def validate_person_evidence(person, sources, latest):
    """Check identities and profile provenance without declaring remote pages true."""
    from datetime import date
    refs = set(person['source_ids'])
    if not refs <= sources.keys() or any(sources[s].get('scope', 'organization') == 'channel' for s in refs):
        raise ValueError('Person identity requires person or organization evidence, not institution-channel sources')
    checked = date.fromisoformat(person['checked_at'])
    if checked > latest or any(checked > date.fromisoformat(sources[s]['checked_at']) for s in refs):
        raise ValueError('Person identity check lacks evidence at the claimed date')
    seen = set()
    history = set(person.get('historical_source_ids', []))
    if not history <= sources.keys() or any(sources[s].get('scope', 'organization') == 'channel' for s in history):
        raise ValueError('Historical person evidence must reference existing person or organization sources')
    used = set(refs) | history
    for profile in person['profiles']:
        normalized = person_profile_url(profile['url'], profile['platform'])
        key = (profile['platform'], normalized)
        if key in seen:
            raise ValueError('Duplicate person profile URL')
        seen.add(key)
        refs = set(profile['source_ids'])
        if not refs <= sources.keys() or any(sources[s].get('scope', 'organization') == 'channel' for s in refs):
            raise ValueError('Person profile requires person or organization evidence')
        observed = date.fromisoformat(profile['checked_at'])
        if observed > latest or any(observed > date.fromisoformat(sources[s]['checked_at']) for s in refs):
            raise ValueError('Person profile check lacks evidence at the claimed date')
        urls = {sources[s]['url'] for s in refs}
        if profile['verification_status'] == 'confirmed':
            if normalized not in urls or len(urls) < 2:
                raise ValueError('Confirmed person profiles require the profile and a distinct identity evidence URL')
        if profile['platform'] == 'github':
            api_url = 'https://api.github.com/users/' + normalized.rsplit('/', 1)[1]
            if profile.get('account_type') != 'User' or api_url not in urls:
                raise ValueError('GitHub people require API evidence of account type User, not Organization')
        used.update(refs)
    if person.get('photo'):
        used.update(validate_person_photo(person['photo'], sources, latest))
    if person['verification_status'] == 'confirmed' and len({sources[s]['url'] for s in person['source_ids']}) < 2:
        raise ValueError('Confirmed person identity requires two distinct public evidence URLs')
    return used
