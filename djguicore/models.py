from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

# Create your models here.
class DjanguiJob(models.Model):
    """
    This model serves to link the submitted celery tasks to a script submitted
    """
    djangui_user = models.OneToOneField(settings.AUTH_USER_MODEL, blank=True, null=True)
    djangui_celery_id = models.CharField(max_length=255, null=True)
    content_type = models.ForeignKey(ContentType, null=True)
    object_id = models.PositiveIntegerField(null=True)
    content_object = GenericForeignKey('content_type', 'object_id')
