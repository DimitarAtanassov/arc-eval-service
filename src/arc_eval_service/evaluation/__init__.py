"""The evaluation vertical: the ``POST /v1/evaluate`` endpoint and its core.

``router`` exposes the endpoint, ``service`` orchestrates scoring and
persistence, ``contract`` is the public request/response shape, ``records`` is the
persistence domain, and ``schemas`` holds the internal judging types shared with
the metrics and judging libraries.
"""
