from enum import Enum


class StatusCode(Enum):

    # 1xx
    CONTINUE = ('Continue', 100)
    SWITCHING_PROTOCOLS = ('Switching Protocols', 101)
    PROCESSING = ('Processing', 102)
    EARLY_HINTS = ('Early Hints ', 103)

    # 2xx
    OK = ('OK', 200)
    CREATED = ('Created', 201)
    ACCEPTED = ('Accepted', 202)
    NON_AUTHORITATIVE_INFORMATION = ('Non-Authoritative Information', 203)
    NO_CONTENT = ('No Content', 204)
    RESET_CONTENT = ('Reset Content', 205)
    PARTIAL_CONTENT = ('Partial Content', 206)
    MULTI_STATUS = ('Multi-Status', 207)
    ALREADY_REPORTED = ('Already Reported', 208)
    IM_USED = ('IM Used', 226)

    # 3xx
    MULTIPLE_CHOICES = (300, 'Multiple Choices')
    MOVED_PERMANENTLY = (301, 'Moved Permanently')
    FOUND = (302, 'Found')
    SEE_OTHER = (303, 'See Other')
    NOT_MODIFIED = (304, 'Not Modified')
    USE_PROXY = (305, 'Use Proxy') # (Deprecated in RFC 7231)
    UNUSED = (306, 'Unused')
    TEMPORARY_REDIRECT = (307, 'Temporary Redirect')
    PERMANENT_REDIRECT = (308, 'Permanent Redirect') #(RFC 7538)

    # 4xx
    BAD_REQUEST = (400, 'Bad Request')
    UNAUTHORIZED = (401, 'Unauthorized')
    FORBIDDEN = (403, 'Forbidden')
    NOT_FOUND = (404, 'Not Found')
    METHOD_NOT_ALLOWED = (405, 'Method Not Allowed')
    NOT_ACCEPTABLE = (406, 'Not Acceptable')
    PROXY_AUTHENTICATION_REQUIRE = (407, 'Proxy Authentication Required')
    REQUEST_TIMEOUT = (408, 'Request Timeout')
    CONFLICT = (409, 'Conflict')
    GONE = (410, 'Gone')
    LENGTH_REQUIRED = (411, 'Length Required')
    PRECONDITION_FAILED = (412, 'Precondition Failed')
    PAYLOAD_TOO_LARGE = (413, 'Payload Too Large')
    URI_TOO_LONG = (414, 'URI Too Long')
    UNSUPPORTED_MEDIA_TYPE = (415, 'Unsupported Media Type')
    RANGE_NOT_SATISFIABLE = (416, 'Range Not Satisfiable')
    EXPECTATION_FAILED = (417, 'Expectation Failed')
    IM_A_TEAPOT = (418, "I'm a teapot") # (RFC 2324) (Easter Egg)
    MISDIRECTED_REQUEST = (421, 'Misdirected Request') # (RFC 7540)
    UNPROCESSABLE_ENTITY = (422, 'Unprocessable Entity') #  (RFC 4918)
    LOCKED = (423, 'Locked')  #(RFC 4918)
    FAILED_DEPENDENCY = (424, 'Failed Dependency') # (RFC 4918)
    TOO_EARLY = (425, 'Too Early') # (RFC 8470)
    UPGRADE_REQUIRED = (426, 'Upgrade Required')
    PRECONDITION_REQUIRED = (428, 'Precondition Required') # (RFC 6585)
    TOO_MANY_REQUESTS = (429, 'Too Many Requests') # (RFC 6585)
    REQUEST_HEADER_FIELDS_TOO_LARGE = (431, 'Request Header Fields Too Large') # (RFC 6585)
    UNAVAILABLE_FOR_LEGAL_REASONS = (451, 'Unavailable For Legal Reasons') # (RFC 7725)

    # 5xx
    INTERNAL_SERVER_ERROR = (500, 'Internal Server Error')
    NOT_IMPLEMENTED = (501, 'Not Implemented')
    BAD_GATEWAY = (502, 'Bad Gateway')
    SERVICE_UNAVAILABLE = (503, 'Service Unavailable')
    GATEWAY_TIMEOUT = (504, 'Gateway Timeout')
    HTTP_VERSION_NOT_SUPPORTED = (505, 'HTTP Version Not Supported')
    VARIANT_ALSO_NEGOTIATES = (506, 'Variant Also Negotiates') # (RFC 2295)
    INSUFFICIENT_STORAGE = (507, 'Insufficient Storage') # (RFC 4918)
    LOOP_DETECTED = (508, 'Loop Detected') # (RFC 5842)
    NOT_EXTENDED = (510, 'Not Extended') # (RFC 2774)
    NETWORK_AUTHENTICATION_REQUIRED = (511, 'Network Authentication Required') # (RFC 6585)

    def __init__(self, text: str, status_code: int):
        self._text = text
        self._status_code = status_code

    @property
    def text(self):
        return self._text

    @property
    def status_code(self):
        return self._status_code
