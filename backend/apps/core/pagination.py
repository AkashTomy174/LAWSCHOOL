"""Pagination defaults shared by every list endpoint.

Page-number pagination is used deliberately: course lists, payments and the
leaderboard all need stable ``?page=`` semantics that a human can deep-link to,
and every ordering they use sits on an indexed column.
"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data) -> Response:
        return Response(
            {
                "count": self.page.paginator.count,
                "num_pages": self.page.paginator.num_pages,
                "page": self.page.number,
                "page_size": self.get_page_size(self.request),
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )


class LargeResultsSetPagination(StandardResultsSetPagination):
    """For append-only feeds (notifications, progress events)."""

    page_size = 50
    max_page_size = 200
