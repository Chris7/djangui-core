from django.http import JsonResponse
from djcelery.models import TaskMeta
from django.core.urlresolvers import reverse
from django.views.generic import TemplateView
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from .models import DjanguiJob

def celery_status(request):
    jobs = [job.content_object for job in DjanguiJob.objects.filter(djangui_user=request.user if request.user.is_authenticated() else None)]
    # TODO: Batch this
    tasks = [job.djangui_celery_id for job in jobs]
    celery_tasks = dict([(task.task_id, task) for task in TaskMeta.objects.filter(task_id__in=tasks)])
    to_update = []
    for job in jobs:
        celery_task = celery_tasks.get(job.djangui_celery_id)
        if celery_task is None:
            continue
        if job.djangui_celery_state != celery_task.status:
            job.djangui_celery_state = celery_task.status
            to_update.append(job)
    for i in to_update:
        i.save()
    return JsonResponse([{'job_name': job.djangui_job_name, 'job_status': job.djangui_celery_state,
                        'job_submitted': job.created_date.strftime('%b %d %Y'),
                        'job_id': job.djangui_celery_id,
                        'job_url': reverse('celery_results_info', kwargs={'task_id': job.djangui_celery_id})} for job in jobs], safe=False)


def celery_task_command(request):
    command = request.POST.get('celery-command')
    task_id = request.POST.get('task-id')
    job = DjanguiJob.objects.get(djangui_celery_id=task_id)
    user = None if not request.user.is_authenticated() and settings.DJANGUI_ALLOW_ANONYMOUS else request.user
    if user != job.djangui_user:
        response = JsonResponse({})
    else:
        if command is None:
            response = JsonResponse({})
        if command == 'resubmit':
            obj = job.content_object.submit_to_celery(resubmit=True)
            response = JsonResponse({'valid': True, 'extra': {'task_url': reverse('celery_results_info', kwargs={'task_id': obj.djangui_celery_id})}})
        elif command == 'clone':
            response = JsonResponse({'valid': True, 'redirect': reverse('celery_job_repopulate', kwargs={'task_id': task_id})})
        elif command == 'delete':
            job.delete()
            response = JsonResponse({'valid': True, 'redirect': reverse('djangui_home')})
        else:
            response = JsonResponse({'valid': False, 'errors': {'__all__': _("Unknown Command")}})
    return response


class CeleryTaskView(TemplateView):
    template_name = 'tasks/task_view.html'

    def get_file_fields(self, model):
        return dict([(field.name, getattr(model, field.name)) for field in model._meta.fields if getattr(getattr(model, field.name), 'path', False)])

    def get_context_data(self, **kwargs):
        ctx = super(CeleryTaskView, self).get_context_data(**kwargs)
        task_id = ctx.get('task_id')
        try:
            celery_task = TaskMeta.objects.get(task_id=task_id)
        except TaskMeta.DoesNotExist:
            celery_task = None
        djangui_job = DjanguiJob.objects.get(djangui_celery_id=task_id).content_object
        ctx['task_info'] = {'stdout': '', 'stderr': '', 'job_id': djangui_job.djangui_celery_id,
                            'status': djangui_job.djangui_celery_state, 'submission_time': djangui_job.created_date,
                            'last_modified': djangui_job.modified_date, 'job_name': djangui_job.djangui_job_name,
                            'job_command': djangui_job.djangui_command,
                            'job_description': djangui_job.djangui_job_description, 'files': {}}
        if celery_task:
            ctx['task_info'].update({
                'stdout': celery_task.result[0],
                'stderr': celery_task.result[1],
                'status': celery_task.status,
                'last_modified': celery_task.date_done,
                'files': self.get_file_fields(djangui_job)
            })
        return ctx