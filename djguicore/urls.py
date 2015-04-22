from django.conf import settings
from django.conf.urls import include, url
from .views import celery_status, CeleryTaskView, celery_task_command

urlpatterns = [
    url(r'^celery/command$', celery_task_command, name='celery_task_command'),
    url(r'^celery/status$', celery_status, name='celery_results'),
    url(r'^celery/(?P<task_id>[a-zA-Z0-9\-]+)/$', CeleryTaskView.as_view(), name='celery_results_info'),
]

# add urlpatterns of djangui apps
for app_name, app in getattr(settings, 'DJANGUI_APPS', {}).iteritems():
    dj_app = app['app']
    urlpatterns += [
        url(r'^', include('{0}.urls'.format(dj_app.DJANGUI_NAME)))
    ]