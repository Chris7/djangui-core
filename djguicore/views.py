from django.http import JsonResponse
from djcelery.models import TaskMeta
from .models import DjanguiJob

def celery_status(request):
    jobs = [job.content_object for job in DjanguiJob.objects.filter(djangui_user=request.user if request.user.is_authenticated() else None)]
    # TODO: Batch this
    tasks = [job.djangui_celery_id for job in jobs]
    celery_tasks = TaskMeta.objects.filter(task_id__in=tasks)
    to_update = []
    for job, task, celery_task in zip(jobs, tasks, celery_tasks):
        if job.djangui_celery_state != celery_task.status:
            job.djangui_celery_state = celery_task.status
            to_update.append(job)
    for i in to_update:
        i.save()
    return JsonResponse([{'job_name': job.djangui_job_name, 'job_status': job.djangui_celery_state,
                        'job_submitted': job.created_date.strftime('%b %d %Y'),
                        'job_id': job.djangui_celery_id} for job in jobs], safe=False)