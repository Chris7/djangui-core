import os

from django.http import JsonResponse
from django.core.urlresolvers import reverse
from django.views.generic import TemplateView
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils.encoding import force_unicode

from djcelery.models import TaskMeta
from celery import app, states

celery_app = app.app_or_default()

from ..models import DjanguiJob

def celery_status(request):
    jobs = [job.content_object for job in DjanguiJob.objects.filter(djangui_user=request.user if request.user.is_authenticated() else None)]
    # TODO: Batch this to a scheduled task
    tasks = [job.djangui_celery_id for job in jobs]
    celery_tasks = dict([(task.task_id, task) for task in TaskMeta.objects.filter(task_id__in=tasks)])
    to_update = []
    for job in jobs:
        celery_task = celery_tasks.get(job.djangui_celery_id)
        if celery_task is None and job.djangui_celery_state != states.FAILURE:
            continue
            # the task doesn't exist, consider it a failure
            # TODO: we can't report these with all backends, code a way to figure out backend and see if this is viable
            job.djangui_celery_state = states.FAILURE
            to_update.append(job)
        elif celery_task is not None and job.djangui_celery_state != celery_task.status:
            job.djangui_celery_state = celery_task.status
            to_update.append(job)
    for i in to_update:
        i.save()
    return JsonResponse([{'job_name': job.djangui_job_name, 'job_status': job.djangui_celery_state,
                        'job_submitted': job.created_date.strftime('%b %d %Y, %H:%M:%S'),
                        'job_id': job.djangui_celery_id,
                        'job_url': reverse('celery_results_info', kwargs={'task_id': job.djangui_celery_id})} for job in jobs], safe=False)


def celery_task_command(request):
    command = request.POST.get('celery-command')
    task_id = request.POST.get('task-id')
    job = DjanguiJob.objects.get(djangui_celery_id=task_id)
    user = None if not request.user.is_authenticated() and settings.DJANGUI_ALLOW_ANONYMOUS else request.user
    response = {'valid': False,}
    if user == job.djangui_user:
        if command == 'resubmit':
            obj = job.content_object.submit_to_celery(resubmit=True)
            response.update({'valid': True, 'extra': {'task_url': reverse('celery_results_info', kwargs={'task_id': obj.djangui_celery_id})}})
        elif command == 'clone':
            response.update({'valid': True, 'redirect': '{0}?task_id={1}'.format(reverse('djangui_task_launcher'), task_id)})
        elif command == 'delete':
            job.delete()
            response.update({'valid': True, 'redirect': reverse('djangui_home')})
        elif command == 'stop':
            celery_app.control.revoke(task_id, terminate=True)
            response.update({'valid': True, 'redirect': reverse('celery_results_info', kwargs={'task_id': task_id})})
        else:
            response.update({'errors': {'__all__': force_unicode(_("Unknown Command"))}})
    return JsonResponse(response)


class CeleryTaskView(TemplateView):
    template_name = 'tasks/task_view.html'

    @staticmethod
    def get_file_fields(model):
        files = []
        for field in model._meta.fields:
            try:
                if getattr(getattr(model, field.name), 'path', False):
                    d = {'name': field.name}
                    d['url'] = getattr(getattr(model, field.name), 'url', None)
                    d['path'] = getattr(getattr(model, field.name), 'path', None)
                    files.append(d)
            except ValueError:
                continue

        known_files = {i['url'] for i in files}
        # add the user_output files, these are things which may be missed by the model fields because the script
        # generated them without an explicit argument reference in argparse
        file_groups = {'archives': []}
        absbase = os.path.join(settings.MEDIA_ROOT, model.djangui_save_path)
        for filename in os.listdir(absbase):
            url = os.path.join(model.djangui_save_path, filename)
            if url in known_files:
                continue
            d = {'name': filename, 'path': os.path.join(absbase, filename), 'url': '{0}{1}'.format(settings.MEDIA_URL, url)}
            if filename.startswith('djangui_all'):
                file_groups['archives'].append(d)
            else:
                files.append(d)

        # establish grouping by inferring common things
        file_groups['all'] = files
        import imghdr
        file_groups['images'] = [{'name': filemodel['name'], 'url': filemodel['url']} for filemodel in files if imghdr.what(filemodel.get('path', filemodel['url']))]
        file_groups['tabular'] = []

        def test_delimited(filepath):
            import csv
            with open(filepath, 'rb') as csv_file:
                try:
                    dialect = csv.Sniffer().sniff(csv_file.read(1024*16), delimiters=',\t')
                except Exception as e:
                    return False, None
                csv_file.seek(0)
                reader = csv.reader(csv_file, dialect)
                rows = []
                try:
                    for index, entry in enumerate(reader):
                        if index == 5:
                            break
                        rows.append(entry)
                except Exception as e:
                    return False, None
                return True, rows

        for filemodel in files:
            is_delimited, first_rows = test_delimited(filemodel.get('path', filemodel['url']))
            if is_delimited:
                file_groups['tabular'].append({'name': filemodel['name'], 'preview': first_rows, 'url': filemodel['url']})
        return file_groups

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
                            'job_description': djangui_job.djangui_job_description, 'all_files': {},
                            'file_groups': {}}
        if celery_task:
            out_files = self.get_file_fields(djangui_job)
            all = out_files.pop('all')
            archives = out_files.pop('archives')
            ctx['task_info'].update({
                'stdout': celery_task.result[0],
                'stderr': celery_task.result[1],
                'status': celery_task.status,
                'last_modified': celery_task.date_done,
                'all_files': all,
                'archives': archives,
                'file_groups': out_files,
            })
        return ctx

