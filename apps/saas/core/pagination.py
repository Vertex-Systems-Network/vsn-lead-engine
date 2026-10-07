from rest_framework.pagination import LimitOffsetPagination


class BoundedPagination(LimitOffsetPagination):
    default_limit = 25
    max_limit = 100
