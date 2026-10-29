class RobotsTagMiddleware:
    """Mark every API response noindex, nofollow.

    This keeps API URLs out of search results without stopping anyone from
    fetching them. There is deliberately no robots.txt: Google renders the
    client-side course pages by calling this API, and obeys this host's
    robots.txt while doing it, so a Disallow would leave those pages empty.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        return response
