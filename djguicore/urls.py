from django.conf.urls import include, url
from .views import celery_status, CeleryTaskView

urlpatterns = [
    url(r'^celery-status/(?P<task_id>[a-zA-Z0-9\-]+)/$', CeleryTaskView.as_view(), name='celery_results_info'),
    url(r'^celery-status/$', celery_status, name='celery_results'),
]