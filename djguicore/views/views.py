from django.views.generic import TemplateView, View
from django.http import JsonResponse
from django.forms import modelform_factory
from django.conf import settings

from djangui.backend import utils
from djangui.db import fields as djangui_fields

from .mixins import DjanguiScriptMixin
from ..models import DjanguiJob


class DjanguiScriptJSON(DjanguiScriptMixin, View):
    def get(self, request, *args, **kwargs):
        # returns the models required and optional fields as html
        task_id = request.GET.get('task_id')
        instance = None
        if task_id:
            job = DjanguiJob.objects.get(djangui_celery_id=task_id)
            if job.djangui_user is None or (request.user.is_authenticated() and job.djangui_user == request.user):
                instance = job.content_object
        d = utils.get_modelform_dict(self.model, instance=instance)
        return JsonResponse(d)

    def post(self, request, *args, **kwargs):
        model_form = modelform_factory(self.model, fields='__all__', exclude=set(settings.DJANGUI_EXCLUDES)-{'djangui_job_name', 'djangui_job_description', 'djangui_user'})
        post = request.POST.copy()
        if request.user.is_authenticated() or not settings.DJANGUI_ALLOW_ANONYMOUS:
            post['djangui_user'] = request.user
        form = model_form(post, request.FILES)
        if form.is_valid():
            # We don't do commit=False here, even though we are saving the model again below in our celery submission.
            # this ensures the file is uploaded if needed.
            model = form.save()
            model.submit_to_celery()
            return JsonResponse({'valid': True})
        # we can not validate due to files not yet being created, which will be created once the script is run.
        # purge these
        deleted_files = {}
        for i in self.model.djangui_output_options:
            if i in form.errors:
                deleted_files[i] = post.get(i, None)
                del form.errors[i]
        # we also cannot validate due to files not being replaced, though they are set such as when cloning a job
        files_to_sync = set([])
        for i in self.model._meta.fields:
            if issubclass(type(i), djangui_fields.DjanguiUploadFileField):
                if post.get(i.name):
                    if i.name in form.errors:
                        del form.errors[i.name]
                    files_to_sync.add(i.name)
        if not form.errors:
            model = form.save(commit=False)
            # update our instance with where we want to save files if the user specified it
            for i,v in deleted_files.iteritems():
                if v:
                    try:
                        model._djangui_temp_output[i] = v[0] if isinstance(v, list) else v
                    except AttributeError:
                        model._djangui_temp_output = {i: v[0] if isinstance(v, list) else v}
            # update out instance with any referenced files
            if files_to_sync:
                parent = DjanguiJob.objects.get(djangui_celery_id=post.get('djangui_clone_task_id')).content_object
                for model_field in files_to_sync:
                    setattr(model, model_field, getattr(parent, model_field))
            model.save()
            model.submit_to_celery()
            return JsonResponse({'valid': True})
        return JsonResponse({'valid': False, 'errors': form.errors})


class DjanguiScriptHome(DjanguiScriptMixin, TemplateView):
    template_name = 'scripts_home.html'

    def get_context_data(self, **kwargs):
        ctx = super(DjanguiScriptHome, self).get_context_data(**kwargs)
        ctx['scripts'] = []
        # import pdb; pdb.set_trace();
        for model in dir(self.djangui_models):
            if model == 'DjanguiModel':
                continue
            klass = getattr(self.djangui_models, model)
            try:
                if klass._meta.app_label == self.app_name:
                    ctx['scripts'].append({
                        'name': klass._meta.object_name,
                        'objects': klass.objects.all(),
                        'url': utils.get_model_script_url(klass, json=False)
                    })
            except AttributeError:
                continue
        return ctx