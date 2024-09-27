from datetime import datetime, timezone
from copy import deepcopy
from http_2.version import VERSION

COMMON_HEADERS = {
    'server': f'Ganae-soogongup/{VERSION}'
}

def get_date_for_header(headers: dict[str, str]) -> dict[str, str]:
    current_time = datetime.now(timezone.utc)
    # https://datatracker.ietf.org/doc/html/rfc7231#section-7.1.1.1
    formatted_time = current_time.strftime("%a, %d %b %Y %H:%M:%S GMT")
    headers['date'] = formatted_time
    return headers

COMMON_HEADERS_CHAINS = []
COMMON_HEADERS_CHAINS.append(get_date_for_header)


def get_common_headers():
    common_headers = deepcopy(COMMON_HEADERS)
    for chain in COMMON_HEADERS_CHAINS:
        common_headers = chain(common_headers)

    return common_headers
