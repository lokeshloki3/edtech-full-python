from django.test import SimpleTestCase


class RobotsTests(SimpleTestCase):
    def test_every_response_is_noindex(self):
        response = self.client.get('/no-such-page')

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers['X-Robots-Tag'], 'noindex, nofollow')

    def test_no_robots_txt(self):
        # A Disallow here would stop Google fetching course data while it
        # renders the client-side pages; see RobotsTagMiddleware.
        response = self.client.get('/robots.txt')

        self.assertEqual(response.status_code, 404)
