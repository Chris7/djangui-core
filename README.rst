=====
Djangui Core
=====

The core app of Djangui for handling things like user profiles, etc.

Quick start
-----------

1. Add "djguicore" to your INSTALLED_APPS setting in user_settings like this::

    INSTALLED_APPS += ('djguihome',)

2. Include the djguicore URLconf in your project urls.py like this::

    url(r'^/', include('djguicore.urls')),