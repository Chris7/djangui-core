from django.conf.urls import include, url
from .views import celery_status

urlpatterns = [
    url(r'^celery-status/$', celery_status, name='celery_results'),
]