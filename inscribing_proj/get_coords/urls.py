from django.urls import path
# from .views import GeoQueryView,GeoQueryViewDatacube
from .views import GeoQueryView, GeoQueryViewDatacube, InscriberView

# urlpatterns = [
#     path('geo-query/', GeoQueryView.as_view(), name='geo-query'),
#     path('geo-query-cube/', GeoQueryViewDatacube.as_view(), name='geo-query-cube')

# ]

urlpatterns = [
    path('geo-query/', GeoQueryView.as_view(), name='geo-query'),
    path('geo-query-cube/', GeoQueryViewDatacube.as_view(), name='geo-query-cube'),
    path('inscribe/', InscriberView.as_view(), name='inscribe'),
]